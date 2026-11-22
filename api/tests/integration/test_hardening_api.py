"""Phase 7 hardening over the API: tenant isolation on every claim route, roles, DPDP export and
erasure, retention, security headers, request limits and active-content PDF uploads.
"""

import datetime as dt
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from arzi.adapters.auth import DEMO_PRINCIPAL, DemoAuthVerifier
from arzi.bootstrap import Services, build_services
from arzi.config import LlmMode, Settings
from arzi.main import create_app
from arzi.services.ports import Principal
from tests.integration.pipeline_support import prepare_case, run_to_end
from tests.unit.rules.helpers import DEMO_CASES

OTHER_ADMIN = Principal(
    user_id="intruder", display_name="Other hospital", hospital_id="another-hospital", role="admin"
)
ADMIN = DEMO_PRINCIPAL.model_copy(update={"user_id": "admin-01", "role": "admin"})
DESK = DEMO_PRINCIPAL.model_copy(update={"user_id": "desk-01", "role": "billing_executive"})
SIGNER = {"reviewer_name": "Riya Mehta", "reviewer_role": "TPA desk manager", "declaration": True}

# A valid body for every claim route that takes one, so validation never answers before the
# tenant check does. A new route without an entry here fails the sweep with a 422.
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/consent"): {"json": {"given_by": "patient"}},
    ("PATCH", "/lines/{line_id}"): {"json": {}},
    ("POST", "/flags/{flag_id}/review"): {"json": {"decision": "accepted"}},
    ("POST", "/appeals"): {"json": {"forum": "insurer_gro"}},
    ("PUT", "/appeals/{version}"): {"json": {"subject": "Request to review the deduction"}},
    ("POST", "/appeals/{version}/sign"): {"json": SIGNER},
    ("POST", "/documents"): {"files": {"file": ("x.pdf", b"%PDF-1.4\n", "application/pdf")}},
}


@pytest.fixture
def fake_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"llm_mode": LlmMode.FAKE, "replay_dir": DEMO_CASES})


