"""Tests for Document AI online processing in PdfChunker."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
    """PDFs with <=30 pages use a single online API call."""
    pdf_path = _make_pdf(tmp_path, 5)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch", return_value="# Title\n\nContent") as mock_sync:
        result = chunker.chunk_file(pdf_path, "test.pdf")
        mock_sync.assert_called_once()
        assert len(result) > 0


def test_medium_pdf_splits_into_sync_batches(tmp_path):
    """PDFs with 31-60 pages use the online API in 30-page slices."""
    pdf_path = _make_pdf(tmp_path, 50)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch", return_value="# Sync\n\nContent") as mock_sync:
        result = chunker.chunk_file(
            pdf_path, "test.pdf",
            gcs_path="tenants/x/files/y/test.pdf",
            file_id="test-id",
        )
        assert mock_sync.call_count == 2
        assert len(result) > 0


def test_large_pdf_splits_into_sync_batches(tmp_path):
    """PDFs with >500 pages still use the online API in 30-page slices."""
    pdf_path = _make_pdf(tmp_path, 600)
    chunker = PdfChunker()
    with patch.object(chunker, "_process_batch", return_value="# Sync\n\nContent") as mock_sync:
        result = chunker.chunk_file(pdf_path, "test.pdf")
        assert mock_sync.call_count == 20
        assert len(result) > 0


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
