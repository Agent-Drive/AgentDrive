"""Tests for streaming download and chunk_file interface."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.pdf import PdfChunker
from agentdrive.services.storage import StorageService


# ---------------------------------------------------------------------------
# StorageService.download_to_tempfile
# ---------------------------------------------------------------------------


@patch("agentdrive.services.storage._get_s3_client")
@patch("agentdrive.services.storage.settings")
def test_download_to_tempfile(mock_settings, mock_get_client):
    """download_to_tempfile returns a path with correct extension and file content."""
    mock_settings.s3_bucket = "test-bucket"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.download_file.side_effect = lambda bucket, key, filename: Path(filename).write_bytes(
        b"fake-pdf-content"
    )

    svc = StorageService()
    result = svc.download_to_tempfile("tenants/abc/files/123/report.pdf")

    try:
        assert isinstance(result, Path)
        assert result.suffix == ".pdf"
        assert result.exists()
        assert result.read_bytes() == b"fake-pdf-content"
        mock_client.download_file.assert_called_once()
        assert mock_client.download_file.call_args[0][1] == "tenants/abc/files/123/report.pdf"
    finally:
        result.unlink(missing_ok=True)


@patch("agentdrive.services.storage._get_s3_client")
@patch("agentdrive.services.storage.settings")
def test_download_to_tempfile_preserves_extension(mock_settings, mock_get_client):
    """download_to_tempfile preserves .xlsx extension."""
    mock_settings.s3_bucket = "test-bucket"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    svc = StorageService()
    result = svc.download_to_tempfile("tenants/abc/files/123/data.xlsx")

    try:
        assert result.suffix == ".xlsx"
    finally:
        result.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# BaseChunker.chunk_file default delegation
# ---------------------------------------------------------------------------


class StubChunker(BaseChunker):
    """Minimal concrete chunker for testing default chunk_file behavior."""

    def __init__(self):
        self.chunk_bytes_called_with: tuple | None = None

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        return []

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        self.chunk_bytes_called_with = (data, filename, metadata)
        return []

    def supported_types(self) -> list[str]:
        return ["text/plain"]


def test_base_chunker_chunk_file_delegates_to_chunk_bytes(tmp_path):
    """Default chunk_file reads file bytes and delegates to chunk_bytes."""
    test_file = tmp_path / "test.txt"
    test_file.write_bytes(b"hello world")

    chunker = StubChunker()
    chunker.chunk_file(test_file, "test.txt", {"key": "val"})

    assert chunker.chunk_bytes_called_with is not None
    data, filename, metadata = chunker.chunk_bytes_called_with
    assert data == b"hello world"
    assert filename == "test.txt"
    assert metadata == {"key": "val"}


# ---------------------------------------------------------------------------
# PdfChunker.chunk_file does NOT call chunk_bytes
# ---------------------------------------------------------------------------


def _make_one_page_pdf(path: Path) -> None:
    """Create a minimal 1-page PDF at the given path."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        writer.write(f)


@patch("agentdrive.chunking.pdf.settings")
def test_pdf_chunker_chunk_file_uses_file_path(mock_settings, tmp_path):
    """PdfChunker.chunk_file reads from disk, does NOT call chunk_bytes."""
    mock_settings.gcp_project_id = "test-project"
    mock_settings.docai_location = "us"
    mock_settings.docai_processor_id = "abc123"

    pdf_path = tmp_path / "test.pdf"
    _make_one_page_pdf(pdf_path)

    chunker = PdfChunker()

    # Patch chunk_bytes to raise — proving chunk_file doesn't call it
    with patch.object(chunker, "chunk_bytes", side_effect=AssertionError("chunk_bytes should not be called")):
        # Patch _process_batch to return minimal markdown
        with patch.object(chunker, "_process_batch", return_value="# Test heading\n\nSome content."):
            result = chunker.chunk_file(pdf_path, "test.pdf")

    assert len(result) > 0


# ---------------------------------------------------------------------------
# StorageService.download_stream
# ---------------------------------------------------------------------------


@patch("agentdrive.services.storage._get_s3_client")
@patch("agentdrive.services.storage.settings")
def test_download_stream_yields_chunks(mock_settings, mock_get_client):
    """download_stream yields file content in chunks from S3."""
    import io

    mock_settings.s3_bucket = "test-bucket"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    content = b"A" * 8192 + b"B" * 4096  # 12KB total
    mock_client.get_object.return_value = {"Body": io.BytesIO(content)}

    svc = StorageService()
    chunks = list(svc.download_stream("fake/path", chunk_size=4096))

    assert b"".join(chunks) == content
    assert len(chunks) == 3  # 4096 + 4096 + 4096


@patch("agentdrive.services.storage._get_s3_client")
@patch("agentdrive.services.storage.settings")
def test_download_stream_raises_on_missing_blob(mock_settings, mock_get_client):
    """download_stream raises FileNotFoundError when object does not exist."""
    from botocore.exceptions import ClientError

    mock_settings.s3_bucket = "test-bucket"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
    )

    svc = StorageService()

    with pytest.raises(FileNotFoundError):
        list(svc.download_stream("missing/path"))
