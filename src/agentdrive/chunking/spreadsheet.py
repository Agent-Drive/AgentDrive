import csv
import io
from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens

ROWS_PER_CHUNK = 30


class SpreadsheetChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["csv", "xlsx"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            return []
        headers = rows[0]
        data_rows = rows[1:]
        prefix = build_context_prefix(content_type="csv", filename=filename, columns=headers)
        results: list[ParentChildChunks] = []
        for i in range(0, len(data_rows), ROWS_PER_CHUNK):
            batch = data_rows[i:i + ROWS_PER_CHUNK]
            lines = ["| " + " | ".join(headers) + " |"]
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in batch:
                padded = row + [""] * (len(headers) - len(row))
                lines.append("| " + " | ".join(padded) + " |")
            text = "\n".join(lines)
            token_count = count_tokens(text)
            chunk = ChunkResult(content=text, context_prefix=prefix, token_count=token_count, content_type="text")
            results.append(ParentChildChunks(parent=chunk, children=[chunk]))
        return results
