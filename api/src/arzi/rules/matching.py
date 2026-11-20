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
from functools import cache, lru_cache

from rapidfuzz import fuzz, process

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


@cache
def _vocabulary() -> tuple[str, ...]:
    return tuple(sorted({token for tokens, _, _ in _alias_index() for token in tokens}))


def _token_scores(tokens: tuple[str, ...]) -> dict[str, float]:
    """Best ratio (at or above the threshold) of each reference token against the line.

    The same comparison ``coverage_score`` makes for every (reference token, line token) pair,
    but run inside rapidfuzz per line token instead of a Python loop per pair. Reference tokens
    below the threshold are absent, which reads as 0.
    """
    best: dict[str, float] = {}
    for token in tokens:
        for choice, score, _ in process.extract(
            token, _vocabulary(), scorer=fuzz.ratio, score_cutoff=THRESHOLD, limit=None
        ):
            best[choice] = max(score, best.get(choice, 0.0))
    return best


@lru_cache(maxsize=4096)
def match_non_payable(description: str) -> NonPayableMatch | None:
    """The IRDAI Annexure I entry a bill line describes, or ``None`` below the threshold.

    The highest score wins, then the most specific alias (more words), so "Face mask" is the
    List II face mask rather than the List I "mask". A remaining tie goes to the earlier entry
    in the reference file, so the result never depends on iteration order.
    """
    tokens = normalise(description)
    if not tokens:
        return None
    scores = _token_scores(tokens)
    best: NonPayableMatch | None = None
    best_rank = (0.0, 0)
    for alias_tokens, alias, item in _alias_index():
        score = min(scores.get(token, 0.0) for token in alias_tokens)
        rank = (score, len(alias_tokens))
        if score >= THRESHOLD and (best is None or rank > best_rank):
            best, best_rank = NonPayableMatch(item=item, alias=alias, score=score), rank
    return best


def mentions(condition: str, texts: Iterable[str]) -> bool:
    """Whether any of ``texts`` (diagnosis, procedure) names ``condition``."""
    phrase = normalise(condition)
    return any(coverage_score(phrase, normalise(text)) >= THRESHOLD for text in texts)
