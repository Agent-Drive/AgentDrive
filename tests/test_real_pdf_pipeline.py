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


LARGE_DOC_MARKDOWN = """# Annual Financial Report 2025

## Executive Summary

Revenue grew 23% year-over-year to $4.2B. Operating margins expanded to 18.5%, driven by cloud services growth and cost optimization initiatives. Free cash flow reached $890M, enabling continued investment in R&D and strategic acquisitions.

## 1. Revenue Breakdown

### 1.1 Cloud Services

Cloud revenue reached $2.1B, representing 50% of total revenue. Key growth drivers included:

- Enterprise migrations increased 45% YoY
- New customer acquisitions in APAC region
- Expansion of managed services portfolio
- Strategic partnerships with hyperscaler providers

### 1.2 Professional Services

Professional services contributed $1.4B in revenue:

| Service Line | Revenue | Growth | Margin |
| --- | --- | --- | --- |
| Consulting | $620M | +15% | 22% |
| Implementation | $480M | +28% | 19% |
| Managed Services | $300M | +42% | 31% |

### 1.3 Product Licensing

Legacy product licensing revenue was $700M, declining 8% as customers transition to subscription models.

## 2. Operating Expenses

Total operating expenses were $3.42B:

### 2.1 Research and Development

R&D spending increased to $840M (20% of revenue), focused on:

- AI/ML capabilities for the platform
- Security and compliance automation
- Developer experience improvements
- Edge computing infrastructure

### 2.2 Sales and Marketing

Sales and marketing expenses were $1.1B, with customer acquisition costs improving 12% due to product-led growth initiatives.

### 2.3 General and Administrative

G&A expenses were $480M, including $85M in restructuring charges related to the EMEA consolidation.

## 3. Balance Sheet Highlights

| Item | 2025 | 2024 | Change |
| --- | --- | --- | --- |
| Cash and Equivalents | $3.2B | $2.8B | +14% |
| Total Debt | $1.5B | $1.8B | -17% |
| Stockholders Equity | $8.4B | $7.1B | +18% |
| Working Capital | $2.1B | $1.6B | +31% |

## 4. Strategic Acquisitions

Three acquisitions were completed during the fiscal year:

### 4.1 CloudSecure Inc.

Acquired for $340M in Q1. CloudSecure's zero-trust security platform was integrated into the core offering, contributing $45M in incremental revenue.

### 4.2 DataFlow Analytics

Acquired for $210M in Q2. Real-time analytics capabilities enhanced the platform's data processing pipeline.

### 4.3 EdgeNet Systems

Acquired for $180M in Q3. Edge computing infrastructure expanded geographic coverage to 42 countries.

## 5. Risk Factors

Key risks include:

- Increasing competition from hyperscaler providers offering integrated solutions
- Regulatory changes in data sovereignty requirements across jurisdictions
- Currency fluctuations impacting international revenue (32% of total)
- Talent retention in competitive AI/ML engineering market
- Supply chain constraints affecting hardware procurement timelines

## 6. Forward Guidance

For fiscal year 2026, management expects:

- Revenue of $4.9B-$5.1B (17-21% growth)
- Operating margin expansion to 20-21%
- Cloud services to exceed 55% of total revenue
- R&D investment to increase to 22% of revenue
- Two to three additional strategic acquisitions

## 7. Corporate Governance

### 7.1 Board Composition

The board was expanded to 11 members with the addition of two independent directors with expertise in AI governance and international regulatory compliance.

### 7.2 ESG Initiatives

The company achieved carbon neutrality for Scope 1 and Scope 2 emissions. A commitment was made to achieve net-zero for Scope 3 emissions by 2030. The diversity report showed improvement across all metrics, with women representing 38% of leadership positions.

## Appendix A: Quarterly Revenue Detail

| Quarter | Cloud | Services | Licensing | Total |
| --- | --- | --- | --- | --- |
| Q1 | $480M | $330M | $185M | $995M |
| Q2 | $510M | $345M | $180M | $1,035M |
| Q3 | $540M | $360M | $172M | $1,072M |
| Q4 | $570M | $365M | $163M | $1,098M |
"""

BATCH2_MARKDOWN = """# Operations Report: Pages 501-600

## 8. Regional Operations

### 8.1 North America

North American operations contributed 52% of total revenue. The region saw strong enterprise adoption.

### 8.2 EMEA

EMEA operations were restructured in Q2, consolidating three regional offices into a single European hub in Amsterdam.

### 8.3 APAC

APAC revenue grew 38% YoY, driven by expansion into Japan and South Korea markets.

## 9. Technology Infrastructure

### 9.1 Data Centers

The company operates 24 data centers globally with 99.99% uptime SLA. Three new facilities were commissioned.

### 9.2 Network Architecture

Edge computing nodes were deployed in 15 new locations, reducing average latency by 34%.

## 10. Human Resources

Total headcount reached 12,400 employees across 28 countries. Engineering represents 45% of the workforce.
"""


