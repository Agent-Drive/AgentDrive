import re
from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.hierarchy import build_parent_child_chunks
from agentdrive.chunking.tokens import count_tokens

FRONT_MATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
CODE_BLOCK_RE = re.compile(r'```[\s\S]*?```', re.MULTILINE)

MIN_SECTION_TOKENS = 100


class MarkdownChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["markdown"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        metadata = metadata or {}

        # Extract front matter
        front_matter = {}
        fm_match = FRONT_MATTER_RE.match(content)
        if fm_match:
            fm_text = fm_match.group(1)
            content = content[fm_match.end():]
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    front_matter[key.strip()] = value.strip()

        # Protect code blocks from heading detection
        code_blocks: dict[str, str] = {}
        counter = 0
        def replace_code(match: re.Match) -> str:
            nonlocal counter
            key = f"__CODE_BLOCK_{counter}__"
            code_blocks[key] = match.group(0)
            counter += 1
            return key
        protected = CODE_BLOCK_RE.sub(replace_code, content)

        # Parse sections by H1/H2 headings
        sections = self._split_by_headings(protected)

        # Restore code blocks and build chunks
        all_results: list[ParentChildChunks] = []
        pending_tiny: list[tuple[str, list[str]]] = []

        for section_text, breadcrumb in sections:
            # Restore code blocks
            for key, value in code_blocks.items():
                section_text = section_text.replace(key, value)

            section_tokens = count_tokens(section_text)

            # Merge tiny sections
            if section_tokens < MIN_SECTION_TOKENS:
                pending_tiny.append((section_text, breadcrumb))
                continue

            # Flush any pending tiny sections — keep the current section's breadcrumb
            # since it is more specific (e.g. H2) than the preceding tiny intro text
            if pending_tiny:
                merged_text = "\n\n".join(t for t, _ in pending_tiny) + "\n\n" + section_text
                pending_tiny = []
                section_text = merged_text

            prefix = build_context_prefix(
                content_type="markdown", filename=filename, heading_breadcrumb=breadcrumb,
            )

            results = build_parent_child_chunks(
                text=section_text.strip(), content_type="text", context_prefix=prefix,
            )
            for group in results:
                group.parent.metadata = {**front_matter, **metadata}
                for child in group.children:
                    child.metadata = {**front_matter, **metadata}

            all_results.extend(results)

        # Flush remaining tiny sections
        if pending_tiny:
            merged_text = "\n\n".join(t for t, _ in pending_tiny)
            breadcrumb = pending_tiny[0][1]
            prefix = build_context_prefix(
                content_type="markdown", filename=filename, heading_breadcrumb=breadcrumb,
            )
            results = build_parent_child_chunks(
                text=merged_text.strip(), content_type="text", context_prefix=prefix,
            )
            all_results.extend(results)

        return all_results

    def _split_by_headings(self, text: str) -> list[tuple[str, list[str]]]:
        """Split text at H1/H2 boundaries, returning (section_text, breadcrumb) pairs."""
        lines = text.split("\n")
        sections: list[tuple[str, list[str]]] = []
        current_lines: list[str] = []
        current_breadcrumb: list[str] = []
        h1 = ""

        for line in lines:
            heading_match = HEADING_RE.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                if level == 1:
                    if current_lines:
                        sections.append(("\n".join(current_lines), list(current_breadcrumb)))
                        current_lines = []
                    h1 = title
                    current_breadcrumb = [h1]

                elif level == 2:
                    if current_lines:
                        sections.append(("\n".join(current_lines), list(current_breadcrumb)))
                        current_lines = []
                    current_breadcrumb = [h1, title] if h1 else [title]

            current_lines.append(line)

        if current_lines:
            sections.append(("\n".join(current_lines), list(current_breadcrumb)))

        return sections if sections else [(text, [])]
