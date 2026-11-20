"""In-memory adapters: local replay mode with no cloud project, and the test suite.

They implement the same contracts as the Firestore and Cloud Storage adapters, including the
tenant boundary and optimistic concurrency, so behaviour seen locally is behaviour in the cloud.
"""

import datetime as dt
from collections import defaultdict

from arzi.adapters.demo_seed import (
    DEMO_HOSPITAL,
    DEMO_HOSPITAL_ID,
    PUBLIC_HOSPITAL,
    PUBLIC_HOSPITAL_ID,
)
from arzi.domain.enums import ClaimMode, ClaimStatus
from arzi.domain.models import (
    AppealVersion,
    AuditRun,
    ClaimRecord,
    Hospital,
    LlmCall,
    ShareLink,
)
from arzi.services.ports import AuditLogEntry, ClaimPage, ConcurrentUpdateError, StoredDocument


def encode_cursor(record: ClaimRecord) -> str:
    stamp = record.updated_at.isoformat() if record.updated_at else ""
    return f"{stamp}|{record.claim_id}"


def _sort_key(record: ClaimRecord) -> tuple[str, str]:
    return (record.updated_at.isoformat() if record.updated_at else "", record.claim_id)


class InMemoryClaimRepository:
    def __init__(self, hospitals: dict[str, Hospital] | None = None) -> None:
        self._hospitals = (
            hospitals
            if hospitals is not None
            else {DEMO_HOSPITAL_ID: DEMO_HOSPITAL, PUBLIC_HOSPITAL_ID: PUBLIC_HOSPITAL}
        )
        self._claims: dict[tuple[str, str], ClaimRecord] = {}
        self._documents: dict[tuple[str, str], list[StoredDocument]] = defaultdict(list)
        self._runs: dict[tuple[str, str, str], AuditRun] = {}
        self._log: dict[tuple[str, str], list[AuditLogEntry]] = defaultdict(list)
        self.vaults: dict[tuple[str, str], dict[str, str]] = {}
        self._appeals: dict[tuple[str, str, int], AppealVersion] = {}
        self._shares: dict[str, ShareLink] = {}

    async def get_hospital(self, hospital_id: str) -> Hospital | None:
        return self._hospitals.get(hospital_id)

    async def create_claim(self, record: ClaimRecord) -> ClaimRecord:
        key = (record.hospital_id, record.claim_id)
        if key in self._claims:
            raise ConcurrentUpdateError(record.claim_id)
        stored = record.model_copy(update={"revision": 1})
        self._claims[key] = stored
        return stored

    async def get_claim(self, hospital_id: str, claim_id: str) -> ClaimRecord | None:
        return self._claims.get((hospital_id, claim_id))

    async def save_claim(self, record: ClaimRecord) -> ClaimRecord:
        key = (record.hospital_id, record.claim_id)
        current = self._claims.get(key)
        if current is None or current.revision != record.revision:
            raise ConcurrentUpdateError(record.claim_id)
        stored = record.model_copy(update={"revision": record.revision + 1})
        self._claims[key] = stored
        return stored

    async def list_claims(
        self,
        hospital_id: str,
        *,
        status: ClaimStatus | None = None,
        mode: ClaimMode | None = None,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 25,
    ) -> ClaimPage:
        needle = query.lower() if query else None
        rows = sorted(
            (
                r
                for (hid, _), r in self._claims.items()
                if hid == hospital_id
                and (status is None or r.status is status)
                and (mode is None or r.mode is mode)
                and (
                    needle is None
                    or needle in r.claim_id.lower()
                    or needle in (r.insurer_hint or "").lower()
                )
            ),
            key=_sort_key,
            reverse=True,
        )
        if cursor:
            stamp, _, claim_id = cursor.partition("|")
            rows = [r for r in rows if _sort_key(r) < (stamp, claim_id)]
        page = rows[:limit]
        more = len(rows) > limit
        return ClaimPage(items=page, next_cursor=encode_cursor(page[-1]) if more else None)

    async def add_document(self, hospital_id: str, claim_id: str, document: StoredDocument) -> None:
        self._documents[(hospital_id, claim_id)].append(document)

    async def list_documents(self, hospital_id: str, claim_id: str) -> list[StoredDocument]:
        return list(self._documents.get((hospital_id, claim_id), []))

    async def save_run(self, hospital_id: str, claim_id: str, run: AuditRun) -> None:
        self._runs[(hospital_id, claim_id, run.run_id)] = run

    async def get_run(self, hospital_id: str, claim_id: str, run_id: str) -> AuditRun | None:
        return self._runs.get((hospital_id, claim_id, run_id))

    async def find_run_by_key(
        self, hospital_id: str, claim_id: str, idempotency_key: str
    ) -> AuditRun | None:
        return next(
            (
                run
                for (hid, cid, _), run in self._runs.items()
                if (hid, cid) == (hospital_id, claim_id) and run.idempotency_key == idempotency_key
            ),
            None,
        )

    async def append_audit_log(self, hospital_id: str, claim_id: str, entry: AuditLogEntry) -> None:
        self._log[(hospital_id, claim_id)].append(entry)

    async def list_audit_log(self, hospital_id: str, claim_id: str) -> list[AuditLogEntry]:
        return list(self._log.get((hospital_id, claim_id), []))

    async def save_identity_vault(
        self, hospital_id: str, claim_id: str, vault: dict[str, str]
    ) -> None:
        self.vaults[(hospital_id, claim_id)] = dict(vault)

    async def get_identity_vault(self, hospital_id: str, claim_id: str) -> dict[str, str]:
        return dict(self.vaults.get((hospital_id, claim_id), {}))

    async def save_appeal(self, hospital_id: str, appeal: AppealVersion) -> None:
        self._appeals[(hospital_id, appeal.claim_id, appeal.version)] = appeal

    async def get_appeal(
        self, hospital_id: str, claim_id: str, version: int
    ) -> AppealVersion | None:
        return self._appeals.get((hospital_id, claim_id, version))

    async def list_appeals(self, hospital_id: str, claim_id: str) -> list[AppealVersion]:
        found = [a for (h, c, _), a in self._appeals.items() if (h, c) == (hospital_id, claim_id)]
        return sorted(found, key=lambda a: a.version)

    async def save_share(self, share: ShareLink) -> None:
        self._shares[share.token_sha256] = share

    async def get_share(self, token_sha256: str) -> ShareLink | None:
        return self._shares.get(token_sha256)

    async def list_shares(self, hospital_id: str, claim_id: str) -> list[ShareLink]:
        found = [
            s
            for s in self._shares.values()
            if (s.hospital_id, s.claim_id) == (hospital_id, claim_id)
        ]
        return sorted(found, key=lambda s: s.created_at)


class InMemoryBlobStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(
        self, hospital_id: str, claim_id: str, document_id: str, data: bytes, content_type: str
    ) -> str:
        uri = f"memory://hospitals/{hospital_id}/claims/{claim_id}/{document_id}"
        self._blobs[uri] = data
        return uri

    async def get(self, uri: str) -> bytes:
        return self._blobs[uri]

    async def view_url(self, uri: str, *, ttl_s: int = 600) -> str | None:
        return None  # the API streams the bytes itself


class InMemoryCostLedger:
    def __init__(self) -> None:
        self.days: dict[dt.date, int] = defaultdict(int)
        self.calls: dict[dt.date, int] = defaultdict(int)

    async def spent_micro_inr(self, day: dt.date) -> int:
        return self.days[day]

    async def add(self, day: dt.date, call: LlmCall) -> None:
        self.days[day] += call.cost_micro_inr
        self.calls[day] += 1
