"""Audit runs: start (idempotently), execute the pipeline, stream persisted events.

A run executes as a background task in the instance that accepted it. Every event is appended
to the run document before it is announced, so a subscriber can resume with ``Last-Event-ID``,
and a subscriber on another instance still sees progress by polling the repository.
"""

import asyncio
import contextlib
import datetime as dt
import logging
import traceback
from collections.abc import AsyncIterator, Callable, Sequence

from arzi.domain.enums import ClaimStatus
from arzi.domain.models import AuditRun, RunEvent, RunEventType
from arzi.domain.state import ClaimEvent, IllegalTransitionError, transition
from arzi.rules.engine import ENGINE_VERSION
from arzi.services.cost_ledger import BudgetExceededError, PriceUnknownError
from arzi.services.errors import (
    AppError,
    ClaimNotFoundError,
    ConsentRequiredError,
    InvalidStateError,
    RunNotFoundError,
)
from arzi.services.pipeline import Pipeline, RunContext, Summary
from arzi.services.ports import (
    AuditLogEntry,
    ClaimRepository,
    LlmUnavailableError,
    Principal,
)

logger = logging.getLogger(__name__)

TERMINAL = frozenset({"completed", "failed"})
_STARTABLE = {
    ClaimStatus.DOCUMENTS_UPLOADED: (ClaimEvent.START_PROCESSING,),
    ClaimStatus.AUDITED: (ClaimEvent.REAUDIT,),
    ClaimStatus.FAILED: (ClaimEvent.RETRY, ClaimEvent.START_PROCESSING),
}

Clock = Callable[[], dt.datetime]
IdFactory = Callable[[], str]


def _error_slug(exc: BaseException) -> str:
    """A stable, user-safe slug for why a run failed (never the exception message)."""
    if isinstance(exc, BaseExceptionGroup):  # concurrent extraction wraps failures
        return _error_slug(exc.exceptions[0])
    if isinstance(exc, AppError):
        return exc.slug
    if isinstance(exc, LlmUnavailableError):
        return exc.slug
    if isinstance(exc, BudgetExceededError):
        return "budget-exceeded"
    if isinstance(exc, PriceUnknownError):
        return "model-price-unknown"
    return "internal-error"


