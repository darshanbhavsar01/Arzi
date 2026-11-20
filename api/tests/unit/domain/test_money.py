from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from arzi.domain.money import (
    ZERO,
    MoneyParseError,
    Paise,
    allocate,
    format_inr,
    percent_of,
    ratio_apply,
    rupees,
    scale,
    to_paise,
    total,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("₹1,57,612.50", 15_761_250),
        ("Rs. 8000/-", 800_000),
        ("Rs 8000", 800_000),
        ("8,000.00", 800_000),
        ("INR 500", 50_000),
        ("1200 rupees", 120_000),
        ("₹ 0.005", 1),
        ("₹0.004", 0),
        ("17512.5", 1_751_250),
        (8000, 800_000),
        (Decimal("17512.505"), 1_751_251),
        (0, 0),
    ],
)
def test_to_paise_parses_printed_amounts(raw: str | int | Decimal, expected: int) -> None:
    assert to_paise(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "₹", "abc", "1.2.3", "-500", "₹ -1", "1e5", "NaN", "12 34 rs 5x"]
)
def test_to_paise_rejects_non_amounts(raw: str) -> None:
    with pytest.raises(MoneyParseError):
        to_paise(raw)


@pytest.mark.parametrize("raw", [-1, Decimal(-1), Decimal("NaN"), Decimal("Infinity")])
def test_to_paise_rejects_negative_and_non_finite(raw: int | Decimal) -> None:
    with pytest.raises(MoneyParseError):
        to_paise(raw)


@pytest.mark.parametrize("raw", [1.5, True, None])
def test_to_paise_rejects_floats_and_other_types(raw: object) -> None:
    with pytest.raises(MoneyParseError):
        to_paise(raw)  # type: ignore[arg-type]  # deliberately wrong types


def test_rupees() -> None:
    assert rupees(5_000) == 500_000
    with pytest.raises(MoneyParseError):
        rupees(-1)


@pytest.mark.parametrize(
    ("amount", "num", "den", "expected"),
    [
        (rupees(93_000), 5_000, 8_000, rupees(58_125)),
        (Paise(1), 1, 2, Paise(1)),  # exactly half a paisa rounds up
        (Paise(3), 1, 2, Paise(2)),
        (Paise(1), 1, 3, Paise(0)),
        (Paise(0), 7, 9, Paise(0)),
    ],
)
def test_ratio_apply_rounds_half_up(amount: Paise, num: int, den: int, expected: Paise) -> None:
    assert ratio_apply(amount, num, den) == expected


@pytest.mark.parametrize(
    ("amount", "num", "den"), [(Paise(1), 1, 0), (Paise(-1), 1, 1), (Paise(1), -1, 1)]
)
def test_ratio_apply_rejects_bad_input(amount: Paise, num: int, den: int) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        ratio_apply(amount, num, den)


def test_percent_of_and_scale() -> None:
    assert percent_of(rupees(175_125), Decimal(10)) == 1_751_250
    assert percent_of(Paise(10_000_005), Decimal(10)) == 1_000_001  # ₹0.005 boundary
    assert percent_of(rupees(1_000), Decimal("12.5")) == rupees(125)
    assert scale(rupees(5_000), Decimal("2.5")) == rupees(12_500)


def test_total() -> None:
    assert total([rupees(1), Paise(50)]) == 150
    assert total([]) == ZERO


def test_allocate_splits_exactly_with_largest_remainder() -> None:
    assert allocate(Paise(10), [Paise(1), Paise(1), Paise(1)]) == [4, 3, 3]
    assert allocate(rupees(58_125), [rupees(60_000), rupees(25_000), rupees(8_000)]) == [
        rupees(37_500),
        rupees(15_625),
        rupees(5_000),
    ]
    assert allocate(ZERO, [ZERO, ZERO]) == [0, 0]
    assert allocate(ZERO, []) == []


@pytest.mark.parametrize(
    ("amount", "weights"),
    [(Paise(-1), [Paise(1)]), (Paise(1), [Paise(-1), Paise(2)]), (Paise(1), [ZERO])],
)
def test_allocate_rejects_bad_input(amount: Paise, weights: list[Paise]) -> None:
    with pytest.raises(ValueError, match="allocate"):
        allocate(amount, weights)


@given(
    amount=st.integers(min_value=0, max_value=10**12),
    weights=st.lists(st.integers(min_value=0, max_value=10**10), min_size=1, max_size=12),
)
def test_allocate_properties(amount: int, weights: list[int]) -> None:
    amount = min(amount, sum(weights))
    parts = allocate(Paise(amount), [Paise(w) for w in weights])

    assert sum(parts) == amount
    assert all(0 <= p <= w for p, w in zip(parts, weights, strict=True))


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Paise(15_761_250), "₹1,57,612.50"),
        (rupees(225_500), "₹2,25,500"),
        (rupees(12_000), "₹12,000"),
        (rupees(500), "₹500"),
        (Paise(5), "₹0.05"),
        (rupees(10_000_000), "₹1,00,00,000"),
        (Paise(-150), "-₹1.50"),
    ],
)
def test_format_inr_uses_indian_grouping(amount: Paise, expected: str) -> None:
    assert format_inr(amount) == expected


def test_format_inr_always_paise() -> None:
    assert format_inr(rupees(12_000), always_paise=True) == "₹12,000.00"


@given(st.integers(min_value=0, max_value=10**13))
def test_format_then_parse_round_trips(paise: int) -> None:
    assert to_paise(format_inr(Paise(paise))) == paise
