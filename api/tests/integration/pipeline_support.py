"""Helpers for driving the claim API end to end in tests."""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import httpx

from tests.unit.rules.helpers import DEMO_CASES

CASE_DOCUMENTS = {
    "case_a": (
        "policy_schedule.pdf",
        "policy_wording_excerpt.pdf",
        "bill_scanned.jpg",
        "discharge_summary.pdf",
        "investigation_reports.pdf",
        "implant_invoice.pdf",
    ),
    "case_b": (
        "policy_schedule.pdf",
        "policy_wording_excerpt.pdf",
        "itemised_bill.pdf",
        "discharge_summary.pdf",
        "investigation_reports.pdf",
        "implant_invoice.pdf",
        "insurer_deduction_letter.pdf",
    ),
    "case_c": (
        "policy_schedule.pdf",
        "policy_wording_excerpt.pdf",
        "itemised_bill.pdf",
        "discharge_summary.pdf",
        "investigation_reports.pdf",
        "implant_invoice.pdf",
        "insurer_rejection_letter.pdf",
    ),
}
CASE_MODES = {"case_a": "pre_submission", "case_b": "post_deduction", "case_c": "post_rejection"}


@dataclass
class SseEvent:
    id: int | None
    event: str
    data: dict[str, Any] = field(default_factory=dict)


def parse_sse(text: str) -> list[SseEvent]:
    events = []
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith(":") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            fields[key] = value.strip()
        if "event" in fields:
            events.append(
                SseEvent(
                    id=int(fields["id"]) if "id" in fields else None,
                    event=fields["event"],
                    data=json.loads(fields.get("data", "{}")),
                )
            )
    return events


async def create_claim(client: httpx.AsyncClient, mode: str) -> str:
    response = await client.post("/api/v1/claims", json={"mode": mode})
    assert response.status_code == 201, response.text
    claim_id: str = response.json()["claim_id"]
    return claim_id


async def upload(client: httpx.AsyncClient, claim_id: str, path: Path) -> httpx.Response:
    mime = "image/jpeg" if path.suffix == ".jpg" else "application/pdf"
    data = await anyio.Path(path).read_bytes()
    return await client.post(
        f"/api/v1/claims/{claim_id}/documents", files={"file": (path.name, data, mime)}
    )


async def prepare_case(
    client: httpx.AsyncClient, case: str, *, documents: Iterable[str] | None = None
) -> str:
    claim_id = await create_claim(client, CASE_MODES[case])
    consent = await client.post(f"/api/v1/claims/{claim_id}/consent", json={"given_by": "patient"})
    assert consent.status_code == 200, consent.text
    for name in documents if documents is not None else CASE_DOCUMENTS[case]:
        response = await upload(client, claim_id, DEMO_CASES / case / name)
        assert response.status_code == 201, response.text
    return claim_id


async def run_to_end(
    client: httpx.AsyncClient, claim_id: str, *, key: str | None = None
) -> tuple[str, list[SseEvent]]:
    headers = {"Idempotency-Key": key} if key else {}
    started = await client.post(f"/api/v1/claims/{claim_id}/runs", headers=headers)
    assert started.status_code == 202, started.text
    body = started.json()
    stream = await client.get(body["events_url"])
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    return body["run_id"], parse_sse(stream.text)
