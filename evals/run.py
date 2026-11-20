"""Replay eval over the three demo cases -> ``evals/report.md``.

Measures what the deterministic engine and the recorded agent answers produce against the
committed ``expected.json``: exact-rupee totals, flag precision/recall and the share of agent
answers that passed their guardrails. Run from ``api/`` (``make eval``); it never calls a
Google API, so the numbers are free and reproducible. Extraction accuracy against a live model
is a follow-up in ``docs/PROGRESS.md``.
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "api"), str(ROOT / "scripts")]

from gen_demo_cases import expected  # noqa: E402
from tests.integration.pipeline_support import prepare_case, run_to_end  # noqa: E402

from arzi.bootstrap import build_services  # noqa: E402
from arzi.config import LlmMode, Settings  # noqa: E402
from arzi.domain.models import ClaimRecord  # noqa: E402
from arzi.main import create_app  # noqa: E402

CASES = ("case_a", "case_b", "case_c")
PASSED = {"passed", "retried"}


async def evaluate(case: str) -> dict[str, object]:
    settings = Settings(
        _env_file=None, google_cloud_project=None, bucket=None,
        llm_mode=LlmMode.REPLAY, replay_dir=ROOT / "demo_cases",
    )  # fmt: skip
    app = create_app(settings, readiness_probes=[], services=build_services(settings))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://eval") as client:
        started = time.perf_counter()
        claim_id = await prepare_case(client, case)
        _, events = await run_to_end(client, claim_id)
        latency = time.perf_counter() - started
        record = ClaimRecord.model_validate((await client.get(f"/api/v1/claims/{claim_id}")).json())
    if record.audit is None:
        raise SystemExit(f"{case}: run did not finish: {events[-1].data}")
    got = expected(record.audit)
    want = json.loads((ROOT / "demo_cases" / case / "expected.json").read_text(encoding="utf-8"))
    got_flags, want_flags = (
        {f["flag_id"] for f in got["flags"]},
        {f["flag_id"] for f in want["flags"]},
    )
    amounts = {f["flag_id"]: f["amount_at_risk"] for f in got["flags"]}
    wanted = {f["flag_id"]: f["amount_at_risk"] for f in want["flags"]}
    narrated = record.narratives is not None and record.narratives.status.value in PASSED
    return {
        "case": case,
        "completed": events[-1].event == "run.completed",
        "totals_exact": got["totals"] == want["totals"],
        "tp": len(got_flags & want_flags),
        "got": len(got_flags),
        "want": len(want_flags),
        "amounts_exact": sum(amounts.get(k) == v for k, v in wanted.items()),
        "narrated": narrated,
        "latency_s": latency,
    }


def render(rows: list[dict[str, object]]) -> str:
    tp, got, want = (sum(int(r[k]) for r in rows) for k in ("tp", "got", "want"))  # type: ignore[call-overload]
    amounts = sum(int(r["amounts_exact"]) for r in rows)  # type: ignore[call-overload]
    lines = [
        "# Arzi eval report (replay mode)",
        "",
        "Deterministic engine plus recorded agent answers, synthetic demo cases only.",
        "",
        "| Case | Run completed | Totals exact (paise) | Flags caught | Flag amounts exact"
        " | Narration passed guardrails | Latency (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['completed']} | {r['totals_exact']} | {r['tp']}/{r['want']}"
            f" | {r['amounts_exact']}/{r['want']} | {r['narrated']} | {float(r['latency_s']):.2f} |"  # type: ignore[arg-type]
        )
    median = statistics.median(float(r["latency_s"]) for r in rows)  # type: ignore[arg-type]
    lines += [
        "",
        f"- Flag precision: {tp}/{got}; recall: {tp}/{want}",
        f"- Rupee exact-match (flag amounts): {amounts}/{want}",
        f"- Median end-to-end latency (replay): {median:.2f} s",
        "- Cost per claim in replay: INR 0 (live cost is measured in the cost ledger).",
        "",
    ]
    return "\n".join(lines)


async def main() -> None:
    rows = [await evaluate(case) for case in CASES]
    report = render(rows)
    (ROOT / "evals" / "report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
