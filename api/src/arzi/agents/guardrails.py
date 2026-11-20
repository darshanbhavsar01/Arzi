"""Guardrails on every model-written (or person-edited) piece of prose (AGENTS.md §5).

1. **Amount guard.** Prose may mention money only as placeholders such as
   ``{{flag.PROP_ROOM_RENT.amount}}`` or ``{{totals.recoverable}}``. Any rupee figure written out
   (₹, Rs., INR, rupees, रुपये/रु., રૂપિયા/રૂ., "/-", lakh/crore with digits, or a comma-grouped
   number) is rejected, in English, Hindi and Gujarati, with Latin or native digits.
2. **Citation whitelist.** Cited refs must be in the claim's ``allowed_refs``: rule IDs from the
   registry plus ``policy:<clause>`` IDs present in the policy. Prose may not name a circular
   number, policy clause or paragraph that is not in context.
3. **Rendering.** Placeholders are filled from rules-engine output only, formatted ``en-IN``.

Violations carry a code and the field they were found in, never the offending text, so they
are safe to store and log.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from arzi.domain.models import AuditResult, ClaimFacts, PerDayAmountCap, Policy
from arzi.domain.money import Paise, format_inr
from arzi.rules.context import POLICY_REF_PREFIX
from arzi.rules.forums import OMBUDSMAN_MAX_CLAIM
from arzi.rules.reference import citations

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")

_D = "0-9\\u0966-\\u096f\\u0ae6-\\u0aef"  # Latin, Devanagari and Gujarati digit ranges (regex)
_NUMBER = rf"[{_D}](?:[{_D},.]*[{_D}])?"
_CURRENCY = (
    r"(?:₹|\bRs\.?(?![a-z])|\bINR(?![a-z])|\brupees?\b|/-"
    r"|रुपये|रुपए|रुपया|रुपयों|रु\.?|રૂપિયા|રૂ\.?)"
)
_MAGNITUDE = (
    r"(?:\blakhs?\b|\blacs?\b|\bcrores?\b|\bthousand\b|हज़ार|हजार|लाख|करोड़|करोड|હજાર|લાખ|કરોડ)"
)
_AMOUNT_PATTERNS = (
    re.compile(rf"{_CURRENCY}\s*{_NUMBER}", re.IGNORECASE),
    re.compile(rf"{_NUMBER}\s*(?:{_MAGNITUDE}\s*)?{_CURRENCY}", re.IGNORECASE),
    re.compile(rf"{_NUMBER}\s*{_MAGNITUDE}", re.IGNORECASE),
    # A comma-grouped figure (Indian 1,57,612.50 or Western 157,612) reads as money even bare.
    re.compile(
        rf"(?<![{_D}.,])[{_D}]{{1,3}}(?:(?:,[{_D}]{{2}})*,[{_D}]{{3}}|(?:,[{_D}]{{3}})+)"
        rf"(?:\.[{_D}]{{1,2}})?(?![{_D}])"
    ),
)
_CURRENCY_BEFORE_PLACEHOLDER = re.compile(rf"{_CURRENCY}\s*\{{\{{", re.IGNORECASE)
_CIRCULAR_CODE = re.compile(r"\bIRDAI?/[A-Z0-9][A-Z0-9/.\-]*[A-Z0-9]", re.IGNORECASE)
_CIRCULAR_NUMBER = re.compile(r"\bcircular\s+(?:no\.?|number)\s*[\w/.\-]+", re.IGNORECASE)
_CLAUSE = re.compile(r"\b(?:clause|section)\s+([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE)
_REF_ID = re.compile(r"\(?\b(policy:[0-9]+(?:\.[0-9]+)*|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b\)?")
_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([,.;:)])")
_PARAGRAPH = re.compile(r"\bpara(?:graph)?\.?\s+[0-9]", re.IGNORECASE)

_NATIVE_DIGITS = {
    "hi": str.maketrans("0123456789", "०१२३४५६७८९"),
    "gu": str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯"),
}


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    where: str

    def __str__(self) -> str:
        return f"{self.code} in {self.where}"


MESSAGES = {
    "stray_amount": "wrote a rupee amount; use only the placeholders listed in the input",
    "currency_before_placeholder": "put a currency sign before a placeholder; the placeholder "
    "already renders the ₹ sign",
    "unknown_placeholder": "used a placeholder that is not in the input's list",
    "unknown_citation": "cited a reference that is not in allowed_refs",
    "unknown_regulation": "named a circular number that is not in allowed_refs",
    "unknown_clause": "named a policy clause that is not in the policy",
    "paragraph_reference": "named a paragraph number; cite the reference ID instead",
    "missing_flag": "left out a flag that needs an entry",
    "unexpected_flag": "wrote an entry for a flag that is not in the input",
    "missing_relief": "did not state the relief with its placeholder",
}


class GuardrailError(ValueError):
    """Raised for person-written edits, which are rejected rather than retried."""

    def __init__(self, violations: Iterable[Violation]) -> None:
        self.violations = tuple(violations)
        super().__init__("; ".join(str(v) for v in self.violations))


@dataclass(frozen=True)
class ProsePolicy:
    """What prose about one claim may contain."""

    allowed_refs: frozenset[str]
    placeholders: frozenset[str]

    @property
    def clause_ids(self) -> frozenset[str]:
        n = len(POLICY_REF_PREFIX)
        return frozenset(r[n:] for r in self.allowed_refs if r.startswith(POLICY_REF_PREFIX))

    @property
    def circular_codes(self) -> tuple[str, ...]:
        registry = citations()
        return tuple(registry[r].ref.upper() for r in self.allowed_refs if r in registry)


def policy_clause_ids(policy: Policy) -> frozenset[str]:
    """Clause IDs in the (redacted) policy: its clause list and every clause a term cites."""
    cited = (
        policy.room_rent_cap.clause_id if policy.room_rent_cap else None,
        policy.proportionate_clause_id,
        policy.icu_cap.clause_id if policy.icu_cap else None,
        policy.copay.clause_id if policy.copay else None,
        policy.claims_clause_id,
        *(w.clause_id for w in (*policy.ped_declared, *policy.specific_waiting)),
        *(s.clause_id for s in policy.sub_limits),
    )
    return frozenset({c.id for c in policy.clauses} | {c for c in cited if c})


def allowed_refs(facts: ClaimFacts, extra: Iterable[str] = ()) -> frozenset[str]:
    """Every policy clause in context, plus those ``extra`` refs (the claim's flag citations,
    the forum's rules) that really are in the registry or the policy."""
    clause_refs = {POLICY_REF_PREFIX + c for c in policy_clause_ids(facts.policy)}
    registry = citations()
    return frozenset(clause_refs | {r for r in extra if r in registry or r in clause_refs})


def placeholder_values(facts: ClaimFacts, result: AuditResult | None = None) -> dict[str, Paise]:
    """Every amount prose may reference, by placeholder name: policy and letter amounts from the
    confirmed facts, and (once the engine has run) totals and per-flag amounts."""
    policy = facts.policy
    values: dict[str, Paise] = {
        "policy.sum_insured": policy.sum_insured,
        "forum.ombudsman_limit": OMBUDSMAN_MAX_CLAIM,
    }
    if isinstance(policy.room_rent_cap, PerDayAmountCap):
        values["policy.room_rent_cap"] = policy.room_rent_cap.amount
    if policy.icu_cap:
        values["policy.icu_cap"] = policy.icu_cap.amount_per_day
    if facts.insurer_letter is not None:
        values["letter.claimed"] = facts.insurer_letter.amount_claimed
        values["letter.approved"] = facts.insurer_letter.amount_approved
    if result is None:
        return values
    totals = result.totals
    values |= {
        "totals.billed": totals.billed,
        "totals.predicted_payable": totals.predicted_payable,
        "totals.at_risk": totals.at_risk,
        "totals.recoverable": totals.recoverable_on_appeal,
        "totals.fix_savings": result.fix_savings,
    }
    for flag in result.flags:
        values[f"flag.{flag.flag_id}.amount"] = flag.amount_at_risk
        values[f"flag.{flag.flag_id}.recoverable"] = flag.recoverable
        values[f"flag.{flag.flag_id}.fix_savings"] = flag.fix_savings
    return values


def validate_amounts(text: str, where: str) -> list[Violation]:
    """Reject rupee figures that did not come from a placeholder."""
    found: list[Violation] = []
    if _CURRENCY_BEFORE_PLACEHOLDER.search(text):
        found.append(Violation("currency_before_placeholder", where))
    bare = PLACEHOLDER.sub(" ", text)
    if any(p.search(bare) for p in _AMOUNT_PATTERNS):
        found.append(Violation("stray_amount", where))
    return found


def validate_citations(refs: Iterable[str], allowed: frozenset[str], where: str) -> list[Violation]:
    unknown = any(ref not in allowed for ref in refs)
    return [Violation("unknown_citation", where)] if unknown else []


def check_prose(text: str, policy: ProsePolicy, where: str) -> list[Violation]:
    """Every rule prose must pass: amounts, placeholders, and references named in the text."""
    found = validate_amounts(text, where)
    if any(name not in policy.placeholders for name in PLACEHOLDER.findall(text)):
        found.append(Violation("unknown_placeholder", where))
    codes = policy.circular_codes
    named = [m.group(0).upper() for m in _CIRCULAR_CODE.finditer(text)]
    invented = any(not any(code in known for known in codes) for code in named)
    if invented or (_CIRCULAR_NUMBER.search(text) and not named):
        found.append(Violation("unknown_regulation", where))
    if any(c not in policy.clause_ids for c in _CLAUSE.findall(text)):
        found.append(Violation("unknown_clause", where))
    if _PARAGRAPH.search(text):
        found.append(Violation("paragraph_reference", where))
    return found


FEEDBACK_HEADER = "Your previous answer broke these rules:"


def feedback(violations: Iterable[Violation]) -> str:
    """The note appended to the retry, telling the model what to fix (and where)."""
    lines = [f"- In `{v.where}` you {MESSAGES.get(v.code, v.code)}." for v in violations]
    return FEEDBACK_HEADER + "\n" + "\n".join(lines) + "\nAnswer again."


class UnknownPlaceholderError(KeyError):
    pass


def humanise_refs(text: str) -> str:
    """Reference IDs read as words: ``policy:4.3`` becomes "clause 4.3"; a registry ID becomes its
    title, or disappears where it only repeats a title in parentheses ("Norms on proportionate
    deductions (IRDAI_PROP_DED_2020)"). Unknown tokens are left alone."""
    registry = citations()

    def swap(match: re.Match[str]) -> str:
        whole, ref = match.group(0), match.group(1)
        lead = "(" if whole.startswith("(") else ""
        trail = ")" if whole.endswith(")") else ""
        if ref.startswith(POLICY_REF_PREFIX):
            return f"{lead}clause {ref.removeprefix(POLICY_REF_PREFIX)}{trail}"
        if ref in registry:
            return "" if lead and trail else f"{lead}{registry[ref].title}{trail}"
        return whole

    shown = _REF_ID.sub(swap, text)
    return _SPACE_BEFORE_PUNCTUATION.sub(r"\1", _SPACES.sub(" ", shown)).strip()


def render(
    template: str, values: Mapping[str, Paise], *, locale: str = "en", native_digits: bool = False
) -> str:
    """Fill placeholders with engine amounts and make reference IDs readable. Hindi and Gujarati
    keep Latin digits unless ``native_digits`` is set (bills and letters in India mostly print
    Latin digits)."""

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise UnknownPlaceholderError(name)
        shown = format_inr(values[name])
        table = _NATIVE_DIGITS.get(locale) if native_digits else None
        return shown.translate(table) if table else shown

    return humanise_refs(PLACEHOLDER.sub(fill, template))


def try_render(template: str, values: Mapping[str, Paise]) -> str | None:
    try:
        return render(template, values)
    except UnknownPlaceholderError:
        return None
