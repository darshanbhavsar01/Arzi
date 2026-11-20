"""Deterministic text matching for bill lines and medical conditions.

A match here can turn into a rupee cut, so it is conservative: every token of the reference
phrase must appear in the text (allowing small spelling variants, ratio ≥ 90), which means
"Laundary charges x2" matches "laundry" but a bare "Charges" never matches "registration
charges". Anything below the threshold returns ``None``; the extractor's category guess is then
only a hint for a human to confirm, never an automatic cut.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from rapidfuzz import fuzz

from arzi.rules.reference import NonPayableItem, non_payable_items

THRESHOLD = 90.0

_PUNCTUATION = re.compile(r"[^\w\s]|_")
_QUANTITY_OR_UNIT = re.compile(r"^(x?\d[\d.]*[a-z]{0,5}|x|nos?|pcs?|qty|units?)$")
_CONNECTORS = frozenset({"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"})


@dataclass(frozen=True, slots=True)
class NonPayableMatch:
    item: NonPayableItem
    alias: str
    score: float


def normalise(text: str) -> tuple[str, ...]:
    """Lowercase word tokens without punctuation, quantities, units or connector words."""
    words = _PUNCTUATION.sub(" ", text.lower()).split()
    return tuple(w for w in words if w not in _CONNECTORS and not _QUANTITY_OR_UNIT.match(w))


def coverage_score(phrase: tuple[str, ...], text: tuple[str, ...]) -> float:
    """How well ``text`` contains every token of ``phrase``: the weakest token's best ratio."""
    if not phrase or not text:
        return 0.0
    return min(max(fuzz.ratio(token, candidate) for candidate in text) for token in phrase)


@cache
def _alias_index() -> tuple[tuple[tuple[str, ...], str, NonPayableItem], ...]:
    return tuple(
        (normalise(alias), alias, item) for item in non_payable_items() for alias in item.aliases
    )


def match_non_payable(description: str) -> NonPayableMatch | None:
    """The IRDAI Annexure I entry a bill line describes, or ``None`` below the threshold.

    The highest score wins; on a tie the earlier entry in the reference file wins, so the
    result never depends on iteration order.
    """
    tokens = normalise(description)
    best: NonPayableMatch | None = None
    for alias_tokens, alias, item in _alias_index():
        score = coverage_score(alias_tokens, tokens)
        if score >= THRESHOLD and (best is None or score > best.score):
            best = NonPayableMatch(item=item, alias=alias, score=score)
    return best


def mentions(condition: str, texts: Iterable[str]) -> bool:
    """Whether any of ``texts`` (diagnosis, procedure) names ``condition``."""
    phrase = normalise(condition)
    return any(coverage_score(phrase, normalise(text)) >= THRESHOLD for text in texts)
