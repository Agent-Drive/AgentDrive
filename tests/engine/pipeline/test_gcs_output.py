from unittest.mock import MagicMock, patch

from agentdrive.engine.pipeline.storage import StorageService


def _service(mock_client):
    with patch("agentdrive.engine.pipeline.storage._get_s3_client", return_value=mock_client):
        with patch("agentdrive.engine.pipeline.storage.settings") as mock_settings:
            mock_settings.s3_bucket = "test-bucket"
            return StorageService()


def test_list_blobs():
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {"Key": "tmp/docai/abc/output-0.json"},
                {"Key": "tmp/docai/abc/output-1.json"},
            ]
        }
    ]
    service = _service(mock_client)
    names = service.list_blobs("tmp/docai/abc/")
    assert names == ["tmp/docai/abc/output-0.json", "tmp/docai/abc/output-1.json"]


def test_delete_prefix():
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "tmp/a"}, {"Key": "tmp/b"}]}
    ]
    service = _service(mock_client)
    service.delete_prefix("tmp/")
    assert mock_client.delete_object.call_count == 2


def test_upload_bytes():
    mock_client = MagicMock()
    service = _service(mock_client)
    service.upload_bytes("tmp/splits/test.pdf", b"fake pdf bytes", "application/pdf")
    mock_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="tmp/splits/test.pdf",
        Body=b"fake pdf bytes",
        ContentType="application/pdf",
    )
