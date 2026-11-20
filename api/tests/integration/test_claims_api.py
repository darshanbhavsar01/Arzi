"""Claim endpoints: create, worklist, uploads, documents, consent, corrections, audit log."""

import io
from collections.abc import AsyncIterator, Callable

import anyio
import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from arzi.bootstrap import Services, build_services
from arzi.config import LlmMode, Settings
from arzi.main import create_app
from tests.integration.pipeline_support import create_claim, prepare_case, run_to_end, upload
from tests.unit.rules.helpers import DEMO_CASES

BILL = DEMO_CASES / "case_a" / "itemised_bill.pdf"


@pytest.fixture
async def api(
    settings: Settings, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    fake = settings.model_copy(
        update={
            "llm_mode": LlmMode.FAKE,
            "replay_dir": DEMO_CASES,
            "max_upload_mb": 1,
            "max_pages": 2,
        }
    )
    services: Services = build_services(fake)
    async with client_for(create_app(fake, readiness_probes=[], services=services)) as client:
        yield client


def _problem(response: httpx.Response, status: int, slug: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"].endswith(f"/{slug}")
    assert body["request_id"] == response.headers["x-request-id"]


async def test_create_and_fetch_a_claim(api: httpx.AsyncClient) -> None:
    created = await api.post(
        "/api/v1/claims", json={"mode": "post_deduction", "insurer_hint": "Suraksha"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["claim_id"].startswith("ARZ-")
    assert body["status"] == "draft"
    assert body["revision"] == 1
    fetched = await api.get(f"/api/v1/claims/{body['claim_id']}")
    assert fetched.json()["insurer_hint"] == "Suraksha"
    _problem(await api.get("/api/v1/claims/ARZ-0000-NOPE"), 404, "claim-not-found")
    _problem(await api.post("/api/v1/claims", json={"mode": "unknown"}), 422, "validation-error")


async def test_worklist_filters_and_paginates(api: httpx.AsyncClient) -> None:
    ids = [await create_claim(api, "pre_submission") for _ in range(3)]
    deduction = await create_claim(api, "post_deduction")

    page = (await api.get("/api/v1/claims", params={"limit": 2})).json()
    assert len(page["items"]) == 2
    rest = (
        await api.get("/api/v1/claims", params={"limit": 2, "cursor": page["next_cursor"]})
    ).json()
    seen = [i["claim_id"] for i in page["items"] + rest["items"]]
    assert sorted(seen) == sorted([*ids, deduction])
    assert rest["next_cursor"] is None

    filtered = (await api.get("/api/v1/claims", params={"mode": "post_deduction"})).json()
    assert [i["claim_id"] for i in filtered["items"]] == [deduction]
    by_status = (await api.get("/api/v1/claims", params={"status": "audited"})).json()
    assert by_status["items"] == []
    searched = (await api.get("/api/v1/claims", params={"q": deduction[-6:].lower()})).json()
    assert [i["claim_id"] for i in searched["items"]] == [deduction]
    row = filtered["items"][0]
    assert row["totals"] is None
    assert row["flag_count"] == 0


async def test_audited_claims_show_totals_in_the_worklist(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    await run_to_end(api, claim_id)
    row = (await api.get("/api/v1/claims", params={"status": "audited"})).json()["items"][0]
    assert row["claim_id"] == claim_id
    assert row["totals"]["at_risk"] == 6_788_750
    assert row["flag_count"] == 4


async def test_upload_checks_type_size_and_pages(api: httpx.AsyncClient) -> None:
    claim_id = await create_claim(api, "pre_submission")
    url = f"/api/v1/claims/{claim_id}/documents"
    _problem(
        await api.post(url, files={"file": ("notes.txt", b"hello", "text/plain")}),
        415,
        "unsupported-media-type",
    )
    big = b"%PDF-" + b"0" * (1024 * 1024)
    _problem(
        await api.post(url, files={"file": ("big.pdf", big, "application/pdf")}),
        413,
        "file-too-large",
    )
    broken = b"%PDF-1.4 this is not really a pdf"
    _problem(
        await api.post(url, files={"file": ("x.pdf", broken, "application/pdf")}),
        422,
        "upload-rejected",
    )

    png = io.BytesIO()
    Image.new("L", (8, 8), 255).save(png, "PNG")
    stored = await api.post(
        url, files={"file": ("scan.png", png.getvalue(), "application/octet-stream")}
    )
    assert stored.status_code == 201
    assert stored.json()["content_type"] == "image/png"  # sniffed, not trusted from the client
    assert "uri" not in stored.json()


async def test_too_many_pages(api: httpx.AsyncClient) -> None:
    claim_id = await create_claim(api, "pre_submission")
    from pypdfium2 import PdfDocument

    pdf = PdfDocument.new()
    for _ in range(3):
        pdf.new_page(100, 100)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    response = await api.post(
        f"/api/v1/claims/{claim_id}/documents",
        files={"file": ("long.pdf", buffer.getvalue(), "application/pdf")},
    )
    _problem(response, 422, "upload-rejected")


async def test_documents_can_be_listed_viewed_and_streamed(api: httpx.AsyncClient) -> None:
    claim_id = await create_claim(api, "pre_submission")
    doc = (await upload(api, claim_id, BILL)).json()
    listed = (await api.get(f"/api/v1/claims/{claim_id}/documents")).json()
    assert [d["document_id"] for d in listed] == [doc["document_id"]]

    view = (await api.get(f"/api/v1/claims/{claim_id}/documents/{doc['document_id']}/url")).json()
    assert view["expires_in_s"] is None
    content = await api.get(view["url"])
    assert content.content == await anyio.Path(BILL).read_bytes()
    assert content.headers["cache-control"] == "private, no-store"
    _problem(
        await api.get(f"/api/v1/claims/{claim_id}/documents/doc-missing/url"),
        404,
        "document-not-found",
    )


async def test_documents_cannot_be_added_after_the_audit(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    await run_to_end(api, claim_id)
    _problem(await upload(api, claim_id, BILL), 409, "invalid-state")


async def test_human_correction_reruns_the_engine_without_the_model(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    _problem(await api.patch(f"/api/v1/claims/{claim_id}/lines/9", json={}), 409, "invalid-state")
    await run_to_end(api, claim_id)

    # The desk says laundry (line 9) is on no IRDAI list: the ₹1,200 cut disappears.
    corrected = await api.patch(f"/api/v1/claims/{claim_id}/lines/9", json={"irdai_list": None})
    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    line = next(line for line in body["facts"]["bill_lines"] if line["line_id"] == 9)
    assert line["confirmed_by_human"] is True
    non_payable = next(f for f in body["audit"]["flags"] if f["rule_id"] == "NON_PAYABLE")
    assert non_payable["amount_at_risk"] == 230_000

    # And the surgeon's fee was misread: correct the amount and the category stays.
    corrected = await api.patch(
        f"/api/v1/claims/{claim_id}/lines/3", json={"amount": "50,000.00", "category": "surgeon"}
    )
    assert corrected.json()["audit"]["totals"]["billed"] == 21_550_000
    _problem(
        await api.patch(f"/api/v1/claims/{claim_id}/lines/3", json={"amount": "fifty"}),
        422,
        "invalid-input",
    )
    _problem(await api.patch(f"/api/v1/claims/{claim_id}/lines/99", json={}), 404, "line-not-found")
    _problem(
        await api.patch(f"/api/v1/claims/{claim_id}/lines/3", json={"bogus": 1}),
        422,
        "validation-error",
    )


async def test_audit_log_records_actions_without_document_content(api: httpx.AsyncClient) -> None:
    claim_id = await prepare_case(api, "case_a")
    await run_to_end(api, claim_id)
    log = (await api.get(f"/api/v1/claims/{claim_id}/audit-log")).json()
    actions = [entry["action"] for entry in log]
    assert actions[:2] == ["claim.created", "consent.recorded"]
    assert actions.count("document.uploaded") == 6
    assert actions[-2:] == ["run.started", "run.completed"]
    assert "bill_scanned.jpg" not in str(log)  # file names can carry patient names


async def test_meta_lists_citations_with_their_status(api: httpx.AsyncClient) -> None:
    citations = (await api.get("/api/v1/meta/citations")).json()
    statuses = {c["id"]: c["status"] for c in citations}
    assert statuses["IRDAI_PROP_DED_2020"] == "verified"
    assert statuses["IRDAI_NON_PAYABLE_ANNEX_I"] == "verify"


async def test_unknown_run_is_a_problem(api: httpx.AsyncClient) -> None:
    claim_id = await create_claim(api, "pre_submission")
    _problem(await api.get(f"/api/v1/claims/{claim_id}/runs/run-nope"), 404, "run-not-found")
    _problem(await api.get(f"/api/v1/claims/{claim_id}/runs/run-nope/events"), 404, "run-not-found")
