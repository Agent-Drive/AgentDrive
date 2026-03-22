import json
from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens


class NotebookChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["notebook"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        try:
            nb = json.loads(content)
        except json.JSONDecodeError:
            return []
        cells = nb.get("cells", [])
        results: list[ParentChildChunks] = []
        current_section = ""
        cell_num = 0
        i = 0
        while i < len(cells):
            cell = cells[i]
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            if cell_type == "markdown":
                for line in source.split("\n"):
                    if line.startswith("#"):
                        current_section = line.lstrip("#").strip()
                if i + 1 < len(cells) and cells[i + 1].get("cell_type") == "code":
                    next_source = "".join(cells[i + 1].get("source", []))
                    combined = f"{source}\n\n```python\n{next_source}\n```"
                    cell_num += 1
                    prefix = build_context_prefix(
                        content_type="notebook", filename=filename,
                        notebook_section=current_section, cell_number=cell_num,
                    )
                    chunk = ChunkResult(content=combined, context_prefix=prefix, token_count=count_tokens(combined), content_type="code")
                    results.append(ParentChildChunks(parent=chunk, children=[chunk]))
                    i += 2
                    continue
            if cell_type == "code" and source.strip():
                cell_num += 1
                prefix = build_context_prefix(
                    content_type="notebook", filename=filename,
                    notebook_section=current_section, cell_number=cell_num,
                )
                chunk = ChunkResult(content=source, context_prefix=prefix, token_count=count_tokens(source), content_type="code")
                results.append(ParentChildChunks(parent=chunk, children=[chunk]))
            i += 1
        return results
