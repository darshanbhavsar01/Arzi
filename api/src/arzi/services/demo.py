"""Load the three synthetic demo cases into the caller's workspace and audit them.

One click on an empty worklist gives a judge or a new pilot user the full story: a pre-submission
audit (A), a deduction to appeal (B) and a rejection to appeal (C). The documents are the
generated synthetic PDFs in ``demo_cases/``; in replay mode their model calls are served from the
committed recordings, so loading the demo costs nothing.
"""

from dataclasses import dataclass
from pathlib import Path

import anyio
from pydantic import BaseModel, ConfigDict

from arzi.domain.enums import ClaimMode
from arzi.services.claims import ClaimService
from arzi.services.errors import DemoUnavailableError
from arzi.services.ports import Principal
from arzi.services.runs import RunService

DEMO_INSURER = "Suraksha Health Insurance Co. (fictional)"
_COMMON = (
    "policy_schedule.pdf",
    "policy_wording_excerpt.pdf",
    "discharge_summary.pdf",
    "investigation_reports.pdf",
    "implant_invoice.pdf",
)


@dataclass(frozen=True)
class DemoCase:
    case: str
    title: str
    mode: ClaimMode
    documents: tuple[str, ...]


CASES = (
    DemoCase(
        "case_a",
        "Pre-submission audit: hip hemiarthroplasty in a single AC room",
        ClaimMode.PRE_SUBMISSION,
        (*_COMMON, "bill_scanned.jpg"),
    ),
    DemoCase(
        "case_b",
        "Deduction appeal: hip hemiarthroplasty, wrongly prorated",
        ClaimMode.POST_DEDUCTION,
        (*_COMMON, "itemised_bill.pdf", "insurer_deduction_letter.pdf"),
    ),
    DemoCase(
        "case_c",
        "Rejection appeal: knee replacement rejected for PED waiting",
        ClaimMode.POST_REJECTION,
        (*_COMMON, "itemised_bill.pdf", "insurer_rejection_letter.pdf"),
    ),
)


class DemoClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    case: str
    title: str
    claim_id: str
    run_id: str


class DemoService:
    def __init__(
        self, claims: ClaimService, runs: RunService, root: Path, *, enabled: bool
    ) -> None:
        self._claims = claims
        self._runs = runs
        self._root = root
        self._enabled = enabled

    @property
    def available(self) -> bool:
        return self._enabled and all(
            (self._root / c.case / name).is_file() for c in CASES for name in c.documents
        )

    async def load(self, principal: Principal) -> list[DemoClaim]:
        if not self.available:
            raise DemoUnavailableError
        loaded = []
        for case in CASES:
            claim = await self._claims.create(principal, case.mode, DEMO_INSURER)
            await self._claims.record_consent(
                principal, claim.claim_id, "patient (synthetic demo data)"
            )
            for name in case.documents:
                data = await anyio.Path(self._root / case.case / name).read_bytes()
                await self._claims.upload(
                    principal, claim.claim_id, filename=name, data=data, document_type=None
                )
            run = await self._runs.start(principal, claim.claim_id, None)
            loaded.append(
                DemoClaim(
                    case=case.case, title=case.title, claim_id=claim.claim_id, run_id=run.run_id
                )
            )
        return loaded
