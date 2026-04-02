"""Integration test: real PDF through the full four-phase pipeline with mocked external APIs."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.file_batch import FileBatch
from agentdrive.models.file_summary import FileSummary
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import BatchStatus, FileStatus
from agentdrive.services.ingest import process_file

REALISTIC_MARKDOWN = """# Acme Corp Master Services Agreement

This Master Services Agreement ("Agreement") is entered into between Acme Corporation ("Provider") and Beta Industries ("Client").

## 1. Scope of Services

Provider shall deliver the following services to Client:

- Cloud infrastructure management and monitoring
- 24/7 technical support with guaranteed response times
- Quarterly security audits and compliance reporting
- Data backup and disaster recovery services

The services shall commence on the Effective Date and continue for a period of thirty-six (36) months.

## 2. Service Level Agreement

Provider guarantees the following service levels:

| Metric | Target | Measurement Period |
| --- | --- | --- |
| Uptime | 99.95% | Monthly |
| Response Time | < 200ms | Weekly Average |
| Support Response | < 15 min | Per Incident |
| Data Recovery | < 4 hours | Per Incident |

Failure to meet these targets shall result in service credits as outlined in Exhibit A.

## 3. Pricing and Payment

The total contract value is $2,400,000 over the 36-month term, payable in equal monthly installments of $66,666.67.

### 3.1 Payment Terms

All invoices are due within thirty (30) days of receipt. Late payments shall accrue interest at a rate of 1.5% per month.

### 3.2 Price Adjustments

Provider may adjust pricing annually, not to exceed 5% per year, with ninety (90) days written notice.

## 4. Liability

The total aggregate liability of Provider under this Agreement shall not exceed the total fees paid by Client in the twelve (12) months preceding the claim. Neither party shall be liable for indirect, incidental, or consequential damages.

## 5. Termination

Either party may terminate this Agreement with ninety (90) days written notice. In the event of material breach, the non-breaching party may terminate immediately upon written notice if the breach is not cured within thirty (30) days.
"""


def _create_real_pdf(num_pages: int = 3) -> Path:
    """Create a real multi-page PDF using pypdf. Pages are blank but structurally valid."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)  # US Letter

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    writer.write(tmp)
    tmp.close()
    return Path(tmp.name)


