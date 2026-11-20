import datetime as dt

import pytest

from arzi.adapters.demo_seed import DEMO_HOSPITAL
from arzi.adapters.firestore_repo import FirestoreClaimRepository, FirestoreCostLedger
from arzi.domain.enums import ClaimMode, ClaimStatus
from arzi.domain.models import AuditRun, ClaimRecord, LlmCall
from arzi.services.ports import AuditLogEntry, ConcurrentUpdateError, StoredDocument
from tests.firestore_fake import FakeFirestore

T0 = dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.UTC)


def _record(claim_id: str, minutes: int = 0, **extra: object) -> ClaimRecord:
    stamp = T0 + dt.timedelta(minutes=minutes)
    return ClaimRecord.model_validate(
        {
            "hospital_id": "h1",
            "claim_id": claim_id,
            "created_at": stamp,
            "updated_at": stamp,
            **extra,
        }
    )


@pytest.fixture
def db() -> FakeFirestore:
    return FakeFirestore()


@pytest.fixture
def repo(db: FakeFirestore) -> FirestoreClaimRepository:
    return FirestoreClaimRepository(db)


async def test_claims_round_trip_with_optimistic_concurrency(
    repo: FirestoreClaimRepository,
) -> None:
    created = await repo.create_claim(_record("ARZ-1"))
    assert created.revision == 1
    with pytest.raises(ConcurrentUpdateError):
        await repo.create_claim(_record("ARZ-1"))

    saved = await repo.save_claim(
        created.model_copy(update={"status": ClaimStatus.DOCUMENTS_UPLOADED})
    )
    assert saved.revision == 2
    assert await repo.get_claim("h1", "ARZ-1") == saved
    with pytest.raises(ConcurrentUpdateError):
        await repo.save_claim(created)  # stale revision
    with pytest.raises(ConcurrentUpdateError):
        await repo.save_claim(_record("ARZ-404", revision=1))
    assert await repo.get_claim("other-hospital", "ARZ-1") is None


async def test_a_write_between_read_and_update_loses(
    repo: FirestoreClaimRepository, db: FakeFirestore
) -> None:
    created = await repo.create_claim(_record("ARZ-1"))
    original_get = db.collection("hospitals/h1/claims").document("ARZ-1").get

    class Racing:
        """Another writer commits right after our read."""

        def __init__(self, inner: object) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

        async def get(self) -> object:
            snapshot = await original_get()
            await db.collection("hospitals/h1/claims").document("ARZ-1").set({"revision": 1})
            return snapshot

    repo._claim = lambda hid, cid: Racing(db.collection(f"hospitals/{hid}/claims").document(cid))  # type: ignore[method-assign]
    with pytest.raises(ConcurrentUpdateError):
        await repo.save_claim(created)


async def test_listing_filters_orders_and_pages(repo: FirestoreClaimRepository) -> None:
    for i in range(3):
        await repo.create_claim(_record(f"ARZ-{i}", minutes=i, insurer_hint="Suraksha"))
    await repo.create_claim(_record("ARZ-X", minutes=9, mode=ClaimMode.POST_DEDUCTION))

    first = await repo.list_claims("h1", limit=2)
    assert [c.claim_id for c in first.items] == ["ARZ-X", "ARZ-2"]
    second = await repo.list_claims("h1", limit=2, cursor=first.next_cursor)
    assert [c.claim_id for c in second.items] == ["ARZ-1", "ARZ-0"]
    assert second.next_cursor is None
    deduction = await repo.list_claims("h1", mode=ClaimMode.POST_DEDUCTION)
    assert [c.claim_id for c in deduction.items] == ["ARZ-X"]
    assert (await repo.list_claims("h1", status=ClaimStatus.AUDITED)).items == []
    searched = await repo.list_claims("h1", query="suraksha", limit=2)
    assert len(searched.items) == 2
    assert searched.next_cursor is not None


async def test_documents_runs_log_vault_and_hospital(
    repo: FirestoreClaimRepository, db: FakeFirestore
) -> None:
    await repo.create_claim(_record("ARZ-1"))
    document = StoredDocument(
        document_id="doc-1",
        filename="bill.pdf",
        content_type="application/pdf",
        size_bytes=10,
        pages=1,
        sha256="0" * 64,
        uri="gs://b/x",
        uploaded_at=T0,
    )
    await repo.add_document("h1", "ARZ-1", document)
    assert await repo.list_documents("h1", "ARZ-1") == [document]

    run = AuditRun(run_id="run-1", engine_version="v", started_at=T0, idempotency_key="k1")
    await repo.save_run("h1", "ARZ-1", run)
    assert await repo.get_run("h1", "ARZ-1", "run-1") == run
    assert await repo.get_run("h1", "ARZ-1", "run-2") is None
    assert await repo.find_run_by_key("h1", "ARZ-1", "k1") == run
    assert await repo.find_run_by_key("h1", "ARZ-1", "k2") is None

    entry = AuditLogEntry(at=T0, actor="u", action="claim.created")
    await repo.append_audit_log("h1", "ARZ-1", entry)
    assert await repo.list_audit_log("h1", "ARZ-1") == [entry]

    await repo.save_identity_vault("h1", "ARZ-1", {"P-ABCD": "Name"})
    assert db.docs["hospitals/h1/claims/ARZ-1/restricted/identity"][0] == {
        "values": {"P-ABCD": "Name"}
    }

    assert await repo.get_hospital("h1") is None
    await repo.seed_hospital("h1", DEMO_HOSPITAL)
    assert await repo.get_hospital("h1") == DEMO_HOSPITAL


async def test_cost_ledger_increments(db: FakeFirestore) -> None:
    ledger = FirestoreCostLedger(db)
    day = dt.date(2026, 11, 20)
    assert await ledger.spent_micro_inr(day) == 0
    call = LlmCall(
        prompt_ref="p",
        model="m",
        input_tokens=10,
        output_tokens=5,
        thinking_tokens=1,
        cost_micro_inr=700,
    )
    await ledger.add(day, call)
    await ledger.add(day, call)
    assert await ledger.spent_micro_inr(day) == 1400
    assert db.docs["cost_ledger/2026-11-20"][0]["output_tokens"] == 12
