"""Cloud Storage (asia-south1, uniform access, public access prevention) for uploaded documents.

Objects live at ``hospitals/{hid}/claims/{cid}/{doc_id}``; a lifecycle rule deletes them after
30 days (``infra/``). Viewing uses V4 signed URLs valid for 10 minutes. On Cloud Run that needs
the runtime identity to sign via IAM (``iam.serviceAccountTokenCreator`` on itself); without it,
``view_url`` returns None and the API streams the bytes instead.
"""

import datetime as dt
import logging
from typing import Any

import anyio

logger = logging.getLogger(__name__)

StorageClient = Any  # google-cloud-storage ships no type information


class GcsBlobStore:
    def __init__(self, client: StorageClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def _blob(self, uri: str) -> Any:  # noqa: ANN401 - SDK Blob
        prefix = f"gs://{self._bucket}/"
        if not uri.startswith(prefix):
            raise ValueError("object is not in this deployment's bucket")
        return self._client.bucket(self._bucket).blob(uri.removeprefix(prefix))

    async def put(
        self, hospital_id: str, claim_id: str, document_id: str, data: bytes, content_type: str
    ) -> str:
        path = f"hospitals/{hospital_id}/claims/{claim_id}/{document_id}"
        blob = self._client.bucket(self._bucket).blob(path)
        await anyio.to_thread.run_sync(
            lambda: blob.upload_from_string(data, content_type=content_type)
        )
        return f"gs://{self._bucket}/{path}"

    async def get(self, uri: str) -> bytes:
        blob = self._blob(uri)
        data: bytes = await anyio.to_thread.run_sync(blob.download_as_bytes)
        return data

    async def view_url(self, uri: str, *, ttl_s: int = 600) -> str | None:
        blob = self._blob(uri)

        def sign() -> str:
            url: str = blob.generate_signed_url(
                version="v4", expiration=dt.timedelta(seconds=ttl_s), method="GET"
            )
            return url

        try:
            return await anyio.to_thread.run_sync(sign)
        except Exception as exc:  # signing needs IAM the deployment may not have
            logger.warning("signed URL unavailable (%s); streaming instead", type(exc).__name__)
            return None

    async def delete_claim(self, hospital_id: str, claim_id: str) -> int:
        prefix = f"hospitals/{hospital_id}/claims/{claim_id}/"

        def delete_all() -> int:
            blobs = list(self._client.list_blobs(self._bucket, prefix=prefix))
            for blob in blobs:
                blob.delete()
            return len(blobs)

        removed: int = await anyio.to_thread.run_sync(delete_all)
        return removed
