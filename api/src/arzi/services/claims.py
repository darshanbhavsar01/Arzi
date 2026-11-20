"""Claims: create, list, upload documents, record consent, correct a bill line.

Every call is scoped to the caller's hospital. Audit-log entries record actions and IDs, never
file names or document content, which can carry patient identifiers.
"""

import datetime as dt
import hashlib
from collections.abc import Callable
from typing import Literal

import anyio
from pydantic import BaseModel, ConfigDict, Field

from arzi.domain.enums import ClaimMode, ClaimStatus, IrdaiList, LineCategory
from arzi.domain.models import ClaimRecord, Consent, FlagReview
from arzi.domain.money import MoneyParseError, to_paise
from arzi.domain.state import ClaimEvent, transition
from arzi.rules.engine import audit
from arzi.services.errors import (
    ClaimNotFoundError,
    ConflictError,
    DocumentNotFoundError,
    FileTooLargeError,
    FlagNotFoundError,
    InvalidInputError,
    InvalidStateError,
    LineNotFoundError,
    UnsupportedMediaError,
    UploadRejectedError,
)
from arzi.services.extraction_schemas import DocType
from arzi.services.ports import (
    AuditLogEntry,
    BlobStore,
    ClaimPage,
    ClaimRepository,
    ConcurrentUpdateError,
    Principal,
    StoredDocument,
)

_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
_UPLOADABLE = {ClaimStatus.DRAFT, ClaimStatus.DOCUMENTS_UPLOADED, ClaimStatus.FAILED}


class FlagDecision(BaseModel):
    """Accept a flag as a real risk, or dismiss it with a reason (both are audited)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["accepted", "dismissed"]
    reason: str = Field("", max_length=500)


class LineCorrection(BaseModel):
    """A person's correction to one bill line. Omitted fields are left as they are."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: LineCategory | None = None
    amount: str | None = Field(None, max_length=32, description="Rupees, e.g. '8,000.00'")
    irdai_list: IrdaiList | None = None
    """Send null to say the item is on no IRDAI list."""


def sniff(data: bytes) -> str | None:
    return next((mime for magic, mime in _SIGNATURES if data.startswith(magic)), None)


def count_pages(data: bytes, content_type: str) -> int:
    if content_type != "application/pdf":
        return 1
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        raise UploadRejectedError("The PDF could not be opened.") from None
    try:
        return len(document)
    finally:
        document.close()


