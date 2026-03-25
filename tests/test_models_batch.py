import pytest
import pytest_asyncio
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus


@pytest.mark.asyncio
async def test_create_file_batch(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.flush()

    batch = FileBatch(
        file_id=file.id,
        batch_index=0,
        page_range="1-30",
        chunk_count=0,
    )
    db_session.add(batch)
    await db_session.flush()

    assert batch.id is not None
    assert batch.chunking_status == BatchStatus.PENDING
    assert batch.enrichment_status == BatchStatus.PENDING
    assert batch.embedding_status == BatchStatus.PENDING


@pytest.mark.asyncio
async def test_create_file_summary(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.flush()

    summary = FileSummary(
        file_id=file.id,
        document_summary="This is a test document about widgets.",
        section_summaries=[
            {"heading": "Introduction", "summary": "Overview of widgets"},
            {"heading": "Pricing", "summary": "Widget pricing details"},
        ],
    )
    db_session.add(summary)
    await db_session.flush()

    assert summary.id is not None
    assert summary.document_summary == "This is a test document about widgets."
    assert len(summary.section_summaries) == 2


@pytest.mark.asyncio
async def test_file_progress_fields(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()

    file = File(
        tenant_id=tenant.id,
        filename="test.pdf",
        content_type="pdf",
        gcs_path="tenants/x/files/y/test.pdf",
        file_size=1000,
    )
    db_session.add(file)
    await db_session.flush()

    assert file.total_batches == 0
    assert file.completed_batches == 0
    assert file.current_phase is None
    assert file.retry_count == 0
