import pytest
import pytest_asyncio
from sqlalchemy import select

from agentdrive.knowledge.models import (
    Article,
    ArticleLink,
    ArticleSource,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import (
    ArticleStatus,
    ArticleType,
    KBStatus,
    LinkType,
)


# ── Enum unit tests (existing) ──────────────────────────────────


class TestKBStatus:
    def test_values(self) -> None:
        assert KBStatus.ACTIVE == "active"
        assert KBStatus.COMPILING == "compiling"
        assert KBStatus.ERROR == "error"

    def test_members(self) -> None:
        assert set(KBStatus) == {KBStatus.ACTIVE, KBStatus.COMPILING, KBStatus.ERROR}


class TestArticleType:
    def test_values(self) -> None:
        assert ArticleType.CONCEPT == "concept"
        assert ArticleType.SUMMARY == "summary"
        assert ArticleType.CONNECTION == "connection"
        assert ArticleType.QUESTION == "question"
        assert ArticleType.DERIVED == "derived"
        assert ArticleType.MANUAL == "manual"

    def test_members(self) -> None:
        assert len(ArticleType) == 6


class TestArticleStatus:
    def test_values(self) -> None:
        assert ArticleStatus.DRAFT == "draft"
        assert ArticleStatus.PUBLISHED == "published"
        assert ArticleStatus.STALE == "stale"

    def test_members(self) -> None:
        assert set(ArticleStatus) == {
            ArticleStatus.DRAFT,
            ArticleStatus.PUBLISHED,
            ArticleStatus.STALE,
        }


class TestLinkType:
    def test_values(self) -> None:
        assert LinkType.RELATED == "related"
        assert LinkType.CONTRADICTS == "contradicts"
        assert LinkType.EXTENDS == "extends"
        assert LinkType.PREREQUISITE == "prerequisite"

    def test_members(self) -> None:
        assert len(LinkType) == 4


# ── DB integration tests ────────────────────────────────────────


@pytest_asyncio.fixture
async def tenant(db_session):
    t = Tenant(name="Test")
    db_session.add(t)
    await db_session.flush()
    return t


@pytest_asyncio.fixture
async def file(db_session, tenant):
    f = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="gs://bucket/test.pdf",
        file_size=1024,
        status="ready",
    )
    db_session.add(f)
    await db_session.flush()
    return f


@pytest_asyncio.fixture
async def kb(db_session, tenant):
    kb = KnowledgeBase(
        tenant_id=tenant.id,
        name="Test KB",
        description="A test knowledge base",
        status=KBStatus.ACTIVE,
    )
    db_session.add(kb)
    await db_session.flush()
    return kb


@pytest.mark.asyncio
async def test_create_knowledge_base(db_session, tenant):
    kb = KnowledgeBase(
        tenant_id=tenant.id,
        name="My KB",
        description="Description here",
        status=KBStatus.ACTIVE,
    )
    db_session.add(kb)
    await db_session.flush()

    result = await db_session.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
    )
    loaded = result.scalar_one()

    assert loaded.name == "My KB"
    assert loaded.description == "Description here"
    assert loaded.status == KBStatus.ACTIVE
    assert loaded.tenant_id == tenant.id
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


@pytest.mark.asyncio
async def test_add_file_to_kb(db_session, kb, file):
    kbf = KnowledgeBaseFile(
        knowledge_base_id=kb.id,
        file_id=file.id,
    )
    db_session.add(kbf)
    await db_session.flush()

    result = await db_session.execute(
        select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.knowledge_base_id == kb.id,
            KnowledgeBaseFile.file_id == file.id,
        )
    )
    loaded = result.scalar_one()

    assert loaded.knowledge_base_id == kb.id
    assert loaded.file_id == file.id
    assert loaded.added_at is not None


@pytest.mark.asyncio
async def test_create_article(db_session, kb):
    article = Article(
        knowledge_base_id=kb.id,
        title="Test Article",
        content="This is the content of the article.",
        article_type=ArticleType.CONCEPT,
        category="testing",
        status=ArticleStatus.DRAFT,
        token_count=42,
    )
    db_session.add(article)
    await db_session.flush()

    result = await db_session.execute(
        select(Article).where(Article.id == article.id)
    )
    loaded = result.scalar_one()

    assert loaded.title == "Test Article"
    assert loaded.content == "This is the content of the article."
    assert loaded.article_type == ArticleType.CONCEPT
    assert loaded.category == "testing"
    assert loaded.status == ArticleStatus.DRAFT
    assert loaded.token_count == 42
    assert loaded.knowledge_base_id == kb.id


@pytest.mark.asyncio
async def test_article_source_provenance(db_session, kb, file):
    # Create parent chunk and chunk
    parent = ParentChunk(
        file_id=file.id,
        content="Parent content",
        token_count=10,
    )
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=file.id,
        parent_chunk_id=parent.id,
        chunk_index=0,
        content="Chunk content for provenance",
        token_count=5,
        content_type="pdf",
    )
    db_session.add(chunk)
    await db_session.flush()

    article = Article(
        knowledge_base_id=kb.id,
        title="Provenance Article",
        content="Article derived from chunk.",
        article_type=ArticleType.SUMMARY,
        status=ArticleStatus.PUBLISHED,
        token_count=8,
    )
    db_session.add(article)
    await db_session.flush()

    source = ArticleSource(
        article_id=article.id,
        chunk_id=chunk.id,
        excerpt="Chunk content for provenance",
    )
    db_session.add(source)
    await db_session.flush()

    result = await db_session.execute(
        select(ArticleSource).where(ArticleSource.article_id == article.id)
    )
    loaded = result.scalar_one()

    assert loaded.chunk_id == chunk.id
    assert loaded.excerpt == "Chunk content for provenance"


@pytest.mark.asyncio
async def test_article_link_backlinks(db_session, kb):
    a1 = Article(
        knowledge_base_id=kb.id,
        title="Article A",
        content="First article content",
        article_type=ArticleType.CONCEPT,
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    a2 = Article(
        knowledge_base_id=kb.id,
        title="Article B",
        content="Second article content",
        article_type=ArticleType.CONNECTION,
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    db_session.add_all([a1, a2])
    await db_session.flush()

    link = ArticleLink(
        source_article_id=a1.id,
        target_article_id=a2.id,
        link_type=LinkType.RELATED,
    )
    db_session.add(link)
    await db_session.flush()

    # Verify forward link
    result = await db_session.execute(
        select(ArticleLink).where(ArticleLink.source_article_id == a1.id)
    )
    loaded = result.scalar_one()
    assert loaded.target_article_id == a2.id
    assert loaded.link_type == LinkType.RELATED

    # Verify backward query
    result = await db_session.execute(
        select(ArticleLink).where(ArticleLink.target_article_id == a2.id)
    )
    backlink = result.scalar_one()
    assert backlink.source_article_id == a1.id
