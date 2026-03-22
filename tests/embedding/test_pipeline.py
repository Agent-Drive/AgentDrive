from unittest.mock import MagicMock, patch
import pytest
import pytest_asyncio
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key


@pytest_asyncio.fixture
async def file_with_chunks(db_session):
    tenant = Tenant(name="Test", api_key_hash=hash_api_key("sk-test"))
    db_session.add(tenant)
    await db_session.commit()
    file = File(
        tenant_id=tenant.id, filename="test.md", content_type="markdown",
        gcs_path="path", file_size=100, status="ready",
    )
    db_session.add(file)
    await db_session.commit()
    parent = ParentChunk(file_id=file.id, content="Full section", token_count=50)
    db_session.add(parent)
    await db_session.flush()
    chunk = Chunk(
        file_id=file.id, parent_chunk_id=parent.id, chunk_index=0,
        content="Hello world", context_prefix="File: test.md",
        token_count=5, content_type="text",
    )
    db_session.add(chunk)
    await db_session.commit()
    return file


@pytest.mark.asyncio
@patch("agentdrive.embedding.pipeline.EmbeddingClient")
async def test_embed_file_chunks(mock_client_cls, file_with_chunks, db_session):
    mock_client = MagicMock()
    mock_client.embed.return_value = [[0.1] * 1024]
    mock_client.truncate.return_value = [0.1] * 256
    mock_client_cls.return_value = mock_client
    from agentdrive.embedding.pipeline import embed_file_chunks
    count = await embed_file_chunks(file_with_chunks.id, db_session)
    assert count == 1
    mock_client.embed.assert_called_once()
