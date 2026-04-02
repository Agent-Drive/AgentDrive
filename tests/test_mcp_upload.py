import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from agentdrive.mcp.server import call_tool

@pytest.mark.asyncio
async def test_mcp_small_file_direct_upload(tmp_path):
    small = tmp_path / "small.txt"
    small.write_text("hello" * 100)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "abc", "status": "pending"}
    with patch("agentdrive.mcp.server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        await call_tool("upload_file", {"path": str(small)})
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args[0][0] == "/v1/files"

@pytest.mark.asyncio
async def test_mcp_large_file_signed_url(tmp_path):
    large = tmp_path / "large.pdf"
    large.write_bytes(b"\x00" * (33 * 1024 * 1024))
    mock_url_resp = MagicMock()
    mock_url_resp.json.return_value = {"file_id": "abc-123", "upload_url": "https://storage.googleapis.com/signed", "expires_at": "2026-03-28T12:00:00Z"}
    mock_url_resp.status_code = 200
    mock_put_resp = MagicMock()
    mock_put_resp.status_code = 200
    mock_complete_resp = MagicMock()
    mock_complete_resp.json.return_value = {"id": "abc-123", "status": "pending"}
    with patch("agentdrive.mcp.server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_client
        mock_client.post.side_effect = [mock_url_resp, mock_complete_resp]
        mock_client.put.return_value = mock_put_resp
        await call_tool("upload_file", {"path": str(large)})
        assert mock_client.post.call_count == 2
        assert mock_client.put.call_count == 1
