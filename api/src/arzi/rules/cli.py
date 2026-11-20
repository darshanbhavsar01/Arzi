"""Run the rules engine over a facts file and print flags, totals and the computation trace.

    python -m arzi.rules.cli demo_cases/case_a/facts.json [--json]

A developer and demo tool: it reads one local JSON file and writes to stdout, nothing else.
"""

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from arzi.domain.models import AuditResult, ClaimFacts
from arzi.domain.money import format_inr
from arzi.rules.engine import audit


def render(result: AuditResult) -> str:
    rows = [("Flag", "Kind", "Severity", "At risk", "Recoverable", "Lines", "Citations")]
    rows += [
        (
            f.flag_id,
            f.kind,
            f.severity,
            format_inr(f.amount_at_risk, always_paise=True),
            format_inr(f.recoverable, always_paise=True),
            ",".join(map(str, f.lines)) or "-",
            ", ".join(f.citation_refs) or "-",
        )
        for f in result.flags
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    numeric = {3, 4}
    table = [
        "  ".join(
            cell.rjust(widths[i]) if i in numeric else cell.ljust(widths[i])
            for i, cell in enumerate(row)
        ).rstrip()
        for row in rows
    ]
    t = result.totals
    totals = [
        f"Billed              {format_inr(t.billed, always_paise=True)}",
        f"Predicted payable   {format_inr(t.predicted_payable, always_paise=True)}",
        f"At risk             {format_inr(t.at_risk, always_paise=True)}",
        f"Recoverable         {format_inr(t.recoverable_on_appeal, always_paise=True)}",
        f"Fix savings         {format_inr(result.fix_savings, always_paise=True)}",
    ]
    trace = [f"{s.step_id}  {s.rule_id:<26} {s.formula}" for s in result.trace]
    header = f"Arzi rules engine {result.engine_version} · mode {result.mode}"
    return "\n".join([header, "", *table, "", *totals, "", "Trace", *trace]) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m arzi.rules.cli", description=__doc__)
    parser.add_argument("facts", type=Path, help="path to a ClaimFacts JSON file")
    parser.add_argument("--json", action="store_true", help="print the AuditResult as JSON")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # ₹ on Windows consoles
    try:
        facts = ClaimFacts.model_validate_json(args.facts.read_bytes())
    except OSError as exc:
        print(f"cannot read {args.facts}: {exc.strerror}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        print(f"{args.facts} is not valid ClaimFacts:\n{exc}", file=sys.stderr)
        return 2
    result = audit(facts)
    sys.stdout.write(result.model_dump_json(indent=2) + "\n" if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
