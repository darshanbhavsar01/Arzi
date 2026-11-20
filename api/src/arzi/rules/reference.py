"""Reference data shipped with the engine: the citation whitelist and IRDAI non-payable items.

Both are versioned JSON inside the package so an audit is reproducible from the code revision
alone. Citations carry a ``status``; anything still ``verify`` is shown with an amber
"Verify before filing" badge and must never be presented as settled regulation.
"""

from functools import cache
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from arzi.domain.enums import CitationStatus, IrdaiList


class RuleCitation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    title: str
    source_doc: str
    ref: str
    summary_en: str
    status: CitationStatus
    url: str | None = None


class NonPayableItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    list: IrdaiList
    number: int = Field(ge=1)
    item: str
    aliases: tuple[str, ...] = Field(min_length=1)
    source: str
    status: CitationStatus


def _load[T](name: str, adapter: TypeAdapter[T]) -> T:
    return adapter.validate_json(files("arzi.rules").joinpath("data", name).read_bytes())


@cache
def citations() -> dict[str, RuleCitation]:
    """The whitelist of regulator references the product may cite, keyed by id."""
    return index_citations(_load("rule_citations.json", TypeAdapter(tuple[RuleCitation, ...])))


def index_citations(entries: tuple[RuleCitation, ...]) -> dict[str, RuleCitation]:
    by_id = {entry.id: entry for entry in entries}
    if len(by_id) != len(entries):
        raise ValueError("duplicate citation id")
    return by_id


@cache
def non_payable_items() -> tuple[NonPayableItem, ...]:
    return _load("irdai_non_payable.json", TypeAdapter(tuple[NonPayableItem, ...]))
