"""Appeal journey over the API: draft (AppealDrafter in ``fake`` mode), edit, review, sign.

Gate checks for Phase 4: case B's GRO appeal disputes exactly the engine's appealable items,
with their citations and the relief total from ``expected.json``; case C's appeal cites
``IRDAI_PED_36M``; and nothing can be signed out of order.
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from arzi.adapters.fixture_llm import FixtureLlmClient
from arzi.agents.schemas import AppealDraftOutput
from arzi.agents.stubs import FakeLlmClient, StubReasoner
from arzi.bootstrap import Services, build_services
from arzi.config import LlmMode, Settings
from arzi.main import create_app
from arzi.services.errors import ClaimNotFoundError
from arzi.services.ports import LlmClient, LlmRequest, LlmResult, LlmUnavailableError, Principal
from tests.integration.pipeline_support import prepare_case, run_to_end
from tests.unit.rules.helpers import DEMO_CASES

GRO = {"forum": "insurer_gro"}


@pytest.fixture
def fake_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"llm_mode": LlmMode.FAKE, "replay_dir": DEMO_CASES})


def _api(
    settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient], llm: LlmClient | None
) -> tuple[Services, httpx.AsyncClient]:
    services = build_services(settings, llm=llm)
    app = create_app(settings, readiness_probes=[], services=services)
    return services, client_for(app)


@pytest.fixture
async def api(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    _, client = _api(fake_settings, client_for, None)
    async with client:
        yield client


async def _audited(api: httpx.AsyncClient, case: str) -> str:
    claim_id = await prepare_case(api, case)
    _, events = await run_to_end(api, claim_id)
    assert events[-1].event == "run.completed"
    return claim_id


async def _draft(api: httpx.AsyncClient, claim_id: str, body: dict[str, Any] = GRO) -> Any:  # noqa: ANN401
    response = await api.post(f"/api/v1/claims/{claim_id}/appeals", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _expected_disputes(case: str) -> tuple[list[dict[str, Any]], int]:
    want = json.loads((DEMO_CASES / case / "expected.json").read_text(encoding="utf-8"))
    flags = [f for f in want["flags"] if f["kind"] == "dispute" and f["appealable"]]
    return flags, want["totals"]["recoverable_on_appeal"]


@pytest.mark.parametrize("case", ["case_b", "case_c"])
async def test_appeal_disputes_the_engine_items_with_their_citations_and_relief(
    api: httpx.AsyncClient, case: str
) -> None:
    claim_id = await _audited(api, case)
    appeal = await _draft(api, claim_id)

    flags, relief = _expected_disputes(case)
    items = appeal["content"]["items"]
    assert [i["flag_id"] for i in items] == [f["flag_id"] for f in flags]
    assert [i["amount"] for i in items] == [f["recoverable"] for f in flags]
    for item, flag in zip(items, flags, strict=True):
        assert list(flag["citations"]) == item["citations"][: len(flag["citations"])]
        assert item["argument"]["text"]
    assert appeal["content"]["relief_amount"] == relief
    assert appeal["version"] == 1
    assert appeal["status"] == "draft"
    assert appeal["drafting"] == "passed"
    assert appeal["prompt_ref"] == "appeal_insurer_gro@v1"
    assert "Copy of the insurer's letter" in appeal["content"]["enclosures"]
    claim = (await api.get(f"/api/v1/claims/{claim_id}")).json()
    assert claim["status"] == "appeal_drafted"
    assert claim["appeals"] == [
        {
            "appeal_id": "v1",
            "forum": "insurer_gro",
            "version": 1,
            "status": "draft",
            "content_sha256": None,
        }
    ]


async def test_relief_and_amounts_are_rendered_from_the_engine(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_b")
    appeal = await _draft(api, claim_id)
    relief = appeal["content"]["relief"]
    assert relief["template"] == "We request that the insurer pay {{totals.recoverable}}."
    assert relief["text"] == "We request that the insurer pay ₹20,137.50."


async def test_case_c_appeal_cites_the_36_month_ped_cap(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_c")
    appeal = await _draft(api, claim_id)
    (item,) = appeal["content"]["items"]
    assert "IRDAI_PED_36M" in item["citations"]
    assert item["insurer_reason"] == "Rejected under the pre-existing disease waiting period"
    assert appeal["content"]["relief"]["text"].endswith("₹3,10,000.")


async def test_a_pre_submission_audit_has_nothing_to_appeal(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_a")
    response = await api.post(f"/api/v1/claims/{claim_id}/appeals", json=GRO)
    assert response.status_code == 409
    assert response.json()["type"].endswith("/invalid-state")


async def test_an_unaudited_claim_cannot_be_appealed(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_b")
    response = await api.get(f"/api/v1/claims/{claim_id}/appeals/forums")
    assert response.status_code == 409


async def test_forum_checklist_disables_the_ombudsman_until_eligible(
    api: httpx.AsyncClient,
) -> None:
    claim_id = await _audited(api, "case_b")
    base = f"/api/v1/claims/{claim_id}/appeals"

    options = {o["forum"]: o for o in (await api.get(f"{base}/forums")).json()}
    assert options["insurer_gro"]["eligible"]
    assert options["insurer_gro"]["response_window"] == "about 15 days (verify)"
    assert options["bima_bharosa"]["eligible"]
    assert not options["ombudsman"]["eligible"]
    assert "complaint" in options["ombudsman"]["reason"]

    refused = await api.post(base, json={"forum": "ombudsman"})
    assert refused.status_code == 409
    assert refused.json()["type"].endswith("/forum-not-eligible")

    complaint = {"filed_on": "2026-01-05", "outcome": "rejected", "replied_on": "2026-01-20"}
    query = "gro_filed_on=2026-01-05&gro_outcome=rejected&gro_replied_on=2026-01-20"
    options = {o["forum"]: o for o in (await api.get(f"{base}/forums?{query}")).json()}
    assert options["ombudsman"]["eligible"]
    appeal = await _draft(api, claim_id, {"forum": "ombudsman", "gro_complaint": complaint})
    assert appeal["prompt_ref"] == "appeal_ombudsman@v1"
    assert appeal["forum"] == "ombudsman"


async def test_drafting_with_the_same_idempotency_key_returns_the_same_version(
    api: httpx.AsyncClient,
) -> None:
    claim_id = await _audited(api, "case_b")
    url = f"/api/v1/claims/{claim_id}/appeals"
    first = await api.post(url, json=GRO, headers={"Idempotency-Key": "draft-1"})
    again = await api.post(url, json=GRO, headers={"Idempotency-Key": "draft-1"})
    assert first.status_code == again.status_code == 201
    assert again.json()["version"] == first.json()["version"] == 1
    assert len((await api.get(url)).json()) == 1


async def test_edits_are_guarded_and_create_new_versions(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_b")
    await _draft(api, claim_id)
    base = f"/api/v1/claims/{claim_id}/appeals"

    stray = await api.put(f"{base}/1", json={"facts": "The insurer paid only ₹1,38,375."})
    assert stray.status_code == 422
    problem = stray.json()
    assert problem["type"].endswith("/appeal-guardrail")
    assert "stray_amount in facts" in problem["detail"]
    invented = await api.put(
        f"{base}/1",
        json={"arguments": [{"flag_id": "SUBSUMED_ITEM", "argument": "See circular no. 12."}]},
    )
    assert invented.status_code == 422
    assert "unknown_regulation" in invented.json()["detail"]
    unknown = await api.put(f"{base}/1", json={"arguments": [{"flag_id": "NOPE", "argument": "x"}]})
    assert unknown.status_code == 422

    facts = "The patient was admitted for cataract surgery; the insurer paid {{letter.approved}}."
    edited = await api.put(f"{base}/1", json={"facts": facts})
    assert edited.status_code == 201, edited.text
    v2 = edited.json()
    assert (v2["version"], v2["based_on"], v2["prompt_ref"]) == (2, 1, None)
    assert v2["content"]["facts"]["text"].endswith("the insurer paid ₹1,38,375.")
    assert v2["content"]["subject"] == (await api.get(f"{base}/1")).json()["content"]["subject"]

    stale = await api.put(f"{base}/1", json={"facts": "Older."})
    assert stale.status_code == 409
    assert "latest version (v2)" in stale.json()["detail"]
    assert [a["version"] for a in (await api.get(base)).json()] == [1, 2]


async def test_review_sign_and_revise(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_b")
    await _draft(api, claim_id)
    base = f"/api/v1/claims/{claim_id}/appeals"
    signer = {"reviewer_name": "R. Mehta", "reviewer_role": "TPA desk manager", "declaration": True}

    early = await api.post(f"{base}/1/sign", json=signer)
    assert early.status_code == 409
    no_declaration = await api.post(f"{base}/1/sign", json=signer | {"declaration": False})
    assert no_declaration.status_code == 422

    submitted = await api.post(f"{base}/1/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "in_review"
    assert (await api.post(f"{base}/1/submit")).status_code == 409
    assert (await api.get(f"/api/v1/claims/{claim_id}")).json()["status"] == "in_review"

    signed = (await api.post(f"{base}/1/sign", json=signer)).json()
    assert signed["status"] == "signed"
    signature = signed["signature"]
    assert re.fullmatch(r"[0-9a-f]{64}", signature["content_sha256"])
    assert (signature["reviewer_name"], signature["reviewer_role"]) == (
        "R. Mehta",
        "TPA desk manager",
    )
    claim = (await api.get(f"/api/v1/claims/{claim_id}")).json()
    assert claim["status"] == "signed"
    assert claim["appeals"][0]["content_sha256"] == signature["content_sha256"]

    # An edit after signing is a new, unsigned draft; the signed version stays as it was.
    revised = await api.put(f"{base}/1", json={"subject": "Request to review the deductions"})
    assert revised.status_code == 201
    assert revised.json()["status"] == "draft"
    assert revised.json()["signature"] is None
    assert (await api.get(f"{base}/1")).json()["status"] == "signed"
    assert (await api.get(f"/api/v1/claims/{claim_id}")).json()["status"] == "appeal_drafted"

    log = (await api.get(f"/api/v1/claims/{claim_id}/audit-log")).json()
    actions = [
        (e["action"], e["detail"].get("version")) for e in log if e["action"].startswith("appeal.")
    ]
    assert actions == [
        ("appeal.drafted", 1),
        ("appeal.submitted", 1),
        ("appeal.signed", 1),
        ("appeal.edited", 2),
    ]
    signed_entry = next(e for e in log if e["action"] == "appeal.signed")
    assert signed_entry["detail"]["sha256"] == signature["content_sha256"]


async def test_redrafting_during_review_sends_the_claim_back_to_drafting(
    api: httpx.AsyncClient,
) -> None:
    claim_id = await _audited(api, "case_b")
    await _draft(api, claim_id)
    await api.post(f"/api/v1/claims/{claim_id}/appeals/1/submit")
    redraft = await _draft(api, claim_id, {"forum": "bima_bharosa"})
    assert redraft["version"] == 2
    assert redraft["prompt_ref"] == "appeal_bima_bharosa@v1"
    assert (await api.get(f"/api/v1/claims/{claim_id}")).json()["status"] == "appeal_drafted"


class _AppealAnswer:
    """Stub reasoning, except the appeal: a fixed answer (or an outage)."""

    def __init__(self, appeal: dict[str, Any] | None) -> None:
        self._appeal = appeal
        self._stubs = StubReasoner()

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        if request.schema is not AppealDraftOutput:
            return await self._stubs.generate_structured(request)
        if self._appeal is None:
            raise LlmUnavailableError("replay-miss")
        result = await self._stubs.generate_structured(request)
        output = request.schema.model_validate(result.output.model_dump() | self._appeal)
        return LlmResult(output=output, call=result.call)


def _llm(appeal: dict[str, Any] | None) -> LlmClient:
    return FakeLlmClient(FixtureLlmClient(DEMO_CASES), _AppealAnswer(appeal))


async def test_a_draft_that_fails_its_checks_must_be_fixed_before_review(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    _, client = _api(fake_settings, client_for, _llm({"facts": "The insurer paid Rs. 1,38,375."}))
    async with client as api:
        claim_id = await _audited(api, "case_b")
        appeal = await _draft(api, claim_id)
        assert appeal["drafting"] == "needs_review"
        assert appeal["violations"] == ["stray_amount in facts"]
        base = f"/api/v1/claims/{claim_id}/appeals"
        blocked = await api.post(f"{base}/1/submit")
        assert blocked.status_code == 409
        assert "did not pass its checks" in blocked.json()["detail"]

        fixed = await api.put(f"{base}/1", json={"facts": "The insurer paid {{letter.approved}}."})
        assert fixed.json()["drafting"] == "passed"
        assert (await api.post(f"{base}/2/submit")).status_code == 200


async def test_an_unavailable_drafter_leaves_a_skeleton_for_a_person_to_write(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    _, client = _api(fake_settings, client_for, _llm(None))
    async with client as api:
        claim_id = await _audited(api, "case_c")
        appeal = await _draft(api, claim_id)
        assert appeal["drafting"] == "unavailable"
        (item,) = appeal["content"]["items"]
        assert item["argument"]["template"] == ""
        assert item["amount"] == 31_000_000
        blocked = await api.post(f"/api/v1/claims/{claim_id}/appeals/1/submit")
        assert blocked.status_code == 409


async def test_appeals_are_scoped_to_the_hospital(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    services, client = _api(fake_settings, client_for, None)
    async with client as api:
        claim_id = await _audited(api, "case_b")
        await _draft(api, claim_id)
        missing = await api.get(f"/api/v1/claims/{claim_id}/appeals/9")
        assert missing.status_code == 404
        assert missing.json()["type"].endswith("/appeal-not-found")
    other = Principal(
        user_id="u2", display_name="Other desk", hospital_id="another-hospital", role="reviewer"
    )
    with pytest.raises(ClaimNotFoundError):
        await services.appeals.get(other, claim_id, 1)
    with pytest.raises(ClaimNotFoundError):
        await services.appeals.versions(other, claim_id)
