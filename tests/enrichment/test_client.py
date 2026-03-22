from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentdrive.enrichment.client import EnrichmentClient


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_context(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="This chunk is from a Q3 board meeting about revenue.")]
    )
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context(
        document_text="Full document text here...",
        chunk_text="Revenue grew 34% YoY.",
    )

    assert len(context) > 10
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_context_uses_cache_control(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Context about the chunk.")]
    )
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    await client.generate_context("doc text", "chunk 1")

    call_args = mock_client.messages.create.call_args
    messages = call_args[1]["messages"]
    # The user message content should have cache_control on the document part
    content_blocks = messages[0]["content"]
    assert any("cache_control" in block for block in content_blocks if isinstance(block, dict))


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_table_questions(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="What was Q3 revenue?\nHow did revenue grow?\nWhich quarter was highest?")]
    )
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    questions = await client.generate_table_questions(
        "| Quarter | Revenue |\n|---|---|\n| Q1 | 3.8 |\n| Q2 | 4.0 |"
    )

    assert len(questions) >= 3
    assert all(isinstance(q, str) for q in questions)
    assert all(len(q) > 5 for q in questions)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_context_fallback_on_error(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = Exception("API error")
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context("doc", "chunk")

    assert context == ""


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_table_questions_fallback_on_error(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = Exception("API error")
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    questions = await client.generate_table_questions("| A | B |")

    assert questions == []
