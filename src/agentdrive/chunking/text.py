from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.hierarchy import build_parent_child_chunks

class TextChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["text"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        prefix = build_context_prefix(content_type="text", filename=filename)
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        text = "\n\n".join(paragraphs)
        return build_parent_child_chunks(text=text, content_type="text", context_prefix=prefix)
