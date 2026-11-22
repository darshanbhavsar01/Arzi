"""DPDP requests and retention (``/api/v1``): export and erase a claim, sweep old claims."""

from typing import Annotated

from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict, Field

from arzi.api.deps import PrincipalDep, ServicesDep, SettingsDep
from arzi.services.privacy import ClaimExport, Erasure, RetentionResult

router = APIRouter(prefix="/api/v1", tags=["privacy"])


class RetentionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    older_than_days: int | None = Field(None, ge=1, le=3650)
    """Defaults to ``ARZI_RETENTION_DAYS``."""


@router.get("/claims/{claim_id}/export")
async def export_claim(
    claim_id: str, principal: PrincipalDep, services: ServicesDep
) -> ClaimExport:
    """Everything held about the claim, for a data principal's access request."""
    return await services.privacy.export(principal, claim_id)


@router.delete("/claims/{claim_id}")
async def erase_claim(claim_id: str, principal: PrincipalDep, services: ServicesDep) -> Erasure:
    """Erase the claim and all its data (administrators only; cannot be undone)."""
    return await services.privacy.erase(principal, claim_id)


@router.post("/admin/retention")
async def run_retention(
    principal: PrincipalDep,
    services: ServicesDep,
    settings: SettingsDep,
    body: Annotated[RetentionRequest | None, Body()] = None,
) -> RetentionResult:
    """Erase claims not updated within the retention window. Meant for Cloud Scheduler."""
    days = (body.older_than_days if body else None) or settings.retention_days
    return await services.privacy.sweep(principal, days)