@pytest.fixture
async def wired(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[tuple[Services, httpx.AsyncClient]]:
    services = build_services(fake_settings)
    app = create_app(fake_settings, readiness_probes=[], services=services)
    async with client_for(app) as client:
        yield services, client


async def _appealed_claim(api: httpx.AsyncClient) -> dict[str, str]:
    """Case B audited, its appeal drafted and signed, and a family link created."""
    claim_id = await prepare_case(api, "case_b")
    run_id, _ = await run_to_end(api, claim_id)
    record = (await api.get(f"/api/v1/claims/{claim_id}")).json()
    base = f"/api/v1/claims/{claim_id}/appeals"
    await api.post(base, json={"forum": "insurer_gro"})
    await api.post(f"{base}/1/submit")
    signed = await api.post(f"{base}/1/sign", json=SIGNER)
    assert signed.status_code == 200, signed.text
    await api.post(f"/api/v1/claims/{claim_id}/shares")
    share = (await api.get(f"/api/v1/claims/{claim_id}/shares")).json()[0]
    document = (await api.get(f"/api/v1/claims/{claim_id}/documents")).json()[0]
    return {
        "claim_id": claim_id,
        "run_id": run_id,
        "version": "1",
        "document_id": document["document_id"],
        "flag_id": record["audit"]["flags"][0]["flag_id"],
        "line_id": str(record["audit"]["lines"][0]["line_id"]),
        "token_sha256": share["token_sha256"],
    }


async def test_another_hospital_gets_404_on_every_claim_route(
    wired: tuple[Services, httpx.AsyncClient],
) -> None:
    services, api = wired
    ids = await _appealed_claim(api)
    services.auth = DemoAuthVerifier(OTHER_ADMIN)
    spec = (await api.get("/openapi.json")).json()
    swept = 0
    for template, operations in spec["paths"].items():
        if "{claim_id}" not in template:
            continue
        suffix = template.split("{claim_id}", 1)[1]
        path = re.sub(r"\{(\w+)\}", lambda m: ids[m.group(1)], template)
        for method in operations:
            response = await api.request(
                method.upper(), path, **BODIES.get((method.upper(), suffix), {})
            )
            assert response.status_code == 404, f"{method.upper()} {template}: {response.text}"
            swept += 1
    assert swept >= 27  # every claim route in the contract, including privacy ones

    services.auth = DemoAuthVerifier()
    still_there = await api.get(f"/api/v1/claims/{ids['claim_id']}")
    assert still_there.status_code == 200  # the intruder changed nothing


async def test_export_holds_the_whole_record_but_no_raw_identifiers(
    wired: tuple[Services, httpx.AsyncClient],
) -> None:
    services, api = wired
    ids = await _appealed_claim(api)
    vault = await services.repo.get_identity_vault(DEMO_PRINCIPAL.hospital_id, ids["claim_id"])
    assert vault  # redaction stored raw values in the restricted vault

    export = (await api.get(f"/api/v1/claims/{ids['claim_id']}/export")).json()
    assert export["claim"]["claim_id"] == ids["claim_id"]
    assert len(export["documents"]) == 7
    assert "uri" not in export["documents"][0]
    assert export["appeals"][0]["status"] == "signed"
    assert export["runs"][0]["run_id"] == ids["run_id"]
    assert export["family_links"] == 1
    assert export["identifiers_held"] == sorted(vault)
    text = str(export)
    assert not any(raw in text for raw in vault.values())
    log = (await api.get(f"/api/v1/claims/{ids['claim_id']}/audit-log")).json()
    assert log[-1]["action"] == "claim.exported"


async def test_only_an_admin_can_erase_and_erasure_is_total(
    wired: tuple[Services, httpx.AsyncClient],
) -> None:
    services, api = wired
    ids = await _appealed_claim(api)
    claim_url = f"/api/v1/claims/{ids['claim_id']}"

    for principal in (DESK, DEMO_PRINCIPAL):  # billing executive, reviewer
        services.auth = DemoAuthVerifier(principal)
        denied = await api.delete(claim_url)
        assert denied.status_code == 403
        assert denied.json()["type"].endswith("/role-forbidden")

    services.auth = DemoAuthVerifier(ADMIN)
    erased = await api.delete(claim_url)
    assert erased.status_code == 200
    assert erased.json()["objects_deleted"] >= 7  # uploads plus narrated audio
    assert (await api.get(claim_url)).status_code == 404
    assert await services.repo.get_share(ids["token_sha256"]) is None
    assert await services.repo.get_identity_vault(ADMIN.hospital_id, ids["claim_id"]) == {}
    assert (await api.delete(claim_url)).status_code == 404


async def test_retention_sweep_erases_only_stale_claims(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    now = [dt.datetime(2026, 10, 1, 9, tzinfo=dt.UTC)]
    services = build_services(fake_settings, clock=lambda: now[0])
    app = create_app(fake_settings, readiness_probes=[], services=services)
    async with client_for(app) as api:
        old = (await api.post("/api/v1/claims", json={"mode": "pre_submission"})).json()
        now[0] += dt.timedelta(days=40)
        fresh = (await api.post("/api/v1/claims", json={"mode": "pre_submission"})).json()

        assert (await api.post("/api/v1/admin/retention")).status_code == 403
        services.auth = DemoAuthVerifier(ADMIN)
        swept = (await api.post("/api/v1/admin/retention")).json()  # default 30 days
        assert swept["erased"] == [old["claim_id"]]
        assert (await api.get(f"/api/v1/claims/{fresh['claim_id']}")).status_code == 200
        custom = await api.post("/api/v1/admin/retention", json={"older_than_days": 1})
        assert custom.json()["erased"] == []  # the fresh claim was updated just now


async def test_responses_carry_security_headers_and_no_cors(
    wired: tuple[Services, httpx.AsyncClient],
) -> None:
    _, api = wired
    for response in (
        await api.get("/api/v1/claims"),
        await api.get("/api/v1/claims/ARZ-NOPE"),  # problem responses too
        await api.get("/health"),
    ):
        csp = response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp
        assert "default-src 'self'" in csp
        assert response.headers["strict-transport-security"].startswith("max-age=")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-frame-options"] == "DENY"
    preflight = await api.options(
        "/api/v1/claims",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in preflight.headers


async def test_status_reports_build_ai_and_budget(
    wired: tuple[Services, httpx.AsyncClient],
) -> None:
    _, api = wired
    status = (await api.get("/api/v1/meta/status")).json()
    assert status["llm_mode"] == "fake"
    assert status["daily_budget_inr"] == 150
    assert status["budget_used_fraction"] == 0
    assert "appeal_insurer_gro@v1" in status["prompt_versions"]


async def test_oversized_requests_and_floods_are_refused(
    fake_settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    tight = fake_settings.model_copy(
        update={"max_request_mb": 1, "rate_limit_burst": 3, "rate_limit_per_minute": 1}
    )
    app = create_app(tight, readiness_probes=[], services=build_services(tight))
    async with client_for(app) as api:
        big = await api.post("/api/v1/claims", content=b"x" * (1024 * 1024 + 1))
        assert big.status_code == 413
        assert big.json()["type"].endswith("/request-too-large")
        statuses = [(await api.get("/api/v1/claims")).status_code for _ in range(3)]
        assert statuses == [200, 200, 200]  # a refused oversized body costs no token
        limited = await api.get("/api/v1/claims")
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1
        assert "x-request-id" in limited.headers
        assert (await api.get("/health")).status_code == 200  # probes are never limited


async def test_pdfs_with_active_content_are_refused(
    wired: tuple[Services, httpx.AsyncClient],
) -> None:
    _, api = wired
    claim_id = (await api.post("/api/v1/claims", json={"mode": "pre_submission"})).json()[
        "claim_id"
    ]
    clean = (DEMO_CASES / "case_a" / "policy_schedule.pdf").read_bytes()
    for payload in (b"/JavaScript (app.alert(1))", b"/Launch << /F (cmd.exe) >>", b"/JS(x)"):
        armed = clean.replace(b"%%EOF", b"1 0 obj << " + payload + b" >> endobj\n%%EOF")
        refused = await api.post(
            f"/api/v1/claims/{claim_id}/documents",
            files={"file": ("armed.pdf", armed, "application/pdf")},
        )
        assert refused.status_code == 422, refused.text
        assert "scripts" in refused.json()["detail"]
    accepted = await api.post(
        f"/api/v1/claims/{claim_id}/documents",
        files={"file": ("policy_schedule.pdf", clean, "application/pdf")},
    )
    assert accepted.status_code == 201
