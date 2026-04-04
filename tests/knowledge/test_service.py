import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from agentdrive.knowledge.models import (
    Article,
    ArticleSource,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from agentdrive.knowledge.service import KBService
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import ArticleStatus, ArticleType, FileStatus, KBStatus


@pytest_asyncio.fixture
async def tenant(db_session):
    t = Tenant(name="Test Tenant")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def ready_file(db_session, tenant):
    f = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="t/f/test.pdf",
        file_size=100,
        status=FileStatus.READY,
    )
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f


@pytest_asyncio.fixture
async def service(db_session):
    return KBService(db_session)


@pytest.mark.asyncio
async def test_create_kb(service, tenant):
    kb = await service.create(tenant.id, "My KB", description="Test KB")
    assert kb.name == "My KB"
    assert kb.description == "Test KB"
    assert kb.status == KBStatus.ACTIVE
    assert kb.tenant_id == tenant.id
    assert kb.id is not None


@pytest.mark.asyncio
async def test_create_duplicate_kb_raises(service, tenant):
    await service.create(tenant.id, "Duplicate KB")
    with pytest.raises(ValueError, match="already exists"):
        await service.create(tenant.id, "Duplicate KB")


@pytest.mark.asyncio
async def test_get_kb_by_name(service, tenant):
    kb = await service.create(tenant.id, "Named KB")
    resolved = await service.resolve(tenant.id, "Named KB")
    assert resolved is not None
    assert resolved.id == kb.id


@pytest.mark.asyncio
async def test_resolve_by_uuid(service, tenant):
    kb = await service.create(tenant.id, "UUID KB")
    resolved = await service.resolve(tenant.id, str(kb.id))
    assert resolved is not None
    assert resolved.id == kb.id


@pytest.mark.asyncio
async def test_resolve_not_found(service, tenant):
    result = await service.resolve(tenant.id, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_kbs(service, tenant):
    await service.create(tenant.id, "KB One")
    await service.create(tenant.id, "KB Two")
    kbs = await service.list(tenant.id)
    assert len(kbs) == 2
    names = {kb.name for kb in kbs}
    assert names == {"KB One", "KB Two"}


@pytest.mark.asyncio
async def test_delete_kb(service, tenant, db_session):
    kb = await service.create(tenant.id, "Delete Me")
    kb_id = kb.id
    await service.delete(tenant.id, kb_id)
    result = await service.get(tenant.id, kb_id)
    assert result is None


@pytest.mark.asyncio
async def test_add_files_to_kb(service, tenant, ready_file):
    kb = await service.create(tenant.id, "File KB")
    added = await service.add_files(tenant.id, kb.id, [ready_file.id])
    assert len(added) == 1
    assert added[0].file_id == ready_file.id
    count = await service.get_file_count(kb.id)
    assert count == 1


@pytest.mark.asyncio
async def test_add_duplicate_file_skips(service, tenant, ready_file, db_session):
    kb = await service.create(tenant.id, "Dup File KB")
    await service.add_files(tenant.id, kb.id, [ready_file.id])
    await db_session.commit()

    second_add = await service.add_files(tenant.id, kb.id, [ready_file.id])
    assert len(second_add) == 0
    count = await service.get_file_count(kb.id)
    assert count == 1


@pytest.mark.asyncio
async def test_add_files_invalid_file_raises(service, tenant):
    kb = await service.create(tenant.id, "Bad File KB")
    with pytest.raises(ValueError, match="not found"):
        await service.add_files(tenant.id, kb.id, [uuid.uuid4()])


@pytest.mark.asyncio
async def test_add_files_invalid_kb_raises(service, tenant, ready_file):
    with pytest.raises(ValueError, match="not found"):
        await service.add_files(tenant.id, uuid.uuid4(), [ready_file.id])


@pytest.mark.asyncio
async def test_remove_files_marks_articles_stale(service, tenant, ready_file, db_session):
    kb = await service.create(tenant.id, "Stale KB")
    await service.add_files(tenant.id, kb.id, [ready_file.id])

    # Create parent chunk + chunk for the file
    parent = ParentChunk(
        file_id=ready_file.id,
        content="Parent content",
        token_count=10,
    )
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=ready_file.id,
        parent_chunk_id=parent.id,
        chunk_index=0,
        content="Chunk content",
        token_count=5,
        content_type="pdf",
    )
    db_session.add(chunk)
    await db_session.flush()

    # Create an article with a source pointing to the chunk
    article = Article(
        knowledge_base_id=kb.id,
        title="Test Article",
        content="Article based on chunk.",
        article_type=ArticleType.CONCEPT,
        status=ArticleStatus.PUBLISHED,
        token_count=8,
    )
    db_session.add(article)
    await db_session.flush()

    source = ArticleSource(
        article_id=article.id,
        chunk_id=chunk.id,
        excerpt="Chunk content",
    )
    db_session.add(source)
    await db_session.commit()

    # Remove the file
    await service.remove_files(tenant.id, kb.id, [ready_file.id])
    await db_session.commit()

    # Article should be STALE
    result = await db_session.execute(
        select(Article).where(Article.id == article.id)
    )
    updated_article = result.scalar_one()
    assert updated_article.status == ArticleStatus.STALE

    # ArticleSource should be deleted
    source_result = await db_session.execute(
        select(ArticleSource).where(ArticleSource.article_id == article.id)
    )
    assert source_result.scalar_one_or_none() is None

    # KnowledgeBaseFile junction should be deleted
    kbf_result = await db_session.execute(
        select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.knowledge_base_id == kb.id,
            KnowledgeBaseFile.file_id == ready_file.id,
        )
    )
    assert kbf_result.scalar_one_or_none() is None
