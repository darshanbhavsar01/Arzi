"""Firestore (Native, asia-south1) implementations of the claim repository and cost ledger.

Layout (``docs/BUILD_PLAN.md`` §3.1)::

    hospitals/{hid}                                  hospital profile and room tariff
    hospitals/{hid}/claims/{cid}                     ClaimRecord
    hospitals/{hid}/claims/{cid}/documents/{did}     StoredDocument
    hospitals/{hid}/claims/{cid}/runs/{rid}          AuditRun with its events and model calls
    hospitals/{hid}/claims/{cid}/events/{eid}        append-only audit log
    hospitals/{hid}/claims/{cid}/restricted/identity pseudonym → original identifiers
    hospitals/{hid}/claims/{cid}/appeals/{version}   AppealVersion (immutable content)
    share_tokens/{sha256(token)}                     ShareLink (the token itself is never stored)
    cost_ledger/{yyyy-mm-dd}                         daily cost and token totals

Concurrency: a claim write compares the stored ``revision`` and then writes with a
``last_update_time`` precondition, so two writers that read the same revision cannot both win.
"""

import datetime as dt
from typing import Any

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

# The Firestore SDK is only partly typed; values crossing this boundary are plain dicts.
Client = Any
_QUERY_SCAN_LIMIT = 200


def _cursor(data: dict[str, Any]) -> str:
    return f"{data.get('updated_at') or ''}|{data['claim_id']}"


