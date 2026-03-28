import pytest
from unittest.mock import patch
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus
from agentdrive.embedding.pipeline import embed_file_chunks


@pytest.mark.asyncio
async def test_embed_with_batch_id_scopes_to_batch(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    file = File(tenant_id=tenant.id, filename="t.pdf", content_type="pdf", gcs_path="t/p", file_size=100)
    db_session.add(file)
    await db_session.flush()
    batch1 = FileBatch(file_id=file.id, batch_index=0, chunking_status=BatchStatus.COMPLETED, chunk_count=1)
    batch2 = FileBatch(file_id=file.id, batch_index=1, chunking_status=BatchStatus.COMPLETED, chunk_count=1)
    db_session.add_all([batch1, batch2])
    await db_session.flush()
    p1 = ParentChunk(file_id=file.id, batch_id=batch1.id, content="P1", token_count=5)
    p2 = ParentChunk(file_id=file.id, batch_id=batch2.id, content="P2", token_count=5)
    db_session.add_all([p1, p2])
    await db_session.flush()
    c1 = Chunk(file_id=file.id, parent_chunk_id=p1.id, batch_id=batch1.id, chunk_index=0, content="B1", context_prefix="", token_count=5, content_type="text")
    c2 = Chunk(file_id=file.id, parent_chunk_id=p2.id, batch_id=batch2.id, chunk_index=1, content="B2", context_prefix="", token_count=5, content_type="text")
    db_session.add_all([c1, c2])
    await db_session.commit()

    with patch("agentdrive.embedding.pipeline.EmbeddingClient") as MockClient:
        instance = MockClient.return_value
        instance.embed.return_value = [[0.1] * 1024]
        instance.truncate.return_value = [0.1] * 256
        count = await embed_file_chunks(file.id, db_session, batch_id=batch1.id)
        assert count == 1  # Only batch 1
