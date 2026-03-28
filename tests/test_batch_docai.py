"""Tests for batch Document AI processing in PdfChunker."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from agentdrive.chunking.pdf import PdfChunker, _doc_ai_to_markdown


def _make_pdf(tmp_path: Path, num_pages: int) -> Path:
    """Create a blank PDF with the given number of pages."""
    pdf_path = tmp_path / f"test_{num_pages}pg.pdf"
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


def test_small_pdf_uses_sync_api(tmp_path):
    """PDFs with <=30 pages use the sync online API path."""
    pdf_path = _make_pdf(tmp_path, 5)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch", return_value="# Title\n\nContent") as mock_sync:
        result = chunker.chunk_file(pdf_path, "test.pdf")
        mock_sync.assert_called_once()
        assert len(result) > 0


def test_medium_pdf_uses_batch_api(tmp_path):
    """PDFs with 31-500 pages use batch API when gcs_path and file_id provided."""
    pdf_path = _make_pdf(tmp_path, 50)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch", side_effect=AssertionError("should not call sync")), \
         patch.object(chunker, "_process_batch_api", return_value="# Batch\n\nContent") as mock_batch:
        result = chunker.chunk_file(
            pdf_path, "test.pdf",
            gcs_path="tenants/x/files/y/test.pdf",
            file_id="test-id",
        )
        mock_batch.assert_called_once()
        assert len(result) > 0


def test_large_pdf_returns_batched(tmp_path):
    """PDFs with >500 pages are split into multiple batch API calls."""
    pdf_path = _make_pdf(tmp_path, 600)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch_api", return_value="# Split\n\nContent") as mock_batch, \
         patch("agentdrive.chunking.pdf.StorageService") as mock_storage_cls:
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        results = chunker.chunk_file_batched(
            pdf_path, "test.pdf",
            gcs_path="tenants/x/files/y/test.pdf",
            file_id="abc-123",
        )

        assert len(results) == 2  # 500 + 100
        assert results[0][0] == "1-500"
        assert results[1][0] == "501-600"
        assert mock_batch.call_count == 2


def test_no_gcs_path_falls_back_to_sync(tmp_path):
    """PDFs >30 pages without gcs_path fall back to sync online API."""
    pdf_path = _make_pdf(tmp_path, 50)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch", return_value="# Sync\n\nContent") as mock_sync:
        result = chunker.chunk_file(pdf_path, "test.pdf")  # No gcs_path
        assert mock_sync.called
        assert len(result) > 0


def test_large_pdf_chunk_file_dispatches_to_batched(tmp_path):
    """>500 page PDF via chunk_file delegates to chunk_file_batched."""
    pdf_path = _make_pdf(tmp_path, 600)
    chunker = PdfChunker()
    mock_batch_result = [("1-500", []), ("501-600", [])]
    with patch.object(chunker, "chunk_file_batched", return_value=mock_batch_result) as mock_batched:
        result = chunker.chunk_file(
            pdf_path, "test.pdf",
            gcs_path="tenants/x/files/y/test.pdf",
            file_id="abc-123",
        )
        mock_batched.assert_called_once()
        assert result == []


def test_doc_ai_to_markdown_with_batch_output():
    """Verify _doc_ai_to_markdown handles a simple paragraph block."""
    mock_block = MagicMock()
    mock_block.table_block = None
    mock_block.text_block.type_ = "paragraph"
    mock_block.text_block.text = "Batch output paragraph"
    mock_block.text_block.blocks = []

    mock_doc = MagicMock()
    mock_doc.document_layout.blocks = [mock_block]

    result = _doc_ai_to_markdown(mock_doc)
    assert "Batch output paragraph" in result
