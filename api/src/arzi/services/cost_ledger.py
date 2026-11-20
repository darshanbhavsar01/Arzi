"""Per-call cost estimates and the daily budget guard.

The event budget is small (AGENTS.md §7), so every live call is priced from its token usage
before the next one is allowed. Costs are integer micro-rupees: a single Flash call costs a
fraction of a paisa, and floats are not used for money anywhere in Arzi.
"""

import datetime as dt
import json
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from arzi.domain.models import LlmCall
from arzi.services.ports import CostLedgerStore, LlmClient, LlmRequest, LlmResult

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")  # no DST, so a fixed offset
MICRO = 1_000_000


class ModelPrice(BaseModel):
    """Rupees per million tokens. Thinking tokens are billed as output tokens."""

    model_config = ConfigDict(frozen=True)

    input_inr_per_1m: Decimal = Field(ge=0)
    output_inr_per_1m: Decimal = Field(ge=0)


PriceTable = dict[str, ModelPrice]


class BudgetExceededError(Exception):
    """Today's estimated spend has reached the daily cap; live calls are refused."""


class PriceUnknownError(Exception):
    """A live call was requested for a model with no price, so its cost cannot be bounded."""


def parse_price_table(raw: str | None) -> PriceTable:
    if not raw:
        return {}
    return TypeAdapter(PriceTable).validate_python(json.loads(raw))


def estimate_micro_inr(call: LlmCall, price: ModelPrice) -> int:
    billed_output = call.output_tokens + call.thinking_tokens
    rupees_e6 = (
        Decimal(call.input_tokens) * price.input_inr_per_1m
        + Decimal(billed_output) * price.output_inr_per_1m
    )  # tokens × ₹/1M tokens = micro-rupees
    return int(rupees_e6.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def today_ist(clock: Callable[[], dt.datetime]) -> dt.date:
    """The budget day follows the hospital's day (IST), not UTC."""
    return clock().astimezone(IST).date()


class BudgetedLlmClient:
    """Wraps a live client: refuse when over budget, price each call, add it to the ledger."""

    def __init__(
        self,
        inner: LlmClient,
        ledger: CostLedgerStore,
        prices: PriceTable,
        *,
        daily_cap_inr: int,
        clock: Callable[[], dt.datetime],
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._prices = prices
        self._cap_micro = daily_cap_inr * MICRO
        self._clock = clock

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        price = self._prices.get(request.model)
        if price is None:
            raise PriceUnknownError(request.model)
        day = today_ist(self._clock)
        if await self._ledger.spent_micro_inr(day) >= self._cap_micro:
            raise BudgetExceededError
        result = await self._inner.generate_structured(request)
        call = result.call.model_copy(
            update={"cost_micro_inr": estimate_micro_inr(result.call, price)}
        )
        await self._ledger.add(day, call)
        return LlmResult(output=result.output, call=call)
