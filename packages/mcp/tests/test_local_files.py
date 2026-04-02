"""Tests for local_files module — manifest, path resolution, caching, save, native open."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentdrive_mcp.local_files import (
    is_cached,
    is_stale,
    open_native,
    read_manifest,
    resolve_local_path,
    save_file,
    write_manifest,
)


# ---------------------------------------------------------------------------
# TestManifest
# ---------------------------------------------------------------------------


class TestManifest:
    def test_read_manifest_returns_empty_when_missing(self, tmp_path: Path) -> None:
        result = read_manifest(tmp_path)
        assert result == {"version": 1, "files": {}}

    def test_read_manifest_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / ".manifest.json"
        manifest_path.write_text("NOT VALID JSON {{{")
        result = read_manifest(tmp_path)
        assert result == {"version": 1, "files": {}}

    def test_write_then_read_manifest(self, tmp_path: Path) -> None:
        data = {"version": 1, "files": {"abc": {"local_path": "default/test.txt"}}}
        write_manifest(data, tmp_path)
        result = read_manifest(tmp_path)
        assert result == data


# ---------------------------------------------------------------------------
# TestPathResolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_resolve_path_with_collection(self, tmp_path: Path) -> None:
        path = resolve_local_path("report.pdf", "finance", "abcd1234", tmp_path)
        assert path == tmp_path / "finance" / "report.pdf"

    def test_resolve_path_default_collection(self, tmp_path: Path) -> None:
        path = resolve_local_path("report.pdf", None, "abcd1234", tmp_path)
        assert path == tmp_path / "default" / "report.pdf"

    def test_resolve_path_handles_collision(self, tmp_path: Path) -> None:
        # Create existing file so collision triggers
        collection_dir = tmp_path / "finance"
        collection_dir.mkdir(parents=True)
        (collection_dir / "report.pdf").write_text("existing")

        path = resolve_local_path("report.pdf", "finance", "abcd1234efgh", tmp_path)
        assert path == tmp_path / "finance" / "report_abcd1234.pdf"


# ---------------------------------------------------------------------------
# TestCaching
# ---------------------------------------------------------------------------


class TestCaching:
    def test_is_cached_false_when_not_in_manifest(self, tmp_path: Path) -> None:
        assert is_cached("nonexistent-id", tmp_path) is False

    def test_is_cached_false_when_file_deleted_from_disk(self, tmp_path: Path) -> None:
        # Put entry in manifest but don't create the file on disk
        manifest = {
            "version": 1,
            "files": {
                "file-123": {"local_path": "default/gone.txt"},
            },
        }
        write_manifest(manifest, tmp_path)
        assert is_cached("file-123", tmp_path) is False

    def test_is_stale_when_remote_is_newer(self, tmp_path: Path) -> None:
        manifest = {
            "version": 1,
            "files": {
                "file-123": {
                    "local_path": "default/test.txt",
                    "remote_updated_at": "2025-01-01T00:00:00Z",
                },
            },
        }
        write_manifest(manifest, tmp_path)

        # Remote is newer → stale
        assert is_stale("file-123", "2025-06-01T00:00:00Z", tmp_path) is True

        # Remote is same → not stale
        assert is_stale("file-123", "2025-01-01T00:00:00Z", tmp_path) is False

        # Remote is older → not stale
        assert is_stale("file-123", "2024-06-01T00:00:00Z", tmp_path) is False


# ---------------------------------------------------------------------------
# TestSaveFile
# ---------------------------------------------------------------------------


class TestSaveFile:
    def test_save_file_writes_bytes_and_updates_manifest(self, tmp_path: Path) -> None:
        content = b"hello world"
        byte_stream = iter([content])
        metadata = {
            "filename": "notes.txt",
            "collection": "work",
            "file_size": 11,
            "content_type": "text/plain",
            "remote_updated_at": "2025-03-28T12:00:00Z",
        }

        result = save_file("file-abc", byte_stream, metadata, tmp_path)

        # File written to disk
        local_path = Path(result["local_path"])
        assert local_path.exists()
        assert local_path.read_bytes() == content

        # Manifest updated
        manifest = read_manifest(tmp_path)
        assert "file-abc" in manifest["files"]

        # Result dict has expected keys
        assert result["local_path"] == str(local_path)
        assert result["filename"] == "notes.txt"
        assert result["collection"] == "work"
        assert result["file_size"] == 11
        assert result["already_cached"] is False

    def test_save_file_redownload_reuses_path(self, tmp_path: Path) -> None:
        # First download
        result1 = save_file("file-redownload", iter([b"old content"]), {
            "filename": "reuse.txt", "collection": "docs",
            "file_size": 11, "content_type": "text/plain",
            "remote_updated_at": "2026-04-01T08:00:00Z",
        }, tmp_path)

        # Re-download same file_id with new content
        result2 = save_file("file-redownload", iter([b"new content"]), {
            "filename": "reuse.txt", "collection": "docs",
            "file_size": 11, "content_type": "text/plain",
            "remote_updated_at": "2026-04-02T12:00:00Z",
        }, tmp_path)

        # Same path, not collision-suffixed
        assert result1["local_path"] == result2["local_path"]
        # Content overwritten
        assert Path(result2["local_path"]).read_bytes() == b"new content"
        # Manifest updated
        manifest = read_manifest(tmp_path)
        assert manifest["files"]["file-redownload"]["remote_updated_at"] == "2026-04-02T12:00:00Z"


# ---------------------------------------------------------------------------
# TestOpenNative
# ---------------------------------------------------------------------------


class TestOpenNative:
    @patch("agentdrive_mcp.local_files.subprocess.Popen")
    @patch("agentdrive_mcp.local_files.platform.system", return_value="Darwin")
    def test_open_native_macos(self, mock_system, mock_popen) -> None:
        open_native(Path("/tmp/test.pdf"))
        mock_popen.assert_called_once_with(["open", "/tmp/test.pdf"])

    @patch("agentdrive_mcp.local_files.subprocess.Popen")
    @patch("agentdrive_mcp.local_files.platform.system", return_value="Linux")
    def test_open_native_linux(self, mock_system, mock_popen) -> None:
        open_native(Path("/tmp/test.pdf"))
        mock_popen.assert_called_once_with(["xdg-open", "/tmp/test.pdf"])
