from collections.abc import Iterator
from typing import Any

import pytest

from arzi.adapters.readiness_probes import (
    FirestoreProbe,
    StorageProbe,
    build_readiness_probes,
)
from arzi.config import Settings


class _Query:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def get(self) -> list[Any]:
        self._log.append("get")
        return []


class _Collection:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def limit(self, count: int) -> _Query:
        self._log.append(f"limit:{count}")
        return _Query(self._log)


class FakeFirestore:
    def __init__(self) -> None:
        self.log: list[str] = []

    def collection(self, collection_path: str) -> _Collection:
        self.log.append(f"collection:{collection_path}")
        return _Collection(self.log)


class FakeStorage:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, int, str]] = []
        self._error = error

    def list_blobs(self, bucket_or_name: str, *, max_results: int, prefix: str) -> Iterator[Any]:
        self.calls.append((bucket_or_name, max_results, prefix))

        def pages() -> Iterator[Any]:
            if self._error is not None:
                raise self._error
            yield from ()

        return pages()


async def test_firestore_probe_reads_at_most_one_document() -> None:
    client = FakeFirestore()

    await FirestoreProbe(client).check()

    assert client.log == ["collection:_health", "limit:1", "get"]


async def test_storage_probe_consumes_the_lazy_listing() -> None:
    client = FakeStorage(error=PermissionError("denied"))

    with pytest.raises(PermissionError):
        await StorageProbe(client, "docs-bucket").check()
    assert client.calls == [("docs-bucket", 1, "_health/")]


def _settings(**overrides: Any) -> Settings:  # noqa: ANN401 - mirrors Settings kwargs
    return Settings(_env_file=None, **overrides)


def test_no_project_means_no_probes() -> None:
    assert build_readiness_probes(_settings(google_cloud_project=None)) == []


def test_project_without_bucket_probes_firestore_only() -> None:
    probes = build_readiness_probes(
        _settings(google_cloud_project="p", bucket=None),
        firestore_factory=lambda _: FakeFirestore(),
    )

    assert [p.name for p in probes] == ["firestore"]


def test_project_and_bucket_probe_both() -> None:
    probes = build_readiness_probes(
        _settings(google_cloud_project="p", bucket="b"),
        firestore_factory=lambda _: FakeFirestore(),
        storage_factory=lambda _: FakeStorage(),
    )

    assert [p.name for p in probes] == ["firestore", "storage"]


def test_default_factories_build_real_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr("google.cloud.firestore.AsyncClient", lambda **kw: built.append(("fs", kw)))
    monkeypatch.setattr("google.cloud.storage.Client", lambda **kw: built.append(("gcs", kw)))

    build_readiness_probes(_settings(google_cloud_project="p", bucket="b"))

    assert built == [
        ("fs", {"project": "p", "database": "(default)"}),
        ("gcs", {"project": "p"}),
    ]