class RunService:
    def __init__(
        self,
        repo: ClaimRepository,
        pipeline: Pipeline,
        *,
        clock: Clock,
        new_id: IdFactory,
        poll_s: float = 1.0,
    ) -> None:
        self._repo = repo
        self._pipeline = pipeline
        self._clock = clock
        self._new_id = new_id
        self._poll_s = poll_s
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._wakeups: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------ start

    async def start(
        self, principal: Principal, claim_id: str, idempotency_key: str | None
    ) -> AuditRun:
        hid = principal.hospital_id
        claim = await self._repo.get_claim(hid, claim_id)
        if claim is None:
            raise ClaimNotFoundError
        if idempotency_key:
            existing = await self._repo.find_run_by_key(hid, claim_id, idempotency_key)
            if existing is not None:
                return existing
        if claim.consent is None:
            raise ConsentRequiredError
        documents = await self._repo.list_documents(hid, claim_id)
        if not documents:
            raise InvalidStateError("Upload the claim documents first.")
        hospital = await self._repo.get_hospital(hid)
        if hospital is None:
            raise InvalidStateError("This hospital has no profile yet.")
        status = claim.status
        try:
            for event in _STARTABLE.get(claim.status, (ClaimEvent.START_PROCESSING,)):
                status = transition(status, event)
        except IllegalTransitionError:
            raise InvalidStateError(f"A claim that is {claim.status} cannot be audited.") from None

        now = self._clock()
        run = AuditRun(
            run_id=f"run-{self._new_id()}",
            engine_version=ENGINE_VERSION,
            status="queued",
            idempotency_key=idempotency_key,
            started_at=now,
        )
        await self._repo.save_run(hid, claim_id, run)
        claim = await self._repo.save_claim(
            claim.model_copy(
                update={"status": status, "updated_at": now, "runs": (*claim.runs, run)}
            )
        )
        await self._log(hid, claim_id, principal.user_id, "run.started", run_id=run.run_id)
        context = RunContext(claim=claim, hospital=hospital, documents=documents)
        self._wakeups[run.run_id] = asyncio.Event()
        self._tasks[run.run_id] = asyncio.create_task(self._execute(principal, run, context))
        return run

    async def wait(self, run_id: str) -> None:
        """Block until a run started by this instance has finished (tests, graceful shutdown)."""
        task = self._tasks.get(run_id)
        if task is not None:
            await task

    # ------------------------------------------------------------------ execute

    async def _execute(self, principal: Principal, run: AuditRun, ctx: RunContext) -> None:
        hid, cid = principal.hospital_id, ctx.claim.claim_id
        run = run.model_copy(update={"status": "running"})
        try:
            async for event in self._pipeline.stream(ctx):
                run = await self._emit(hid, cid, run, event.type, event.stage, event.data)
            audit = ctx.audit
            if audit is None or ctx.reconciled is None:  # pragma: no cover - steps guarantee it
                raise RuntimeError("pipeline finished without an audit")
            await self._finish_claim(hid, cid, ctx, run, failed=False)
            run = await self._emit(
                hid,
                cid,
                run.model_copy(update={"status": "completed", "finished_at": self._clock()}),
                "run.completed",
                None,
                {
                    "at_risk": audit.totals.at_risk,
                    "recoverable": audit.totals.recoverable_on_appeal,
                    "cost_micro_inr": sum(c.cost_micro_inr for c in ctx.calls),
                },
                calls=ctx.calls,
            )
            await self._log(hid, cid, principal.user_id, "run.completed", run_id=run.run_id)
        except Exception as exc:
            slug = _error_slug(exc)
            if slug == "internal-error":
                # Type and stack frames only: the message can quote document text.
                logger.error(
                    "run %s failed with %s\n%s",
                    run.run_id,
                    type(exc).__name__,
                    "".join(traceback.format_tb(exc.__traceback__)),
                )
            await self._finish_claim(hid, cid, ctx, run, failed=True)
            run = await self._emit(
                hid,
                cid,
                run.model_copy(
                    update={"status": "failed", "finished_at": self._clock(), "error": slug}
                ),
                "run.failed",
                None,
                {"error": slug},
                calls=ctx.calls,
            )
            await self._log(
                hid, cid, principal.user_id, "run.failed", run_id=run.run_id, error=slug
            )
        finally:
            self._wakeups.pop(run.run_id, asyncio.Event()).set()

    async def _emit(
        self,
        hid: str,
        cid: str,
        run: AuditRun,
        kind: RunEventType,
        stage: str | None,
        data: Summary | None = None,
        *,
        calls: Sequence[object] | None = None,
    ) -> AuditRun:
        event = RunEvent(
            seq=len(run.events) + 1, type=kind, stage=stage, at=self._clock(), data=data or {}
        )
        update: dict[str, object] = {"events": (*run.events, event)}
        if calls is not None:
            update["calls"] = tuple(calls)
            update["prompt_versions"] = tuple(sorted({getattr(c, "prompt_ref", "") for c in calls}))
        run = run.model_copy(update=update)
        await self._repo.save_run(hid, cid, run)
        wakeup = self._wakeups.get(run.run_id)
        if wakeup is not None:
            wakeup.set()
            self._wakeups[run.run_id] = asyncio.Event()
        return run

    async def _finish_claim(
        self, hid: str, cid: str, ctx: RunContext, run: AuditRun, *, failed: bool
    ) -> None:
        claim = await self._repo.get_claim(hid, cid)
        if claim is None:  # pragma: no cover - claims are never deleted mid-run
            return
        # The claim keeps a light copy of each run (no events) for the worklist's timings.
        summary = run.model_copy(
            update={
                "status": "failed" if failed else "completed",
                "finished_at": self._clock(),
                "events": (),
                "calls": tuple(ctx.calls),
            }
        )
        runs = tuple(summary if r.run_id == run.run_id else r for r in claim.runs)
        update: dict[str, object] = {"updated_at": self._clock(), "runs": runs}
        if failed:
            update["status"] = transition(claim.status, ClaimEvent.FAIL)
        else:
            reconciled, result = ctx.reconciled, ctx.audit
            update |= {
                "status": transition(claim.status, ClaimEvent.COMPLETE_AUDIT),
                "facts": reconciled.facts if reconciled else None,
                "issues": (*(reconciled.issues if reconciled else ()), *ctx.review_issues),
                "audit": result,
                "redaction": ctx.redaction.summary if ctx.redaction else None,
                "policy_review": ctx.policy_review,
                "narratives": ctx.narratives,
                "document_types": {
                    e.document.document_id: str(e.document_type) for e in ctx.extractions
                },
                # Decisions on flags the new audit no longer raises would point at nothing.
                "flag_reviews": tuple(
                    r
                    for r in claim.flag_reviews
                    if result and r.flag_id in {f.flag_id for f in result.flags}
                ),
            }
            if ctx.redaction is not None:
                await self._repo.save_identity_vault(hid, cid, ctx.redaction.vault)
        await self._repo.save_claim(claim.model_copy(update=update))

    # ------------------------------------------------------------------ stream

    async def list(self, principal: Principal, claim_id: str) -> list[AuditRun]:
        """Every run of a claim, newest first, with its events and model calls."""
        claim = await self._repo.get_claim(principal.hospital_id, claim_id)
        if claim is None:
            raise ClaimNotFoundError
        runs = [
            await self._repo.get_run(principal.hospital_id, claim_id, r.run_id) for r in claim.runs
        ]
        return sorted((r for r in runs if r), key=lambda r: r.started_at, reverse=True)

    async def get(self, principal: Principal, claim_id: str, run_id: str) -> AuditRun:
        run = await self._repo.get_run(principal.hospital_id, claim_id, run_id)
        if run is None:
            raise RunNotFoundError
        return run

    async def events(
        self, principal: Principal, claim_id: str, run_id: str, after: int = 0
    ) -> AsyncIterator[RunEvent]:
        """Persisted events with ``seq > after``, then new ones until the run ends."""
        run = await self.get(principal, claim_id, run_id)
        sent = after
        while True:
            for event in run.events:
                if event.seq > sent:
                    sent = event.seq
                    yield event
            if run.status in TERMINAL:
                return
            wakeup = self._wakeups.get(run_id)
            if wakeup is not None:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wakeup.wait(), timeout=self._poll_s)
            else:
                await asyncio.sleep(self._poll_s)
            run = await self.get(principal, claim_id, run_id)

    async def _log(self, hid: str, cid: str, actor: str, action: str, **detail: str) -> None:
        entry = AuditLogEntry(at=self._clock(), actor=actor, action=action, detail=dict(detail))
        await self._repo.append_audit_log(hid, cid, entry)
