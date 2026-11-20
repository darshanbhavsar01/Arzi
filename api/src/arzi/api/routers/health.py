"""Liveness and readiness endpoints for Cloud Run and uptime checks.

These live outside ``/api/v1`` and stay unauthenticated: platform health checks cannot carry
user credentials.
"""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from arzi.api.deps import ReadinessProbesDep, SettingsDep
from arzi.services.readiness import ReadinessReport, check_readiness

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    build_sha: str


@router.get("/healthz", summary="Liveness: the process is up")
async def healthz(settings: SettingsDep) -> Liveness:
    """Deliberately dependency-free, so a slow database never restarts a healthy container."""
    return Liveness(build_sha=settings.build_sha)


@router.get(
    "/readyz",
    summary="Readiness: backing services are reachable",
    responses={503: {"model": ReadinessReport, "description": "A dependency is unreachable"}},
)
async def readyz(
    response: Response, settings: SettingsDep, probes: ReadinessProbesDep
) -> ReadinessReport:
    report = await check_readiness(probes, settings.readiness_timeout_s)
    if not report.ready:
        response.status_code = 503
    return report
