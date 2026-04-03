from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentdrive.enrichment.client import EnrichmentClient


def _mock_chat_response(content: str) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_context(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        "This chunk is from a Q3 board meeting about revenue."
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context(
        document_text="Full document text here...",
        chunk_text="Revenue grew 34% YoY.",
    )

    assert len(context) > 10
    mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_context_sends_document_and_chunk(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        "Context about the chunk."
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    await client.generate_context("doc text", "chunk 1")

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args[1]["messages"]
    content = messages[0]["content"]
    assert "<document>" in content
    assert "chunk 1" in content


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_summary(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        '{"document_summary": "A quarterly report.", "section_summaries": [{"heading": "Revenue", "summary": "Revenue grew."}]}'
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.generate_summary("Full document text here...")

    assert result["document_summary"] == "A quarterly report."
    assert len(result["section_summaries"]) == 1
    call_args = mock_client.chat.completions.create.call_args
    assert call_args[1]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_table_questions(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        "What was Q3 revenue?\nHow did revenue grow?\nWhich quarter was highest?"
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    questions = await client.generate_table_questions(
        "| Quarter | Revenue |\n|---|---|\n| Q1 | 3.8 |\n| Q2 | 4.0 |"
    )

    assert len(questions) >= 3
    assert all(isinstance(q, str) for q in questions)
    assert all(len(q) > 5 for q in questions)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_context_with_summary(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        "This chunk discusses Q3 revenue in the context of annual growth."
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context_with_summary(
        doc_summary="Annual financial report for FY2025.",
        section_summary="Revenue: Revenue grew 34% YoY.",
        neighbors="Q2 showed strong growth in enterprise segment.",
        chunk_text="Q3 revenue reached $4.2M.",
    )

    assert len(context) > 10
    mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_context_with_summary_fallback_on_error(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context_with_summary(
        doc_summary="summary",
        section_summary="section",
        neighbors="neighbors",
        chunk_text="chunk",
    )

    assert context == ""


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_context_fallback_on_error(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context("doc", "chunk")

    assert context == ""


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_table_questions_fallback_on_error(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    questions = await client.generate_table_questions("| A | B |")

    assert questions == []


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_summary_fallback_on_error(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.generate_summary("doc text")

    assert result == {"document_summary": "", "section_summaries": []}
