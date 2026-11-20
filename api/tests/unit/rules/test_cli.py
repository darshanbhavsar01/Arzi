import io
import json
import sys
from pathlib import Path

import pytest

from arzi.rules.cli import main
from tests.unit.rules.helpers import DEMO_CASES

CASE_A = DEMO_CASES / "case_a" / "facts.json"


def test_prints_flags_totals_and_trace(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(CASE_A)]) == 0
    out = capsys.readouterr().out
    assert "PROP_ROOM_RENT" in out
    assert "At risk             ₹67,887.50" in out
    assert "₹93,000 associated expenses × ₹5,000 / ₹8,000 = ₹58,125" in out


def test_json_output_is_an_audit_result(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(CASE_A), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["totals"]["at_risk"] == 6_788_750


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "nope.json")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_invalid_facts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"claim_id": "x"}', encoding="utf-8")
    assert main([str(bad)]) == 2
    assert "not valid ClaimFacts" in capsys.readouterr().err


def test_reconfigures_a_real_console_to_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    assert main([str(CASE_A)]) == 0
    console.flush()
    assert "₹67,887.50" in buffer.getvalue().decode("utf-8")


def test_leaves_a_non_console_stdout_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = io.StringIO()
    monkeypatch.setattr(sys, "stdout", sink)
    assert main([str(CASE_A)]) == 0
    assert "₹67,887.50" in sink.getvalue()
