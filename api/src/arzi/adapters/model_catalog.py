"""Discover which Gemini-family models the project can call on Vertex AI.

Model IDs are configuration (``ARZI_MODEL_*``); this module is how the owner finds the current
ones for a given location instead of trusting a hard-coded list that goes stale.
"""

import re
from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ModelFamily(StrEnum):
    TTS = "tts"
    LIVE = "live"
    GEMINI = "gemini"
    GEMMA = "gemma"


class ModelLike(Protocol):
    @property
    def name(self) -> str | None: ...

    @property
    def display_name(self) -> str | None: ...

    @property
    def supported_actions(self) -> list[str] | None: ...


class ListedModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    family: ModelFamily
    display_name: str
    actions: tuple[str, ...]


_TTS = re.compile(r"(^|[-_.])tts([-_.]|$)")
_LIVE = re.compile(r"(^|[-_.])(live|native-audio)([-_.]|$)")


def classify(model_id: str) -> ModelFamily | None:
    """Family by naming convention; TTS and Live are checked first because they are also Gemini."""
    lowered = model_id.lower()
    if _TTS.search(lowered):
        return ModelFamily.TTS
    if _LIVE.search(lowered):
        return ModelFamily.LIVE
    if lowered.startswith("gemini"):
        return ModelFamily.GEMINI
    if lowered.startswith("gemma"):
        return ModelFamily.GEMMA
    return None


def short_id(resource_name: str) -> str:
    """``publishers/google/models/gemini-x`` → ``gemini-x`` (the form settings expect)."""
    return resource_name.rsplit("/", 1)[-1]


def filter_models(models: Iterable[ModelLike]) -> list[ListedModel]:
    """Keep gemini/gemma/tts/live models, de-duplicated and sorted by family then ID."""
    seen: dict[str, ListedModel] = {}
    for model in models:
        if not model.name:
            continue
        model_id = short_id(model.name)
        family = classify(model_id)
        if family is None or model_id in seen:
            continue
        seen[model_id] = ListedModel(
            model_id=model_id,
            family=family,
            display_name=model.display_name or model_id,
            actions=tuple(model.supported_actions or ()),
        )
    order = list(ModelFamily)
    return sorted(seen.values(), key=lambda m: (order.index(m.family), m.model_id))


def format_table(models: Iterable[ListedModel], location: str) -> str:
    rows = [("FAMILY", "MODEL ID", "DISPLAY NAME")]
    rows += [(m.family.value, m.model_id, m.display_name) for m in models]
    widths = [max(len(row[i]) for row in rows) for i in range(2)]
    lines = [f"{r[0]:<{widths[0]}}  {r[1]:<{widths[1]}}  {r[2]}".rstrip() for r in rows]
    count = len(rows) - 1
    return "\n".join([f"Vertex AI location: {location} ({count} models)", *lines])


def list_vertex_models(project: str, location: str) -> list[ListedModel]:
    """Query Vertex AI for publisher base models visible to ``project`` in ``location``."""
    # Imported lazily: only the model-listing command needs the SDK.
    from google import genai

    client = genai.Client(vertexai=True, project=project, location=location)
    return filter_models(client.models.list(config={"query_base": True, "page_size": 100}))
