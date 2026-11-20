"""Family links and the free public check, over the API (fake mode: stub agents, silent audio)."""

import datetime as dt
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from arzi.agents.family_explainer import HUMAN_REVIEW
from arzi.bootstrap import Services, build_services
from arzi.config import LlmMode, Settings
from arzi.main import create_app
from tests.integration.pipeline_support import parse_sse, prepare_case, run_to_end
from tests.unit.rules.helpers import DEMO_CASES

T0 = dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> dt.datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fake_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "llm_mode": LlmMode.FAKE,
            "replay_dir": DEMO_CASES,
            "public_checks_per_ip_per_day": 3,
        }
    )


@pytest.fixture
def services(fake_settings: Settings, clock: Clock) -> Services:
    return build_services(fake_settings, clock=clock)


@pytest.fixture
async def api(
    fake_settings: Settings, services: Services, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(create_app(fake_settings, readiness_probes=[], services=services)) as c:
        yield c


async def _audited(api: httpx.AsyncClient, case: str) -> str:
    claim_id = await prepare_case(api, case)
    _, events = await run_to_end(api, claim_id)
    assert events[-1].event == "run.completed"
    return claim_id


def _identifiers(case: str) -> list[str]:
    values = json.loads((DEMO_CASES / case / "identifiers.json").read_text(encoding="utf-8"))
    return [v for v in values.values() if len(v) > 4]


async def test_family_explanation_is_written_in_three_languages_and_narrated(
    api: httpx.AsyncClient,
) -> None:
    claim_id = await _audited(api, "case_c")
    pack = (await api.post(f"/api/v1/claims/{claim_id}/family")).json()
    langs = [e["lang"] for e in pack["explanations"]]
    assert langs == ["gu", "hi", "en"]
    assert all(e["status"] == "passed" for e in pack["explanations"])
    for e in pack["explanations"]:
        assert e["reassurance"]["text"].endswith(HUMAN_REVIEW[e["lang"]])
        assert "{{" not in json.dumps([p["text"] for p in e["what_happened"]])
    assert [a["lang"] for a in pack["audio"]] == ["gu", "hi", "en"]
    # Cached: a second call writes nothing new.
    again = (await api.post(f"/api/v1/claims/{claim_id}/family")).json()
    assert again["generated_at"] == pack["generated_at"]


async def test_share_link_opens_a_redacted_family_view(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_c")
    created = await api.post(f"/api/v1/claims/{claim_id}/shares")
    assert created.status_code == 201
    path = created.json()["url_path"]
    token = path.removeprefix("/f/")
    assert len(token) >= 40
    assert created.json()["share"]["token_sha256"] != token

    response = await api.get(f"/api/v1/family/{token}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    view = response.json()
    assert view["purpose"] == "family"
    assert view["hospital_name"] == "Sanjeevani Multispeciality Hospital"
    assert view["desk_contact"]
    assert view["procedure"] == "Right total knee replacement"
    assert {f["key"]: f["amount"] for f in view["figures"]}["recoverable"] == 31_000_000
    assert [e["lang"] for e in view["explanations"]] == ["gu", "hi", "en"]
    assert view["can_draft_appeal"] is False  # the desk appeals for a hospital claim
    leaked = [v for v in _identifiers("case_c") if v.lower() in response.text.lower()]
    assert not leaked

    audio = await api.get(view["audio"][0]["url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content.startswith(b"RIFF")
    missing = await api.get(f"/api/v1/family/{token}/audio/xx")
    assert missing.status_code == 422


async def test_links_expire_and_can_be_withdrawn(api: httpx.AsyncClient, clock: Clock) -> None:
    claim_id = await _audited(api, "case_b")
    first = (await api.post(f"/api/v1/claims/{claim_id}/shares")).json()
    second = (await api.post(f"/api/v1/claims/{claim_id}/shares")).json()
    listed = (await api.get(f"/api/v1/claims/{claim_id}/shares")).json()
    assert len(listed) == 2
    assert "url_path" not in json.dumps(listed)

    sha = first["share"]["token_sha256"]
    revoked = await api.post(f"/api/v1/claims/{claim_id}/shares/{sha}/revoke")
    assert revoked.json()["revoked_at"] is not None
    gone = await api.get(f"/api/v1/family/{first['url_path'].removeprefix('/f/')}")
    assert gone.status_code == 404
    assert gone.json()["type"].endswith("/share-link-invalid")
    assert (await api.get("/api/v1/family/not-a-real-token")).status_code == 404

    token = second["url_path"].removeprefix("/f/")
    assert (await api.get(f"/api/v1/family/{token}")).status_code == 200
    clock.now = T0 + dt.timedelta(days=7, seconds=1)
    assert (await api.get(f"/api/v1/family/{token}")).status_code == 404

    log = (await api.get(f"/api/v1/claims/{claim_id}/audit-log")).json()
    actions = [e["action"] for e in log if e["action"].startswith("family.")]
    assert actions == ["family.prepared", "family.shared", "family.shared", "family.link_revoked"]
    assert (
        await api.post(f"/api/v1/claims/{claim_id}/shares/{'0' * 64}/revoke")
    ).status_code == 404


async def test_an_unaudited_claim_cannot_be_shared(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    assert (await api.post(f"/api/v1/claims/{claim_id}/shares")).status_code == 409


def _check_files(
    case: str, *, letter: str, with_bill: bool = True
) -> list[tuple[str, tuple[str, bytes, str]]]:
    folder = DEMO_CASES / case
    pdf = "application/pdf"

    def part(field: str, name: str) -> tuple[str, tuple[str, bytes, str]]:
        return field, (name, Path(folder / name).read_bytes(), pdf)

    files = [
        part("letter", letter),
        part("policy", "policy_schedule.pdf"),
        part("policy", "policy_wording_excerpt.pdf"),
        part("discharge", "discharge_summary.pdf"),
    ]
    if with_bill:
        files.append(part("bill", "itemised_bill.pdf"))
    return files


async def test_public_check_runs_end_to_end_and_the_family_signs_the_appeal(
    api: httpx.AsyncClient, services: Services
) -> None:
    response = await api.post(
        "/api/v1/check",
        data={"mode": "post_rejection", "consent": "true", "given_by": "policyholder"},
        files=_check_files("case_c", letter="insurer_rejection_letter.pdf"),
    )
    assert response.status_code == 202, response.text
    started = response.json()
    token = started["url_path"].removeprefix("/f/")
    await services.runs.wait(started["run_id"])

    events = parse_sse((await api.get(f"/api/v1/family/{token}/events")).text)
    assert events[-1].event == "run.completed"
    view = (await api.post(f"/api/v1/family/{token}/prepare")).json()
    assert view["purpose"] == "public_check"
    assert view["desk_contact"] == ""
    assert [e["lang"] for e in view["explanations"]] == ["gu", "hi", "en"]
    assert view["can_draft_appeal"] is True

    drafted = await api.post(f"/api/v1/family/{token}/appeal")
    assert drafted.status_code == 201
    assert drafted.json()["content"]["relief_amount"] == 31_000_000
    assert (await api.get(f"/api/v1/family/{token}/appeal.pdf")).status_code == 409
    unsigned = await api.post(
        f"/api/v1/family/{token}/appeal/sign", json={"name": "A", "declaration": True}
    )
    assert unsigned.status_code == 422
    signed = await api.post(
        f"/api/v1/family/{token}/appeal/sign", json={"name": "Bhanuben's son", "declaration": True}
    )
    assert signed.status_code == 200
    assert signed.json()["signature"]["reviewer_role"] == "Policyholder or family member"
    pdf = await api.get(f"/api/v1/family/{token}/appeal.pdf")
    assert pdf.content.startswith(b"%PDF-")
    after = (await api.get(f"/api/v1/family/{token}")).json()
    assert after["appeal"]["status"] == "exported"
    assert after["can_draft_appeal"] is False

    # The public tenant is separate from the hospital's desk.
    desk = (await api.get("/api/v1/claims")).json()["items"]
    assert all(c["mode"] != "post_rejection" for c in desk)


async def test_family_links_cannot_draft_public_appeals(api: httpx.AsyncClient) -> None:
    claim_id = await _audited(api, "case_c")
    token = (await api.post(f"/api/v1/claims/{claim_id}/shares")).json()["url_path"][3:]
    assert (await api.post(f"/api/v1/family/{token}/appeal")).status_code == 404


async def test_public_check_validates_its_input_and_is_rate_limited(api: httpx.AsyncClient) -> None:
    base = {"mode": "post_rejection", "consent": "true"}
    no_bill = await api.post(
        "/api/v1/check",
        data=base,
        files=_check_files("case_c", letter="insurer_rejection_letter.pdf", with_bill=False),
    )
    assert no_bill.status_code == 422
    no_consent = await api.post(
        "/api/v1/check",
        data=base | {"consent": "false"},
        files=_check_files("case_c", letter="insurer_rejection_letter.pdf"),
    )
    assert no_consent.status_code == 422
    assert "Consent" in no_consent.json()["detail"]
    wrong_mode = await api.post(
        "/api/v1/check",
        data=base | {"mode": "pre_submission"},
        files=_check_files("case_c", letter="insurer_rejection_letter.pdf"),
    )
    assert wrong_mode.status_code == 422

    statuses = []
    for _ in range(4):
        r = await api.post(
            "/api/v1/check",
            data=base,
            files=_check_files("case_c", letter="insurer_rejection_letter.pdf"),
        )
        statuses.append(r.status_code)
    assert statuses == [202, 202, 202, 429]
    assert r.json()["type"].endswith("/rate-limited")


async def test_recorded_family_explanations_and_narration_replay_offline(
    settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    """The committed recordings cover the family page of case C in all three languages."""
    replay = settings.model_copy(update={"llm_mode": LlmMode.REPLAY, "replay_dir": DEMO_CASES})
    async with client_for(create_app(replay, readiness_probes=[])) as api:
        claim_id = await _audited(api, "case_c")
        token = (await api.post(f"/api/v1/claims/{claim_id}/shares")).json()["url_path"][3:]
        view = (await api.get(f"/api/v1/family/{token}")).json()
        audio = await api.get(f"/api/v1/family/{token}/audio/gu")
    assert [e["lang"] for e in view["explanations"]] == ["gu", "hi", "en"]
    assert all(e["status"] in {"passed", "retried"} for e in view["explanations"])
    gujarati = view["explanations"][0]
    assert any("઀" <= ch <= "૿" for ch in gujarati["headline"]["text"])
    assert gujarati["reassurance"]["text"].endswith(HUMAN_REVIEW["gu"])
    assert audio.headers["content-type"] == "audio/mpeg"
    assert len(audio.content) > 50_000


async def test_a_free_check_ends_with_the_family_signing_note(
    api: httpx.AsyncClient, services: Services
) -> None:
    from arzi.agents.family_explainer import SELF_REVIEW

    response = await api.post(
        "/api/v1/check",
        data={"mode": "post_rejection", "consent": "true"},
        files=_check_files("case_c", letter="insurer_rejection_letter.pdf"),
    )
    started = response.json()
    await services.runs.wait(started["run_id"])
    view = (await api.post(f"/api/v1/family/{started['url_path'][3:]}/prepare")).json()
    for e in view["explanations"]:
        assert e["reassurance"]["text"].endswith(SELF_REVIEW[e["lang"]])
        assert HUMAN_REVIEW[e["lang"]] not in e["reassurance"]["text"]