class ClaimService:
    def __init__(
        self,
        repo: ClaimRepository,
        blobs: BlobStore,
        *,
        clock: Callable[[], dt.datetime],
        new_id: Callable[[], str],
        max_upload_mb: int,
        max_pages: int,
    ) -> None:
        self._repo = repo
        self._blobs = blobs
        self._clock = clock
        self._new_id = new_id
        self._max_bytes = max_upload_mb * 1024 * 1024
        self._max_pages = max_pages

    async def create(
        self, principal: Principal, mode: ClaimMode, insurer_hint: str | None
    ) -> ClaimRecord:
        now = self._clock()
        record = ClaimRecord(
            hospital_id=principal.hospital_id,
            claim_id=f"ARZ-{now.year}-{self._new_id()[:6].upper()}",
            mode=mode,
            insurer_hint=insurer_hint,
            created_at=now,
            updated_at=now,
        )
        stored = await self._repo.create_claim(record)
        await self._log(principal, stored.claim_id, "claim.created", mode=str(mode))
        return stored

    async def get(self, principal: Principal, claim_id: str) -> ClaimRecord:
        record = await self._repo.get_claim(principal.hospital_id, claim_id)
        if record is None:
            raise ClaimNotFoundError
        return record

    async def page(
        self,
        principal: Principal,
        *,
        status: ClaimStatus | None,
        mode: ClaimMode | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> ClaimPage:
        return await self._repo.list_claims(
            principal.hospital_id, status=status, mode=mode, query=query, cursor=cursor, limit=limit
        )

    async def upload(
        self,
        principal: Principal,
        claim_id: str,
        *,
        filename: str,
        data: bytes,
        document_type: DocType | None,
    ) -> StoredDocument:
        claim = await self.get(principal, claim_id)
        if claim.status not in _UPLOADABLE:
            raise InvalidStateError("Documents can only be added before the audit runs.")
        if len(data) > self._max_bytes:
            raise FileTooLargeError(f"Files can be at most {self._max_bytes // 2**20} MB.")
        content_type = sniff(data)
        if content_type is None:
            raise UnsupportedMediaError
        pages = await anyio.to_thread.run_sync(count_pages, data, content_type)
        if pages > self._max_pages:
            raise UploadRejectedError(f"Documents can have at most {self._max_pages} pages.")
        document_id = f"doc-{self._new_id()}"
        uri = await self._blobs.put(
            principal.hospital_id, claim_id, document_id, data, content_type
        )
        document = StoredDocument.model_validate(
            {
                "document_id": document_id,
                "filename": filename[-200:] or document_id,
                "content_type": content_type,
                "size_bytes": len(data),
                "pages": pages,
                "sha256": hashlib.sha256(data).hexdigest(),
                "uri": uri,
                "document_type": document_type,
                "uploaded_at": self._clock(),
            }
        )
        await self._repo.add_document(principal.hospital_id, claim_id, document)
        status = claim.status
        if status is ClaimStatus.FAILED:
            status = transition(status, ClaimEvent.RETRY)
        status = transition(status, ClaimEvent.UPLOAD_DOCUMENTS)
        types = dict(claim.document_types)
        if document_type is not None:
            types[document_id] = str(document_type)
        await self._save(
            claim.model_copy(
                update={"status": status, "updated_at": self._clock(), "document_types": types}
            )
        )
        await self._log(
            principal,
            claim_id,
            "document.uploaded",
            document_id=document_id,
            document_type=str(document_type) if document_type else None,
            size_bytes=len(data),
        )
        return document

    async def documents(self, principal: Principal, claim_id: str) -> list[StoredDocument]:
        await self.get(principal, claim_id)
        return await self._repo.list_documents(principal.hospital_id, claim_id)

    async def document(
        self, principal: Principal, claim_id: str, document_id: str
    ) -> StoredDocument:
        for document in await self.documents(principal, claim_id):
            if document.document_id == document_id:
                return document
        raise DocumentNotFoundError

    async def document_bytes(self, document: StoredDocument) -> bytes:
        return await self._blobs.get(document.uri)

    async def view_url(self, document: StoredDocument) -> str | None:
        return await self._blobs.view_url(document.uri)

    async def record_consent(
        self, principal: Principal, claim_id: str, given_by: str
    ) -> ClaimRecord:
        claim = await self.get(principal, claim_id)
        consent = Consent(given_by=given_by, recorded_by=principal.user_id, at=self._clock())
        saved = await self._save(
            claim.model_copy(update={"consent": consent, "updated_at": self._clock()})
        )
        await self._log(principal, claim_id, "consent.recorded", purpose=consent.purpose)
        return saved

    async def correct_line(
        self, principal: Principal, claim_id: str, line_id: int, correction: LineCorrection
    ) -> ClaimRecord:
        """Apply a person's correction and re-run the rules engine (no model call)."""
        claim = await self.get(principal, claim_id)
        if claim.facts is None or claim.status is not ClaimStatus.AUDITED:
            raise InvalidStateError("Lines can be corrected once the claim has been audited.")
        lines = list(claim.facts.bill_lines)
        index = next((i for i, line in enumerate(lines) if line.line_id == line_id), None)
        if index is None:
            raise LineNotFoundError
        update: dict[str, object] = {"confirmed_by_human": True, "confidence": 1.0}
        if correction.category is not None:
            update["category"] = correction.category
        if correction.amount is not None:
            try:
                update["amount"] = to_paise(correction.amount)
            except MoneyParseError:
                raise InvalidInputError("The amount must be a rupee figure.") from None
        if "irdai_list" in correction.model_fields_set:
            update["irdai_list"] = correction.irdai_list
        lines[index] = lines[index].model_copy(update=update)
        facts = claim.facts.model_validate(
            {**claim.facts.model_dump(), "bill_lines": [line.model_dump() for line in lines]}
        )
        saved = await self._save(
            claim.model_copy(
                update={
                    "facts": facts,
                    "audit": audit(facts),
                    "issues": tuple(i for i in claim.issues if i.line_id != line_id),
                    "updated_at": self._clock(),
                }
            )
        )
        fields = ",".join(sorted(correction.model_fields_set)) or "confirm"
        await self._log(principal, claim_id, "line.corrected", line_id=line_id, fields=fields)
        return saved

    async def review_flag(
        self, principal: Principal, claim_id: str, flag_id: str, decision: FlagDecision
    ) -> ClaimRecord:
        claim = await self.get(principal, claim_id)
        if claim.audit is None or flag_id not in {f.flag_id for f in claim.audit.flags}:
            raise FlagNotFoundError
        if decision.decision == "dismissed" and not decision.reason.strip():
            raise InvalidInputError("Say why the flag is dismissed; the reason is audited.")
        review = FlagReview(
            flag_id=flag_id,
            decision=decision.decision,
            reason=decision.reason.strip(),
            by=principal.user_id,
            at=self._clock(),
        )
        others = tuple(r for r in claim.flag_reviews if r.flag_id != flag_id)
        saved = await self._save(
            claim.model_copy(
                update={"flag_reviews": (*others, review), "updated_at": self._clock()}
            )
        )
        await self._log(principal, claim_id, f"flag.{decision.decision}", flag_id=flag_id)
        return saved

    async def audit_log(self, principal: Principal, claim_id: str) -> list[AuditLogEntry]:
        await self.get(principal, claim_id)
        return await self._repo.list_audit_log(principal.hospital_id, claim_id)

    async def _save(self, record: ClaimRecord) -> ClaimRecord:
        try:
            return await self._repo.save_claim(record)
        except ConcurrentUpdateError:
            raise ConflictError from None

    async def _log(
        self, principal: Principal, claim_id: str, action: str, **detail: str | int | None
    ) -> None:
        entry = AuditLogEntry(
            at=self._clock(), actor=principal.user_id, action=action, detail=dict(detail)
        )
        await self._repo.append_audit_log(principal.hospital_id, claim_id, entry)
