import json
import yaml
from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens


class StructuredChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["json", "yaml"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        try:
            if filename.endswith((".yaml", ".yml")):
                data = yaml.safe_load(content)
            elif filename.endswith(".toml"):
                import tomllib
                data = tomllib.loads(content)
            else:
                data = json.loads(content)
        except (json.JSONDecodeError, yaml.YAMLError):
            prefix = build_context_prefix(content_type="json", filename=filename)
            chunk = ChunkResult(content=content, context_prefix=prefix, token_count=count_tokens(content), content_type="text")
            return [ParentChildChunks(parent=chunk, children=[chunk])]

        if not isinstance(data, dict):
            prefix = build_context_prefix(content_type="json", filename=filename)
            text = json.dumps(data, indent=2) if not isinstance(data, str) else data
            chunk = ChunkResult(content=text, context_prefix=prefix, token_count=count_tokens(text), content_type="text")
            return [ParentChildChunks(parent=chunk, children=[chunk])]

        results: list[ParentChildChunks] = []
        for key, value in data.items():
            serialized = json.dumps({key: value}, indent=2)
            prefix = build_context_prefix(content_type="json", filename=filename, key_path=key)
            token_count = count_tokens(serialized)
            chunk = ChunkResult(content=serialized, context_prefix=prefix, token_count=token_count, content_type="text")
            results.append(ParentChildChunks(parent=chunk, children=[chunk]))

        return results if results else [ParentChildChunks(
            parent=ChunkResult(content=content, context_prefix="", token_count=count_tokens(content), content_type="text"),
            children=[ChunkResult(content=content, context_prefix="", token_count=count_tokens(content), content_type="text")],
        )]
