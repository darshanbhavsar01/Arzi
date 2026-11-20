"""Reference data and workspace facts the UI renders: citations, hospital, system status."""

from importlib.resources import files

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from arzi.api.deps import PrincipalDep, ServicesDep, SettingsDep
from arzi.domain.models import Hospital
from arzi.rules.reference import RuleCitation, citations
from arzi.services.cost_ledger import today_ist

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])


class ModelIds(BaseModel):
    model_config = ConfigDict(frozen=True)

    flash: str | None
    pro: str | None
    tts: str | None
    live: str | None


class Workspace(BaseModel):
    """Who is signed in, for which hospital, and how the AI is configured right now."""

    model_config = ConfigDict(frozen=True)

    hospital_id: str
    hospital: Hospital | None
    user_name: str
    user_role: str
    environment: str
    region: str
    llm_mode: str
    llm_provider: str
    models: ModelIds
    prompt_versions: list[str]
    daily_budget_inr: int
    spent_today_inr: float
    demo_cases_available: bool
    build_sha: str


def prompt_versions() -> list[str]:
    names = (r.name for r in files("arzi.prompts").iterdir() if r.name.endswith(".md"))
    return sorted(n.removesuffix(".md").replace(".v", "@v") for n in names)


@router.get("/citations")
async def list_citations() -> list[RuleCitation]:
    return list(citations().values())


@router.get("/workspace")
async def workspace(
    principal: PrincipalDep, services: ServicesDep, settings: SettingsDep
) -> Workspace:
    spent = await services.ledger.spent_micro_inr(today_ist(services.clock))
    return Workspace(
        hospital_id=principal.hospital_id,
        hospital=await services.repo.get_hospital(principal.hospital_id),
        user_name=principal.display_name,
        user_role=principal.role,
        environment=str(settings.env),
        region=settings.gcp_region,
        llm_mode=str(settings.llm_mode),
        llm_provider=str(settings.llm_provider),
        models=ModelIds(
            flash=settings.model_flash,
            pro=settings.model_pro,
            tts=settings.model_tts,
            live=settings.model_live,
        ),
        prompt_versions=prompt_versions(),
        daily_budget_inr=settings.daily_budget_inr,
        spent_today_inr=spent / 1_000_000,
        demo_cases_available=services.demo.available,
        build_sha=settings.build_sha,
    )
