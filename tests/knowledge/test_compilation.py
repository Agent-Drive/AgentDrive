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


# --- Pipeline sub-module integration tests (require DB) ---


@pytest.mark.asyncio
@patch("agentdrive.knowledge.compilation.concepts.EnrichmentClient")
async def test_extract_concepts_for_kb(mock_client_cls, db_session):
    """Phase 5a: given a KB with files, extract new concepts."""
    from agentdrive.knowledge.compilation.concepts import extract_concepts_for_kb
    from agentdrive.knowledge.models import KnowledgeBase, KnowledgeBaseFile
    from agentdrive.models import File, FileSummary, Tenant
    from agentdrive.models.types import FileStatus, KBStatus

    tenant = Tenant(name="Test")
    db_session.add(tenant)
    await db_session.flush()

    f = File(
        tenant_id=tenant.id,
        filename="paper.pdf",
        content_type="pdf",
        gcs_path="t/f/p.pdf",
        file_size=100,
        status=FileStatus.READY,
    )
    db_session.add(f)
    await db_session.flush()

    summary = FileSummary(
        file_id=f.id,
        document_summary="Paper about RLHF",
        section_summaries=[{"heading": "Intro", "summary": "RLHF overview"}],
    )
    db_session.add(summary)

    kb = KnowledgeBase(tenant_id=tenant.id, name="Test KB", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()

    kb_file = KnowledgeBaseFile(knowledge_base_id=kb.id, file_id=f.id)
    db_session.add(kb_file)
    await db_session.commit()

    mock_instance = AsyncMock()
    mock_instance.extract_concepts.return_value = [
        {"concept_name": "RLHF", "description": "RL from human feedback", "is_new": True}
    ]
    mock_client_cls.return_value = mock_instance

    concepts = await extract_concepts_for_kb(kb.id, db_session)
    assert len(concepts) == 1
    assert concepts[0]["concept_name"] == "RLHF"


@pytest.mark.asyncio
@patch("agentdrive.knowledge.compilation.concepts.EnrichmentClient")
async def test_extract_concepts_empty_kb(mock_client_cls, db_session):
    """Phase 5a: KB with no files returns empty list."""
    from agentdrive.knowledge.compilation.concepts import extract_concepts_for_kb
    from agentdrive.knowledge.models import KnowledgeBase
    from agentdrive.models import Tenant
    from agentdrive.models.types import KBStatus

    tenant = Tenant(name="Test")
    db_session.add(tenant)
    await db_session.flush()

    kb = KnowledgeBase(tenant_id=tenant.id, name="Empty KB", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.commit()

    concepts = await extract_concepts_for_kb(kb.id, db_session)
    assert concepts == []
    # EnrichmentClient should not have been instantiated
    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
@patch("agentdrive.knowledge.compilation.connections.EnrichmentClient")
async def test_discover_and_link_creates_symmetric(mock_client_cls, db_session):
    """Phase 5c-5d: symmetric link types get reverse links."""
    from agentdrive.knowledge.compilation.connections import discover_and_link
    from agentdrive.knowledge.models import Article, KnowledgeBase
    from agentdrive.models import Tenant
    from agentdrive.models.types import ArticleStatus, ArticleType, KBStatus

    tenant = Tenant(name="Test")
    db_session.add(tenant)
    await db_session.flush()

    kb = KnowledgeBase(tenant_id=tenant.id, name="Link KB", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()

    a1 = Article(
        knowledge_base_id=kb.id, title="RLHF", content="RLHF content",
        article_type=ArticleType.CONCEPT, status=ArticleStatus.PUBLISHED, token_count=10,
    )
    a2 = Article(
        knowledge_base_id=kb.id, title="PPO", content="PPO content",
        article_type=ArticleType.CONCEPT, status=ArticleStatus.PUBLISHED, token_count=10,
    )
    db_session.add_all([a1, a2])
    await db_session.commit()

    mock_instance = AsyncMock()
    mock_instance.discover_connections.return_value = [
        {"source_title": "RLHF", "target_title": "PPO", "link_type": "related", "rationale": "PPO is used in RLHF"}
    ]
    mock_client_cls.return_value = mock_instance

    links = await discover_and_link(kb.id, db_session)
    # "related" is symmetric, so we get forward + reverse
    assert len(links) == 2
    titles = {(l.source_article_id, l.target_article_id) for l in links}
    assert (a1.id, a2.id) in titles
    assert (a2.id, a1.id) in titles


@pytest.mark.asyncio
@patch("agentdrive.knowledge.compilation.connections.EnrichmentClient")
async def test_discover_and_link_skips_single_article(mock_client_cls, db_session):
    """Phase 5c-5d: fewer than 2 articles returns empty."""
    from agentdrive.knowledge.compilation.connections import discover_and_link
    from agentdrive.knowledge.models import Article, KnowledgeBase
    from agentdrive.models import Tenant
    from agentdrive.models.types import ArticleStatus, ArticleType, KBStatus

    tenant = Tenant(name="Test")
    db_session.add(tenant)
    await db_session.flush()

    kb = KnowledgeBase(tenant_id=tenant.id, name="Solo KB", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()

    a = Article(
        knowledge_base_id=kb.id, title="Only", content="Only article",
        article_type=ArticleType.CONCEPT, status=ArticleStatus.PUBLISHED, token_count=5,
    )
    db_session.add(a)
    await db_session.commit()

    links = await discover_and_link(kb.id, db_session)
    assert links == []
    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
@patch("agentdrive.knowledge.compilation.embedding.EmbeddingClient")
async def test_embed_articles(mock_embed_cls, db_session):
    """Phase 5e: articles get embedded via raw SQL."""
    from agentdrive.knowledge.compilation.embedding import embed_articles
    from agentdrive.knowledge.models import Article, KnowledgeBase
    from agentdrive.models import Tenant
    from agentdrive.models.types import ArticleStatus, ArticleType, KBStatus

    tenant = Tenant(name="Test")
    db_session.add(tenant)
    await db_session.flush()

    kb = KnowledgeBase(tenant_id=tenant.id, name="Embed KB", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()

    article = Article(
        knowledge_base_id=kb.id, title="Test Article", content="Some content here",
        article_type=ArticleType.CONCEPT, status=ArticleStatus.PUBLISHED, token_count=3,
    )
    db_session.add(article)
    await db_session.commit()

    fake_vector = [0.1] * 1024
    mock_instance = MagicMock()
    mock_instance.embed.return_value = [fake_vector]
    mock_instance.truncate.return_value = fake_vector[:256]
    mock_embed_cls.return_value = mock_instance

    count = await embed_articles(kb.id, db_session)
    assert count == 1
    mock_instance.embed.assert_called_once()
    mock_instance.truncate.assert_called_once_with(fake_vector, 256)
