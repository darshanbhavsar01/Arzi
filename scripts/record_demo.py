"""Run demo cases through the real pipeline and record the Gemini responses for replay.

Covers the whole demo: extraction, the policy interpreter and flag explainer (ADK workflow),
for cases B and C a GRO appeal, the family explanation in Gujarati, Hindi and English with its
narration (Gemini TTS, ``ARZI_MODEL_TTS``), and the free public check of cases B and C.

    # AI Studio (free tier; synthetic data only), key in the git-ignored api/.env.local:
    ARZI_MODEL_FLASH=<model> uv run python ../scripts/record_demo.py case_a --env-file .env.local

    # Vertex AI (billed):
    GOOGLE_CLOUD_PROJECT=... ARZI_MODEL_FLASH=... ARZI_VERTEX_LOCATION=global \\
    ARZI_PRICE_TABLE_JSON='{"<model>": {"input_inr_per_1m": ..., "output_inr_per_1m": ...}}' \\
    uv run python ../scripts/record_demo.py case_a [case_b case_c] [--replay]

Live mode spends money: every call goes through the budget guard and is priced from its token
usage. Storage is in memory, so nothing is written to Firestore or Cloud Storage. Responses are
saved to ``demo_cases/<case>/llm_cache/``. ``--replay`` re-runs from those recordings offline.
Exit status is 1 if any case does not audit to its ``expected.json``, a reasoning step did not
pass its guardrails, or an appeal's disputed items, citations or relief differ from it.
"""

import argparse
import asyncio
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gen_demo_cases import expected
from pydantic import BaseModel

from arzi.adapters.auth import DEMO_PRINCIPAL
from arzi.adapters.genai_client import ReplayLlmClient
from arzi.adapters.memory import InMemoryBlobStore, InMemoryClaimRepository, InMemoryCostLedger
from arzi.adapters.tts import ReplaySpeech
from arzi.bootstrap import Services, build_llm, build_services, build_speech, utc_now
from arzi.config import LlmMode, Settings
from arzi.domain.enums import AppealForum, ClaimMode, ReasoningStatus
from arzi.services.ports import (
    LlmClient,
    LlmRequest,
    LlmResult,
    LlmUnavailableError,
    SpeechClient,
    SpeechResult,
)
from arzi.services.public_check import CheckFile

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
APPEALS = ("case_b", "case_c")
CHECKED = {ReasoningStatus.PASSED, ReasoningStatus.RETRIED}
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


class SpeechRecordingsFirst:
    """Narrations already recorded are served; only missing ones go to Gemini TTS."""

    def __init__(self, recorded: SpeechClient, live: SpeechClient) -> None:
        self._recorded = recorded
        self._live = live

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        try:
            return await self._recorded.synthesize(text, lang)
        except LlmUnavailableError:
            return await self._live.synthesize(text, lang)


PUBLIC_FILES = {
    "case_b": "insurer_deduction_letter.pdf",
    "case_c": "insurer_rejection_letter.pdf",
}


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
    speech: SpeechClient | None = None
    if not replay:
        llm = RecordingsFirst(ReplayLlmClient(DEMO), build_llm(settings, ledger, utc_now))
        speech = SpeechRecordingsFirst(
            ReplaySpeech(DEMO, voice=settings.tts_voice), build_speech(settings, ledger, utc_now)
        )
    services = build_services(
        settings,
        llm=llm,
        speech=speech,
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
    ok = True
    steps = (("policy reading", record.policy_review), ("explanations", record.narratives))
    for label, step in steps:
        status = step.status if step else None
        print(f"   {label}: {status} {list(step.violations) if step else ''}")
        ok &= status in CHECKED
    if case in APPEALS:
        ok &= await check_appeal(services, claim.claim_id, want)
    ok &= await check_family(services, claim.claim_id)
    if case in PUBLIC_FILES:
        ok &= await check_public(services, case)
    return ok


async def check_family(services: Services, claim_id: str) -> bool:
    pack = await services.family.prepare(DEMO_PRINCIPAL, claim_id)
    langs = {e.lang: str(e.status) for e in pack.explanations}
    print(f"   family: {langs} · audio {[a.lang for a in pack.audio]}")
    for e in pack.explanations:
        for v in e.violations:
            print(f"     {e.lang}: {v}")
    passed = all(e.status in CHECKED for e in pack.explanations) and len(pack.explanations) == 3
    return passed and len(pack.audio) == 3


async def check_public(services: Services, case: str) -> bool:
    folder = DEMO / case
    files = [
        CheckFile("letter", PUBLIC_FILES[case], (folder / PUBLIC_FILES[case]).read_bytes()),
        CheckFile("bill", "itemised_bill.pdf", (folder / "itemised_bill.pdf").read_bytes()),
        CheckFile(
            "discharge", "discharge_summary.pdf", (folder / "discharge_summary.pdf").read_bytes()
        ),
        *(
            CheckFile("policy", name, (folder / name).read_bytes())
            for name in ("policy_schedule.pdf", "policy_wording_excerpt.pdf")
        ),
    ]
    started = await services.public_check.start("127.0.0.1", MODES[case], files, "policyholder")
    await services.runs.wait(started.run_id)
    token = started.url_path.removeprefix("/f/")
    view = await services.family.prepare_by_token(token)
    appeal = await services.family.draft_public_appeal(token)
    print(
        f"   public check: {[e.lang for e in view.explanations]} explained · audio "
        f"{[a.lang for a in view.audio]} · appeal {appeal.drafting} · "
        f"{[f.key for f in view.figures]}"
    )
    return len(view.explanations) == 3 and len(view.audio) == 3 and appeal.drafting in CHECKED


async def check_appeal(services: Services, claim_id: str, want: dict[str, Any]) -> bool:
    """Draft the GRO appeal and compare it with the engine's appealable disputes."""
    appeal = await services.appeals.draft(
        DEMO_PRINCIPAL, claim_id, AppealForum.INSURER_GRO, None, None
    )
    disputes = [f for f in want["flags"] if f["kind"] == "dispute" and f["appealable"]]
    items = appeal.content.items
    print(f"   appeal v{appeal.version} ({appeal.prompt_ref}): {appeal.drafting}")
    for violation in appeal.violations:
        print(f"     {violation}")
    same_items = [(i.flag_id, i.amount) for i in items] == [
        (f["flag_id"], f["recoverable"]) for f in disputes
    ]
    cited = all(
        set(f["citations"]) <= set(i.citations) for i, f in zip(items, disputes, strict=False)
    )
    relief = appeal.content.relief_amount == want["totals"]["recoverable_on_appeal"]
    print(f"   appeal items {same_items} · citations {cited} · relief {relief}")
    return appeal.drafting in CHECKED and same_items and cited and relief


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
