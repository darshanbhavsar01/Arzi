"""Run demo cases through the real pipeline and record the Gemini responses for replay.

    # AI Studio (free tier; synthetic data only), key in the git-ignored api/.env.local:
    ARZI_MODEL_FLASH=<model> uv run python ../scripts/record_demo.py case_a --env-file .env.local

    # Vertex AI (billed):
    GOOGLE_CLOUD_PROJECT=... ARZI_MODEL_FLASH=... ARZI_VERTEX_LOCATION=global \\
    ARZI_PRICE_TABLE_JSON='{"<model>": {"input_inr_per_1m": ..., "output_inr_per_1m": ...}}' \\
    uv run python ../scripts/record_demo.py case_a [case_b case_c] [--replay]

Live mode spends money: every call goes through the budget guard and is priced from its token
usage. Storage is in memory, so nothing is written to Firestore or Cloud Storage. Responses are
saved to ``demo_cases/<case>/llm_cache/``. ``--replay`` re-runs from those recordings offline.
Exit status is 1 if any case does not audit to its ``expected.json``.
"""

import argparse
import asyncio
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from gen_demo_cases import expected
from pydantic import BaseModel

from arzi.adapters.auth import DEMO_PRINCIPAL
from arzi.adapters.genai_client import ReplayLlmClient
from arzi.adapters.memory import InMemoryBlobStore, InMemoryClaimRepository, InMemoryCostLedger
from arzi.bootstrap import build_llm, build_services, utc_now
from arzi.config import LlmMode, Settings
from arzi.domain.enums import ClaimMode
from arzi.services.ports import LlmClient, LlmRequest, LlmResult, LlmUnavailableError

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo_cases"
MODES = {
    "case_a": ClaimMode.PRE_SUBMISSION,
    "case_b": ClaimMode.POST_DEDUCTION,
    "case_c": ClaimMode.POST_REJECTION,
}
DOCUMENTS = {
    "case_a": ("bill_scanned.jpg",),  # the photographed bill, to prove image extraction
    "case_b": ("itemised_bill.pdf", "insurer_deduction_letter.pdf"),
    "case_c": ("itemised_bill.pdf", "insurer_rejection_letter.pdf"),
}
COMMON = (
    "policy_schedule.pdf",
    "policy_wording_excerpt.pdf",
    "discharge_summary.pdf",
    "investigation_reports.pdf",
    "implant_invoice.pdf",
)


class RecordingsFirst:
    """Serve a call from an existing recording; only missing responses go to the live model.

    Re-running after a quota error therefore costs only the calls that are still missing.
    """

    def __init__(self, recorded: LlmClient, live: LlmClient) -> None:
        self._recorded = recorded
        self._live = live

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        try:
            return await self._recorded.generate_structured(request)
        except LlmUnavailableError:
            return await self._live.generate_structured(request)


async def run_case(case: str, *, replay: bool, env_file: Path | None) -> bool:
    mode = LlmMode.REPLAY if replay else LlmMode.LIVE
    settings = Settings(
        _env_file=env_file,
        llm_mode=mode,
        replay_dir=DEMO,
        llm_record_dir=None if replay else DEMO / case / "llm_cache",
    )
    ledger = InMemoryCostLedger()
    llm: LlmClient | None = None
    if not replay:
        llm = RecordingsFirst(ReplayLlmClient(DEMO), build_llm(settings, ledger, utc_now))
    services = build_services(
        settings,
        llm=llm,
        repo=InMemoryClaimRepository(),
        blobs=InMemoryBlobStore(),
        ledger=ledger,
    )
    claim = await services.claims.create(DEMO_PRINCIPAL, MODES[case], None)
    await services.claims.record_consent(DEMO_PRINCIPAL, claim.claim_id, "patient (synthetic demo)")
    for name in (*COMMON, *DOCUMENTS[case]):
        data = (DEMO / case / name).read_bytes()
        await services.claims.upload(
            DEMO_PRINCIPAL, claim.claim_id, filename=name, data=data, document_type=None
        )
    run = await services.runs.start(DEMO_PRINCIPAL, claim.claim_id, None)
    await services.runs.wait(run.run_id)
    run = await services.runs.get(DEMO_PRINCIPAL, claim.claim_id, run.run_id)
    record = await services.claims.get(DEMO_PRINCIPAL, claim.claim_id)

    cost_inr = run.cost_micro_inr / 1_000_000
    tokens_in = sum(c.input_tokens for c in run.calls)
    tokens_out = sum(c.output_tokens + c.thinking_tokens for c in run.calls)
    print(f"\n== {case} ({mode}) run {run.status} {run.error or ''}")
    print(f"   model calls {len(run.calls)} · tokens in {tokens_in} / out {tokens_out}")
    print(f"   estimated cost ₹{cost_inr:.4f}")
    if record.audit is None:
        return False
    want = json.loads((DEMO / case / "expected.json").read_text(encoding="utf-8"))
    got = expected(record.audit)
    shown = got["totals_display"]
    print(f"   at risk {shown['at_risk']} · recoverable {shown['recoverable_on_appeal']}")
    for issue in record.issues:
        print(f"   needs confirmation: {issue.code} {issue.message}")
    if got != want:
        for key in ("totals", "fix_savings", "flags"):
            if got[key] != want[key]:
                print(f"   MISMATCH {key}:\n     got  {got[key]}\n     want {want[key]}")
        return False
    print("   matches expected.json")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("cases", nargs="+", choices=sorted(MODES))
    parser.add_argument(
        "--replay", action="store_true", help="use recordings instead of live calls"
    )
    parser.add_argument(
        "--env-file", type=Path, help="read settings (e.g. the API key) from this file"
    )
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # ₹ on Windows consoles
    results = [
        asyncio.run(run_case(case, replay=args.replay, env_file=args.env_file))
        for case in args.cases
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
