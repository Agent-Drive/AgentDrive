import pytest
import pytest_asyncio
from sqlalchemy import func, select

from agentdrive.knowledge.health.checker import run_health_check
from agentdrive.knowledge.health.repair import repair_kb
from agentdrive.knowledge.models import Article, ArticleLink, KnowledgeBase
from agentdrive.models import Tenant
from agentdrive.models.types import ArticleStatus, KBStatus


@pytest_asyncio.fixture
async def tenant(db_session):
    t = Tenant(name="Test")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest.mark.asyncio
async def test_health_check_empty_kb(db_session, tenant):
    kb = KnowledgeBase(tenant_id=tenant.id, name="Empty", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.commit()
    report = await run_health_check(kb.id, db_session, quick=True)
    assert report["score"] == 1.0
    assert report["issues"] == []


@pytest.mark.asyncio
async def test_health_check_detects_stale(db_session, tenant):
    kb = KnowledgeBase(tenant_id=tenant.id, name="Test", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()
    stale = Article(
        knowledge_base_id=kb.id,
        title="Stale",
        content="...",
        article_type="concept",
        status=ArticleStatus.STALE,
        token_count=5,
    )
    db_session.add(stale)
    await db_session.commit()
    report = await run_health_check(kb.id, db_session, quick=True)
    stale_issues = [i for i in report["issues"] if i["type"] == "stale"]
    assert len(stale_issues) == 1


@pytest.mark.asyncio
async def test_health_check_detects_orphans(db_session, tenant):
    kb = KnowledgeBase(tenant_id=tenant.id, name="Test", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()
    a1 = Article(
        knowledge_base_id=kb.id,
        title="A1",
        content="...",
        article_type="concept",
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    a2 = Article(
        knowledge_base_id=kb.id,
        title="A2",
        content="...",
        article_type="concept",
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    db_session.add_all([a1, a2])
    await db_session.commit()
    report = await run_health_check(kb.id, db_session, quick=True)
    orphan_issues = [i for i in report["issues"] if i["type"] == "orphan"]
    assert len(orphan_issues) == 2  # Both articles are orphans


@pytest.mark.asyncio
async def test_health_check_linked_not_orphan(db_session, tenant):
    kb = KnowledgeBase(tenant_id=tenant.id, name="Test", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()
    a1 = Article(
        knowledge_base_id=kb.id,
        title="A1",
        content="...",
        article_type="concept",
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    a2 = Article(
        knowledge_base_id=kb.id,
        title="A2",
        content="...",
        article_type="concept",
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    db_session.add_all([a1, a2])
    await db_session.flush()
    link = ArticleLink(
        source_article_id=a1.id, target_article_id=a2.id, link_type="related"
    )
    db_session.add(link)
    await db_session.commit()
    report = await run_health_check(kb.id, db_session, quick=True)
    orphan_issues = [i for i in report["issues"] if i["type"] == "orphan"]
    assert len(orphan_issues) == 0  # Both linked


@pytest.mark.asyncio
async def test_repair_deletes_stale(db_session, tenant):
    kb = KnowledgeBase(tenant_id=tenant.id, name="Test", status=KBStatus.ACTIVE)
    db_session.add(kb)
    await db_session.flush()
    stale = Article(
        knowledge_base_id=kb.id,
        title="Stale",
        content="...",
        article_type="concept",
        status=ArticleStatus.STALE,
        token_count=5,
    )
    ok = Article(
        knowledge_base_id=kb.id,
        title="OK",
        content="...",
        article_type="concept",
        status=ArticleStatus.PUBLISHED,
        token_count=5,
    )
    db_session.add_all([stale, ok])
    await db_session.commit()

    result = await repair_kb(kb.id, db_session, ["stale"])
    await db_session.commit()
    assert result["count"] == 1

    count = await db_session.execute(
        select(func.count())
        .select_from(Article)
        .where(Article.knowledge_base_id == kb.id)
    )
    assert count.scalar() == 1  # Only "OK" remains
