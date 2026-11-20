"""Readiness probes for Firestore and Cloud Storage.

Each probe performs the cheapest call that the runtime service account is actually allowed
to make (least-privilege IAM: ``datastore.user`` and bucket-level ``storage.objectAdmin``),
so a passing probe also proves the IAM wiring, not just network reachability.
"""

from collections.abc import Callable, Iterable
from typing import Any, Protocol

import anyio

from arzi.config import Settings
from arzi.services.readiness import ReadinessProbe

_HEALTH_PREFIX = "_health/"


class _FirestoreQuery(Protocol):
    async def get(self) -> Any: ...  # noqa: ANN401 - SDK returns untyped snapshots


class _FirestoreCollection(Protocol):
    def limit(self, count: int) -> _FirestoreQuery: ...


class FirestoreClientLike(Protocol):
    def collection(self, collection_path: str) -> _FirestoreCollection: ...


class StorageClientLike(Protocol):
    def list_blobs(
        self, bucket_or_name: str, *, max_results: int, prefix: str
    ) -> Iterable[Any]: ...


class FirestoreProbe:
    """Reads at most one document from a collection that normally does not exist."""

    name = "firestore"

    def __init__(self, client: FirestoreClientLike) -> None:
        self._client = client

    async def check(self) -> None:
        await self._client.collection("_health").limit(1).get()


class StorageProbe:
    """Lists at most one object under a reserved prefix in the documents bucket."""

    name = "storage"

    def __init__(self, client: StorageClientLike, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def check(self) -> None:
        def list_one() -> None:
            # The iterator is lazy; consuming it is what issues the request.
            list(self._client.list_blobs(self._bucket, max_results=1, prefix=_HEALTH_PREFIX))

        await anyio.to_thread.run_sync(list_one)


def _default_firestore(settings: Settings) -> FirestoreClientLike:
    # Imported lazily so the SDK loads only when a cloud project is configured.
    from google.cloud import firestore

    client: FirestoreClientLike = firestore.AsyncClient(
        project=settings.google_cloud_project, database=settings.firestore_database
    )
    return client


def _default_storage(settings: Settings) -> StorageClientLike:
    # google-cloud-storage ships no type information (third-party boundary).
    from google.cloud import storage  # type: ignore[attr-defined]

    client: StorageClientLike = storage.Client(project=settings.google_cloud_project)
    return client


def build_readiness_probes(
    settings: Settings,
    *,
    firestore_factory: Callable[[Settings], FirestoreClientLike] = _default_firestore,
    storage_factory: Callable[[Settings], StorageClientLike] = _default_storage,
) -> list[ReadinessProbe]:
    """Probes for whichever dependencies are configured.

    Local development without a GCP project has nothing to probe, which is reported as ready:
    readiness answers "can I serve?", and replay mode can serve without the cloud.
    """
    probes: list[ReadinessProbe] = []
    if settings.google_cloud_project is None:
        return probes
    probes.append(FirestoreProbe(firestore_factory(settings)))
    if settings.bucket is not None:
        probes.append(StorageProbe(storage_factory(settings), settings.bucket))
    return probes
