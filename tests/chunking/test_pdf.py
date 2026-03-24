from unittest.mock import MagicMock, patch

from agentdrive.chunking.pdf import PdfChunker


def test_supported_types():
    chunker = PdfChunker()
    assert "pdf" in chunker.supported_types()


@patch("agentdrive.chunking.pdf.documentai")
@patch("agentdrive.chunking.pdf.settings")
def test_pdf_produces_chunks(mock_settings, mock_docai):
    mock_settings.gcp_project_id = "test-project"
    mock_settings.docai_location = "us"
    mock_settings.docai_processor_id = "abc123"

    layout_block = MagicMock()
    layout_block.table_block = None
    layout_block.text_block.type_ = "paragraph"
    layout_block.text_block.text = "This is the intro."
    layout_block.text_block.blocks = []

    results_block = MagicMock()
    results_block.table_block = None
    results_block.text_block.type_ = "heading-1"
    results_block.text_block.text = "Results"
    results_block.text_block.blocks = []

    mock_document = MagicMock()
    mock_document.document_layout.blocks = [layout_block, results_block]

    mock_result = MagicMock()
    mock_result.document = mock_document

    mock_client = MagicMock()
    mock_client.process_document.return_value = mock_result
    mock_docai.DocumentProcessorServiceClient.return_value = mock_client
    mock_docai.RawDocument = MagicMock()
    mock_docai.ProcessRequest = MagicMock()

    chunker = PdfChunker()
    results = chunker.chunk_bytes(b"fake pdf bytes", "report.pdf")
    assert len(results) >= 1
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "intro" in all_content.lower()
    assert "results" in all_content.lower()


@patch("agentdrive.chunking.pdf.documentai")
@patch("agentdrive.chunking.pdf.settings")
def test_pdf_breadcrumbs(mock_settings, mock_docai):
    mock_settings.gcp_project_id = "test-project"
    mock_settings.docai_location = "us"
    mock_settings.docai_processor_id = "abc123"

    heading_block = MagicMock()
    heading_block.table_block = None
    heading_block.text_block.type_ = "heading-1"
    heading_block.text_block.text = "Setup"
    heading_block.text_block.blocks = []

    body_text = "Install the package by running the installer script. " * 20
    body_block = MagicMock()
    body_block.table_block = None
    body_block.text_block.type_ = "paragraph"
    body_block.text_block.text = body_text
    body_block.text_block.blocks = []

    mock_document = MagicMock()
    mock_document.document_layout.blocks = [heading_block, body_block]

    mock_result = MagicMock()
    mock_result.document = mock_document

    mock_client = MagicMock()
    mock_client.process_document.return_value = mock_result
    mock_docai.DocumentProcessorServiceClient.return_value = mock_client
    mock_docai.RawDocument = MagicMock()
    mock_docai.ProcessRequest = MagicMock()

    chunker = PdfChunker()
    results = chunker.chunk_bytes(b"pdf", "guide.pdf")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Setup" in p for p in prefixes)
