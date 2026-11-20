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
from typing import Any

from arzi.adapters.auth import DemoAuthVerifier
from arzi.adapters.fixture_llm import FixtureLlmClient
from arzi.adapters.genai_client import (
    GeminiLlmClient,
    RecordingLlmClient,
    ReplayLlmClient,
    ai_studio_models,
    vertex_models,
)
from arzi.adapters.hybrid import ReplayThenLiveLlm, ReplayThenLiveSpeech
from arzi.adapters.memory import InMemoryBlobStore, InMemoryClaimRepository, InMemoryCostLedger
from arzi.adapters.tts import (
    BudgetedSpeech,
    GeminiSpeech,
    RecordingSpeech,
    ReplaySpeech,
    SilentSpeech,
)
from arzi.agents.nodes import ModelSettings
from arzi.agents.pipeline import AdkAuditPipeline, run_reasoning
from arzi.agents.stubs import FakeLlmClient
from arzi.config import AuthMode, Environment, LlmMode, LlmProvider, Settings
from arzi.services.appeal import AppealService
from arzi.services.claims import ClaimService
from arzi.services.cost_ledger import BudgetedLlmClient, ModelPrice, PriceTable, parse_price_table
from arzi.services.demo import DemoService
from arzi.services.extraction import ExtractionService
from arzi.services.family import FamilyService
from arzi.services.pipeline import AuditStep, ExtractStep, ReconcileStep, RedactStep
from arzi.services.ports import (
    AuthVerifier,
    BlobStore,
    ClaimRepository,
    CostLedgerStore,
    LlmClient,
    SpeechClient,
    StoredDocument,
)
from arzi.services.public_check import DailyLimiter, PublicCheckService
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
    appeals: AppealService
    demo: DemoService
    family: FamilyService
    public_check: PublicCheckService
    clock: Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _live_models(settings: Settings, model: str) -> tuple[Any, bool, PriceTable]:
    """The live Gemini models API (Vertex AI, or AI Studio for local testing), whether it can
    read gs:// URIs, and the price table (free-tier models priced at zero)."""
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
            model, ModelPrice(input_inr_per_1m=Decimal(0), output_inr_per_1m=Decimal(0))
        )
        return models, False, prices
    if not settings.google_cloud_project:
        raise ConfigurationError("Vertex AI needs GOOGLE_CLOUD_PROJECT")
    models = vertex_models(
        settings.google_cloud_project, settings.vertex_location, settings.llm_timeout_s
    )
    return models, True, prices


def build_speech(
    settings: Settings, ledger: CostLedgerStore, clock: Callable[[], dt.datetime]
) -> SpeechClient:
    """Narration for the family page: recorded (replay), silence (fake) or Gemini TTS (live)."""
    if settings.llm_mode is LlmMode.REPLAY:
        return ReplaySpeech(settings.replay_dir, voice=settings.tts_voice)
    if settings.llm_mode is LlmMode.FAKE:
        return SilentSpeech()
    live = _live_speech(settings, ledger, clock)
    if settings.llm_mode is LlmMode.HYBRID:
        return ReplayThenLiveSpeech(
            ReplaySpeech(settings.replay_dir, voice=settings.tts_voice), live
        )
    return live


def _live_speech(
    settings: Settings, ledger: CostLedgerStore, clock: Callable[[], dt.datetime]
) -> SpeechClient:
    if not settings.model_tts:
        raise ConfigurationError("live mode needs ARZI_MODEL_TTS for narration")
    models, _, prices = _live_models(settings, settings.model_tts)
    gemini = GeminiSpeech(
        models,
        model=settings.model_tts,
        voice=settings.tts_voice,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
    speech: SpeechClient = BudgetedSpeech(
        gemini,
        ledger,
        prices,
        model=settings.model_tts,
        daily_cap_inr=settings.daily_budget_inr,
        clock=clock,
    )
    if settings.llm_record_dir is not None:
        return RecordingSpeech(
            speech, settings.llm_record_dir.parent / "audio_cache", voice=settings.tts_voice
        )
    return speech


def build_llm(
    settings: Settings, ledger: CostLedgerStore, clock: Callable[[], dt.datetime]
) -> LlmClient:
    if settings.llm_mode is LlmMode.REPLAY:
        return ReplayLlmClient(settings.replay_dir, delay_s=settings.replay_delay_ms / 1000)
    if settings.llm_mode is LlmMode.FAKE:
        return FakeLlmClient(FixtureLlmClient(settings.replay_dir))
    live = _live_llm(settings, ledger, clock)
    if settings.llm_mode is LlmMode.HYBRID:
        replay = ReplayLlmClient(settings.replay_dir, delay_s=settings.replay_delay_ms / 1000)
        return ReplayThenLiveLlm(replay, live)
    return live


def _live_llm(
    settings: Settings, ledger: CostLedgerStore, clock: Callable[[], dt.datetime]
) -> LlmClient:
    if not settings.model_flash:
        raise ConfigurationError("live mode needs ARZI_MODEL_FLASH")
    models, gcs_uris, prices = _live_models(settings, settings.model_flash)
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
        from google.cloud import storage

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
    speech: SpeechClient | None = None,
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
    speech = speech or build_speech(settings, ledger, clock)
    store = blobs

    async def load(document: StoredDocument) -> bytes:
        return await store.get(document.uri)

    extraction = ExtractionService(
        llm,
        model=settings.model_flash or "model-not-configured",
        thinking_budget=settings.llm_thinking_budget,
        concurrency=settings.extraction_concurrency,
    )
    models = ModelSettings(
        client=llm,
        model=settings.model_flash or "model-not-configured",
        thinking_budget=settings.reasoning_thinking_budget,
    )
    pipeline = AdkAuditPipeline(
        ExtractStep(extraction, load),
        RedactStep(Redactor(settings.pseudonym_salt.get_secret_value().encode())),
        ReconcileStep(),
        AuditStep(),
        models,
    )
    claims = ClaimService(
        repo,
        blobs,
        clock=clock,
        new_id=id_factory,
        max_upload_mb=settings.max_upload_mb,
        max_pages=settings.max_pages,
    )
    runs = RunService(repo, pipeline, clock=clock, new_id=id_factory)
    appeals = AppealService(repo, models, clock=clock, reason=run_reasoning)
    family = FamilyService(
        repo,
        blobs,
        appeals,
        speech,
        models,
        clock=clock,
        reason=run_reasoning,
        share_days=settings.share_link_days,
        desk_contact=settings.desk_contact,
    )
    return Services(
        repo=repo,
        blobs=blobs,
        ledger=ledger,
        llm=llm,
        auth=DemoAuthVerifier(),
        claims=claims,
        runs=runs,
        appeals=appeals,
        demo=DemoService(claims, runs, settings.replay_dir, enabled=settings.demo_cases_enabled),
        family=family,
        public_check=PublicCheckService(
            claims,
            runs,
            family,
            DailyLimiter(
                settings.pseudonym_salt.get_secret_value().encode(),
                per_key=settings.public_checks_per_ip_per_day,
                total=settings.public_checks_per_day,
                clock=clock,
            ),
            tenant_id=settings.public_tenant_id,
        ),
        clock=clock,
    )
