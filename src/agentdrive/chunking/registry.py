from pathlib import Path

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.code import CodeChunker
from agentdrive.chunking.markdown import MarkdownChunker
from agentdrive.chunking.notebook import NotebookChunker
from agentdrive.chunking.pdf import PdfChunker
from agentdrive.chunking.spreadsheet import SpreadsheetChunker
from agentdrive.chunking.structured import StructuredChunker
from agentdrive.chunking.text import TextChunker


class ChunkerRegistry:
    def __init__(self) -> None:
        self._chunkers: dict[str, BaseChunker] = {}
        self._fallback = TextChunker()
        for chunker in [
            PdfChunker(), MarkdownChunker(), CodeChunker(),
            StructuredChunker(), SpreadsheetChunker(),
            NotebookChunker(), TextChunker(),
        ]:
            for content_type in chunker.supported_types():
                self._chunkers[content_type] = chunker

    def get_chunker(self, content_type: str) -> BaseChunker:
        return self._chunkers.get(content_type, self._fallback)

    def chunk_file(
        self, content_type: str, path: Path, filename: str, metadata: dict | None = None,
        gcs_path: str | None = None, file_id: str | None = None,
    ) -> list[ParentChildChunks]:
        """Dispatch to the appropriate chunker's chunk_file method."""
        chunker = self.get_chunker(content_type)
        return chunker.chunk_file(path, filename, metadata, gcs_path=gcs_path, file_id=file_id)
