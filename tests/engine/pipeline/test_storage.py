import uuid
from unittest.mock import MagicMock, patch

import pytest

from agentdrive.engine.pipeline.storage import StorageService


@pytest.fixture
def storage():
    with patch("agentdrive.engine.pipeline.storage._get_s3_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        with patch("agentdrive.engine.pipeline.storage.settings") as mock_settings:
            mock_settings.s3_bucket = "test-bucket"
            svc = StorageService()
            yield svc, mock_client


def test_generate_object_path(storage):
    svc, _ = storage
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    path = svc.generate_path(tenant_id, file_id, "report.pdf")
    assert str(tenant_id) in path
    assert str(file_id) in path
    assert path.endswith("report.pdf")


def test_upload_file(storage):
    svc, mock_client = storage
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    path = svc.upload(tenant_id, file_id, "report.pdf", b"file content", "application/pdf")
    mock_client.put_object.assert_called_once()
    kwargs = mock_client.put_object.call_args[1]
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Body"] == b"file content"
    assert kwargs["ContentType"] == "application/pdf"
    assert kwargs["Key"].endswith("report.pdf")
    assert "report.pdf" in path


def test_download_file(storage):
    svc, mock_client = storage
    body = MagicMock()
    body.read.return_value = b"file content"
    mock_client.get_object.return_value = {"Body": body}
    data = svc.download("tenants/abc/files/def/report.pdf")
    assert data == b"file content"
    mock_client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="tenants/abc/files/def/report.pdf"
    )


def test_generate_signed_download_url(storage):
    svc, mock_client = storage
    mock_client.generate_presigned_url.return_value = "https://storage.example/get"
    url = svc.generate_signed_download_url("tenants/abc/files/def/report.pdf", "report.pdf")
    assert url == "https://storage.example/get"
    mock_client.generate_presigned_url.assert_called_once()
    kwargs = mock_client.generate_presigned_url.call_args
    assert kwargs[0][0] == "get_object"
    assert kwargs[1]["Params"]["Key"] == "tenants/abc/files/def/report.pdf"


def test_delete_file(storage):
    svc, mock_client = storage
    svc.delete("tenants/abc/files/def/report.pdf")
    mock_client.delete_object.assert_called_once_with(
        Bucket="test-bucket", Key="tenants/abc/files/def/report.pdf"
    )
