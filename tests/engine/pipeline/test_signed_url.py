import uuid
from unittest.mock import MagicMock, patch

from agentdrive.engine.pipeline.storage import StorageService


def _service(mock_client):
    with patch("agentdrive.engine.pipeline.storage._get_s3_client", return_value=mock_client):
        with patch("agentdrive.engine.pipeline.storage.settings") as mock_settings:
            mock_settings.s3_bucket = "test-bucket"
            return StorageService()


def test_generate_signed_upload_url():
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://s3.example/signed-url"
    service = _service(mock_client)
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    url = service.generate_signed_upload_url(
        tenant_id, file_id, "large.pdf", "application/pdf"
    )

    assert url == "https://s3.example/signed-url"
    kwargs = mock_client.generate_presigned_url.call_args
    assert kwargs[0][0] == "put_object"
    params = kwargs[1]["Params"]
    assert params["Bucket"] == "test-bucket"
    assert params["Key"].endswith("large.pdf")
    assert params["ContentType"] == "application/pdf"
    assert kwargs[1]["ExpiresIn"] == 3600


def test_blob_exists():
    mock_client = MagicMock()
    mock_client.head_object.return_value = {}
    service = _service(mock_client)
    assert service.blob_exists("test/path") is True
    mock_client.head_object.assert_called_once_with(Bucket="test-bucket", Key="test/path")


def test_blob_exists_missing():
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    mock_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )
    service = _service(mock_client)
    assert service.blob_exists("test/path") is False


def test_get_blob_size():
    mock_client = MagicMock()
    mock_client.head_object.return_value = {"ContentLength": 50_000_000}
    service = _service(mock_client)
    assert service.get_blob_size("test/path") == 50_000_000
