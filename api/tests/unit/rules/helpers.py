from pathlib import Path

from arzi.domain.models import AuditResult, ClaimFacts, Flag
from arzi.rules.engine import audit

DEMO_CASES = Path(__file__).resolve().parents[4] / "demo_cases"


def audit_case(case: str) -> AuditResult:
    return audit(ClaimFacts.model_validate_json((DEMO_CASES / case / "facts.json").read_bytes()))


def only(result: AuditResult, rule_id: str) -> Flag:
    matches = [f for f in result.flags if f.rule_id == rule_id]
    assert len(matches) == 1, f"expected one {rule_id} flag, got {len(matches)}"
    return matches[0]


def rule_ids(result: AuditResult) -> list[str]:
    return [f.rule_id for f in result.flags]


def line_cut(result: AuditResult, line_id: int, rule_id: str) -> int:
    outcome = next(o for o in result.lines if o.line_id == line_id)
    return sum(d.amount for d in outcome.deductions if d.rule_id == rule_id)
