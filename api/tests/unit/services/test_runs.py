import datetime as dt
import itertools
from collections.abc import AsyncIterator

import pytest

from arzi.adapters.auth import DEMO_PRINCIPAL
from arzi.adapters.memory import InMemoryClaimRepository
from arzi.api.sse import stream
from arzi.domain.enums import ClaimMode, ClaimStatus
from arzi.domain.models import ClaimRecord, Consent, RunEvent
from arzi.prompts import load_prompt
from arzi.services.cost_ledger import BudgetExceededError, PriceUnknownError
from arzi.services.errors import InvalidStateError
from arzi.services.pipeline import RunContext, Summary
from arzi.services.ports import LlmUnavailableError, StoredDocument
from arzi.services.runs import RunService, _error_slug

T0 = dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.UTC)
P = DEMO_PRINCIPAL


class Step:
    """A pipeline step that succeeds with a summary or fails with the given error."""

    def __init__(self, name: str, error: BaseException | None = None) -> None:
        self.name = name
        self._error = error

    async def run(self, ctx: RunContext) -> Summary:
        if self._error is not None:
            raise self._error
        return {"ok": True}


def _service(repo: InMemoryClaimRepository, *steps: Step) -> RunService:
    ids = itertools.count(1)
    return RunService(repo, steps, clock=lambda: T0, new_id=lambda: f"{next(ids):04d}", poll_s=0.01)


async def _ready_claim(repo: InMemoryClaimRepository, status: ClaimStatus) -> str:
    record = ClaimRecord(
        hospital_id=P.hospital_id,
        claim_id="ARZ-1",
        mode=ClaimMode.PRE_SUBMISSION,
        status=status,
        consent=Consent(given_by="patient", recorded_by="u", at=T0),
    )
    await repo.create_claim(record)
    document = StoredDocument(
        document_id="doc-1",
        filename="bill.pdf",
        content_type="application/pdf",
        size_bytes=1,
        pages=1,
        sha256="0" * 64,
        uri="memory://x",
        uploaded_at=T0,
    )
    await repo.add_document(P.hospital_id, "ARZ-1", document)
    return "ARZ-1"


@pytest.mark.parametrize(
    ("error", "slug"),
    [
        (LlmUnavailableError("replay-miss"), "replay-miss"),
        (BudgetExceededError(), "budget-exceeded"),
        (PriceUnknownError("m"), "model-price-unknown"),
        (InvalidStateError(), "invalid-state"),
        (ExceptionGroup("g", [LlmUnavailableError("llm-timeout")]), "llm-timeout"),
        (RuntimeError("boom with patient text"), "internal-error"),
    ],
)
def test_failure_slugs_are_stable_and_never_the_message(error: BaseException, slug: str) -> None:
    assert _error_slug(error) == slug


async def test_failed_step_marks_run_and_claim_failed(caplog: pytest.LogCaptureFixture) -> None:
    repo = InMemoryClaimRepository()
    claim_id = await _ready_claim(repo, ClaimStatus.DOCUMENTS_UPLOADED)
    service = _service(repo, Step("extract", RuntimeError("Ramesh Parmar")))
    run = await service.start(P, claim_id, None)
    await service.wait(run.run_id)

    stored = await service.get(P, claim_id, run.run_id)
    assert stored.status == "failed"
    assert stored.error == "internal-error"
    assert (await repo.get_claim(P.hospital_id, claim_id)).status is ClaimStatus.FAILED  # type: ignore[union-attr]
    assert "Ramesh" not in caplog.text  # the message never reaches the logs


async def test_audited_claims_can_be_audited_again_and_drafts_cannot() -> None:
    repo = InMemoryClaimRepository()
    claim_id = await _ready_claim(repo, ClaimStatus.AUDITED)
    service = _service(repo, Step("noop"))
    run = await service.start(P, claim_id, None)
    assert run.status == "queued"
    assert (await repo.get_claim(P.hospital_id, claim_id)).status is ClaimStatus.PROCESSING  # type: ignore[union-attr]
    await service.wait(run.run_id)

    drafts = InMemoryClaimRepository()
    await _ready_claim(drafts, ClaimStatus.DRAFT)
    with pytest.raises(InvalidStateError):
        await _service(drafts).start(P, "ARZ-1", None)


async def test_a_hospital_without_a_profile_cannot_run() -> None:
    repo = InMemoryClaimRepository(hospitals={})
    claim_id = await _ready_claim(repo, ClaimStatus.DOCUMENTS_UPLOADED)
    with pytest.raises(InvalidStateError):
        await _service(repo).start(P, claim_id, None)


async def test_another_instance_follows_the_run_by_polling() -> None:
    repo = InMemoryClaimRepository()
    claim_id = await _ready_claim(repo, ClaimStatus.DOCUMENTS_UPLOADED)
    owner = _service(repo, Step("extract", LlmUnavailableError("replay-miss")))
    run = await owner.start(P, claim_id, None)
    observer = _service(repo)  # never started the run, so it has no wake-up signal
    events = [event async for event in observer.events(P, claim_id, run.run_id)]
    assert [e.type for e in events][-1] == "run.failed"


async def test_sse_sends_heartbeats_while_waiting() -> None:
    async def slow() -> AsyncIterator[RunEvent]:
        import asyncio

        await asyncio.sleep(0.05)
        yield RunEvent(seq=1, type="run.completed", at=T0)

    chunks = [chunk async for chunk in stream(slow(), heartbeat_s=0.01)]
    assert chunks[0].startswith("retry:")
    assert ": ping\n\n" in chunks
    assert chunks[-1].startswith("id: 1\nevent: run.completed\n")


def test_unknown_prompt_versions_fail_loudly() -> None:
    with pytest.raises(LookupError):
        load_prompt("extract_bill", 99)
