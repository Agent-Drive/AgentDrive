import io
import logging

from google.cloud import documentai_v1 as documentai
from pypdf import PdfReader, PdfWriter

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.markdown import MarkdownChunker
from agentdrive.config import settings

_MAX_PAGES_PER_BATCH = 30

logger = logging.getLogger(__name__)

# Map Document AI block types to markdown prefixes
_HEADING_MAP = {
    "title": "# ",
    "heading-1": "## ",
    "heading-2": "### ",
    "heading-3": "#### ",
    "heading-4": "##### ",
    "heading-5": "###### ",
    "heading-6": "###### ",
}

_SKIP_TYPES = {"header", "footer"}


def _table_to_markdown(table_block) -> str:
    """Convert a Document AI TableBlock to markdown table syntax."""
    rows = []

    for header_row in table_block.header_rows:
        cells = []
        for cell in header_row.cells:
            cell_text = " ".join(
                b.text_block.text.strip() for b in cell.blocks if b.text_block
            )
            cells.append(cell_text)
        rows.append("| " + " | ".join(cells) + " |")
        rows.append("| " + " | ".join("---" for _ in cells) + " |")

    for body_row in table_block.body_rows:
        cells = []
        for cell in body_row.cells:
            cell_text = " ".join(
                b.text_block.text.strip() for b in cell.blocks if b.text_block
            )
            cells.append(cell_text)
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join(rows)


def _process_block(block, parts: list[str]) -> None:
    """Recursively process a Document AI block into markdown parts."""
    if block.table_block:
        md_table = _table_to_markdown(block.table_block)
        if md_table:
            parts.append(md_table)
        return

    if not block.text_block:
        return

    type_ = block.text_block.type_
    text = block.text_block.text.strip()

    if not text or type_ in _SKIP_TYPES:
        return

    prefix = _HEADING_MAP.get(type_, "")
    if type_ == "list-item":
        parts.append(f"- {text}")
    elif prefix:
        parts.append(f"{prefix}{text}")
    else:
        parts.append(text)

    # Process nested blocks (e.g., content under a heading)
    for child in block.text_block.blocks:
        _process_block(child, parts)


def _doc_ai_to_markdown(document) -> str:
    """Convert Document AI Layout Parser response to markdown."""
    parts: list[str] = []

    for block in document.document_layout.blocks:
        _process_block(block, parts)

    return "\n\n".join(parts)


class PdfChunker(BaseChunker):
    def __init__(self) -> None:
        self._markdown_chunker = MarkdownChunker()

    def supported_types(self) -> list[str]:
        return ["pdf"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        return []

    def _process_batch(self, data: bytes, processor_name: str) -> str:
        """Send a single PDF (≤30 pages) to Document AI and return markdown."""
        client = documentai.DocumentProcessorServiceClient()
        raw_document = documentai.RawDocument(content=data, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)

        result = client.process_document(request=request)
        return _doc_ai_to_markdown(result.document)

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        processor_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.docai_location}"
            f"/processors/{settings.docai_processor_id}"
        )

        # Split large PDFs into batches of ≤30 pages
        reader = PdfReader(io.BytesIO(data))
        total_pages = len(reader.pages)

        if total_pages <= _MAX_PAGES_PER_BATCH:
            markdown = self._process_batch(data, processor_name)
        else:
            logger.info(f"PDF {filename}: {total_pages} pages, splitting into batches of {_MAX_PAGES_PER_BATCH}")
            markdown_parts = []
            for start in range(0, total_pages, _MAX_PAGES_PER_BATCH):
                writer = PdfWriter()
                for page_num in range(start, min(start + _MAX_PAGES_PER_BATCH, total_pages)):
                    writer.add_page(reader.pages[page_num])
                batch_buffer = io.BytesIO()
                writer.write(batch_buffer)
                batch_md = self._process_batch(batch_buffer.getvalue(), processor_name)
                if batch_md.strip():
                    markdown_parts.append(batch_md)
            markdown = "\n\n".join(markdown_parts)

        if not markdown.strip():
            logger.warning(f"PDF {filename}: Document AI produced empty markdown")
            return []

        return self._markdown_chunker.chunk(markdown, filename, metadata)
