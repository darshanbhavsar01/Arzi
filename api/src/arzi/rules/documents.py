"""Documents an insurer will ask for; a missing one stalls or shrinks the claim."""

from arzi.domain.enums import DocumentKind, FixCode, FlagKind, LineCategory, Severity
from arzi.domain.models import ClaimFacts, Flag
from arzi.domain.money import Paise, total
from arzi.rules.context import AuditContext, line_ids, policy_refs

DOC_MISSING = "DOC_MISSING"

_LINE_DOCUMENTS = (
    (DocumentKind.INVESTIGATION_REPORTS, LineCategory.DIAGNOSTICS, Severity.MEDIUM),
    (DocumentKind.IMPLANT_INVOICE, LineCategory.IMPLANT, Severity.HIGH),
)


def doc_missing(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Discharge summary always; investigation reports and implant invoice when billed.

    The amount on each flag is the exposure: the whole claim for a missing discharge summary,
    otherwise the lines the document supports.
    """
    present = set(facts.documents_present)
    needed: list[tuple[DocumentKind, Severity, Paise, tuple[int, ...]]] = []
    if DocumentKind.DISCHARGE_SUMMARY not in present:
        needed.append((DocumentKind.DISCHARGE_SUMMARY, Severity.HIGH, ctx.payable, ()))
    for kind, category, severity in _LINE_DOCUMENTS:
        lines = ctx.open_lines({category})
        if lines and kind not in present:
            exposure = total(ctx.remaining[line.line_id] for line in lines)
            needed.append((kind, severity, exposure, line_ids(lines)))
    flags = []
    for kind, severity, exposure, lines_supported in needed:
        step_id = ctx.step(DOC_MISSING, f"Required document missing: {kind}", result=exposure)
        flags.append(
            Flag(
                flag_id=f"{DOC_MISSING}-{kind}",
                rule_id=DOC_MISSING,
                kind=FlagKind.ADVISORY,
                severity=severity,
                amount_at_risk=exposure,
                lines=lines_supported,
                citation_refs=policy_refs([facts.policy.claims_clause_id]),
                fix_code=FixCode.ATTACH_DOCUMENT,
                trace_ref=step_id,
                missing_document=kind,
            )
        )
    return flags
