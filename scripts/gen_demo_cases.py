"""Regenerate the synthetic demo cases (``make demo-cases``).

    python scripts/gen_demo_cases.py [--out demo_cases]

For each case this writes facts.json (engine input), expected.json (engine output, reviewed by
hand against docs/BUILD_PLAN.md), identifiers.json (the synthetic identifiers printed on the
documents, for redaction tests) and the PDFs. Running it twice gives identical bytes.
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from demo_data import CASES, DemoCase
from demo_documents import (
    deduction_letter,
    discharge_summary,
    implant_invoice,
    investigation_reports,
    itemised_bill,
    policy_schedule,
    policy_wording_excerpt,
    rejection_letter,
    scan,
)
from demo_extractions import fixtures

from arzi.domain.enums import InsurerLetterType
from arzi.domain.models import AuditResult
from arzi.domain.money import format_inr
from arzi.rules.context import POLICY_REF_PREFIX
from arzi.rules.engine import audit
from arzi.rules.reference import citations

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "demo_cases"
SCAN_SEED = 20261120

Renderer = Callable[[DemoCase, Path], None]

DOCUMENTS: tuple[tuple[str, Renderer], ...] = (
    ("policy_schedule.pdf", policy_schedule),
    ("policy_wording_excerpt.pdf", policy_wording_excerpt),
    ("itemised_bill.pdf", itemised_bill),
    ("discharge_summary.pdf", discharge_summary),
    ("investigation_reports.pdf", investigation_reports),
    ("implant_invoice.pdf", implant_invoice),
)
LETTERS: dict[InsurerLetterType, tuple[str, Renderer]] = {
    InsurerLetterType.DEDUCTION: ("insurer_deduction_letter.pdf", deduction_letter),
    InsurerLetterType.REJECTION: ("insurer_rejection_letter.pdf", rejection_letter),
}


def expected(result: AuditResult) -> dict[str, Any]:
    """The reviewed, stable part of an audit: flags, totals and citation status.

    Trace wording is left out on purpose so copy edits do not churn the fixtures.
    """
    statuses = citations()
    return {
        "engine_version": result.engine_version,
        "mode": str(result.mode),
        "totals": result.totals.model_dump(),
        "totals_display": {
            name: format_inr(value, always_paise=True)
            for name, value in result.totals.model_dump().items()
        },
        "fix_savings": result.fix_savings,
        "flags": [
            {
                "flag_id": f.flag_id,
                "rule_id": f.rule_id,
                "kind": str(f.kind),
                "severity": str(f.severity),
                "amount_at_risk": f.amount_at_risk,
                "recoverable": f.recoverable,
                "lines": list(f.lines),
                "appealable": f.appealable,
                "fix_code": str(f.fix_code) if f.fix_code else None,
                "citations": {
                    ref: "policy"
                    if ref.startswith(POLICY_REF_PREFIX)
                    else str(statuses[ref].status)
                    for ref in f.citation_refs
                },
            }
            for f in result.flags
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def generate_case(case: DemoCase, out_dir: Path) -> list[Path]:
    directory = out_dir / case.slug
    directory.mkdir(parents=True, exist_ok=True)
    facts = case.facts.model_dump(mode="json", exclude_defaults=True)
    _write_json(directory / "facts.json", facts)
    _write_json(directory / "expected.json", expected(audit(case.facts)))
    _write_json(directory / "identifiers.json", case.identifiers())
    written = [directory / n for n in ("facts.json", "expected.json", "identifiers.json")]
    renderers = list(DOCUMENTS)
    letter = case.facts.insurer_letter
    if letter is not None and letter.type in LETTERS:
        renderers.append(LETTERS[letter.type])
    for name, render in renderers:
        render(case, directory / name)
        written.append(directory / name)
    if case.scanned_bill:
        scan(directory / "itemised_bill.pdf", directory / "bill_scanned.jpg", SCAN_SEED)
        written.append(directory / "bill_scanned.jpg")
    written += write_extraction_fixtures(case, directory)
    return written


def write_extraction_fixtures(case: DemoCase, directory: Path) -> list[Path]:
    """``extraction/<file>.json``: the ideal transcription of each document, keyed by its hash."""
    target = directory / "extraction"
    target.mkdir(exist_ok=True)
    written = []
    for name, (doc_type, extraction) in fixtures(case).items():
        payload = {
            "document": name,
            "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
            "document_type": str(doc_type),
            "extraction": extraction.model_dump(mode="json") if extraction else None,
        }
        _write_json(target / f"{name}.json", payload)
        written.append(target / f"{name}.json")
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args(argv)
    for case in CASES:
        for path in generate_case(case, args.out):
            print(path.relative_to(args.out.parent) if args.out.parent in path.parents else path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
