"""Upload → streamed audit → persisted claim, for demo cases A, B and C, with no model costs.

The LLM is ``fake`` mode: the ideal transcription of each demo document and deterministic stubs
for the reasoning agents, so these tests check everything Arzi does around the model: redaction,
reconciliation, the ADK workflow and its guardrails, the rules engine, persistence and the
event stream.
"""

import json
import sys
from collections.abc import AsyncIterator, Callable

import anyio
import httpx
import pytest
from fastapi import FastAPI

from arzi.adapters.memory import InMemoryClaimRepository
from arzi.bootstrap import Services, build_services
from arzi.config import LlmMode, Settings
from arzi.domain.enums import ReasoningStatus
from arzi.domain.models import ClaimRecord
from arzi.main import create_app
from tests.integration.pipeline_support import (
    CASE_DOCUMENTS,
    parse_sse,
    prepare_case,
    run_to_end,
    upload,
)
from tests.unit.rules.helpers import DEMO_CASES

sys.path.insert(0, str(DEMO_CASES.parent / "scripts"))
from gen_demo_cases import expected

STAGES = ("extract", "redact", "reconcile", "interpret_policy", "audit", "explain_flags")


@pytest.fixture
def fake_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"llm_mode": LlmMode.FAKE, "replay_dir": DEMO_CASES})


@pytest.fixture
def services(fake_settings: Settings) -> Services:
    return build_services(fake_settings)