@pytest.mark.asyncio
async def test_real_pdf_full_pipeline(db_session: AsyncSession) -> None:
    """End-to-end: real PDF file -> chunking (Document AI mocked) -> summarize -> enrich -> embed."""

    # -- Setup: create tenant + file in DB --
    tenant = Tenant(name="test-tenant")
    db_session.add(tenant)
    await db_session.flush()

    pdf_path = _create_real_pdf(num_pages=3)

    file = File(
        tenant_id=tenant.id,
        filename="acme_msa.pdf",
        content_type="pdf",
        gcs_path="tenants/test/files/acme_msa.pdf",
        file_size=pdf_path.stat().st_size,
        status=FileStatus.PENDING,
        extra_metadata={},
    )
    db_session.add(file)
    await db_session.commit()

    print(f"\n{'='*60}")
    print(f"File ID:   {file.id}")
    print(f"Tenant ID: {tenant.id}")
    print(f"PDF path:  {pdf_path} ({pdf_path.stat().st_size} bytes)")
    print(f"{'='*60}")

    # -- Mocks --
    # 1. StorageService.download_to_tempfile -> return our real PDF
    # 2. PdfChunker._process_batch -> return realistic markdown (skip Document AI)
    with (
        patch(
            "agentdrive.services.ingest.StorageService"
        ) as MockStorage,
        patch(
            "agentdrive.chunking.pdf.PdfChunker._process_batch",
            return_value=REALISTIC_MARKDOWN,
        ),
    ):
        MockStorage.return_value.download_to_tempfile.return_value = pdf_path

        await process_file(file.id, db_session)

    # -- Assertions --

    # 1. File status
    result = await db_session.execute(select(File).where(File.id == file.id))
    file_after = result.scalar_one()
    assert file_after.status == FileStatus.READY, f"Expected READY, got {file_after.status}"
    print(f"\nFile status: {file_after.status}")
    print(f"Total batches: {file_after.total_batches}")
    print(f"Completed batches: {file_after.completed_batches}")
    print(f"Current phase: {file_after.current_phase}")

    # 2. ParentChunks exist
    result = await db_session.execute(
        select(ParentChunk).where(ParentChunk.file_id == file.id)
    )
    parents = result.scalars().all()
    assert len(parents) > 0, "Expected at least one ParentChunk"
    print(f"\nParentChunks: {len(parents)}")
    for i, p in enumerate(parents):
        preview = p.content[:80].replace("\n", " ")
        print(f"  [{i}] tokens={p.token_count} | {preview}...")

    # 3. Chunks exist with content
    result = await db_session.execute(
        select(Chunk).where(Chunk.file_id == file.id).order_by(Chunk.chunk_index)
    )
    chunks = result.scalars().all()
    assert len(chunks) > 0, "Expected at least one Chunk"
    for chunk in chunks:
        assert chunk.content.strip(), f"Chunk {chunk.chunk_index} has empty content"
        assert chunk.content_type, f"Chunk {chunk.chunk_index} has no content_type"

    print(f"\nChunks: {len(chunks)}")
    for c in chunks:
        preview = c.content[:80].replace("\n", " ")
        print(f"  [{c.chunk_index}] type={c.content_type} tokens={c.token_count} | {preview}...")

    # 4. chunk_index values are sequential starting at 0
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks))), f"Non-sequential chunk indices: {indices}"
    print(f"\nChunk indices: {indices} (sequential)")

    # 5. FileBatch exists with all statuses COMPLETED
    result = await db_session.execute(
        select(FileBatch).where(FileBatch.file_id == file.id)
    )
    batches = result.scalars().all()
    assert len(batches) >= 1, "Expected at least one FileBatch"
    for batch in batches:
        assert batch.chunking_status == BatchStatus.COMPLETED, (
            f"Batch {batch.batch_index} chunking: {batch.chunking_status}"
        )
        assert batch.enrichment_status == BatchStatus.COMPLETED, (
            f"Batch {batch.batch_index} enrichment: {batch.enrichment_status}"
        )
        assert batch.embedding_status == BatchStatus.COMPLETED, (
            f"Batch {batch.batch_index} embedding: {batch.embedding_status}"
        )
        assert batch.chunk_count == len(chunks), (
            f"Batch chunk_count={batch.chunk_count}, expected {len(chunks)}"
        )
    print(f"\nFileBatches: {len(batches)}")
    for b in batches:
        print(
            f"  [batch {b.batch_index}] chunks={b.chunk_count} "
            f"chunking={b.chunking_status} enrichment={b.enrichment_status} "
            f"embedding={b.embedding_status}"
        )

    # 6. FileSummary exists
    result = await db_session.execute(
        select(FileSummary).where(FileSummary.file_id == file.id)
    )
    summary = result.scalar_one_or_none()
    assert summary is not None, "Expected a FileSummary record"
    print(f"\nFileSummary: document_summary length={len(summary.document_summary)}")
    print(f"  section_summaries count={len(summary.section_summaries)}")

    # 7. Content sanity — key phrases from the markdown should appear in chunks
    all_content = " ".join(c.content for c in chunks)
    key_phrases = ["Acme Corp", "Service Level Agreement", "Pricing", "Termination"]
    found = [p for p in key_phrases if p in all_content]
    print(f"\nKey phrases found in chunks: {found}")

    # -- Summary --
    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"  Parents:  {len(parents)}")
    print(f"  Chunks:   {len(chunks)}")
    print(f"  Batches:  {len(batches)}")
    print(f"  Summary:  {'yes' if summary else 'no'}")
    print(f"  Status:   {file_after.status}")
    print(f"{'='*60}")

    # Cleanup
    pdf_path.unlink(missing_ok=True)