@pytest.mark.asyncio
async def test_large_pdf_batch_path(db_session: AsyncSession) -> None:
    """50-page PDF exercises the batch Document AI path (_process_batch_api)."""

    # -- Setup: create tenant + file in DB --
    tenant = Tenant(name="test-tenant-large")
    db_session.add(tenant)
    await db_session.flush()

    pdf_path = _create_real_pdf(num_pages=50)

    file = File(
        tenant_id=tenant.id,
        filename="annual_report_2025.pdf",
        content_type="pdf",
        gcs_path="tenants/test/files/annual_report_2025.pdf",
        file_size=pdf_path.stat().st_size,
        status=FileStatus.PENDING,
        extra_metadata={},
    )
    db_session.add(file)
    await db_session.commit()

    print(f"\n{'='*60}")
    print(f"File ID:   {file.id}")
    print(f"Tenant ID: {tenant.id}")
    print(f"PDF path:  {pdf_path} ({pdf_path.stat().st_size} bytes, 50 pages)")
    print(f"{'='*60}")

    # -- Mocks --
    # Mock _process_batch_api (NOT _process_batch) since 50 pages > 30 triggers batch path
    # Mock StorageService in ingest module
    with (
        patch(
            "agentdrive.services.ingest.StorageService"
        ) as MockStorage,
        patch(
            "agentdrive.chunking.pdf.PdfChunker._process_batch_api",
            return_value=LARGE_DOC_MARKDOWN,
        ) as mock_batch_api,
        patch(
            "agentdrive.chunking.pdf.PdfChunker._process_batch",
            side_effect=AssertionError("_process_batch should NOT be called for 50-page PDF"),
        ),
    ):
        MockStorage.return_value.download_to_tempfile.return_value = pdf_path

        await process_file(file.id, db_session)

    # -- Assertions --

    # 1. File status is READY
    result = await db_session.execute(select(File).where(File.id == file.id))
    file_after = result.scalar_one()
    assert file_after.status == FileStatus.READY, f"Expected READY, got {file_after.status}"
    print(f"\nFile status: {file_after.status}")
    print(f"Total batches: {file_after.total_batches}")
    print(f"Completed batches: {file_after.completed_batches}")
    print(f"Current phase: {file_after.current_phase}")

    # 2. _process_batch_api was called (proving batch path was taken)
    mock_batch_api.assert_called_once()
    print(f"\n_process_batch_api called: {mock_batch_api.call_count} time(s)")
    print(f"  args: gcs_path={mock_batch_api.call_args[0][0]}, file_id={mock_batch_api.call_args[0][2]}")

    # 3. ParentChunks exist — should be more than the small PDF test
    result = await db_session.execute(
        select(ParentChunk).where(ParentChunk.file_id == file.id)
    )
    parents = result.scalars().all()
    assert len(parents) > 0, "Expected at least one ParentChunk"
    print(f"\nParentChunks: {len(parents)}")
    for i, p in enumerate(parents):
        preview = p.content[:80].replace("\n", " ")
        print(f"  [{i}] tokens={p.token_count} | {preview}...")

    # 4. Chunks — significantly more than the small PDF test (10+)
    result = await db_session.execute(
        select(Chunk).where(Chunk.file_id == file.id).order_by(Chunk.chunk_index)
    )
    chunks = result.scalars().all()
    assert len(chunks) >= 5, f"Expected 5+ chunks from large doc, got {len(chunks)}"
    for chunk in chunks:
        assert chunk.content.strip(), f"Chunk {chunk.chunk_index} has empty content"
        assert chunk.content_type, f"Chunk {chunk.chunk_index} has no content_type"

    print(f"\nChunks: {len(chunks)}")
    for c in chunks:
        preview = c.content[:80].replace("\n", " ")
        print(f"  [{c.chunk_index}] type={c.content_type} tokens={c.token_count} | {preview}...")

    # 5. Sequential chunk indices
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks))), f"Non-sequential chunk indices: {indices}"
    print(f"\nChunk indices: {indices} (sequential)")

    # 6. FileBatch exists with all statuses COMPLETED
    result = await db_session.execute(
        select(FileBatch).where(FileBatch.file_id == file.id)
    )
    batches = result.scalars().all()
    assert len(batches) >= 1, "Expected at least one FileBatch"
    for batch in batches:
        assert batch.chunking_status == BatchStatus.COMPLETED
        assert batch.enrichment_status == BatchStatus.COMPLETED
        assert batch.embedding_status == BatchStatus.COMPLETED
    print(f"\nFileBatches: {len(batches)}")
    for b in batches:
        print(
            f"  [batch {b.batch_index}] chunks={b.chunk_count} "
            f"chunking={b.chunking_status} enrichment={b.enrichment_status} "
            f"embedding={b.embedding_status}"
        )

    # 7. Content sanity — key phrases from the large doc markdown
    all_content = " ".join(c.content for c in chunks)
    key_phrases = ["Annual Financial Report", "Cloud Services", "Strategic Acquisitions", "ESG Initiatives"]
    found = [p for p in key_phrases if p in all_content]
    print(f"\nKey phrases found in chunks: {found}")
    assert len(found) >= 3, f"Expected at least 3 key phrases, found {found}"

    # -- Summary --
    print(f"\n{'='*60}")
    print("LARGE PDF BATCH PATH SUMMARY")
    print(f"  Parents:  {len(parents)}")
    print(f"  Chunks:   {len(chunks)}")
    print(f"  Batches:  {len(batches)}")
    print(f"  Status:   {file_after.status}")
    print(f"  Batch API called: {mock_batch_api.call_count}")
    print(f"{'='*60}")

    # Cleanup
    pdf_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_very_large_pdf_multi_batch(db_session: AsyncSession) -> None:
    """600-page PDF exercises chunk_file_batched (>500 pages -> multiple batch API calls)."""
    from agentdrive.chunking.pdf import PdfChunker

    # -- Create a 600-page PDF --
    pdf_path = _create_real_pdf(num_pages=600)

    print(f"\n{'='*60}")
    print(f"PDF path: {pdf_path} ({pdf_path.stat().st_size} bytes, 600 pages)")
    print(f"{'='*60}")

    call_count = 0

    def mock_batch_api(self, gcs_path: str, processor_name: str, file_id: str) -> str:
        nonlocal call_count
        call_count += 1
        if "1-500" in gcs_path or "1-500" in file_id:
            return LARGE_DOC_MARKDOWN
        else:
            return BATCH2_MARKDOWN

    # -- Mocks --
    with (
        patch(
            "agentdrive.chunking.pdf.PdfChunker._process_batch_api",
            mock_batch_api,
        ),
        patch(
            "agentdrive.chunking.pdf.StorageService"
        ) as MockStorage,
        patch(
            "agentdrive.chunking.pdf._processor_name",
            return_value="projects/test/locations/us/processors/test-proc",
        ),
    ):
        mock_storage_inst = MockStorage.return_value
        mock_storage_inst.upload_bytes.return_value = None
        mock_storage_inst.delete_blob.return_value = None

        chunker = PdfChunker()
        results = chunker.chunk_file_batched(
            path=pdf_path,
            filename="mega_report.pdf",
            gcs_path="tenants/test/files/mega_report.pdf",
            file_id="test-file-id-600",
        )

    # -- Assertions --

    # 1. Two batches returned (pages 1-500, pages 501-600)
    assert len(results) == 2, f"Expected 2 batch results, got {len(results)}"
    print(f"\nBatch results: {len(results)}")

    page_range_1, chunks_1 = results[0]
    page_range_2, chunks_2 = results[1]

    print(f"  Batch 1: range={page_range_1}, chunk_groups={len(chunks_1)}")
    print(f"  Batch 2: range={page_range_2}, chunk_groups={len(chunks_2)}")

    # 2. Correct page ranges
    assert page_range_1 == "1-500", f"Expected '1-500', got '{page_range_1}'"
    assert page_range_2 == "501-600", f"Expected '501-600', got '{page_range_2}'"

    # 3. Both batches produced chunks
    assert len(chunks_1) > 0, "Batch 1 should have chunks"
    assert len(chunks_2) > 0, "Batch 2 should have chunks"

    # 4. _process_batch_api was called twice
    assert call_count == 2, f"Expected 2 batch API calls, got {call_count}"
    print(f"\n_process_batch_api called: {call_count} times")

    # 5. StorageService was used for upload + cleanup
    assert mock_storage_inst.upload_bytes.call_count == 2, (
        f"Expected 2 upload_bytes calls, got {mock_storage_inst.upload_bytes.call_count}"
    )
    assert mock_storage_inst.delete_blob.call_count == 2, (
        f"Expected 2 delete_blob calls, got {mock_storage_inst.delete_blob.call_count}"
    )
    print(f"  upload_bytes calls: {mock_storage_inst.upload_bytes.call_count}")
    print(f"  delete_blob calls: {mock_storage_inst.delete_blob.call_count}")

    # 6. Enumerate actual chunks from both batches
    total_children_1 = sum(len(g.children) for g in chunks_1)
    total_children_2 = sum(len(g.children) for g in chunks_2)
    print(f"\n  Batch 1 total child chunks: {total_children_1}")
    print(f"  Batch 2 total child chunks: {total_children_2}")
    assert total_children_1 > 0, "Batch 1 should have child chunks"
    assert total_children_2 > 0, "Batch 2 should have child chunks"

    # -- Summary --
    print(f"\n{'='*60}")
    print("MULTI-BATCH (600-PAGE) SUMMARY")
    print(f"  Batch 1: range={page_range_1}, groups={len(chunks_1)}, children={total_children_1}")
    print(f"  Batch 2: range={page_range_2}, groups={len(chunks_2)}, children={total_children_2}")
    print(f"  Batch API calls: {call_count}")
    print(f"  Storage uploads: {mock_storage_inst.upload_bytes.call_count}")
    print(f"  Storage deletes: {mock_storage_inst.delete_blob.call_count}")
    print(f"{'='*60}")

    # Cleanup
    pdf_path.unlink(missing_ok=True)
