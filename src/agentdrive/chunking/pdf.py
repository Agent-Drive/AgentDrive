import logging
import tempfile
from pathlib import Path
from docling.document_converter import DocumentConverter
from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.markdown import MarkdownChunker

logger = logging.getLogger(__name__)


class PdfChunker(BaseChunker):
    def __init__(self) -> None:
        self._markdown_chunker = MarkdownChunker()

    def supported_types(self) -> list[str]:
        return ["pdf"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        # PDF content is binary — this method shouldn't be called directly
        # but BaseChunker.chunk_bytes() will decode bytes as UTF-8 which won't work for PDFs
        # Return empty — callers should use chunk_bytes
        return []

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(data)
            temp_path = f.name
        try:
            converter = DocumentConverter()
            result = converter.convert(temp_path)
            markdown = result.document.export_to_markdown()
            if not markdown or not markdown.strip():
                logger.warning(f"PDF {filename}: Docling produced empty markdown")
                return []
            return self._markdown_chunker.chunk(markdown, filename, metadata)
        except Exception:
            logger.exception(f"PDF {filename}: Docling conversion failed")
            return []
        finally:
            Path(temp_path).unlink(missing_ok=True)
