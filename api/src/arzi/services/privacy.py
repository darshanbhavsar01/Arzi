"""DPDP rights and retention: export a claim, erase a claim, sweep claims past retention.

An access request is answered with everything Arzi holds about a claim except the identity
vault's raw values (only which pseudonyms have one), because the export travels outside the
restricted store. Erasure is total: the claim, its documents and recordings, runs, audit log,
appeals and family links. Only an administrator may erase, since it cannot be undone.
"""

import datetime as dt
import logging
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from arzi.domain.models import AppealVersion, AuditRun, ClaimRecord
from arzi.services.claims import ClaimService
from arzi.services.errors import RoleForbiddenError
from arzi.services.ports import AuditLogEntry, BlobStore, ClaimRepository, Principal

logger = logging.getLogger(__name__)


class ExportedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    pages: int
    sha256: str
    uploaded_at: dt.datetime


class ClaimExport(BaseModel):
    """What Arzi holds about one claim, for a DPDP access request."""

    model_config = ConfigDict(frozen=True)

    exported_at: dt.datetime
    claim: ClaimRecord
    documents: list[ExportedDocument]
    runs: list[AuditRun]
    appeals: list[AppealVersion]
    audit_log: list[AuditLogEntry]
    family_links: int = Field(description="Links created; tokens are never stored or exported")
    identifiers_held: list[str] = Field(
        description="Pseudonyms with a raw value in the restricted vault (values not exported)"
    )


class Erasure(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str
    objects_deleted: int


class RetentionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    cutoff: dt.datetime
    erased: list[str]


def _require_admin(principal: Principal, action: str) -> None:
    if principal.role != "admin":
        raise RoleForbiddenError(f"Only an administrator can {action}.")


class PrivacyService:
    def __init__(
        self,
        repo: ClaimRepository,
        blobs: BlobStore,
        claims: ClaimService,
        *,
        clock: Callable[[], dt.datetime],
    ) -> None:
        self._repo = repo
        self._blobs = blobs
        self._claims = claims
        self._clock = clock

    async def export(self, principal: Principal, claim_id: str) -> ClaimExport:
        claim = await self._claims.get(principal, claim_id)
        hid = principal.hospital_id
        runs = [
            run
            for summary in claim.runs
            if (run := await self._repo.get_run(hid, claim_id, summary.run_id)) is not None
        ]
        documents = await self._repo.list_documents(hid, claim_id)
        export = ClaimExport(
            exported_at=self._clock(),
            claim=claim,
            documents=[ExportedDocument.model_validate(d.model_dump()) for d in documents],
            runs=runs,
            appeals=await self._repo.list_appeals(hid, claim_id),
            audit_log=await self._repo.list_audit_log(hid, claim_id),
            family_links=len(await self._repo.list_shares(hid, claim_id)),
            identifiers_held=sorted(await self._repo.get_identity_vault(hid, claim_id)),
        )
        await self._repo.append_audit_log(
            hid,
            claim_id,
            AuditLogEntry(at=self._clock(), actor=principal.user_id, action="claim.exported"),
        )
        return export

    async def erase(self, principal: Principal, claim_id: str) -> Erasure:
        _require_admin(principal, "erase a claim")
        await self._claims.get(principal, claim_id)  # tenant check: another hospital's is 404
        removed = await self._blobs.delete_claim(principal.hospital_id, claim_id)
        await self._repo.delete_claim(principal.hospital_id, claim_id)
        # The claim's own log is gone with it; this line is the accountability record.
        logger.info("claim erased", extra={"claim_id": claim_id, "actor": principal.user_id})
        return Erasure(claim_id=claim_id, objects_deleted=removed)

    async def sweep(self, principal: Principal, older_than_days: int) -> RetentionResult:
        """Erase every claim of the hospital not updated within the retention window."""
        _require_admin(principal, "run the retention sweep")
        cutoff = self._clock() - dt.timedelta(days=older_than_days)
        stale: list[str] = []
        cursor: str | None = None
        while True:
            page = await self._repo.list_claims(principal.hospital_id, cursor=cursor, limit=100)
            stale += [
                c.claim_id for c in page.items if c.updated_at is not None and c.updated_at < cutoff
            ]
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        for claim_id in stale:
            await self.erase(principal, claim_id)
        return RetentionResult(cutoff=cutoff, erased=stale)
