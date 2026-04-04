from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_extract_concepts(mock_openai_cls):
    from agentdrive.enrichment.client import EnrichmentClient

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"concepts": [{"concept_name": "RLHF", "description": "Reinforcement learning from human feedback", "is_new": true}]}'
                )
            )
        ]
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    concepts = await client.extract_concepts("Doc about RLHF", ["PPO"])

    assert len(concepts) == 1
    assert concepts[0]["concept_name"] == "RLHF"
    assert concepts[0]["is_new"] is True


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_extract_concepts_fallback_on_error(mock_openai_cls):
    from agentdrive.enrichment.client import EnrichmentClient

    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.extract_concepts("text", [])

    assert result == []


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_article(mock_openai_cls):
    from agentdrive.enrichment.client import EnrichmentClient

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"title": "RLHF Overview", "content": "# RLHF\\n\\nRLHF is...", "category": "alignment", "source_refs": [{"chunk_id": "abc", "excerpt": "RLHF uses human preferences"}]}'
                )
            )
        ]
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    article = await client.generate_article(
        "RLHF",
        "RL from human feedback",
        [{"chunk_id": "abc", "content": "text"}],
    )

    assert article["title"] == "RLHF Overview"
    assert "category" in article
    assert len(article["source_refs"]) == 1


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_article_fallback_on_error(mock_openai_cls):
    from agentdrive.enrichment.client import EnrichmentClient

    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.generate_article(
        "RLHF", "desc", [{"chunk_id": "abc", "content": "text"}]
    )

    assert result == {"title": "RLHF", "content": "", "category": "", "source_refs": []}


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_discover_connections(mock_openai_cls):
    from agentdrive.enrichment.client import EnrichmentClient

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"connections": [{"source_title": "RLHF", "target_title": "PPO", "link_type": "related", "rationale": "PPO is used in RLHF"}]}'
                )
            )
        ]
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    connections = await client.discover_connections(
        [{"title": "RLHF", "summary": "..."}, {"title": "PPO", "summary": "..."}]
    )

    assert len(connections) == 1
    assert connections[0]["link_type"] == "related"


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_discover_connections_fallback_on_error(mock_openai_cls):
    from agentdrive.enrichment.client import EnrichmentClient

    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.discover_connections([])

    assert result == []
