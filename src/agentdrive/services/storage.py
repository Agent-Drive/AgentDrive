import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

from google.cloud import storage as gcs

from agentdrive.config import settings

storage_client = gcs.Client()


class StorageService:
    def __init__(self) -> None:
        self._bucket = storage_client.bucket(settings.gcs_bucket)

    def generate_path(self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
        return f"tenants/{tenant_id}/files/{file_id}/{filename}"

    def upload(self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str, data: bytes, content_type: str) -> str:
        path = self.generate_path(tenant_id, file_id, filename)
        blob = self._bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)
        return path

    def download_to_tempfile(self, gcs_path: str) -> Path:
        """Download a GCS blob to a temporary file on disk. Caller must clean up."""
        suffix = Path(gcs_path).suffix or ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()
        blob = self._bucket.blob(gcs_path)
        blob.download_to_filename(tmp.name)
        return Path(tmp.name)

    def download_stream(
        self, gcs_path: str, chunk_size: int = 256 * 1024
    ) -> Iterator[bytes]:
        """Yield file content in chunks from GCS. Raises if blob does not exist."""
        blob = self._bucket.blob(gcs_path)
        if not blob.exists():
            raise FileNotFoundError(f"Blob not found: {gcs_path}")
        with blob.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def download(self, gcs_path: str) -> bytes:
        blob = self._bucket.blob(gcs_path)
        return blob.download_as_bytes()

    def delete(self, gcs_path: str) -> None:
        blob = self._bucket.blob(gcs_path)
        blob.delete()

    def list_blobs(self, prefix: str) -> list[str]:
        return [blob.name for blob in self._bucket.list_blobs(prefix=prefix)]

    def delete_prefix(self, prefix: str) -> None:
        for blob in self._bucket.list_blobs(prefix=prefix):
            blob.delete()

    def docai_output_prefix(self, file_id: str) -> str:
        return f"tmp/docai/{file_id}/"

    def gcs_uri(self, path: str) -> str:
        return f"gs://{self._bucket.name}/{path}"

    def upload_bytes(self, gcs_path: str, data: bytes, content_type: str) -> None:
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_string(data, content_type=content_type)

    def delete_blob(self, gcs_path: str) -> None:
        self.delete(gcs_path)

    def generate_signed_upload_url(
        self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str,
        content_type: str, expiry_hours: int = 1,
    ) -> str:
        """Generate a V4 signed URL for direct-to-GCS upload.

        Requires service account credentials (not user ADC).
        """
        from datetime import timedelta
        path = self.generate_path(tenant_id, file_id, filename)
        blob = self._bucket.blob(path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=expiry_hours),
            method="PUT",
            content_type=content_type,
        )

    def blob_exists(self, gcs_path: str) -> bool:
        blob = self._bucket.blob(gcs_path)
        return blob.exists()

    def get_blob_size(self, gcs_path: str) -> int:
        blob = self._bucket.blob(gcs_path)
        blob.reload()
        return blob.size
