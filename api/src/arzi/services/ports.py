"""Ports: what services need from the outside world, as structural Protocols.

Adapters (Firestore, Cloud Storage, Vertex AI) and the in-memory implementations used for local
replay mode and tests satisfy these without importing them. Every claim-scoped method takes the
``hospital_id`` so a tenant boundary is part of each call, not a filter someone can forget.
"""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from arzi.domain.enums import ClaimMode, ClaimStatus
from arzi.domain.models import (
    AppealVersion,
    AuditRun,
    ClaimRecord,
    Hospital,
    LlmCall,
    RunEvent,
    ShareLink,
)
from arzi.services.extraction_schemas import DocType


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- identity


class Principal(_Value):
    user_id: str
    display_name: str
    hospital_id: str
    role: Literal["billing_executive", "reviewer", "admin"]


class AuthVerifier(Protocol):
    async def verify(self, authorization: str | None) -> Principal:
        """Return the caller, or raise ``UnauthenticatedError``."""
        ...


class UnauthenticatedError(Exception):
    """The request carries no valid credential."""


# --------------------------------------------------------------------------- documents


class StoredDocument(_Value):
    document_id: str
    filename: str = Field(max_length=200)
    content_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: int
    pages: int
    sha256: str
    uri: str
    document_type: DocType | None = None
    """Set by the uploader when known; otherwise the pipeline classifies the document."""
    uploaded_at: dt.datetime


class AuditLogEntry(_Value):
    """Append-only record of who did what to a claim (DPDP accountability)."""

    at: dt.datetime
    actor: str
    action: str
    detail: dict[str, str | int | None] = Field(default_factory=dict)


@dataclass(frozen=True)
class ClaimPage:
    items: Sequence[ClaimRecord]
    next_cursor: str | None


class ClaimRepository(Protocol):
    async def get_hospital(self, hospital_id: str) -> Hospital | None: ...

    async def create_claim(self, record: ClaimRecord) -> ClaimRecord: ...

    async def get_claim(self, hospital_id: str, claim_id: str) -> ClaimRecord | None: ...

    async def save_claim(self, record: ClaimRecord) -> ClaimRecord:
        """Write if the stored revision equals ``record.revision``; returns revision + 1.

        Raises ``ConcurrentUpdateError`` otherwise.
        """
        ...

    async def list_claims(
        self,
        hospital_id: str,
        *,
        status: ClaimStatus | None = None,
        mode: ClaimMode | None = None,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 25,
    ) -> ClaimPage: ...

    async def add_document(
        self, hospital_id: str, claim_id: str, document: StoredDocument
    ) -> None: ...

    async def list_documents(self, hospital_id: str, claim_id: str) -> list[StoredDocument]: ...

    async def save_run(self, hospital_id: str, claim_id: str, run: AuditRun) -> None: ...

    async def get_run(self, hospital_id: str, claim_id: str, run_id: str) -> AuditRun | None: ...

    async def find_run_by_key(
        self, hospital_id: str, claim_id: str, idempotency_key: str
    ) -> AuditRun | None: ...

    async def append_audit_log(
        self, hospital_id: str, claim_id: str, entry: AuditLogEntry
    ) -> None: ...

    async def list_audit_log(self, hospital_id: str, claim_id: str) -> list[AuditLogEntry]: ...

    async def save_identity_vault(
        self, hospital_id: str, claim_id: str, vault: dict[str, str]
    ) -> None:
        """Pseudonym → original value, in a restricted document used only for signed letters."""
        ...

    async def get_identity_vault(self, hospital_id: str, claim_id: str) -> dict[str, str]:
        """Read only to address a signed appeal; empty when the claim has none."""
        ...

    async def save_appeal(self, hospital_id: str, appeal: AppealVersion) -> None:
        """Create or replace one appeal version (``claims/{cid}/appeals/{version}``)."""
        ...

    async def get_appeal(
        self, hospital_id: str, claim_id: str, version: int
    ) -> AppealVersion | None: ...

    async def list_appeals(self, hospital_id: str, claim_id: str) -> list[AppealVersion]:
        """All versions, oldest first."""
        ...

    async def save_share(self, share: ShareLink) -> None: ...

    async def get_share(self, token_sha256: str) -> ShareLink | None: ...

    async def list_shares(self, hospital_id: str, claim_id: str) -> list[ShareLink]:
        """Every family link of a claim, oldest first."""
        ...

    async def delete_claim(self, hospital_id: str, claim_id: str) -> None:
        """Erase the claim and everything under it (documents, runs, log, identity vault,
        appeals) plus its family links. A DPDP erasure, so nothing is kept."""
        ...


class ConcurrentUpdateError(Exception):
    """Someone else changed the claim since it was read."""


class BlobStore(Protocol):
    async def put(
        self, hospital_id: str, claim_id: str, document_id: str, data: bytes, content_type: str
    ) -> str:
        """Store bytes and return their URI (``gs://`` in the cloud)."""
        ...

    async def get(self, uri: str) -> bytes: ...

    async def view_url(self, uri: str, *, ttl_s: int = 600) -> str | None:
        """A short-lived URL for the browser, or None when the API must stream the bytes."""
        ...

    async def delete_claim(self, hospital_id: str, claim_id: str) -> int:
        """Delete every object stored for the claim; returns how many were removed."""
        ...


# --------------------------------------------------------------------------- models


@dataclass(frozen=True)
class FilePart:
    data: bytes
    mime_type: str
    sha256: str
    uri: str | None = None


@dataclass(frozen=True)
class LlmRequest[T: BaseModel]:
    """A structured-output call. ``prompt_ref`` (name@version) is recorded with the output."""

    prompt_ref: str
    system: str
    schema: type[T]
    model: str
    text: str = ""
    files: Sequence[FilePart] = field(default_factory=tuple)
    max_output_tokens: int = 8192
    temperature: float = 0.1
    thinking_budget: int = 0


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    output: T
    call: LlmCall


class LlmClient(Protocol):
    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]: ...


class LlmUnavailableError(Exception):
    """The model call failed after retries, or no recording exists in replay mode."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug


class CostLedgerStore(Protocol):
    async def spent_micro_inr(self, day: dt.date) -> int: ...

    async def add(self, day: dt.date, call: LlmCall) -> None:
        """Atomically add one call's cost and tokens to the day's totals."""
        ...


class EventSink(Protocol):
    async def publish(self, event: RunEvent) -> None: ...


# --------------------------------------------------------------------------- speech


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    content_type: Literal["audio/mpeg", "audio/wav"]
    seconds: float
    model: str
    adapter: Literal["gemini_tts", "replay", "fake"]
    call: LlmCall | None = None


class SpeechClient(Protocol):
    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        """Narrate ``text`` (already rendered, amounts included) in ``lang``."""
        ...
