import pytest
from mcp.types import ListToolsRequest
from agentdrive.mcp.server import server


async def _list_tools():
    """Invoke the registered list_tools handler and return the tool list."""
    from mcp.types import ListToolsRequest
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    return result.root.tools


@pytest.mark.asyncio
async def test_list_tools():
    tools = await _list_tools()
    tool_names = [t.name for t in tools]
    assert "upload_file" in tool_names
    assert "search" in tool_names
    assert "get_file_status" in tool_names
    assert "list_files" in tool_names
    assert "delete_file" in tool_names
    assert "download_file" in tool_names
    assert "get_chunk" not in tool_names
    assert "create_api_key" not in tool_names
    assert "list_api_keys" not in tool_names
    assert "revoke_api_key" not in tool_names
    assert "create_knowledge_base" not in tool_names
    assert "search_kb" not in tool_names
    assert len(tool_names) == 6


@pytest.mark.asyncio
async def test_upload_tool_has_path_param():
    tools = await _list_tools()
    upload = next(t for t in tools if t.name == "upload_file")
    assert "path" in upload.inputSchema["properties"]
    assert "path" in upload.inputSchema["required"]
    assert "kb" not in upload.inputSchema["properties"]


@pytest.mark.asyncio
async def test_search_tool_has_query_param():
    tools = await _list_tools()
    search = next(t for t in tools if t.name == "search")
    assert "query" in search.inputSchema["properties"]
    assert "query" in search.inputSchema["required"]
    assert "kb" not in search.inputSchema["properties"]
