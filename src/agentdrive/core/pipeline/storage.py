import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from agentdrive.config import settings

_s3_client = None


def _is_not_found(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            region_name=settings.s3_region or "auto",
            config=Config(s3={"addressing_style": "virtual"}),
        )
    return _s3_client


class StorageService:
    def __init__(self) -> None:
        self._client = _get_s3_client()
        self._bucket = settings.s3_bucket

    def generate_path(self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
        return f"tenants/{tenant_id}/files/{file_id}/{filename}"

    def upload(self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str, data: bytes, content_type: str) -> str:
        path = self.generate_path(tenant_id, file_id, filename)
        self.upload_bytes(path, data, content_type)
        return path

    def download_to_tempfile(self, object_key: str) -> Path:
        """Download an object to a temporary file on disk. Caller must clean up."""
        suffix = Path(object_key).suffix or ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()
        self._client.download_file(self._bucket, object_key, tmp.name)
        return Path(tmp.name)

    def download_stream(
        self, object_key: str, chunk_size: int = 256 * 1024
    ) -> Iterator[bytes]:
        """Yield file content in chunks. Raises if the object does not exist."""
        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise FileNotFoundError(f"Object not found: {object_key}") from exc
            raise
        body = obj["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk

    def download(self, object_key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=object_key)
        return obj["Body"].read()

    def delete(self, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)

    def list_blobs(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                keys.append(obj["Key"])
        return keys

    def delete_prefix(self, prefix: str) -> None:
        for key in self.list_blobs(prefix):
            self.delete(key)

    def upload_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

    def delete_blob(self, object_key: str) -> None:
        self.delete(object_key)

    def generate_signed_upload_url(
        self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str,
        content_type: str, expiry_hours: int = 1,
    ) -> str:
        path = self.generate_path(tenant_id, file_id, filename)
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": path,
                "ContentType": content_type,
            },
            ExpiresIn=expiry_hours * 3600,
        )

    def generate_signed_download_url(
        self, object_key: str, filename: str, expiry_hours: int = 1,
    ) -> str:
        safe_filename = filename.replace('"', "_")
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": object_key,
                "ResponseContentDisposition": f'attachment; filename="{safe_filename}"',
            },
            ExpiresIn=expiry_hours * 3600,
        )

    def blob_exists(self, object_key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise

    def get_blob_size(self, object_key: str) -> int:
        return self._client.head_object(Bucket=self._bucket, Key=object_key)["ContentLength"]
