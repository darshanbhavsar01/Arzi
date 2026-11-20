"""Deterministic redaction of patient identifiers before any reasoning step (AGENTS.md §5.4).

Two passes over every string in the extracted documents:

1. Known values: whatever the extractor copied into ``identifiers`` (name, UHID, policy number
   and so on) is replaced wherever it appears, ignoring case and spacing.
2. Patterns: Aadhaar-shaped numbers, PAN-shaped codes, Indian mobile numbers and emails are
   replaced even if the extractor missed them. Aadhaar-shaped numbers are removed whether or
   not their Verhoeff check digit is valid: a mistyped real number is still personal data.

Each value maps to a stable pseudonym (an HMAC of the value under a per-deployment key), so the
same person is the same ``P-7F3A`` across documents and runs. The original values go only to the
restricted identity vault, used later to address the signed letter.
"""

import hashlib
import hmac
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from arzi.domain.models import RedactionSummary

IDENTIFIER_FIELDS = {
    "patient_name": "name",
    "phone": "phone",
    "email": "email",
    "address": "address",
    "aadhaar": "aadhaar",
    "pan": "pan",
    "uhid": "uhid",
    "ip_number": "ip_number",
    "policy_number": "policy_number",
    "member_id": "member_id",
    "claim_number": "claim_number",
}

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("phone", re.compile(r"(?<![\w+])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("aadhaar", re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("pan", re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")),
)
_NAME_PART_MIN = 4


@dataclass
class RedactionOutcome[T: BaseModel]:
    documents: list[T]
    summary: RedactionSummary
    vault: dict[str, str] = field(default_factory=dict)
    patient_pseudonym: str | None = None


class Redactor:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def pseudonym(self, kind: str, value: str) -> str:
        normalised = " ".join(value.lower().split())
        digest = hmac.new(self._key, f"{kind}:{normalised}".encode(), hashlib.sha256)
        tag = digest.hexdigest()[:4].upper()
        return f"P-{tag}" if kind == "name" else f"[{kind.upper()}-{tag}]"

    def redact[T: BaseModel](self, documents: Sequence[T]) -> RedactionOutcome[T]:
        dumps = [doc.model_dump(mode="json") for doc in documents]
        known = self._known_values(dumps)
        counts: Counter[str] = Counter()
        vault: dict[str, str] = {}

        def scrub(text: str) -> str:
            for pattern, kind, _text, original in known:
                alias = self.pseudonym(kind, original)
                text, n = pattern.subn(alias, text)
                if n:
                    counts[kind] += n
                    vault[alias] = original
            for kind, pattern in PATTERNS:

                def replace(match: re.Match[str], kind: str = kind) -> str:
                    value = match.group(0)
                    alias = self.pseudonym(kind, value)
                    counts[kind] += 1
                    vault[alias] = value
                    return alias

                text = pattern.sub(replace, text)
            return text

        cleaned = [_walk(dump, scrub) for dump in dumps]
        names = [original for _, kind, _, original in known if kind == "name"]
        return RedactionOutcome(
            documents=[
                type(doc).model_validate(c) for doc, c in zip(documents, cleaned, strict=True)
            ],
            summary=RedactionSummary(counts=dict(sorted(counts.items()))),
            vault=vault,
            patient_pseudonym=self.pseudonym("name", names[0]) if names else None,
        )

    @staticmethod
    def _known_values(
        dumps: Sequence[dict[str, Any]],
    ) -> list[tuple[re.Pattern[str], str, str, str]]:
        """(pattern, kind, text to find, original value it stands for), longest text first."""
        values: dict[tuple[str, str], None] = {}
        for dump in dumps:
            identifiers = dump.get("identifiers") or {}
            for field_name, kind in IDENTIFIER_FIELDS.items():
                value = identifiers.get(field_name)
                if isinstance(value, str) and value.strip():
                    values[(kind, " ".join(value.split()))] = None
        found = [(kind, value, value) for kind, value in values]
        # Name parts catch "Mr Parmar" in free text and map to the full name's pseudonym.
        # Short parts would over-match ordinary words, so they are left alone.
        for kind, value, _ in list(found):
            if kind == "name":
                found += [
                    ("name", part, value) for part in value.split() if len(part) >= _NAME_PART_MIN
                ]
        unique = list(dict.fromkeys(found))
        unique.sort(key=lambda entry: len(entry[1]), reverse=True)
        return [(_flexible(text), kind, text, original) for kind, text, original in unique]


def _flexible(value: str) -> re.Pattern[str]:
    """Match the value regardless of case and of how whitespace was transcribed."""
    parts = [re.escape(p) for p in value.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def _walk(node: Any, scrub: Any) -> Any:  # noqa: ANN401 - JSON tree
    if isinstance(node, str):
        return scrub(node)
    if isinstance(node, list):
        return [_walk(item, scrub) for item in node]
    if isinstance(node, dict):
        return {key: _walk(value, scrub) for key, value in node.items()}
    return node
