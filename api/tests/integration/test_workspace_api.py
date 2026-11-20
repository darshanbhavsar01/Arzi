"""What the desk app needs beyond claims and appeals: demo cases, worklist rows, flag decisions,
classified documents, run history and the workspace panel. Replay mode, recorded responses."""

from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import FastAPI

from arzi.bootstrap import Services, build_services
from arzi.config import Settings
from arzi.main import create_app


@pytest.fixture
def services(settings: Settings) -> Services:
    return build_services(settings)


@pytest.fixture
async def api(
    settings: Settings, services: Services, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(create_app(settings, readiness_probes=[], services=services)) as c:
        yield c


async def _load_demo(api: httpx.AsyncClient, services: Services) -> dict[str, str]:
    response = await api.post("/api/v1/demo/cases")
    assert response.status_code == 202, response.text
    loaded = response.json()
    for item in loaded:
        await services.runs.wait(item["run_id"])
    return {item["case"]: item["claim_id"] for item in loaded}


async def test_demo_cases_load_and_audit_into_rich_worklist_rows(
    api: httpx.AsyncClient, services: Services
) -> None:
    claims = await _load_demo(api, services)
    assert set(claims) == {"case_a", "case_b", "case_c"}

    rows = {r["claim_id"]: r for r in (await api.get("/api/v1/claims")).json()["items"]}
    a, b, c = (rows[claims[k]] for k in ("case_a", "case_b", "case_c"))
    assert a["status"] == "audited"
    assert a["insurer"] == "Suraksha Health Insurance Co. (fictional)"
    assert a["patient"].startswith("P-")
    assert a["admitted_on"] == "2026-10-12"
    assert a["totals"]["at_risk"] == 6_788_750
    assert len(a["severities"]) == a["flag_count"] == 4
    assert a["audit_seconds"] is not None
    assert b["totals"]["recoverable_on_appeal"] == 2_013_750
    assert c["mode"] == "post_rejection"
    assert c["latest_appeal"] is None


async def test_demo_cases_can_be_switched_off(
    settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    off = settings.model_copy(update={"demo_cases_enabled": False})
    async with client_for(create_app(off, readiness_probes=[])) as api:
        response = await api.post("/api/v1/demo/cases")
        info = (await api.get("/api/v1/meta/workspace")).json()
    assert response.status_code == 404
    assert response.json()["type"].endswith("/demo-cases-unavailable")
    assert info["demo_cases_available"] is False


async def test_flags_are_accepted_or_dismissed_with_an_audited_reason(
    api: httpx.AsyncClient, services: Services
) -> None:
    claim_id = (await _load_demo(api, services))["case_a"]
    base = f"/api/v1/claims/{claim_id}/flags"
    flag_id = (await api.get(f"/api/v1/claims/{claim_id}")).json()["audit"]["flags"][0]["flag_id"]

    no_reason = await api.post(f"{base}/{flag_id}/review", json={"decision": "dismissed"})
    assert no_reason.status_code == 422
    unknown = await api.post(f"{base}/NOPE/review", json={"decision": "accepted"})
    assert unknown.status_code == 404
    assert unknown.json()["type"].endswith("/flag-not-found")

    accepted = await api.post(f"{base}/{flag_id}/review", json={"decision": "accepted"})
    dismissed = await api.post(
        f"{base}/{flag_id}/review",
        json={"decision": "dismissed", "reason": "Patient signed the upgrade consent"},
    )
    assert accepted.status_code == dismissed.status_code == 200
    (review,) = dismissed.json()["flag_reviews"]
    assert (review["flag_id"], review["decision"]) == (flag_id, "dismissed")
    assert review["reason"] == "Patient signed the upgrade consent"
    log = (await api.get(f"/api/v1/claims/{claim_id}/audit-log")).json()
    assert [e["action"] for e in log if e["action"].startswith("flag.")] == [
        "flag.accepted",
        "flag.dismissed",
    ]


async def test_documents_carry_their_classified_type_and_runs_are_listed(
    api: httpx.AsyncClient, services: Services
) -> None:
    claim_id = (await _load_demo(api, services))["case_b"]
    documents = (await api.get(f"/api/v1/claims/{claim_id}/documents")).json()
    types = {d["filename"]: d["document_type"] for d in documents}
    assert types["itemised_bill.pdf"] == "itemised_bill"
    assert types["insurer_deduction_letter.pdf"] == "insurer_letter"

    (run,) = (await api.get(f"/api/v1/claims/{claim_id}/runs")).json()
    assert run["status"] == "completed"
    assert run["events"]
    assert any(c["prompt_ref"] == "explain_flags@v1" for c in run["calls"])
    missing = await api.get("/api/v1/claims/ARZ-NOPE/runs")
    assert missing.status_code == 404


async def test_workspace_describes_hospital_user_and_ai_configuration(
    api: httpx.AsyncClient,
) -> None:
    info = (await api.get("/api/v1/meta/workspace")).json()
    assert info["hospital"]["name"] == "Sanjeevani Multispeciality Hospital"
    assert info["user_role"] == "billing_executive"
    assert info["llm_mode"] == "replay"
    assert info["region"] == "asia-south1"
    assert "appeal_insurer_gro@v1" in info["prompt_versions"]
    assert "extract_policy@v2" in info["prompt_versions"]
    assert info["spent_today_inr"] == 0
    assert info["demo_cases_available"] is True
