import uuid
from unittest.mock import MagicMock, patch
import pytest
from agentdrive.services.storage import StorageService


@pytest.fixture
def storage():
    with patch("agentdrive.services.storage._get_storage_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        svc = StorageService()
        svc._bucket = mock_bucket
        yield svc, mock_bucket


def test_generate_gcs_path(storage):
    svc, _ = storage
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    path = svc.generate_path(tenant_id, file_id, "report.pdf")
    assert str(tenant_id) in path
    assert str(file_id) in path
    assert path.endswith("report.pdf")


def test_upload_file(storage):
    svc, mock_bucket = storage
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    path = svc.upload(tenant_id, file_id, "report.pdf", b"file content", "application/pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"file content", content_type="application/pdf")
    assert "report.pdf" in path


def test_download_file(storage):
    svc, mock_bucket = storage
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b"file content"
    mock_bucket.blob.return_value = mock_blob
    data = svc.download("tenants/abc/files/def/report.pdf")
    assert data == b"file content"


def test_delete_file(storage):
    svc, mock_bucket = storage
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    svc.delete("tenants/abc/files/def/report.pdf")
    mock_blob.delete.assert_called_once()
