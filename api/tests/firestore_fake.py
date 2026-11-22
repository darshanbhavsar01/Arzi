"""A small in-memory stand-in for the async Firestore client surface the adapter uses.

Covers documents, sub-collections, equality filters, ordering, ``start_after`` cursors,
``Increment`` transforms, ``create`` conflicts and ``last_update_time`` preconditions.
"""

import itertools
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound
from google.cloud.firestore_v1.transforms import Increment

_clock = itertools.count(1)


@dataclass
class Snapshot:
    id: str
    exists: bool
    _data: dict[str, Any] | None
    update_time: int | None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


@dataclass(frozen=True)
class WriteOption:
    last_update_time: int | None


class FakeFirestore:
    def __init__(self) -> None:
        self.docs: dict[str, tuple[dict[str, Any], int]] = {}
        self._ids = itertools.count(1)

    def collection(self, path: str) -> "Collection":
        return Collection(self, path)

    def write_option(self, *, last_update_time: int | None) -> WriteOption:
        return WriteOption(last_update_time)

    async def recursive_delete(self, reference: "Doc") -> None:
        for path in [
            p for p in self.docs if p == reference.path or p.startswith(f"{reference.path}/")
        ]:
            del self.docs[path]


class Doc:
    def __init__(self, db: FakeFirestore, path: str) -> None:
        self._db = db
        self.path = path

    def collection(self, name: str) -> "Collection":
        return Collection(self._db, f"{self.path}/{name}")

    async def get(self) -> Snapshot:
        found = self._db.docs.get(self.path)
        doc_id = self.path.rsplit("/", 1)[-1]
        if found is None:
            return Snapshot(doc_id, False, None, None)
        return Snapshot(doc_id, True, found[0], found[1])

    async def create(self, data: dict[str, Any]) -> None:
        if self.path in self._db.docs:
            raise AlreadyExists(self.path)  # type: ignore[no-untyped-call]  # untyped SDK
        self._db.docs[self.path] = (dict(data), next(_clock))

    async def set(self, data: dict[str, Any], merge: bool = False) -> None:
        current = dict(self._db.docs.get(self.path, ({}, 0))[0]) if merge else {}
        for key, value in data.items():
            current[key] = (
                current.get(key, 0) + value.value if isinstance(value, Increment) else value
            )
        self._db.docs[self.path] = (current, next(_clock))

    async def delete(self) -> None:
        self._db.docs.pop(self.path, None)

    async def update(self, data: dict[str, Any], option: WriteOption | None = None) -> None:
        found = self._db.docs.get(self.path)
        if found is None:
            raise NotFound(self.path)  # type: ignore[no-untyped-call]  # untyped SDK
        if option is not None and option.last_update_time != found[1]:
            raise FailedPrecondition(self.path)  # type: ignore[no-untyped-call]  # untyped SDK
        self._db.docs[self.path] = ({**found[0], **data}, next(_clock))


def _field(name: str) -> Callable[[Snapshot], Any]:
    def key(snapshot: Snapshot) -> Any:  # noqa: ANN401 - stored values
        return (snapshot.to_dict() or {}).get(name) or ""

    return key


class Collection:
    def __init__(
        self,
        db: FakeFirestore,
        path: str,
        filters: tuple[tuple[str, Any], ...] = (),
        orders: tuple[tuple[str, bool], ...] = (),
        after: dict[str, Any] | None = None,
        limit_to: int | None = None,
    ) -> None:
        self._db, self._path = db, path
        self._filters, self._orders, self._after, self._limit = filters, orders, after, limit_to

    def _copy(self, **changes: Any) -> "Collection":  # noqa: ANN401 - query parts
        state = {
            "filters": self._filters,
            "orders": self._orders,
            "after": self._after,
            "limit_to": self._limit,
        } | changes
        return Collection(self._db, self._path, **state)

    def document(self, doc_id: str) -> Doc:
        return Doc(self._db, f"{self._path}/{doc_id}")

    async def add(self, data: dict[str, Any]) -> None:
        await self.document(f"auto-{next(self._db._ids)}").set(data)

    def where(self, *, filter: Any) -> "Collection":  # noqa: ANN401 - SDK keyword
        assert filter.op_string == "=="
        return self._copy(filters=(*self._filters, (filter.field_path, filter.value)))

    def order_by(self, field: str, direction: str = "ASCENDING") -> "Collection":
        return self._copy(orders=(*self._orders, (field, direction == "DESCENDING")))

    def start_after(self, values: dict[str, Any]) -> "Collection":
        return self._copy(after=values)

    def limit(self, count: int) -> "Collection":
        return self._copy(limit_to=count)

    async def stream(self) -> AsyncIterator[Snapshot]:
        depth = self._path.count("/") + 1
        rows = [
            Snapshot(path.rsplit("/", 1)[-1], True, data, stamp)
            for path, (data, stamp) in self._db.docs.items()
            if path.startswith(f"{self._path}/")
            and path.count("/") == depth
            and all(data.get(field) == value for field, value in self._filters)
        ]
        for field, descending in reversed(self._orders):
            rows.sort(key=_field(field), reverse=descending)
        if self._after is not None:
            key = tuple(self._after[f] or "" for f, _ in self._orders)
            rows = [
                r
                for r in rows
                if tuple((r.to_dict() or {}).get(f) or "" for f, _ in self._orders) < key
            ]
        for row in rows[: self._limit]:
            yield row
