"""Appeals: forum checklist, draft, edit, review, sign and export (``/api/v1``).

Arzi is decision support: an appeal can be exported only after a named reviewer has signed the
exact content, and any edit after signing makes a new version that needs a fresh signature.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict

from arzi.api.deps import PrincipalDep, ServicesDep
from arzi.domain.enums import AppealForum, GroOutcome
from arzi.domain.models import AppealVersion
from arzi.rules.forums import ForumOption, GroComplaint
from arzi.services.appeal import AppealEdit, SignRequest
from arzi.services.errors import RoleForbiddenError

SIGNING_ROLES = frozenset({"reviewer", "admin"})

router = APIRouter(prefix="/api/v1/claims/{claim_id}/appeals", tags=["appeals"])


class DraftAppeal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    forum: AppealForum
    gro_complaint: GroComplaint | None = None
    """The written complaint already made to the insurer; the Ombudsman needs it."""


@router.get("/forums")
async def forums(
    claim_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
    gro_filed_on: dt.date | None = None,
    gro_outcome: GroOutcome | None = None,
    gro_replied_on: dt.date | None = None,
) -> list[ForumOption]:
    """Where this appeal can go now, with the checklist behind each answer."""
    complaint = (
        GroComplaint(filed_on=gro_filed_on, outcome=gro_outcome, replied_on=gro_replied_on)
        if gro_filed_on and gro_outcome
        else None
    )
    return list(await services.appeals.forums(principal, claim_id, complaint))


@router.post("", status_code=status.HTTP_201_CREATED)
async def draft_appeal(
    claim_id: str,
    body: DraftAppeal,
    principal: PrincipalDep,
    services: ServicesDep,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> AppealVersion:
    """Draft the next version with the AppealDrafter. Repeating the request with the same
    ``Idempotency-Key`` returns the same version instead of drafting (and paying) again."""
    return await services.appeals.draft(
        principal, claim_id, body.forum, body.gro_complaint, idempotency_key
    )


@router.get("")
async def list_appeals(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> list[AppealVersion]:
    return await services.appeals.versions(principal, claim_id)


@router.get("/{version}")
async def get_appeal(
    claim_id: str, version: int, principal: PrincipalDep, services: ServicesDep
) -> AppealVersion:
    return await services.appeals.get(principal, claim_id, version)


@router.put("/{version}", status_code=status.HTTP_201_CREATED)
async def edit_appeal(
    claim_id: str, version: int, body: AppealEdit, principal: PrincipalDep, services: ServicesDep
) -> AppealVersion:
    """Save a reviewer's edits as the next version. Amounts must stay placeholders."""
    return await services.appeals.edit(principal, claim_id, version, body)


@router.post("/{version}/submit")
async def submit_appeal(
    claim_id: str, version: int, principal: PrincipalDep, services: ServicesDep
) -> AppealVersion:
    return await services.appeals.submit(principal, claim_id, version)


@router.post("/{version}/sign")
async def sign_appeal(
    claim_id: str, version: int, body: SignRequest, principal: PrincipalDep, services: ServicesDep
) -> AppealVersion:
    """A named reviewer signs; the SHA-256 of the exact content is stored with the signature.

    Only the reviewer and admin roles may sign: the human gate is enforced here, not in the UI.
    """
    if principal.role not in SIGNING_ROLES:
        raise RoleForbiddenError("Only a reviewer or administrator can sign an appeal.")
    return await services.appeals.sign(principal, claim_id, version, body)


@router.get(
    "/{version}/export.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def export_appeal(
    claim_id: str,
    version: int,
    principal: PrincipalDep,
    services: ServicesDep,
    download: Annotated[bool, Query()] = True,
) -> Response:
    """The signed letter as a PDF; refused (409) until a named reviewer has signed it."""
    if principal.role not in SIGNING_ROLES:
        raise RoleForbiddenError("Only a reviewer or administrator can export an appeal.")
    pdf, appeal = await services.appeals.export(principal, claim_id, version)
    disposition = "attachment" if download else "inline"
    filename = f"{claim_id}-appeal-v{appeal.version}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
