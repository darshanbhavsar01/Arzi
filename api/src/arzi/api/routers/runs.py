"""Audit runs and their live event stream (``/api/v1``)."""

from typing import Annotated

from fastapi import APIRouter, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from arzi.api.deps import PrincipalDep, ServicesDep, SettingsDep
from arzi.api.sse import stream
from arzi.domain.models import AuditRun, RunStatus

router = APIRouter(prefix="/api/v1/claims/{claim_id}/runs", tags=["runs"])


class RunStarted(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    status: RunStatus
    events_url: str


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    claim_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> RunStarted:
    """Start an audit. Repeating the request with the same ``Idempotency-Key`` returns the
    same run instead of starting another (and paying for another)."""
    run = await services.runs.start(principal, claim_id, idempotency_key)
    return RunStarted(
        run_id=run.run_id,
        status=run.status,
        events_url=f"/api/v1/claims/{claim_id}/runs/{run.run_id}/events",
    )


@router.get("")
async def list_runs(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> list[AuditRun]:
    """Every audit run of the claim, newest first: stages, timings, models, prompts, cost."""
    return await services.runs.list(principal, claim_id)


@router.get("/{run_id}")
async def get_run(
    claim_id: str, run_id: str, principal: PrincipalDep, services: ServicesDep
) -> AuditRun:
    return await services.runs.get(principal, claim_id, run_id)


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def run_events(
    claim_id: str,
    run_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
    settings: SettingsDep,
    last_event_id: Annotated[int | None, Header(ge=0)] = None,
) -> StreamingResponse:
    """``stage.started`` · ``stage.completed`` · ``flag.created`` · ``run.completed`` ·
    ``run.failed``. Reconnect with ``Last-Event-ID`` to resume."""
    await services.runs.get(principal, claim_id, run_id)  # 404 before the stream opens
    events = services.runs.events(principal, claim_id, run_id, after=last_event_id or 0)
    return StreamingResponse(
        stream(events, settings.sse_heartbeat_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
