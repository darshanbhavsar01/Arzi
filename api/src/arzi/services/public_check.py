"""The free "Check my rejection": a family uploads the insurer's letter, the policy and the bill,
and gets the same audit, a plain-language explanation and a draft appeal they can review and sign.

It runs under a separate ``public`` tenant (its data is kept for 7 days) and is rate-limited per
connection and per day, on top of the AI budget guard every live call already passes through.
"""

import datetime as dt
import hashlib
import hmac
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from arzi.domain.enums import ClaimMode
from arzi.services.claims import ClaimService
from arzi.services.cost_ledger import today_ist
from arzi.services.errors import InvalidInputError, RateLimitedError
from arzi.services.extraction_schemas import DocType
from arzi.services.family import FamilyService
from arzi.services.ports import Principal
from arzi.services.runs import RunService

Clock = Callable[[], dt.datetime]
Role = Literal["letter", "policy", "bill", "discharge"]
ROLE_TYPES: dict[Role, DocType | None] = {
    "letter": DocType.INSURER_LETTER,
    "policy": None,  # schedule or wording: Arzi classifies it
    "bill": DocType.ITEMISED_BILL,
    "discharge": DocType.DISCHARGE_SUMMARY,
}
REQUIRED: tuple[Role, ...] = ("letter", "policy", "bill")


class DailyLimiter:
    """Counts checks per connection and in total, per IST day. Connections are keyed by an HMAC
    of the address, so no raw IP is kept. In-memory, so the limit is per instance (max 3)."""

    def __init__(self, key: bytes, *, per_key: int, total: int, clock: Clock) -> None:
        self._key = key
        self._per_key = per_key
        self._total = total
        self._clock = clock
        self._day: dt.date | None = None
        self._counts: Counter[str] = Counter()

    def hit(self, address: str) -> None:
        day = today_ist(self._clock)
        if day != self._day:
            self._day, self._counts = day, Counter()
        who = hmac.new(self._key, address.encode(), hashlib.sha256).hexdigest()
        if self._counts[who] >= self._per_key or self._counts.total() >= self._total:
            raise RateLimitedError
        self._counts[who] += 1


@dataclass(frozen=True)
class CheckFile:
    role: Role
    filename: str
    data: bytes


class CheckStarted(BaseModel):
    model_config = ConfigDict(frozen=True)

    url_path: str
    run_id: str


class PublicCheckService:
    def __init__(
        self,
        claims: ClaimService,
        runs: RunService,
        family: FamilyService,
        limiter: DailyLimiter,
        *,
        tenant_id: str,
    ) -> None:
        self._claims = claims
        self._runs = runs
        self._family = family
        self._limiter = limiter
        self._principal = Principal(
            user_id="public-check",
            display_name="Free claim check",
            hospital_id=tenant_id,
            role="billing_executive",
        )

    async def start(
        self, address: str, mode: ClaimMode, files: list[CheckFile], given_by: str
    ) -> CheckStarted:
        if mode is ClaimMode.PRE_SUBMISSION:
            raise InvalidInputError(
                "The free check is for a claim the insurer has already decided."
            )
        missing = [role for role in REQUIRED if not any(f.role == role for f in files)]
        if missing:
            raise InvalidInputError(f"Add the {', '.join(missing)} to run the check.")
        self._limiter.hit(address)
        claim = await self._claims.create(self._principal, mode, None)
        await self._claims.record_consent(self._principal, claim.claim_id, given_by)
        for f in files:
            await self._claims.upload(
                self._principal,
                claim.claim_id,
                filename=f.filename,
                data=f.data,
                document_type=ROLE_TYPES[f.role],
            )
        run = await self._runs.start(self._principal, claim.claim_id, None)
        link = await self._family.share(self._principal, claim.claim_id, purpose="public_check")
        return CheckStarted(url_path=link.url_path, run_id=run.run_id)
