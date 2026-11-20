import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from arzi.adapters import model_catalog
from arzi.adapters.model_catalog import (
    ListedModel,
    ModelFamily,
    classify,
    filter_models,
    format_table,
    short_id,
)

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "list_models.py"


@dataclass(frozen=True)
class FakeModel:
    name: str | None
    display_name: str | None = None
    supported_actions: list[str] | None = field(default=None)


@pytest.mark.parametrize(
    ("model_id", "family"),
    [
        ("gemini-x-flash", ModelFamily.GEMINI),
        ("gemini-x-pro-preview", ModelFamily.GEMINI),
        ("gemini-x-flash-preview-tts", ModelFamily.TTS),
        ("gemini-x-flash-live-preview", ModelFamily.LIVE),
        ("gemini-x-flash-native-audio", ModelFamily.LIVE),
        ("gemma-x-27b-it", ModelFamily.GEMMA),
        ("imagen-x", None),
        ("text-embedding-x", None),
        ("gemini-deliverable", ModelFamily.GEMINI),
    ],
)
def test_classify(model_id: str, family: ModelFamily | None) -> None:
    assert classify(model_id) is family


def test_short_id_strips_resource_path() -> None:
    assert short_id("publishers/google/models/gemini-x") == "gemini-x"
    assert short_id("gemini-x") == "gemini-x"


def test_filter_models_dedupes_sorts_and_drops_others() -> None:
    models = [
        FakeModel("publishers/google/models/gemini-b", "Gemini B", ["generateContent"]),
        FakeModel("publishers/google/models/imagen-x"),
        FakeModel(None),
        FakeModel("publishers/google/models/gemini-x-tts"),
        FakeModel("publishers/google/models/gemini-a"),
        FakeModel("publishers/google/models/gemini-b", "duplicate"),
    ]

    listed = filter_models(models)

    assert [(m.family, m.model_id, m.display_name) for m in listed] == [
        (ModelFamily.TTS, "gemini-x-tts", "gemini-x-tts"),
        (ModelFamily.GEMINI, "gemini-a", "gemini-a"),
        (ModelFamily.GEMINI, "gemini-b", "Gemini B"),
    ]
    assert listed[2].actions == ("generateContent",)


def test_format_table_aligns_columns() -> None:
    rows = [
        ListedModel(model_id="gemini-a", family=ModelFamily.GEMINI, display_name="A", actions=())
    ]

    assert format_table(rows, "global").splitlines() == [
        "Vertex AI location: global (1 models)",
        "FAMILY  MODEL ID  DISPLAY NAME",
        "gemini  gemini-a  A",
    ]


def test_list_vertex_models_uses_vertex_base_models(monkeypatch: pytest.MonkeyPatch) -> None:
    from google import genai

    captured: dict[str, Any] = {}

    class FakeModels:
        def list(self, config: dict[str, Any]) -> list[FakeModel]:
            captured["config"] = config
            return [FakeModel("publishers/google/models/gemini-a")]

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401 - SDK kwargs
            captured["client"] = kwargs
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)

    listed = model_catalog.list_vertex_models("proj", "asia-south1")

    assert [m.model_id for m in listed] == ["gemini-a"]
    assert captured["client"] == {"vertexai": True, "project": "proj", "location": "asia-south1"}
    assert captured["config"]["query_base"] is True


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("list_models_script", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_prints_each_location_and_survives_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _load_script()

    def fake_list(project: str, location: str) -> list[ListedModel]:
        if location == "global":
            raise PermissionError("no access")
        return [
            ListedModel(
                model_id="gemini-a", family=ModelFamily.GEMINI, display_name="A", actions=()
            )
        ]

    monkeypatch.setattr(script, "list_vertex_models", fake_list)

    assert script.main(["--project", "p"]) == 0
    out = capsys.readouterr().out
    assert "Vertex AI location: asia-south1 (1 models)" in out
    assert "global — listing failed (PermissionError)" in out


def test_script_requires_a_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    script = _load_script()

    with pytest.raises(SystemExit):
        script.main([])
