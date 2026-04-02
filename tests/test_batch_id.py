import pytest
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus


@pytest.mark.asyncio
async def test_chunk_has_batch_id(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    file = File(tenant_id=tenant.id, filename="test.pdf", content_type="pdf", gcs_path="test/path", file_size=100)
    db_session.add(file)
    await db_session.flush()
    batch = FileBatch(file_id=file.id, batch_index=0, chunking_status=BatchStatus.COMPLETED, chunk_count=1)
    db_session.add(batch)
    await db_session.flush()
    parent = ParentChunk(file_id=file.id, batch_id=batch.id, content="Test", token_count=5)
    db_session.add(parent)
    await db_session.flush()
    chunk = Chunk(file_id=file.id, parent_chunk_id=parent.id, batch_id=batch.id,
                  chunk_index=0, content="Child", context_prefix="", token_count=5, content_type="text")
    db_session.add(chunk)
    await db_session.flush()
    assert chunk.batch_id == batch.id
    assert parent.batch_id == batch.id


@pytest.mark.asyncio
async def test_batch_id_nullable(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    file = File(tenant_id=tenant.id, filename="test.pdf", content_type="pdf", gcs_path="test/path", file_size=100)
    db_session.add(file)
    await db_session.flush()
    parent = ParentChunk(file_id=file.id, content="No batch", token_count=5)
    db_session.add(parent)
    await db_session.flush()
    assert parent.batch_id is None
