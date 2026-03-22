from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.hierarchy import build_parent_child_chunks
from agentdrive.chunking.tokens import count_tokens

LANGUAGE_MAP: dict[str, tuple[str, object]] = {
    ".py": ("python", Language(tspython.language())),
}

PYTHON_DEFINITION_TYPES = {"function_definition", "class_definition", "decorated_definition"}


def _node_name(node) -> str | None:
    """Return the identifier name of a definition node, handling decorated_definition."""
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    return name_node.text.decode()
        return None
    name_node = node.child_by_field_name("name")
    return name_node.text.decode() if name_node else None


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode()


def _inner_definition(node):
    """For decorated_definition, return the inner function/class node."""
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return child
    return node


def _chunk_class(
    class_node,
    source_bytes: bytes,
    filename: str,
    class_name: str,
) -> list[ChunkResult]:
    """Extract each method in a class as a separate ChunkResult."""
    body = class_node.child_by_field_name("body")
    if body is None:
        text = _node_text(class_node, source_bytes)
        prefix = build_context_prefix(
            content_type="code", filename=filename, class_name=class_name
        )
        return [
            ChunkResult(
                content=text,
                context_prefix=prefix,
                token_count=count_tokens(text),
                content_type="code",
            )
        ]

    chunks: list[ChunkResult] = []
    for child in body.children:
        if child.type in PYTHON_DEFINITION_TYPES:
            method_name = _node_name(child)
            inner = _inner_definition(child)
            # Only treat as method if it's a function inside a class body
            if inner.type == "function_definition" and method_name:
                text = _node_text(child, source_bytes)
                prefix = build_context_prefix(
                    content_type="code",
                    filename=filename,
                    class_name=class_name,
                    function_name=method_name,
                )
                chunks.append(
                    ChunkResult(
                        content=text,
                        context_prefix=prefix,
                        token_count=count_tokens(text),
                        content_type="code",
                    )
                )

    if not chunks:
        # No methods found — return the entire class as one chunk
        text = _node_text(class_node, source_bytes)
        prefix = build_context_prefix(
            content_type="code", filename=filename, class_name=class_name
        )
        chunks.append(
            ChunkResult(
                content=text,
                context_prefix=prefix,
                token_count=count_tokens(text),
                content_type="code",
            )
        )

    return chunks


def _wrap_as_parent_child(chunks: list[ChunkResult]) -> list[ParentChildChunks]:
    """Wrap a flat list of ChunkResults into ParentChildChunks (one group per chunk)."""
    results: list[ParentChildChunks] = []
    for chunk in chunks:
        results.append(ParentChildChunks(parent=chunk, children=[chunk]))
    return results


class CodeChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["code"]

    def chunk(
        self, content: str, filename: str, metadata: dict | None = None
    ) -> list[ParentChildChunks]:
        suffix = Path(filename).suffix.lower()
        lang_entry = LANGUAGE_MAP.get(suffix)

        if lang_entry is None:
            # Unsupported language — fall back to plain text chunking with code content_type
            prefix = build_context_prefix(content_type="code", filename=filename)
            results = build_parent_child_chunks(
                text=content, content_type="code", context_prefix=prefix
            )
            return results

        _lang_name, language = lang_entry
        parser = Parser(language)
        source_bytes = content.encode()
        tree = parser.parse(source_bytes)
        root = tree.root_node

        all_chunks: list[ChunkResult] = []
        preamble_lines: list[str] = []

        for node in root.children:
            if not node.is_named:
                continue

            if node.type in PYTHON_DEFINITION_TYPES:
                # Flush preamble (imports, module-level assignments, etc.)
                if preamble_lines:
                    preamble_text = "\n".join(preamble_lines).strip()
                    if preamble_text:
                        prefix = build_context_prefix(
                            content_type="code", filename=filename
                        )
                        all_chunks.append(
                            ChunkResult(
                                content=preamble_text,
                                context_prefix=prefix,
                                token_count=count_tokens(preamble_text),
                                content_type="code",
                            )
                        )
                    preamble_lines = []

                inner = _inner_definition(node)
                name = _node_name(node)

                if inner.type == "class_definition" and name:
                    all_chunks.extend(
                        _chunk_class(inner, source_bytes, filename, class_name=name)
                    )
                elif inner.type == "function_definition" and name:
                    text = _node_text(node, source_bytes)
                    prefix = build_context_prefix(
                        content_type="code", filename=filename, function_name=name
                    )
                    all_chunks.append(
                        ChunkResult(
                            content=text,
                            context_prefix=prefix,
                            token_count=count_tokens(text),
                            content_type="code",
                        )
                    )
                else:
                    # Unnamed definition — add raw text to preamble
                    preamble_lines.append(_node_text(node, source_bytes))
            else:
                preamble_lines.append(_node_text(node, source_bytes))

        # Flush remaining preamble
        if preamble_lines:
            preamble_text = "\n".join(preamble_lines).strip()
            if preamble_text:
                prefix = build_context_prefix(content_type="code", filename=filename)
                all_chunks.append(
                    ChunkResult(
                        content=preamble_text,
                        context_prefix=prefix,
                        token_count=count_tokens(preamble_text),
                        content_type="code",
                    )
                )

        if not all_chunks:
            prefix = build_context_prefix(content_type="code", filename=filename)
            all_chunks.append(
                ChunkResult(
                    content=content,
                    context_prefix=prefix,
                    token_count=count_tokens(content),
                    content_type="code",
                )
            )

        return _wrap_as_parent_child(all_chunks)
