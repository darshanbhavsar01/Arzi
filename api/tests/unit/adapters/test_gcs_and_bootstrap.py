from pathlib import Path
from typing import Any

import pytest

from arzi.adapters.gcs import GcsBlobStore
from arzi.adapters.genai_client import RecordingLlmClient, ReplayLlmClient
from arzi.adapters.memory import InMemoryCostLedger
from arzi.agents.stubs import FakeLlmClient
from arzi.bootstrap import ConfigurationError, build_llm, build_services, utc_now
from arzi.config import AuthMode, Environment, LlmMode, LlmProvider, Settings
from arzi.services.cost_ledger import BudgetedLlmClient


class FakeBlob:
    def __init__(self, store: dict[str, bytes], path: str, *, can_sign: bool) -> None:
        self._store, self.path, self._can_sign = store, path, can_sign

    def upload_from_string(self, data: bytes, content_type: str) -> None:
        self._store[self.path] = data

    def download_as_bytes(self) -> bytes:
        return self._store[self.path]

    def delete(self) -> None:
        del self._store[self.path]

    def generate_signed_url(self, **kwargs: Any) -> str:  # noqa: ANN401 - SDK keywords
        if not self._can_sign:
            raise AttributeError("credentials cannot sign")
        assert kwargs["version"] == "v4"
        return f"https://signed.example/{self.path}"


class FakeStorage:
    def __init__(self, *, can_sign: bool = True) -> None:
        self.objects: dict[str, bytes] = {}
        self._can_sign = can_sign

    def bucket(self, name: str) -> "FakeStorage":
        return self

    def blob(self, path: str) -> FakeBlob:
        return FakeBlob(self.objects, path, can_sign=self._can_sign)

    def list_blobs(self, bucket: str, *, prefix: str) -> list[FakeBlob]:
        return [self.blob(p) for p in self.objects if p.startswith(prefix)]


async def test_gcs_deletes_every_object_of_one_claim_only() -> None:
    storage = FakeStorage()
    store = GcsBlobStore(storage, "b")
    await store.put("h1", "ARZ-1", "d1", b"a", "application/pdf")
    await store.put("h1", "ARZ-1", "d2", b"b", "application/pdf")
    await store.put("h1", "ARZ-10", "d3", b"c", "application/pdf")
    assert await store.delete_claim("h1", "ARZ-1") == 2
    assert list(storage.objects) == ["hospitals/h1/claims/ARZ-10/d3"]


async def test_gcs_store_put_get_and_sign() -> None:
    storage = FakeStorage()
    store = GcsBlobStore(storage, "arzi-docs")
    uri = await store.put("h1", "ARZ-1", "doc-1", b"%PDF-", "application/pdf")
    assert uri == "gs://arzi-docs/hospitals/h1/claims/ARZ-1/doc-1"
    assert await store.get(uri) == b"%PDF-"
    assert await store.view_url(uri) == "https://signed.example/hospitals/h1/claims/ARZ-1/doc-1"
    with pytest.raises(ValueError, match="bucket"):
        await store.get("gs://someone-else/x")


async def test_gcs_falls_back_to_streaming_when_it_cannot_sign() -> None:
    store = GcsBlobStore(FakeStorage(can_sign=False), "arzi-docs")
    uri = await store.put("h1", "ARZ-1", "doc-1", b"x", "image/png")
    assert await store.view_url(uri) is None


def _settings(**overrides: Any) -> Settings:  # noqa: ANN401 - settings fields
    fields: dict[str, Any] = {"google_cloud_project": None, "bucket": None} | overrides
    return Settings(_env_file=None, **fields)


def test_llm_mode_selects_the_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import arzi.bootstrap

    monkeypatch.setattr(arzi.bootstrap, "vertex_models", lambda *args: object())  # no credentials
    ledger = InMemoryCostLedger()
    assert isinstance(
        build_llm(_settings(llm_mode=LlmMode.REPLAY), ledger, utc_now), ReplayLlmClient
    )
    assert isinstance(build_llm(_settings(llm_mode=LlmMode.FAKE), ledger, utc_now), FakeLlmClient)
    with pytest.raises(ConfigurationError, match="live mode"):
        build_llm(_settings(llm_mode=LlmMode.LIVE), ledger, utc_now)

    live = _settings(llm_mode=LlmMode.LIVE, google_cloud_project="p", model_flash="flash-x")
    assert isinstance(build_llm(live, ledger, utc_now), BudgetedLlmClient)
    recording = live.model_copy(update={"llm_record_dir": tmp_path})
    assert isinstance(build_llm(recording, ledger, utc_now), RecordingLlmClient)


def test_ai_studio_is_free_local_and_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import arzi.bootstrap

    seen: dict[str, Any] = {}

    def fake_models(api_key: str, timeout_s: float) -> object:
        seen["key"] = api_key
        return object()

    monkeypatch.setattr(arzi.bootstrap, "ai_studio_models", fake_models)
    base = {
        "llm_mode": LlmMode.LIVE,
        "llm_provider": LlmProvider.AI_STUDIO,
        "model_flash": "flash-x",
    }
    ledger = InMemoryCostLedger()
    with pytest.raises(ConfigurationError, match="ARZI_GEMINI_API_KEY"):
        build_llm(_settings(**base), ledger, utc_now)
    with pytest.raises(ConfigurationError, match="synthetic data only"):
        build_llm(_settings(**base, env=Environment.CLOUD, gemini_api_key="k"), ledger, utc_now)

    client = build_llm(_settings(**base, gemini_api_key="k"), ledger, utc_now)
    assert isinstance(client, BudgetedLlmClient)
    assert seen["key"] == "k"
    assert client._prices["flash-x"].input_inr_per_1m == 0  # free tier
    assert client._inner._gcs_uris is False  # type: ignore[attr-defined]  # files go inline


def test_vertex_needs_a_project() -> None:
    with pytest.raises(ConfigurationError, match="GOOGLE_CLOUD_PROJECT"):
        build_llm(
            _settings(llm_mode=LlmMode.LIVE, model_flash="flash-x"), InMemoryCostLedger(), utc_now
        )


def test_only_demo_auth_until_phase_7() -> None:
    with pytest.raises(ConfigurationError, match="demo auth"):
        build_services(_settings(auth_mode=AuthMode.FIREBASE))


def test_cloud_project_wires_firestore_and_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.cloud import firestore, storage

    from arzi.adapters.firestore_repo import FirestoreClaimRepository
    from arzi.adapters.gcs import GcsBlobStore as Gcs

    monkeypatch.setattr(firestore, "AsyncClient", lambda **kwargs: object())
    monkeypatch.setattr(storage, "Client", lambda **kwargs: FakeStorage())
    services = build_services(_settings(google_cloud_project="p", bucket="b"))
    assert isinstance(services.repo, FirestoreClaimRepository)
    assert isinstance(services.blobs, Gcs)
