from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChunkResult:
    content: str
    context_prefix: str
    token_count: int
    content_type: str  # text, code, table, image
    metadata: dict = field(default_factory=dict)


@dataclass
class ParentChildChunks:
    parent: ChunkResult
    children: list[ChunkResult]


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Process text content and return parent-child chunk groups."""
        ...

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Process binary content. Override for binary formats (PDF, XLSX). Default decodes as UTF-8."""
        return self.chunk(data.decode("utf-8", errors="replace"), filename, metadata)

    def chunk_file(
        self, path: Path, filename: str, metadata: dict | None = None,
        gcs_path: str | None = None, file_id: str | None = None,
    ) -> list[ParentChildChunks]:
        """Process a file on disk. Default reads into bytes and delegates to chunk_bytes."""
        data = path.read_bytes()
        return self.chunk_bytes(data, filename, metadata)

    @abstractmethod
    def supported_types(self) -> list[str]:
        """Return list of content_type strings this chunker handles."""
        ...
