import uuid
from unittest.mock import MagicMock, patch

from agentdrive.services.storage import StorageService


def test_generate_signed_upload_url():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"

        service = StorageService()
        url = service.generate_signed_upload_url(
            uuid.uuid4(), uuid.uuid4(), "large.pdf", "application/pdf"
        )

        assert url == "https://storage.googleapis.com/signed-url"
        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["content_type"] == "application/pdf"


def test_blob_exists():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_client.bucket.return_value = MagicMock()
        service = StorageService()
        mock_blob = MagicMock()
        service._bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        assert service.blob_exists("test/path") is True
        mock_blob.exists.assert_called_once()


def test_get_blob_size():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_client.bucket.return_value = MagicMock()
        service = StorageService()
        mock_blob = MagicMock()
        service._bucket.blob.return_value = mock_blob
        mock_blob.size = 50_000_000
        assert service.get_blob_size("test/path") == 50_000_000
        mock_blob.reload.assert_called_once()
