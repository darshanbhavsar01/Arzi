import datetime as dt
from decimal import Decimal

import pytest
from pydantic import BaseModel

from arzi.adapters.memory import InMemoryCostLedger
from arzi.domain.models import LlmCall
from arzi.services.cost_ledger import (
    MICRO,
    BudgetedLlmClient,
    BudgetExceededError,
    ModelPrice,
    PriceUnknownError,
    estimate_micro_inr,
    parse_price_table,
    today_ist,
)
from arzi.services.ports import LlmRequest, LlmResult

PRICE = ModelPrice(input_inr_per_1m=Decimal(25), output_inr_per_1m=Decimal(200))


class Answer(BaseModel):
    ok: bool = True


class Echo:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        self.calls += 1
        call = LlmCall(
            prompt_ref=request.prompt_ref,
            model=request.model,
            input_tokens=4000,
            output_tokens=500,
            thinking_tokens=100,
        )
        return LlmResult(output=request.schema(), call=call)


def _request(model: str = "flash") -> LlmRequest[Answer]:
    return LlmRequest(prompt_ref="p@v1", system="", schema=Answer, model=model)


def _clock() -> dt.datetime:
    return dt.datetime(2026, 11, 20, 20, 0, tzinfo=dt.UTC)  # 01:30 IST on the 21st


def test_estimate_bills_thinking_as_output() -> None:
    call = LlmCall(
        prompt_ref="p", model="m", input_tokens=4000, output_tokens=500, thinking_tokens=100
    )
    # 4000 × ₹25/1M + 600 × ₹200/1M = ₹0.1 + ₹0.12 = ₹0.22
    assert estimate_micro_inr(call, PRICE) == 220_000


def test_price_table_parses_json() -> None:
    table = parse_price_table('{"flash": {"input_inr_per_1m": "25", "output_inr_per_1m": 200}}')
    assert table == {"flash": PRICE}
    assert parse_price_table(None) == {}


def test_budget_day_is_the_indian_day() -> None:
    assert today_ist(_clock) == dt.date(2026, 11, 21)


async def test_live_calls_are_priced_and_recorded() -> None:
    ledger = InMemoryCostLedger()
    client = BudgetedLlmClient(Echo(), ledger, {"flash": PRICE}, daily_cap_inr=150, clock=_clock)
    result = await client.generate_structured(_request())
    assert result.call.cost_micro_inr == 220_000
    assert ledger.days[dt.date(2026, 11, 21)] == 220_000
    assert ledger.calls[dt.date(2026, 11, 21)] == 1


async def test_over_budget_refuses_before_calling() -> None:
    ledger = InMemoryCostLedger()
    ledger.days[dt.date(2026, 11, 21)] = 150 * MICRO
    inner = Echo()
    client = BudgetedLlmClient(inner, ledger, {"flash": PRICE}, daily_cap_inr=150, clock=_clock)
    with pytest.raises(BudgetExceededError):
        await client.generate_structured(_request())
    assert inner.calls == 0


async def test_unpriced_models_are_refused() -> None:
    client = BudgetedLlmClient(Echo(), InMemoryCostLedger(), {}, daily_cap_inr=150, clock=_clock)
    with pytest.raises(PriceUnknownError):
        await client.generate_structured(_request("unknown-model"))