class FirestoreClaimRepository:
    def __init__(self, client: Client) -> None:
        self._db = client

    def _claim(self, hid: str, cid: str) -> Any:  # noqa: ANN401 - SDK DocumentReference
        return self._db.collection(f"hospitals/{hid}/claims").document(cid)

    async def get_hospital(self, hospital_id: str) -> Hospital | None:
        snap = await self._db.collection("hospitals").document(hospital_id).get()
        return Hospital.model_validate(snap.to_dict()) if snap.exists else None

    async def create_claim(self, record: ClaimRecord) -> ClaimRecord:
        from google.api_core.exceptions import AlreadyExists

        stored = record.model_copy(update={"revision": 1})
        try:
            await self._claim(record.hospital_id, record.claim_id).create(
                stored.model_dump(mode="json")
            )
        except AlreadyExists:
            raise ConcurrentUpdateError(record.claim_id) from None
        return stored

    async def get_claim(self, hospital_id: str, claim_id: str) -> ClaimRecord | None:
        snap = await self._claim(hospital_id, claim_id).get()
        return ClaimRecord.model_validate(snap.to_dict()) if snap.exists else None

    async def save_claim(self, record: ClaimRecord) -> ClaimRecord:
        from google.api_core.exceptions import FailedPrecondition, NotFound

        ref = self._claim(record.hospital_id, record.claim_id)
        snap = await ref.get()
        if not snap.exists or (snap.to_dict() or {}).get("revision") != record.revision:
            raise ConcurrentUpdateError(record.claim_id)
        stored = record.model_copy(update={"revision": record.revision + 1})
        option = self._db.write_option(last_update_time=snap.update_time)
        try:
            # update() (unlike set()) honours the precondition; the dump carries every field.
            await ref.update(stored.model_dump(mode="json"), option=option)
        except (FailedPrecondition, NotFound):
            raise ConcurrentUpdateError(record.claim_id) from None
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
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = self._db.collection(f"hospitals/{hospital_id}/claims")
        if status is not None:
            q = q.where(filter=FieldFilter("status", "==", str(status)))
        if mode is not None:
            q = q.where(filter=FieldFilter("mode", "==", str(mode)))
        q = q.order_by("updated_at", direction="DESCENDING").order_by(
            "claim_id", direction="DESCENDING"
        )
        if cursor:
            stamp, _, claim_id = cursor.partition("|")
            q = q.start_after({"updated_at": stamp or None, "claim_id": claim_id})
        # Substring search is not a Firestore query; scan a bounded window instead.
        q = q.limit(_QUERY_SCAN_LIMIT if query else limit + 1)
        rows = [snap.to_dict() async for snap in q.stream()]
        if query:
            needle = query.lower()
            rows = [
                r
                for r in rows
                if needle in r["claim_id"].lower()
                or needle in (r.get("insurer_hint") or "").lower()
            ]
        page, more = rows[:limit], len(rows) > limit
        return ClaimPage(
            items=[ClaimRecord.model_validate(r) for r in page],
            next_cursor=_cursor(page[-1]) if more and page else None,
        )

    async def add_document(self, hospital_id: str, claim_id: str, document: StoredDocument) -> None:
        ref = (
            self._claim(hospital_id, claim_id)
            .collection("documents")
            .document(document.document_id)
        )
        await ref.set(document.model_dump(mode="json"))

    async def list_documents(self, hospital_id: str, claim_id: str) -> list[StoredDocument]:
        q = self._claim(hospital_id, claim_id).collection("documents").order_by("uploaded_at")
        return [StoredDocument.model_validate(s.to_dict()) async for s in q.stream()]

    async def save_run(self, hospital_id: str, claim_id: str, run: AuditRun) -> None:
        ref = self._claim(hospital_id, claim_id).collection("runs").document(run.run_id)
        await ref.set(run.model_dump(mode="json"))

    async def get_run(self, hospital_id: str, claim_id: str, run_id: str) -> AuditRun | None:
        snap = await self._claim(hospital_id, claim_id).collection("runs").document(run_id).get()
        return AuditRun.model_validate(snap.to_dict()) if snap.exists else None

    async def find_run_by_key(
        self, hospital_id: str, claim_id: str, idempotency_key: str
    ) -> AuditRun | None:
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = (
            self._claim(hospital_id, claim_id)
            .collection("runs")
            .where(filter=FieldFilter("idempotency_key", "==", idempotency_key))
            .limit(1)
        )
        found = [AuditRun.model_validate(s.to_dict()) async for s in q.stream()]
        return found[0] if found else None

    async def append_audit_log(self, hospital_id: str, claim_id: str, entry: AuditLogEntry) -> None:
        await (
            self._claim(hospital_id, claim_id)
            .collection("events")
            .add(entry.model_dump(mode="json"))
        )

    async def list_audit_log(self, hospital_id: str, claim_id: str) -> list[AuditLogEntry]:
        q = self._claim(hospital_id, claim_id).collection("events").order_by("at")
        return [AuditLogEntry.model_validate(s.to_dict()) async for s in q.stream()]

    async def save_identity_vault(
        self, hospital_id: str, claim_id: str, vault: dict[str, str]
    ) -> None:
        ref = self._claim(hospital_id, claim_id).collection("restricted").document("identity")
        await ref.set({"values": vault})

    async def get_identity_vault(self, hospital_id: str, claim_id: str) -> dict[str, str]:
        ref = self._claim(hospital_id, claim_id).collection("restricted").document("identity")
        snap = await ref.get()
        data = snap.to_dict() if snap.exists else None
        return dict((data or {}).get("values", {}))

    async def save_appeal(self, hospital_id: str, appeal: AppealVersion) -> None:
        ref = (
            self._claim(hospital_id, appeal.claim_id)
            .collection("appeals")
            .document(str(appeal.version))
        )
        await ref.set(appeal.model_dump(mode="json"))

    async def get_appeal(
        self, hospital_id: str, claim_id: str, version: int
    ) -> AppealVersion | None:
        ref = self._claim(hospital_id, claim_id).collection("appeals").document(str(version))
        snap = await ref.get()
        return AppealVersion.model_validate(snap.to_dict()) if snap.exists else None

    async def list_appeals(self, hospital_id: str, claim_id: str) -> list[AppealVersion]:
        q = self._claim(hospital_id, claim_id).collection("appeals").order_by("version")
        return [AppealVersion.model_validate(s.to_dict()) async for s in q.stream()]

    async def save_share(self, share: ShareLink) -> None:
        ref = self._db.collection("share_tokens").document(share.token_sha256)
        await ref.set(share.model_dump(mode="json"))

    async def get_share(self, token_sha256: str) -> ShareLink | None:
        snap = await self._db.collection("share_tokens").document(token_sha256).get()
        return ShareLink.model_validate(snap.to_dict()) if snap.exists else None

    async def list_shares(self, hospital_id: str, claim_id: str) -> list[ShareLink]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = (
            self._db.collection("share_tokens")
            .where(filter=FieldFilter("hospital_id", "==", hospital_id))
            .where(filter=FieldFilter("claim_id", "==", claim_id))
        )
        found = [ShareLink.model_validate(s.to_dict()) async for s in q.stream()]
        return sorted(found, key=lambda s: s.created_at)

    async def seed_hospital(self, hospital_id: str, hospital: Hospital) -> None:
        await (
            self._db.collection("hospitals")
            .document(hospital_id)
            .set(hospital.model_dump(mode="json"))
        )


class FirestoreCostLedger:
    def __init__(self, client: Client) -> None:
        self._db = client

    async def spent_micro_inr(self, day: dt.date) -> int:
        snap = await self._db.collection("cost_ledger").document(day.isoformat()).get()
        return int((snap.to_dict() or {}).get("cost_micro_inr", 0)) if snap.exists else 0

    async def add(self, day: dt.date, call: LlmCall) -> None:
        from google.cloud.firestore_v1.transforms import Increment

        await (
            self._db.collection("cost_ledger")
            .document(day.isoformat())
            .set(
                {
                    "cost_micro_inr": Increment(call.cost_micro_inr),
                    "calls": Increment(1),
                    "input_tokens": Increment(call.input_tokens),
                    "output_tokens": Increment(call.output_tokens + call.thinking_tokens),
                },
                merge=True,
            )
        )
