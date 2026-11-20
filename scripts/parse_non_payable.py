"""Load IRDAI Annexure I (Lists I-IV) from the official PDF into the engine's reference data.

    python scripts/parse_non_payable.py            # rewrite rules/data/irdai_non_payable.json
    python scripts/parse_non_payable.py --check    # exit 1 if that JSON is out of date

Source: docs/context/irdai/ (see SOURCE.md). The PDF is a scan with an OCR text layer, so the
parser fixes known OCR slips, insists on unbroken item numbering and the exact list sizes, and
leaves every item at status "verify" until a person has reviewed the output.

Aliases drive rupee cuts for List I, so they are generated conservatively. An item whose wording
carries a condition ("other than", "for usage outside", "where", "unless", "with no details")
keeps only its full text, which a matcher cannot satisfy casually. Every alias must contain at
least one specific word, never only "charges".
"""

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
PDF = (
    ROOT
    / "docs/context/irdai/IRDAI_Modification_Guidelines_Standardization_Health_Insurance_2019.pdf"
)
OUT = ROOT / "api/src/arzi/rules/data/irdai_non_payable.json"
REVIEW = PDF.parent / "PARSED_LISTS.md"
SOURCE = "IRDAI Modification Guidelines on Standardization in Health Insurance (27 Sep 2019)"

EXPECTED_SIZES = {"I": 68, "II": 37, "III": 23, "IV": 18}

# OCR slips in the scan's text layer, checked against the page images. Spelling as printed by
# the regulator (e.g. "SHEILD", "TORNIQUET") is kept in `item`; see SPELLING for aliases.
OCR_FIXES = {
    "PEL VIC": "PELVIC",
    "TROLL Y": "TROLLEY",
    "FLEX! MASK": "FLEXI MASK",
    "LUM BO SACRAL": "LUMBO SACRAL",
    "SOLUTIONISTERILLIUM": "SOLUTION/ STERILLIUM",
    "PATIENT's": "PATIENT'S",
}
# Common spellings added as extra aliases, so a correctly spelt bill line still matches.
SPELLING = {
    "sheild": "shield",
    "gause": "gauze",
    "torniquet": "tourniquet",
    "swabes": "swabs",
    "freshners": "fresheners",
    "nebulizer": "nebuliser",
}
CONDITION_WORDS = re.compile(
    r"\b(other than|for usage|outside|where|unless|with no details|not)\b", re.I
)
GENERIC = frozenset({"charges", "charge", "cost", "costs", "expenses", "etc", "of", "and", "any"})
SUFFIXES = ("charges", "charge", "cost")
FILLERS = ("of any type", "etc")

_HEADER = re.compile(r"^List\s*[-\u2013]?\s*(I|II|Ill|III|IV)\s*-\s*", re.I)
_ITEM = re.compile(r"^(\d{1,2})\s+(\S.*)$")
_SKIP = re.compile(r"^(SI\s+Item|No\.?|Page \d+ of \d+|#+.*)$", re.I)


def page_texts(pdf: Path) -> list[str]:
    document = pdfium.PdfDocument(str(pdf))
    try:
        return [page.get_textpage().get_text_range() for page in document]
    finally:
        document.close()


def parse(pages: Sequence[str]) -> dict[str, list[tuple[int, str]]]:
    """Items per list, in printed order. Raises if numbering breaks or a list size is off."""
    text = "\n".join(pages[1:]).replace("￾", "\n").replace("\r", "")
    lists: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or _SKIP.match(line):
            continue
        header = _HEADER.match(line)
        if header:
            current = header.group(1).upper().replace("L", "I")
            lists[current] = []
            continue
        if current is None:
            continue
        items = lists[current]
        numbered = _ITEM.match(line)
        if numbered and int(numbered.group(1)) == len(items) + 1:
            items.append((len(items) + 1, numbered.group(2)))
        elif items:
            number, previous = items[-1]
            items[-1] = (number, f"{previous} {line}")
    sizes = {name: len(items) for name, items in lists.items()}
    if sizes != EXPECTED_SIZES:
        raise ValueError(f"list sizes {sizes} differ from the printed annexure {EXPECTED_SIZES}")
    return lists


