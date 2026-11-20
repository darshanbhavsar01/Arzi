"""Claims, documents, consent and human corrections (``/api/v1``).

Every route is scoped to the caller's hospital through the principal; a claim ID from another
tenant is simply not found.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from arzi.api.deps import PrincipalDep, ServicesDep, SettingsDep
from arzi.domain.enums import ClaimMode, ClaimStatus, Severity
from arzi.domain.models import AppealSummary, ClaimRecord, Totals
from arzi.services.claims import FlagDecision, LineCorrection
from arzi.services.errors import FileTooLargeError
from arzi.services.extraction_schemas import DocType
from arzi.services.ports import AuditLogEntry, StoredDocument

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class CreateClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ClaimMode
    insurer_hint: str | None = Field(None, max_length=200)


class ClaimSummary(_Out):
    """One worklist row: pseudonymised patient, no document content."""

    claim_id: str
    mode: ClaimMode
    status: ClaimStatus
    insurer: str | None
    patient: str | None
    admitted_on: dt.date | None
    discharged_on: dt.date | None
    created_at: dt.datetime | None
    updated_at: dt.datetime | None
    totals: Totals | None
    flag_count: int
    severities: list[Severity]
    needs_confirmation: int
    audit_seconds: float | None
    """How long the last completed audit took."""
    latest_appeal: AppealSummary | None

    @classmethod
    def of(cls, record: ClaimRecord) -> "ClaimSummary":
        facts = record.facts
        done = [r for r in record.runs if r.status == "completed" and r.finished_at]
        last = done[-1] if done else None
        return cls(
            claim_id=record.claim_id,
            mode=record.mode,
            status=record.status,
            insurer=facts.policy.insurer if facts else record.insurer_hint,
            patient=facts.patient.redacted_id if facts else None,
            admitted_on=facts.admission.date_in if facts else None,
            discharged_on=facts.admission.date_out if facts else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
            totals=record.audit.totals if record.audit else None,
            flag_count=len(record.audit.flags) if record.audit else 0,
            severities=[f.severity for f in record.audit.flags] if record.audit else [],
            needs_confirmation=len(record.issues),
            audit_seconds=(last.finished_at - last.started_at).total_seconds()
            if last and last.finished_at
            else None,
            latest_appeal=record.appeals[-1] if record.appeals else None,
        )


class ClaimList(_Out):
    items: list[ClaimSummary]
    next_cursor: str | None


class DocumentOut(_Out):
    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    pages: int
    sha256: str
    document_type: DocType | None
    uploaded_at: dt.datetime

    @classmethod
    def of(cls, doc: StoredDocument, types: dict[str, str] | None = None) -> "DocumentOut":
        out = doc.model_dump(exclude={"uri"})
        if out["document_type"] is None and types:
            out["document_type"] = types.get(doc.document_id)
        return cls.model_validate(out)


class ViewUrl(_Out):
    url: str
    expires_in_s: int | None


class ConsentIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    given_by: str = Field(min_length=1, max_length=120, description="Who consented, e.g. 'patient'")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_claim(
    body: CreateClaim, principal: PrincipalDep, services: ServicesDep
) -> ClaimRecord:
    return await services.claims.create(principal, body.mode, body.insurer_hint)


@router.get("")
async def list_claims(
    principal: PrincipalDep,
    services: ServicesDep,
    status_: Annotated[ClaimStatus | None, Query(alias="status")] = None,
    mode: ClaimMode | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ClaimList:
    page = await services.claims.page(
        principal, status=status_, mode=mode, query=q, cursor=cursor, limit=limit
    )
    return ClaimList(items=[ClaimSummary.of(r) for r in page.items], next_cursor=page.next_cursor)


@router.get("/{claim_id}")
async def get_claim(claim_id: str, principal: PrincipalDep, services: ServicesDep) -> ClaimRecord:
    return await services.claims.get(principal, claim_id)


@router.get("/{claim_id}/documents")
async def list_documents(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> list[DocumentOut]:
    claim = await services.claims.get(principal, claim_id)
    documents = await services.claims.documents(principal, claim_id)
    return [DocumentOut.of(d, claim.document_types) for d in documents]


@router.post("/{claim_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    claim_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="PDF, JPEG or PNG")],
    document_type: Annotated[DocType | None, Form()] = None,
) -> DocumentOut:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise FileTooLargeError(f"Files can be at most {settings.max_upload_mb} MB.")
    document = await services.claims.upload(
        principal, claim_id, filename=file.filename or "", data=data, document_type=document_type
    )
    return DocumentOut.of(document)


@router.get("/{claim_id}/documents/{document_id}/url")
async def document_url(
    claim_id: str, document_id: str, principal: PrincipalDep, services: ServicesDep
) -> ViewUrl:
    document = await services.claims.document(principal, claim_id, document_id)
    signed = await services.claims.view_url(document)
    if signed is not None:
        return ViewUrl(url=signed, expires_in_s=600)
    return ViewUrl(
        url=f"/api/v1/claims/{claim_id}/documents/{document_id}/content", expires_in_s=None
    )


@router.get("/{claim_id}/documents/{document_id}/content")
async def document_content(
    claim_id: str, document_id: str, principal: PrincipalDep, services: ServicesDep
) -> Response:
    document = await services.claims.document(principal, claim_id, document_id)
    data = await services.claims.document_bytes(document)
    return Response(
        data,
        media_type=document.content_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{claim_id}/consent")
async def record_consent(
    claim_id: str, body: ConsentIn, principal: PrincipalDep, services: ServicesDep
) -> ClaimRecord:
    return await services.claims.record_consent(principal, claim_id, body.given_by)


@router.patch("/{claim_id}/lines/{line_id}")
async def correct_line(
    claim_id: str,
    line_id: int,
    body: LineCorrection,
    principal: PrincipalDep,
    services: ServicesDep,
) -> ClaimRecord:
    return await services.claims.correct_line(principal, claim_id, line_id, body)


@router.post("/{claim_id}/flags/{flag_id}/review")
async def review_flag(
    claim_id: str,
    flag_id: str,
    body: FlagDecision,
    principal: PrincipalDep,
    services: ServicesDep,
) -> ClaimRecord:
    """Accept a flag or dismiss it with a reason; the decision is audited."""
    return await services.claims.review_flag(principal, claim_id, flag_id, body)


@router.get("/{claim_id}/audit-log")
async def audit_log(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> list[AuditLogEntry]:
    return await services.claims.audit_log(principal, claim_id)
