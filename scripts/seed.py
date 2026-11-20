"""Seed the demo hospital profile (fictional) into Firestore.

    GOOGLE_CLOUD_PROJECT=... uv run python ../scripts/seed.py [--dry-run]

Writes one document, ``hospitals/sanjeevani-ahd``, with the room tariff the rules engine uses
for category-based room-rent caps. Idempotent: running it again overwrites the same document.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from arzi.adapters.demo_seed import DEMO_HOSPITAL, DEMO_HOSPITAL_ID
from arzi.config import Settings


async def seed(settings: Settings) -> None:
    from google.cloud import firestore

    from arzi.adapters.firestore_repo import FirestoreClaimRepository

    db = firestore.AsyncClient(
        project=settings.google_cloud_project, database=settings.firestore_database
    )
    await FirestoreClaimRepository(db).seed_hospital(DEMO_HOSPITAL_ID, DEMO_HOSPITAL)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would be written")
    args = parser.parse_args(argv)
    settings = Settings()
    if settings.google_cloud_project is None:
        print("GOOGLE_CLOUD_PROJECT is not set", file=sys.stderr)
        return 2
    target = f"projects/{settings.google_cloud_project}/databases/{settings.firestore_database}"
    print(f"{target}: hospitals/{DEMO_HOSPITAL_ID} ← {DEMO_HOSPITAL.model_dump_json()}")
    if not args.dry_run:
        asyncio.run(seed(settings))
        print("written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
