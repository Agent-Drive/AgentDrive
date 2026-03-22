from agentdrive.chunking.base import BaseChunker
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
