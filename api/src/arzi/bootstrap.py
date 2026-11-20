"""Composition root: choose adapters from settings and wire the services.

The only module that knows which concrete adapter backs each port. With no GCP project it uses
in-memory storage, so ``make dev`` works offline; with a project it uses Firestore and Cloud
Storage. The LLM mode picks recorded (``replay``), fixture (``fake``) or Vertex AI (``live``)
responses; live calls always go through the budget guard.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from arzi.adapters.auth import DemoAuthVerifier
from arzi.adapters.fixture_llm import FixtureLlmClient
from arzi.adapters.genai_client import (
    GeminiLlmClient,
    RecordingLlmClient,
    ReplayLlmClient,
    ai_studio_models,
    vertex_models,
)
from arzi.adapters.memory import InMemoryBlobStore, InMemoryClaimRepository, InMemoryCostLedger
from arzi.config import AuthMode, Environment, LlmMode, LlmProvider, Settings
from arzi.services.claims import ClaimService
from arzi.services.cost_ledger import BudgetedLlmClient, ModelPrice, parse_price_table
from arzi.services.extraction import ExtractionService
from arzi.services.pipeline import (
    AuditStep,
    ExtractStep,
    PipelineStep,
    ReconcileStep,
    RedactStep,
)
from arzi.services.ports import (
    AuthVerifier,
    BlobStore,
    ClaimRepository,
    CostLedgerStore,
    LlmClient,
    StoredDocument,
)
from arzi.services.redaction import Redactor
from arzi.services.runs import RunService


class ConfigurationError(RuntimeError):
    """The settings cannot produce a working service (raised at startup, not per request)."""


@dataclass
class Services:
    repo: ClaimRepository
    blobs: BlobStore
    ledger: CostLedgerStore
    llm: LlmClient
    auth: AuthVerifier
    claims: ClaimService
    runs: RunService


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def build_llm(
    settings: Settings, ledger: CostLedgerStore, clock: Callable[[], dt.datetime]
) -> LlmClient:
    if settings.llm_mode is LlmMode.REPLAY:
        return ReplayLlmClient(settings.replay_dir)
    if settings.llm_mode is LlmMode.FAKE:
        return FixtureLlmClient(settings.replay_dir)
    if not settings.model_flash:
        raise ConfigurationError("live mode needs ARZI_MODEL_FLASH")
    prices = parse_price_table(settings.price_table_json)
    if settings.llm_provider is LlmProvider.AI_STUDIO:
        if settings.env is Environment.CLOUD:
            raise ConfigurationError("AI Studio is for local testing with synthetic data only")
        if settings.gemini_api_key is None:
            raise ConfigurationError("AI Studio needs ARZI_GEMINI_API_KEY")
        models = ai_studio_models(
            settings.gemini_api_key.get_secret_value(), settings.llm_timeout_s
        )
        # The free tier costs nothing; the guard still counts calls and tokens.
        prices.setdefault(
            settings.model_flash,
            ModelPrice(input_inr_per_1m=Decimal(0), output_inr_per_1m=Decimal(0)),
        )
        gcs_uris = False
    else:
        if not settings.google_cloud_project:
            raise ConfigurationError("Vertex AI needs GOOGLE_CLOUD_PROJECT")
        models = vertex_models(
            settings.google_cloud_project, settings.vertex_location, settings.llm_timeout_s
        )
        gcs_uris = True
    gemini = GeminiLlmClient(
        models,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        gcs_uris=gcs_uris,
    )
    budgeted: LlmClient = BudgetedLlmClient(
        gemini, ledger, prices, daily_cap_inr=settings.daily_budget_inr, clock=clock
    )
    if settings.llm_record_dir is not None:
        return RecordingLlmClient(budgeted, settings.llm_record_dir)
    return budgeted


def _storage(settings: Settings) -> tuple[ClaimRepository, BlobStore, CostLedgerStore]:
    if settings.google_cloud_project is None:
        return InMemoryClaimRepository(), InMemoryBlobStore(), InMemoryCostLedger()
    from google.cloud import firestore

    from arzi.adapters.firestore_repo import FirestoreClaimRepository, FirestoreCostLedger

    db = firestore.AsyncClient(
        project=settings.google_cloud_project, database=settings.firestore_database
    )
    blobs: BlobStore = InMemoryBlobStore()
    if settings.bucket:
        from google.cloud import storage  # type: ignore[attr-defined]  # untyped SDK

        from arzi.adapters.gcs import GcsBlobStore

        blobs = GcsBlobStore(storage.Client(project=settings.google_cloud_project), settings.bucket)
    return FirestoreClaimRepository(db), blobs, FirestoreCostLedger(db)


def build_services(
    settings: Settings,
    *,
    repo: ClaimRepository | None = None,
    blobs: BlobStore | None = None,
    ledger: CostLedgerStore | None = None,
    llm: LlmClient | None = None,
    clock: Callable[[], dt.datetime] = utc_now,
    id_factory: Callable[[], str] = new_id,
) -> Services:
    """Production passes only settings; tests replace any port they need to control."""
    if settings.auth_mode is not AuthMode.DEMO:
        raise ConfigurationError("only demo auth is available until Phase 7")
    if repo is None or blobs is None or ledger is None:
        default_repo, default_blobs, default_ledger = _storage(settings)
        repo, blobs, ledger = repo or default_repo, blobs or default_blobs, ledger or default_ledger
    llm = llm or build_llm(settings, ledger, clock)
    store = blobs

    async def load(document: StoredDocument) -> bytes:
        return await store.get(document.uri)

    extraction = ExtractionService(
        llm,
        model=settings.model_flash or "model-not-configured",
        thinking_budget=settings.llm_thinking_budget,
        concurrency=settings.extraction_concurrency,
    )
    steps: list[PipelineStep] = [
        ExtractStep(extraction, load),
        RedactStep(Redactor(settings.pseudonym_salt.get_secret_value().encode())),
        ReconcileStep(),
        AuditStep(),
    ]
    return Services(
        repo=repo,
        blobs=blobs,
        ledger=ledger,
        llm=llm,
        auth=DemoAuthVerifier(),
        claims=ClaimService(
            repo,
            blobs,
            clock=clock,
            new_id=id_factory,
            max_upload_mb=settings.max_upload_mb,
            max_pages=settings.max_pages,
        ),
        runs=RunService(repo, steps, clock=clock, new_id=id_factory),
    )
