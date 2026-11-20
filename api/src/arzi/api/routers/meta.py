"""Reference data the UI renders: the citation whitelist with verified/verify status."""

from fastapi import APIRouter

from arzi.rules.reference import RuleCitation, citations

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])


@router.get("/citations")
async def list_citations() -> list[RuleCitation]:
    return list(citations().values())
