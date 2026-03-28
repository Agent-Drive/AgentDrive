import io
import logging
from pathlib import Path

from google.cloud import documentai_v1 as documentai
from pypdf import PdfReader, PdfWriter

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.markdown import MarkdownChunker
from agentdrive.config import settings
from agentdrive.services.storage import StorageService

_MAX_PAGES_PER_BATCH = 30
_MAX_PAGES_PER_BATCH_API = 500

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


def _processor_name() -> str:
    """Build the Document AI processor resource name from settings."""
    return (
        f"projects/{settings.gcp_project_id}"
        f"/locations/{settings.docai_location}"
        f"/processors/{settings.docai_processor_id}"
    )


class PdfChunker(BaseChunker):
    def __init__(self) -> None:
        self._markdown_chunker = MarkdownChunker()

    def supported_types(self) -> list[str]:
        return ["pdf"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        return []

    def _process_batch(self, data: bytes, processor_name: str) -> str:
        """Send a single PDF (<=30 pages) to Document AI online API and return markdown."""
        client = documentai.DocumentProcessorServiceClient()
        raw_document = documentai.RawDocument(content=data, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)

        result = client.process_document(request=request)
        return _doc_ai_to_markdown(result.document)

    def _process_batch_api(self, gcs_path: str, processor_name: str, file_id: str) -> str:
        """Submit a PDF via Document AI batch API and return concatenated markdown."""
        storage = StorageService()
        output_prefix = storage.docai_output_prefix(file_id)
        client = documentai.DocumentProcessorServiceClient()

        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(
                documents=[documentai.GcsDocument(
                    gcs_uri=storage.gcs_uri(gcs_path),
                    mime_type="application/pdf",
                )]
            )
        )
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=storage.gcs_uri(output_prefix),
            )
        )
        request = documentai.BatchProcessRequest(
            name=processor_name,
            input_documents=input_config,
            document_output_config=output_config,
        )

        logger.info(f"Submitting batch Document AI request for {gcs_path}")
        operation = client.batch_process_documents(request=request)
        operation.result(timeout=settings.docai_batch_timeout_seconds)

        output_blobs = storage.list_blobs(output_prefix)
        markdown_parts = []
        for blob_name in output_blobs:
            if blob_name.endswith(".json"):
                blob_bytes = storage.download(blob_name)
                document = documentai.Document.from_json(blob_bytes.decode("utf-8"))
                md = _doc_ai_to_markdown(document)
                if md.strip():
                    markdown_parts.append(md)

        storage.delete_prefix(output_prefix)
        return "\n\n".join(markdown_parts)

    def _chunk_from_reader(self, reader: PdfReader, data: bytes | None, filename: str, metadata: dict | None) -> list[ParentChildChunks]:
        """Shared logic: split into 30-page batches, call Document AI online API, chunk markdown."""
        processor_name = _processor_name()
        total_pages = len(reader.pages)

        if total_pages <= _MAX_PAGES_PER_BATCH and data is not None:
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

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        reader = PdfReader(io.BytesIO(data))
        return self._chunk_from_reader(reader, data, filename, metadata)

    def chunk_file(
        self, path: Path, filename: str, metadata: dict | None = None,
        gcs_path: str | None = None, file_id: str | None = None,
    ) -> list[ParentChildChunks]:
        """Dual-path dispatch: sync online API for <=30 pages, batch API for >30 pages."""
        reader = PdfReader(str(path))
        total_pages = len(reader.pages)

        if total_pages <= _MAX_PAGES_PER_BATCH:
            # Small doc: sync online API with 30-page splitting
            return self._chunk_from_reader(reader, None, filename, metadata)
        elif gcs_path is None or file_id is None:
            # No GCS path available: fall back to sync with 30-page splitting
            logger.warning(f"PDF {filename}: {total_pages} pages but no gcs_path/file_id — sync fallback")
            return self._chunk_from_reader(reader, None, filename, metadata)
        elif total_pages <= _MAX_PAGES_PER_BATCH_API:
            # 31-500 pages: single batch API request
            processor_name = _processor_name()
            markdown = self._process_batch_api(gcs_path, processor_name, file_id)
            if not markdown.strip():
                return []
            return self._markdown_chunker.chunk(markdown, filename, metadata)
        else:
            # >500 pages: split into batch API calls, concat results
            batched = self.chunk_file_batched(path, filename, gcs_path=gcs_path, file_id=file_id, metadata=metadata)
            groups: list[ParentChildChunks] = []
            for _, batch_groups in batched:
                groups.extend(batch_groups)
            return groups

    def chunk_file_batched(
        self, path: Path, filename: str, gcs_path: str, file_id: str,
        metadata: dict | None = None,
    ) -> list[tuple[str, list[ParentChildChunks]]]:
        """Split >500-page PDFs into batch API calls, returning per-batch results."""
        processor_name = _processor_name()
        reader = PdfReader(str(path))
        total_pages = len(reader.pages)
        storage = StorageService()
        results: list[tuple[str, list[ParentChildChunks]]] = []

        for start in range(0, total_pages, _MAX_PAGES_PER_BATCH_API):
            end = min(start + _MAX_PAGES_PER_BATCH_API, total_pages)
            page_range = f"{start + 1}-{end}"

            writer = PdfWriter()
            for page_num in range(start, end):
                writer.add_page(reader.pages[page_num])
            batch_buffer = io.BytesIO()
            writer.write(batch_buffer)

            temp_gcs_path = f"tmp/splits/{file_id}/pages_{page_range}.pdf"
            storage.upload_bytes(temp_gcs_path, batch_buffer.getvalue(), "application/pdf")

            markdown = self._process_batch_api(temp_gcs_path, processor_name, f"{file_id}-{page_range}")
            storage.delete_blob(temp_gcs_path)

            if markdown.strip():
                chunks = self._markdown_chunker.chunk(markdown, filename, metadata)
                results.append((page_range, chunks))
            else:
                results.append((page_range, []))

        return results
