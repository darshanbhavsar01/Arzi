"""Synthetic demo cases: one click loads and audits cases A, B and C (``/api/v1``)."""

from fastapi import APIRouter, status

from arzi.api.deps import PrincipalDep, ServicesDep
from arzi.services.demo import DemoClaim

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@router.post("/cases", status_code=status.HTTP_202_ACCEPTED)
async def load_demo_cases(principal: PrincipalDep, services: ServicesDep) -> list[DemoClaim]:
    """Create the three synthetic demo claims and start their audits (synthetic data only)."""
    return await services.demo.load(principal)