@pytest.fixture
async def api(
    fake_settings: Settings,
    services: Services,
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(fake_settings, readiness_probes=[], services=services)
    async with client_for(app) as client:
        yield client


async def _claim(api: httpx.AsyncClient, claim_id: str) -> ClaimRecord:
    response = await api.get(f"/api/v1/claims/{claim_id}")
    assert response.status_code == 200, response.text
    return ClaimRecord.model_validate(response.json())


@pytest.mark.parametrize("case", ["case_a", "case_b", "case_c"])
async def test_case_audits_to_expected_values(
    case: str, api: httpx.AsyncClient, services: Services
) -> None:
    claim_id = await prepare_case(api, case)
    run_id, events = await run_to_end(api, claim_id)

    kinds = [e.event for e in events]
    stages = [(e.event, e.data.get("stage")) for e in events if e.event.startswith("stage.")]
    assert stages == [
        (kind, stage) for stage in STAGES for kind in ("stage.started", "stage.completed")
    ]
    assert kinds[-1] == "run.completed"
    # Flags are announced as soon as the engine has run, before the explanations are written.
    audit_done = kinds.index("stage.completed", 2 * STAGES.index("audit"))
    assert kinds[audit_done + 1 : audit_done + 1 + kinds.count("flag.created")] == [
        "flag.created"
    ] * kinds.count("flag.created")
    assert [e.id for e in events] == list(range(1, len(events) + 1))

    record = await _claim(api, claim_id)
    assert record.status == "audited"
    assert record.audit is not None
    committed = json.loads((DEMO_CASES / case / "expected.json").read_text(encoding="utf-8"))
    assert expected(record.audit) == committed
    assert kinds.count("flag.created") == len(committed["flags"])

    # Nothing that identifies the patient reaches the facts the engine and agents reason over.
    identifiers = json.loads((DEMO_CASES / case / "identifiers.json").read_text(encoding="utf-8"))
    facts_json = record.facts.model_dump_json() if record.facts else ""
    leaked = [kind for kind, value in identifiers.items() if value.lower() in facts_json.lower()]
    assert not leaked
    assert record.facts is not None
    assert record.facts.patient.redacted_id.startswith("P-")
    assert record.redaction is not None
    assert record.redaction.total > 0
    repo = services.repo
    assert isinstance(repo, InMemoryClaimRepository)
    vault = repo.vaults[(record.hospital_id, claim_id)]
    assert set(identifiers.values()) <= set(vault.values())

    run = (await api.get(f"/api/v1/claims/{claim_id}/runs/{run_id}")).json()
    assert run["status"] == "completed"
    assert {
        "classify_document@v1",
        "extract_bill@v1",
        "extract_policy@v2",
        "interpret_policy@v1",
        "explain_flags@v1",
    } <= set(run["prompt_versions"])

    # The reasoning agents ran under their guardrails: one explanation per flag, amounts rendered
    # from the engine, and every clause the policy reading cites is in the policy.
    assert record.narratives is not None
    assert record.narratives.status is ReasoningStatus.PASSED
    assert [n.flag_id for n in record.narratives.items] == [f.flag_id for f in record.audit.flags]
    assert all(
        n.explanation.text and "{{" not in n.explanation.text for n in record.narratives.items
    )
    assert record.policy_review is not None
    assert record.policy_review.status is ReasoningStatus.PASSED
    assert record.policy_review.terms


async def test_documents_with_a_chosen_type_skip_classification(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_c", documents=())
    for name in CASE_DOCUMENTS["case_c"]:
        path = DEMO_CASES / "case_c" / name
        doc_type = "insurer_letter" if "letter" in name else None
        files = {"file": (path.name, await anyio.Path(path).read_bytes(), "application/pdf")}
        data = {"document_type": doc_type} if doc_type else {}
        response = await api.post(f"/api/v1/claims/{claim_id}/documents", files=files, data=data)
        assert response.status_code == 201
    _, events = await run_to_end(api, claim_id)
    assert events[-1].event == "run.completed"
    extract = next(
        e for e in events if e.event == "stage.completed" and e.data["stage"] == "extract"
    )
    # 7 documents: the typed letter skips classification, so 6 classify + 5 extract calls.
    assert extract.data["data"]["model_calls"] == 11


async def test_events_resume_after_last_event_id(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    run_id, events = await run_to_end(api, claim_id)
    resumed = await api.get(
        f"/api/v1/claims/{claim_id}/runs/{run_id}/events", headers={"Last-Event-ID": "5"}
    )
    replayed = parse_sse(resumed.text)
    assert [e.id for e in replayed] == [e.id for e in events if e.id and e.id > 5]


async def test_idempotency_key_returns_the_same_run(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    first, _ = await run_to_end(api, claim_id, key="key-123")
    again = await api.post(
        f"/api/v1/claims/{claim_id}/runs", headers={"Idempotency-Key": "key-123"}
    )
    assert again.status_code == 202
    assert again.json()["run_id"] == first


async def test_audit_needs_consent_first(api: httpx.AsyncClient) -> None:
    created = await api.post("/api/v1/claims", json={"mode": "pre_submission"})
    claim_id = created.json()["claim_id"]
    await upload(api, claim_id, DEMO_CASES / "case_a" / "itemised_bill.pdf")
    response = await api.post(f"/api/v1/claims/{claim_id}/runs")
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("/consent-required")


async def test_audit_needs_documents(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a", documents=())
    response = await api.post(f"/api/v1/claims/{claim_id}/runs")
    assert response.status_code == 409
    assert response.json()["type"].endswith("/invalid-state")


async def test_a_failed_run_is_reported_and_retryable(api: httpx.AsyncClient) -> None:
    # A post-deduction claim without the insurer's letter cannot be reconciled.
    claim_id = await prepare_case(api, "case_b", documents=CASE_DOCUMENTS["case_b"][:-1])
    _, events = await run_to_end(api, claim_id)
    assert events[-1].event == "run.failed"
    assert events[-1].data["data"]["error"] == "facts-incomplete"
    assert (await _claim(api, claim_id)).status == "failed"

    letter = await upload(api, claim_id, DEMO_CASES / "case_b" / "insurer_deduction_letter.pdf")
    assert letter.status_code == 201
    _, events = await run_to_end(api, claim_id)
    assert events[-1].event == "run.completed"


async def test_unknown_documents_fail_the_run_with_a_slug(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a", documents=())
    blank = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj "
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 10 10]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF"
    )
    response = await api.post(
        f"/api/v1/claims/{claim_id}/documents",
        files={"file": ("blank.pdf", blank, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    _, events = await run_to_end(api, claim_id)
    assert events[-1].data["data"]["error"] == "fixture-miss"


async def test_another_hospital_cannot_see_the_claim(
    fake_settings: Settings,
    services: Services,
    api: httpx.AsyncClient,
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    claim_id = await prepare_case(api, "case_a", documents=())
    from arzi.adapters.auth import DemoAuthVerifier
    from arzi.services.ports import Principal

    other = Principal(
        user_id="u2", display_name="Other", hospital_id="other-hospital", role="admin"
    )
    intruder_services = Services(**{**services.__dict__, "auth": DemoAuthVerifier(other)})
    app = create_app(fake_settings, readiness_probes=[], services=intruder_services)
    async with client_for(app) as intruder:
        for path in (
            f"/api/v1/claims/{claim_id}",
            f"/api/v1/claims/{claim_id}/documents",
            f"/api/v1/claims/{claim_id}/audit-log",
        ):
            response = await intruder.get(path)
            assert response.status_code == 404, path
            assert response.json()["type"].endswith("/claim-not-found")
        listed = await intruder.get("/api/v1/claims")
        assert listed.json()["items"] == []


@pytest.mark.parametrize("case", ["case_a", "case_b", "case_c"])
async def test_recorded_gemini_responses_replay_to_expected_values(
    case: str, settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    """The committed llm_cache recordings (real Gemini output) still audit to expected.json."""
    replay = settings.model_copy(update={"llm_mode": LlmMode.REPLAY, "replay_dir": DEMO_CASES})
    app = create_app(replay, readiness_probes=[], services=build_services(replay))
    async with client_for(app) as client:
        claim_id = await prepare_case(client, case)
        _, events = await run_to_end(client, claim_id)
        assert events[-1].event == "run.completed", events[-1].data
        record = await _claim(client, claim_id)
    assert record.audit is not None
    committed = json.loads((DEMO_CASES / case / "expected.json").read_text(encoding="utf-8"))
    assert expected(record.audit) == committed