def clean(item: str) -> str:
    for wrong, right in OCR_FIXES.items():
        item = item.replace(wrong, right)
    return re.sub(r"\s+", " ", item).strip(" -")


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def _specific(alias: str) -> bool:
    """At least one word that names a thing: not generic, not a two-letter fragment."""
    return any(word not in GENERIC and len(word) > 2 for word in alias.split())


def _strip_filler(phrase: str) -> str:
    for filler in FILLERS:
        phrase = re.sub(rf"\b{filler}\b", " ", phrase)
    return " ".join(phrase.split())


def aliases(item: str) -> list[str]:
    """Match phrases for one item, most literal first."""
    full = " ".join(_words(item))
    if CONDITION_WORDS.search(item):
        return [full]
    base = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", item)  # descriptive parentheticals
    phrases: list[str] = []
    for chunk in re.split(r"\s+-\s*|-\s+|,", base):
        parts = [_strip_filler(" ".join(_words(p))) for p in re.split(r"[/\\&]", chunk)]
        parts = [p for p in parts if p]
        tail = parts[-1].split()[1:] if parts else []
        shared = tail if tail and all(word in SUFFIXES for word in tail) else []
        for part in parts:
            words = part.split()
            if shared and part != parts[-1] and len(words) == 1:
                # "ADMISSION/REGISTRATION CHARGES" means admission and registration charges.
                phrases.append(" ".join([*words, *shared]))
                continue
            phrases.append(part)
            if len(words) > 1 and words[-1] in SUFFIXES:
                phrases.append(" ".join(words[:-1]))
    expanded = [full, *phrases]
    for phrase in list(expanded):
        for wrong, right in SPELLING.items():
            if wrong in phrase.split():
                expanded.append(phrase.replace(wrong, right))
    return list(dict.fromkeys(a for a in expanded if a and _specific(a)))


def entries(lists: dict[str, list[tuple[int, str]]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name in EXPECTED_SIZES:
        for number, raw in lists[name]:
            item = clean(raw)
            rows.append(
                {
                    "list": name,
                    "number": number,
                    "item": item,
                    "aliases": aliases(item),
                    "source": f"{SOURCE}, Annexure I, List {name} item {number}",
                    "status": "verify",
                }
            )
    return rows


def render(rows: Iterable[dict[str, object]]) -> str:
    return json.dumps(list(rows), indent=2, ensure_ascii=False) + "\n"


LIST_TITLES = {
    "I": "List I: optional items (not payable unless an optional cover is in force)",
    "II": "List II: subsumed into room charges",
    "III": "List III: subsumed into procedure charges",
    "IV": "List IV: subsumed into costs of treatment",
}


def render_review(rows: Sequence[dict[str, object]]) -> str:
    """A table a person can check line by line against the scanned pages."""
    out = [
        "# IRDAI Annexure I as parsed (review sheet)",
        "",
        "Generated by `scripts/parse_non_payable.py` from the PDF in this folder; do not edit.",
        "Check each item against the scan. Aliases are what the matcher looks for on a bill line;",
        "an item with a condition in its wording keeps only its full text.",
        "",
    ]
    for name, title in LIST_TITLES.items():
        out += [f"## {title}", "", "| # | Item | Aliases |", "|---|---|---|"]
        for row in rows:
            if row["list"] == name:
                names = row["aliases"]
                joined = "; ".join(map(str, names)) if isinstance(names, list) else ""
                out.append(f"| {row['number']} | {row['item']} | {joined} |")
        out.append("")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the outputs are out of date")
    args = parser.parse_args(argv)
    rows = entries(parse(page_texts(PDF)))
    outputs = {OUT: render(rows), REVIEW: render_review(rows)}
    if args.check:
        stale = [p for p, text in outputs.items() if not p.exists() or p.read_text("utf-8") != text]
        for p in stale:
            print(f"{p} is out of date; run scripts/parse_non_payable.py", file=sys.stderr)
        return 1 if stale else 0
    for p, text in outputs.items():
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
