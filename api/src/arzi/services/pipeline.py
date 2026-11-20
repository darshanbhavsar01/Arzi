"""The audit pipeline: extract → redact → reconcile → audit.

Redaction runs before reconciliation (the plan lists it after): ``ClaimFacts`` is the first
artefact downstream steps reason over, so it must never be built from raw identifiers.
Each step reports a small summary (counts, never document text) for its ``stage.completed``
event. Phase 4 adds reasoning steps behind the same contract.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from arzi.domain.models import AuditResult, ClaimRecord, Hospital, LlmCall
from arzi.rules.engine import audit
from arzi.services.extraction import DocumentExtraction, ExtractionService
from arzi.services.extraction_schemas import (
    BillExtraction,
    DischargeExtraction,
    InsurerLetterExtraction,
    PolicyExtraction,
)
from arzi.services.ports import StoredDocument
from arzi.services.reconcile import ReconcileInput, ReconcileOutcome, reconcile
from arzi.services.redaction import RedactionOutcome, Redactor

Summary = dict[str, int | str | float | bool | None]


@dataclass
class RunContext:
    claim: ClaimRecord
    hospital: Hospital
    documents: Sequence[StoredDocument]
    extractions: list[DocumentExtraction] = field(default_factory=list)
    redaction: RedactionOutcome[BaseModel] | None = None
    reconciled: ReconcileOutcome | None = None
    audit: AuditResult | None = None
    calls: list[LlmCall] = field(default_factory=list)


class PipelineStep(Protocol):
    name: str

    async def run(self, ctx: RunContext) -> Summary: ...


class ExtractStep:
    name = "extract"

    def __init__(
        self, service: ExtractionService, load: Callable[[StoredDocument], Awaitable[bytes]]
    ) -> None:
        self._service = service
        self._load = load

    async def run(self, ctx: RunContext) -> Summary:
        ctx.extractions = await self._service.extract_all(ctx.documents, self._load)
        for item in ctx.extractions:
            ctx.calls.extend(item.calls)
        return {"documents": len(ctx.extractions), "model_calls": len(ctx.calls)}


class RedactStep:
    name = "redact"

    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor

    async def run(self, ctx: RunContext) -> Summary:
        models = [e.extraction for e in ctx.extractions if e.extraction is not None]
        ctx.redaction = self._redactor.redact(models)
        cleaned = iter(ctx.redaction.documents)
        for item in ctx.extractions:
            if item.extraction is not None:
                item.extraction = next(cleaned)
        return {"identifiers_removed": ctx.redaction.summary.total}


class ReconcileStep:
    name = "reconcile"

    async def run(self, ctx: RunContext) -> Summary:
        found = [e.extraction for e in ctx.extractions]
        pseudonym = (ctx.redaction.patient_pseudonym if ctx.redaction else None) or "P-UNKNOWN"
        ctx.reconciled = reconcile(
            ReconcileInput(
                claim_id=ctx.claim.claim_id,
                mode=ctx.claim.mode,
                hospital=ctx.hospital,
                patient_pseudonym=pseudonym,
                document_types=[e.document_type for e in ctx.extractions],
                policies=[x for x in found if isinstance(x, PolicyExtraction)],
                bills=[x for x in found if isinstance(x, BillExtraction)],
                discharges=[x for x in found if isinstance(x, DischargeExtraction)],
                letters=[x for x in found if isinstance(x, InsurerLetterExtraction)],
            )
        )
        return {
            "bill_lines": len(ctx.reconciled.facts.bill_lines),
            "needs_confirmation": len(ctx.reconciled.issues),
        }


class AuditStep:
    name = "audit"

    async def run(self, ctx: RunContext) -> Summary:
        if ctx.reconciled is None:  # pragma: no cover - the runner orders steps
            raise RuntimeError("audit before reconcile")
        ctx.audit = audit(ctx.reconciled.facts)
        totals = ctx.audit.totals
        return {
            "flags": len(ctx.audit.flags),
            "billed": totals.billed,
            "at_risk": totals.at_risk,
            "recoverable": totals.recoverable_on_appeal,
        }
