import uuid
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

    def download(self, gcs_path: str) -> bytes:
        blob = self._bucket.blob(gcs_path)
        return blob.download_as_bytes()

    def delete(self, gcs_path: str) -> None:
        blob = self._bucket.blob(gcs_path)
        blob.delete()
