import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import select, text as sa_text
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.queue import reap_stuck_files

@pytest.mark.asyncio
async def test_reaper_cleans_stale_uploading(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    stale = File(tenant_id=tenant.id, filename="stale.pdf", content_type="pdf",
                 gcs_path="tenants/x/files/stale/stale.pdf", file_size=0, status=FileStatus.UPLOADING)
    db_session.add(stale)
    await db_session.commit()
    await db_session.execute(sa_text("UPDATE files SET created_at = :ts WHERE id = :fid"),
                              {"ts": datetime.now(timezone.utc) - timedelta(hours=25), "fid": stale.id})
    await db_session.commit()

    with patch("agentdrive.services.queue.StorageService") as MockStorage:
        instance = MockStorage.return_value
        instance.blob_exists.return_value = True
        instance.delete = MagicMock()
        await reap_stuck_files(db_session)
        instance.delete.assert_called_once_with("tenants/x/files/stale/stale.pdf")

    result = await db_session.execute(select(File).where(File.id == stale.id))
    assert result.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_reaper_keeps_fresh_uploading(db_session):
    tenant = Tenant(name="test")
    db_session.add(tenant)
    await db_session.flush()
    fresh = File(tenant_id=tenant.id, filename="fresh.pdf", content_type="pdf",
                 gcs_path="tenants/x/files/fresh/fresh.pdf", file_size=0, status=FileStatus.UPLOADING)
    db_session.add(fresh)
    await db_session.commit()
    await reap_stuck_files(db_session)
    result = await db_session.execute(select(File).where(File.id == fresh.id))
    assert result.scalar_one_or_none() is not None
