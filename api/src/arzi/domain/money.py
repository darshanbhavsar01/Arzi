"""Money as integer paise.

Every rupee figure Arzi shows, stores, speaks or writes into an appeal must be reproducible to
the paisa from the inputs alone (ADR-0002). Floats cannot promise that, so amounts are integer
paise from the moment they cross the boundary, all scaling goes through ``Decimal`` with
``ROUND_HALF_UP`` (the convention on Indian hospital bills and insurer settlement letters), and
formatting happens only at presentation time.
"""

import re
from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import NewType

Paise = NewType("Paise", int)

ZERO = Paise(0)
PAISE_PER_RUPEE = 100

_CURRENCY_TOKENS = re.compile(r"(?i)(₹|\binr\b|\brs\b\.?|rupees?|/-)")
_PLAIN_NUMBER = re.compile(r"^\d+(\.\d+)?$")
_ACCEPTED_TYPES = (str, int, Decimal)


class MoneyParseError(ValueError):
    """The value cannot be read as a non-negative rupee amount."""


def rupees(value: int) -> Paise:
    """Whole rupees as paise; a readable way to write literals in tests and demo data."""
    if value < 0:
        raise MoneyParseError("amounts are never negative")
    return Paise(value * PAISE_PER_RUPEE)


def to_paise(value: str | int | Decimal) -> Paise:
    """Parse a rupee amount as printed on a bill, policy or insurer letter.

    Accepts ``"₹1,57,612.50"``, ``"Rs. 8000/-"``, ``"8,000.00"``, ``"INR 500"``, ints and
    Decimals (all in rupees). Fractions of a paisa round half-up. Rejects negatives, floats,
    booleans and anything that is not a single number, so a mis-read never becomes money.
    """
    if type(value) not in _ACCEPTED_TYPES:
        raise MoneyParseError("amount must be str, int or Decimal")
    amount = _parse_text(value) if isinstance(value, str) else Decimal(value)
    if not amount.is_finite() or amount < 0:
        raise MoneyParseError("amounts are finite and never negative")
    paise = (amount * PAISE_PER_RUPEE).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return Paise(int(paise))


def _parse_text(text: str) -> Decimal:
    cleaned = _CURRENCY_TOKENS.sub("", text).replace(",", "").replace(" ", "").strip()
    if not _PLAIN_NUMBER.match(cleaned):
        raise MoneyParseError("not a plain rupee amount")
    return Decimal(cleaned)


def ratio_apply(amount: Paise, numerator: int, denominator: int) -> Paise:
    """``amount × numerator / denominator``, rounded half-up to the paisa.

    Exact rational input (e.g. cap/rate in paise, or a percentage as ``pct/100``) keeps the
    result independent of how the ratio would have printed as a decimal.
    """
    if denominator <= 0 or numerator < 0 or amount < 0:
        raise ValueError("ratio_apply needs a non-negative amount and ratio")
    exact = Decimal(amount) * numerator / denominator
    return Paise(int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def percent_of(amount: Paise, pct: Decimal) -> Paise:
    """``pct`` per cent of ``amount``, half-up. ``pct`` is a finite Decimal such as ``10``."""
    numerator, denominator = pct.as_integer_ratio()
    return ratio_apply(amount, numerator, denominator * 100)


def scale(amount: Paise, factor: Decimal) -> Paise:
    """``amount × factor`` for non-integer quantities such as 2.5 room-days."""
    numerator, denominator = factor.as_integer_ratio()
    return ratio_apply(amount, numerator, denominator)


def total(amounts: Iterable[Paise]) -> Paise:
    return Paise(sum(amounts))


def allocate(amount: Paise, weights: Sequence[Paise]) -> list[Paise]:
    """Split ``amount`` across ``weights`` pro rata so the parts sum exactly to ``amount``.

    Largest-remainder method: everyone gets the floor of their exact share, then the leftover
    paise go to the largest fractional remainders (earlier index wins a tie). This keeps a
    claim-level figure such as "₹93,000 × 5,000 / 8,000 = ₹58,125" and its per-line split in
    agreement to the paisa.
    """
    weight_sum = sum(weights)
    if amount < 0 or any(w < 0 for w in weights) or (weight_sum == 0 and amount != 0):
        raise ValueError("allocate needs non-negative weights that can carry the amount")
    if weight_sum == 0:
        return [ZERO for _ in weights]
    shares = [divmod(amount * w, weight_sum) for w in weights]
    parts = [quotient for quotient, _ in shares]
    leftover = amount - sum(parts)
    by_remainder = sorted(range(len(weights)), key=lambda i: (-shares[i][1], i))
    for index in by_remainder[:leftover]:
        parts[index] += 1
    return [Paise(p) for p in parts]


def format_inr(amount: Paise, *, always_paise: bool = False) -> str:
    """Indian grouping, e.g. ``₹1,57,612.50`` and ``₹2,25,500``.

    Whole-rupee amounts drop ``.00`` unless ``always_paise`` is set (tables align better with
    it; prose reads better without it).
    """
    sign = "-" if amount < 0 else ""
    whole, fraction = divmod(abs(amount), PAISE_PER_RUPEE)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    groups = [head[max(0, i - 2) : i] for i in range(len(head), 0, -2)][::-1]
    grouped = ",".join([*groups, tail]) if head else tail
    suffix = f".{fraction:02d}" if fraction or always_paise else ""
    return f"{sign}₹{grouped}{suffix}"
