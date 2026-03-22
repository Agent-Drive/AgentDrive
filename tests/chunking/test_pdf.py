from unittest.mock import MagicMock, patch
from agentdrive.chunking.pdf import PdfChunker


def test_supported_types():
    chunker = PdfChunker()
    assert "pdf" in chunker.supported_types()


@patch("agentdrive.chunking.pdf.DocumentConverter")
def test_pdf_produces_chunks(mock_converter_cls):
    mock_doc = MagicMock()
    mock_doc.document.export_to_markdown.return_value = (
        "# Report\n\n## Introduction\n\nThis is the intro.\n\n"
        "## Results\n\nThe results show improvement.\n\n"
        "## Conclusion\n\nWe conclude that things are better."
    )
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_doc])
    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_result
    mock_converter_cls.return_value = mock_converter

    chunker = PdfChunker()
    results = chunker.chunk_bytes(b"fake pdf bytes", "report.pdf")
    assert len(results) >= 1
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "intro" in all_content.lower()
    assert "results" in all_content.lower()


@patch("agentdrive.chunking.pdf.DocumentConverter")
def test_pdf_breadcrumbs(mock_converter_cls):
    mock_doc = MagicMock()
    mock_doc.document.export_to_markdown.return_value = (
        "# Guide\n\n## Setup\n\n"
        + "Install the package by running the installer script. "
        * 20
        + "\n"
    )
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_doc])
    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_result
    mock_converter_cls.return_value = mock_converter

    chunker = PdfChunker()
    results = chunker.chunk_bytes(b"pdf", "guide.pdf")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Setup" in p for p in prefixes)
