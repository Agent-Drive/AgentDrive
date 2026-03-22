import re

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.client import EnrichmentClient


def is_table_chunk(content: str) -> bool:
    """Check if chunk contains a markdown table."""
    lines = content.strip().split("\n")
    pipe_lines = [l for l in lines if l.count("|") >= 2 and not l.strip().startswith("`")]
    separator_lines = [l for l in lines if re.match(r'^\|[\s\-:|]+\|$', l.strip())]
    return len(pipe_lines) >= 3 and len(separator_lines) >= 1


async def generate_table_aliases(
    chunk_groups: list[ParentChildChunks],
) -> list[dict]:
    """Generate synthetic questions for table chunks. Returns alias records."""
    client = EnrichmentClient()
    aliases = []

    for group in chunk_groups:
        for child in group.children:
            if is_table_chunk(child.content):
                questions = await client.generate_table_questions(child.content)
                for q in questions:
                    aliases.append({"question": q, "chunk": child})

    return aliases
