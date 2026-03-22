import re
from unittest.mock import AsyncMock, patch

import pytest

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.table_questions import is_table_chunk, generate_table_aliases


def test_is_table_chunk_true():
    content = "| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |"
    assert is_table_chunk(content) is True


def test_is_table_chunk_false():
    content = "This is a normal paragraph with no table."
    assert is_table_chunk(content) is False


def test_is_table_chunk_with_surrounding_text():
    content = "Some intro text.\n\n| Col A | Col B |\n|---|---|\n| 1 | 2 |\n\nMore text."
    assert is_table_chunk(content) is True


def test_is_table_chunk_pipe_in_code_not_table():
    content = "Use `a | b` for piping commands."
    assert is_table_chunk(content) is False


@pytest.mark.asyncio
@patch("agentdrive.enrichment.table_questions.EnrichmentClient")
async def test_generate_table_aliases(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.generate_table_questions.return_value = [
        "What is Alice's age?",
        "How old is Bob?",
        "Who is the oldest person?",
    ]
    mock_client_cls.return_value = mock_client

    table_content = "| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |"
    chunk = ChunkResult(content=table_content, context_prefix="File: data.md", token_count=20, content_type="text")
    group = ParentChildChunks(parent=chunk, children=[chunk])

    aliases = await generate_table_aliases([group])

    assert len(aliases) == 3
    assert all("question" in a for a in aliases)
    assert all("chunk" in a for a in aliases)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.table_questions.EnrichmentClient")
async def test_no_aliases_for_non_table(mock_client_cls):
    chunk = ChunkResult(content="Just a paragraph of text.", context_prefix="", token_count=10, content_type="text")
    group = ParentChildChunks(parent=chunk, children=[chunk])

    aliases = await generate_table_aliases([group])

    assert len(aliases) == 0
    mock_client_cls.return_value.generate_table_questions.assert_not_called()
