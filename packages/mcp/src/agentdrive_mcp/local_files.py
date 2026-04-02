"""Shared module for local file management — manifest, path resolution, caching, native open."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterator

AGENTDRIVE_FILES_DIR = Path.home() / ".agentdrive" / "files"
MANIFEST_FILENAME = ".manifest.json"


# ---------------------------------------------------------------------------
# Manifest operations
# ---------------------------------------------------------------------------


def _empty_manifest() -> dict:
    return {"version": 1, "files": {}}


def read_manifest(files_dir: Path = AGENTDRIVE_FILES_DIR) -> dict:
    """Load manifest from disk. Returns empty manifest if missing or corrupt."""
    manifest_path = files_dir / MANIFEST_FILENAME
    try:
        return json.loads(manifest_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return _empty_manifest()


def write_manifest(data: dict, files_dir: Path = AGENTDRIVE_FILES_DIR) -> None:
    """Atomically write manifest to disk (temp file + rename)."""
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = files_dir / MANIFEST_FILENAME

    fd, tmp_path = tempfile.mkstemp(dir=files_dir, prefix=".manifest_", suffix=".tmp")
    os.close(fd)  # close immediately; write_text opens by path
    try:
        Path(tmp_path).write_text(json.dumps(data, indent=2))
        Path(tmp_path).replace(manifest_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def resolve_local_path(
    filename: str,
    collection: str | None,
    file_id: str,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> Path:
    """Build local path. Appends file_id[:8] prefix on name collision."""
    collection_name = collection or "default"
    target = files_dir / collection_name / filename
    if target.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        short_id = file_id[:8]
        target = files_dir / collection_name / f"{stem}_{short_id}{suffix}"
    return target


# ---------------------------------------------------------------------------
# Cache checking
# ---------------------------------------------------------------------------


def is_cached(file_id: str, files_dir: Path = AGENTDRIVE_FILES_DIR) -> bool:
    """True if file is in manifest AND exists on disk."""
    manifest = read_manifest(files_dir)
    entry = manifest.get("files", {}).get(file_id)
    if not entry:
        return False
    local_path = files_dir / entry["local_path"]
    return local_path.exists()


def is_stale(
    file_id: str,
    remote_updated_at: str,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> bool:
    """True if remote file is newer than cached version. Parses ISO timestamps."""
    manifest = read_manifest(files_dir)
    entry = manifest.get("files", {}).get(file_id)
    if not entry:
        return True
    cached = entry.get("remote_updated_at", "")
    try:
        return datetime.fromisoformat(remote_updated_at) > datetime.fromisoformat(cached)
    except (ValueError, TypeError):
        return True  # can't parse, assume stale


# ---------------------------------------------------------------------------
# File saving
# ---------------------------------------------------------------------------


def save_file(
    file_id: str,
    byte_stream: Iterator[bytes],
    metadata: dict,
    files_dir: Path = AGENTDRIVE_FILES_DIR,
) -> dict:
    """Write streamed bytes to local path and update manifest. Returns result dict."""
    filename = metadata["filename"]
    collection = metadata.get("collection")
    file_size = metadata.get("file_size", 0)
    content_type = metadata.get("content_type", "")
    remote_updated_at = metadata.get("remote_updated_at", "")

    # Check manifest first for existing path (re-download case)
    manifest = read_manifest(files_dir)
    existing = manifest.get("files", {}).get(file_id)
    if existing:
        local_path = files_dir / existing["local_path"]
    else:
        local_path = resolve_local_path(filename, collection, file_id, files_dir)

    # Ensure parent directory exists
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file + rename
    fd, tmp_path_str = tempfile.mkstemp(dir=local_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in byte_stream:
                f.write(chunk)
        Path(tmp_path_str).replace(local_path)
    except Exception:
        Path(tmp_path_str).unlink(missing_ok=True)
        raise

    # Relative path for manifest (relative to files_dir)
    relative_path = str(local_path.relative_to(files_dir))

    # Update manifest
    manifest["files"][file_id] = {
        "local_path": relative_path,
        "filename": filename,
        "remote_updated_at": remote_updated_at,
        "content_type": content_type,
        "file_size": file_size,
    }
    write_manifest(manifest, files_dir)

    return {
        "local_path": str(local_path),
        "filename": filename,
        "collection": collection or "default",
        "file_size": file_size,
        "already_cached": False,
    }


# ---------------------------------------------------------------------------
# Native open
# ---------------------------------------------------------------------------


def open_native(local_path: Path) -> None:
    """Open file in native OS app. Non-blocking via subprocess.Popen."""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(local_path)])
    else:
        subprocess.Popen(["xdg-open", str(local_path)])
