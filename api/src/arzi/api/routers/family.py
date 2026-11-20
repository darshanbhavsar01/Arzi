"""Family links: the desk prepares and shares a claim; the family opens it without an account.

Public routes are authorised by the link token alone (unknown, expired and withdrawn links all
get the same 404) and return only the family view: no identifiers, no document content.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Header, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from arzi.api.deps import PrincipalDep, ServicesDep, SettingsDep
from arzi.api.sse import stream
from arzi.domain.models import AppealVersion, FamilyPack, Language, ShareLink
from arzi.services.errors import ShareLinkInvalidError
from arzi.services.family import FamilyView, ShareCreated

desk = APIRouter(prefix="/api/v1/claims/{claim_id}", tags=["family"])
public = APIRouter(prefix="/api/v1/family/{token}", tags=["family"])

_PRIVATE = {"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"}


class PublicSign(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    declaration: Literal[True]


# --------------------------------------------------------------------------- desk


@desk.post("/family")
async def prepare_family(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> FamilyPack:
    """Write (once) the family explanation in Gujarati, Hindi and English, and narrate it."""
    return await services.family.prepare(principal, claim_id)


@desk.post("/shares", status_code=status.HTTP_201_CREATED)
async def create_share(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> ShareCreated:
    """A 7-day family link. The token appears only in this response; Arzi keeps its hash."""
    return await services.family.share(principal, claim_id)


@desk.get("/shares")
async def list_shares(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> list[ShareLink]:
    return await services.family.shares(principal, claim_id)


@desk.post("/shares/{token_sha256}/revoke")
async def revoke_share(
    claim_id: str, token_sha256: str, principal: PrincipalDep, services: ServicesDep
) -> ShareLink:
    return await services.family.revoke(principal, claim_id, token_sha256)


# --------------------------------------------------------------------------- family (by token)


@public.get("")
async def family_view(token: str, services: ServicesDep, response: Response) -> FamilyView:
    response.headers.update(_PRIVATE)
    return await services.family.view(token)


@public.post("/prepare")
async def family_prepare(token: str, services: ServicesDep, response: Response) -> FamilyView:
    """For the free check: write the explanation once its audit has finished."""
    response.headers.update(_PRIVATE)
    return await services.family.prepare_by_token(token)


@public.get(
    "/audio/{lang}",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}, "audio/wav": {}}}},
)
async def family_audio(token: str, lang: Language, services: ServicesDep) -> Response:
    audio, content_type = await services.family.audio(token, lang)
    return Response(
        audio, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"}
    )


@public.get(
    "/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def family_events(
    token: str,
    services: ServicesDep,
    settings: SettingsDep,
    last_event_id: Annotated[int | None, Header(ge=0)] = None,
) -> StreamingResponse:
    """Progress of the free check's audit (same events as the desk)."""
    _, claim, principal = await services.family.resolve(token)
    if not claim.runs:
        raise ShareLinkInvalidError
    run_id = claim.runs[-1].run_id
    events = services.runs.events(principal, claim.claim_id, run_id, after=last_event_id or 0)
    return StreamingResponse(
        stream(events, settings.sse_heartbeat_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@public.post("/appeal", status_code=status.HTTP_201_CREATED)
async def public_appeal(token: str, services: ServicesDep) -> AppealVersion:
    """Free check only: a draft appeal to the insurer's grievance officer, for review."""
    return await services.family.draft_public_appeal(token)


@public.get("/appeal")
async def public_appeal_latest(token: str, services: ServicesDep) -> AppealVersion:
    _, claim, principal = await services.family.resolve(token)
    versions = await services.appeals.versions(principal, claim.claim_id)
    if not versions:
        raise ShareLinkInvalidError("No appeal has been drafted yet.")
    return versions[-1]


@public.post("/appeal/sign")
async def public_appeal_sign(token: str, body: PublicSign, services: ServicesDep) -> AppealVersion:
    """The policyholder or their family reviews and signs; the SHA-256 is stored as for the desk."""
    return await services.family.sign_public_appeal(token, body.name)


@public.get(
    "/appeal.pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}}
)
async def public_appeal_pdf(token: str, services: ServicesDep) -> Response:
    pdf, appeal = await services.family.export_public_appeal(token)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="appeal-v{appeal.version}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
