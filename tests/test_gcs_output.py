from unittest.mock import MagicMock, patch

from agentdrive.services.storage import StorageService


def test_list_blobs():
    mock_blob1 = MagicMock()
    mock_blob1.name = "tmp/docai/abc/output-0.json"
    mock_blob2 = MagicMock()
    mock_blob2.name = "tmp/docai/abc/output-1.json"
    with patch("agentdrive.services.storage._get_storage_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        mock_client.bucket.return_value = MagicMock()
        service = StorageService()
        service._bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        names = service.list_blobs("tmp/docai/abc/")
        assert names == ["tmp/docai/abc/output-0.json", "tmp/docai/abc/output-1.json"]


def test_delete_prefix():
    mock_blob1 = MagicMock()
    mock_blob2 = MagicMock()
    with patch("agentdrive.services.storage._get_storage_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        mock_client.bucket.return_value = MagicMock()
        service = StorageService()
        service._bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        service.delete_prefix("tmp/docai/abc/")
        mock_blob1.delete.assert_called_once()
        mock_blob2.delete.assert_called_once()


def test_docai_output_prefix():
    with patch("agentdrive.services.storage._get_storage_client"):
        service = StorageService()
        assert service.docai_output_prefix("abc-123") == "tmp/docai/abc-123/"


def test_gcs_uri():
    with patch("agentdrive.services.storage._get_storage_client") as mock_fn:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.name = "my-bucket"
        mock_client.bucket.return_value = mock_bucket
        mock_fn.return_value = mock_client
        service = StorageService()
        assert service.gcs_uri("some/path.pdf") == "gs://my-bucket/some/path.pdf"


def test_upload_bytes():
    with patch("agentdrive.services.storage._get_storage_client") as mock_fn:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_fn.return_value = mock_client
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        service = StorageService()
        service.upload_bytes("tmp/splits/test.pdf", b"fake pdf bytes", "application/pdf")
        mock_blob.upload_from_string.assert_called_once_with(b"fake pdf bytes", content_type="application/pdf")
