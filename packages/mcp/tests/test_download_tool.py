"""Integration-style tests for the download_file tool handler workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agentdrive_mcp.local_files import (
    is_cached,
    is_stale,
    open_native,
    read_manifest,
    save_file,
)


@pytest.fixture()
def files_dir(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# TestDownloadToolFreshDownload
# ---------------------------------------------------------------------------


class TestDownloadToolFreshDownload:
    def test_save_file_creates_file_and_manifest(self, files_dir: Path) -> None:
        content = b"fresh file content"
        result = save_file(
            "file-fresh",
            iter([content]),
            {
                "filename": "fresh.txt",
                "file_size": len(content),
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-02T10:00:00Z",
            },
            files_dir,
        )
        assert result["already_cached"] is False
        assert Path(result["local_path"]).read_bytes() == content
        manifest = read_manifest(files_dir)
        assert "file-fresh" in manifest["files"]


# ---------------------------------------------------------------------------
# TestDownloadToolCachedHit
# ---------------------------------------------------------------------------


class TestDownloadToolCachedHit:
    def test_cached_fresh_file_returns_already_cached(self, files_dir: Path) -> None:
        # First download
        save_file(
            "file-cached",
            iter([b"content"]),
            {
                "filename": "cached.txt",
                "file_size": 7,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-01T08:00:00Z",
            },
            files_dir,
        )
        assert is_cached("file-cached", files_dir) is True
        assert is_stale("file-cached", "2026-04-01T08:00:00Z", files_dir) is False


# ---------------------------------------------------------------------------
# TestDownloadToolStaleRedownload
# ---------------------------------------------------------------------------


class TestDownloadToolStaleRedownload:
    def test_stale_redownload_overwrites_existing_file(self, files_dir: Path) -> None:
        # Initial download
        save_file(
            "file-stale",
            iter([b"old content"]),
            {
                "filename": "stale.txt",
                "file_size": 11,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-01T08:00:00Z",
            },
            files_dir,
        )
        assert is_stale("file-stale", "2026-04-02T12:00:00Z", files_dir) is True

        # Re-download
        result = save_file(
            "file-stale",
            iter([b"new content"]),
            {
                "filename": "stale.txt",
                "file_size": 11,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-02T12:00:00Z",
            },
            files_dir,
        )
        assert "file-sta_stale.txt" in result["local_path"]
        assert Path(result["local_path"]).read_bytes() == b"new content"
        manifest = read_manifest(files_dir)
        assert manifest["files"]["file-stale"]["remote_updated_at"] == "2026-04-02T12:00:00Z"


# ---------------------------------------------------------------------------
# TestDownloadToolOpenFlag
# ---------------------------------------------------------------------------


class TestDownloadToolOpenFlag:
    @patch("agentdrive_mcp.local_files.subprocess.Popen")
    @patch("agentdrive_mcp.local_files.platform.system", return_value="Darwin")
    def test_open_flag_calls_native_open(
        self, mock_system, mock_popen, files_dir: Path
    ) -> None:
        result = save_file(
            "file-open",
            iter([b"open me"]),
            {
                "filename": "open.txt",
                "file_size": 7,
                "content_type": "text/plain",
                "remote_updated_at": "2026-04-02T10:00:00Z",
            },
            files_dir,
        )
        open_native(Path(result["local_path"]))
        mock_popen.assert_called_once()
        assert "open" in mock_popen.call_args[0][0]
