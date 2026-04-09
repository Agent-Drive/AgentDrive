import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from mcp.server import InitializationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import ServerCapabilities, TextContent, Tool

AGENT_DRIVE_URL = os.environ.get("AGENT_DRIVE_URL", "https://api.agentdrive.so")


def _resolve_api_key() -> str:
    """Resolve API key: env var > credentials file."""
    key = os.environ.get("AGENT_DRIVE_API_KEY", "")
    if key:
        return key
    creds_file = Path.home() / ".agentdrive" / "credentials"
    if creds_file.exists():
        creds = json.loads(creds_file.read_text())
        return creds.get("api_key", "")
    return ""


AGENT_DRIVE_API_KEY = _resolve_api_key()

if not AGENT_DRIVE_API_KEY:
    print(
        "WARNING: No Agent Drive API key found. "
        "Set AGENT_DRIVE_API_KEY or run 'agentdrive-mcp login'.",
        file=sys.stderr,
    )

server = Server("agent-drive")


def _headers() -> dict:
    return {"Authorization": f"Bearer {AGENT_DRIVE_API_KEY}"}


# Cache for tool definitions fetched from API
_cached_tools: list[Tool] | None = None
_cached_tool_metadata: list[dict] | None = None


async def _fetch_tools_from_api() -> list[dict]:
    """Fetch tool definitions from the API endpoint.
    
    This enables dynamic tool discovery - new tools added to the API
    will be automatically available in the MCP server without updating
    the package.
    """
    global _cached_tool_metadata
    if _cached_tool_metadata is not None:
        return _cached_tool_metadata
    
    async with httpx.AsyncClient(base_url=AGENT_DRIVE_URL, timeout=30) as client:
        try:
            resp = await client.get("/v1/mcp/tools/full")
            resp.raise_for_status()
            data = resp.json()
            _cached_tool_metadata = data.get("tools", [])
            return _cached_tool_metadata
        except Exception as e:
            print(f"WARNING: Failed to fetch tools from API: {e}", file=sys.stderr)
            print("Falling back to hardcoded tools (if available)", file=sys.stderr)
            return []


async def _resolve_kb_id(client: httpx.AsyncClient, kb_name_or_id: str) -> str | None:
    """Resolve KB name to ID. Returns ID string or None."""
    try:
        uuid.UUID(kb_name_or_id)
        return kb_name_or_id  # Already a UUID
    except ValueError:
        pass
    resp = await client.get("/v1/knowledge-bases")
    if resp.status_code != 200:
        return None
    for kb in resp.json().get("knowledge_bases", []):
        if kb["name"] == kb_name_or_id:
            return kb["id"]
    return None


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return tool list fetched dynamically from API.
    
    This enables automatic discovery of new tools without package updates.
    """
    global _cached_tools
    
    if _cached_tools is not None:
        return _cached_tools
    
    tool_metadata = await _fetch_tools_from_api()
    
    if not tool_metadata:
        # Fallback: return empty list or hardcoded tools if API is unavailable
        # In production, you might want to cache the last known good tool list
        return []
    
    # Convert API tool definitions to MCP Tool objects
    tools = []
    for tool_def in tool_metadata:
        tool = Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            inputSchema=tool_def["inputSchema"],
        )
        tools.append(tool)
    
    _cached_tools = tools
    return tools


async def _dispatch_tool_call(
    client: httpx.AsyncClient,
    tool_name: str,
    arguments: dict,
) -> str:
    """Dispatch a tool call to the appropriate API endpoint.
    
    Uses the routing metadata from the tool definition to determine
    the HTTP method, path, and parameter mapping.
    """
    tool_metadata = await _fetch_tools_from_api()
    tool_def = None
    for t in tool_metadata:
        if t["name"] == tool_name:
            tool_def = t
            break
    
    if not tool_def:
        return f"Unknown tool: {tool_name}"
    
    http_config = tool_def.get("_http", {})
    method = http_config.get("method", "GET")
    path = http_config.get("path", "")
    path_template = http_config.get("path_template", "")
    requires_resolution = http_config.get("requires_resolution", False)
    
    # Build request
    if path_template:
        # Handle path templates like /v1/knowledge-bases/{kb_id}
        path = path_template
        if requires_resolution and "kb" in arguments:
            # Resolve KB name to ID
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return f"Knowledge base '{arguments['kb']}' not found"
            path = path.replace("{kb_id}", kb_id)
        # Replace other path parameters
        for key, value in arguments.items():
            path = path.replace(f"{{{key}}}", str(value))
    
    # Make the request
    try:
        if method == "GET":
            resp = await client.get(path)
        elif method == "POST":
            # Build request body from arguments
            body_fields = http_config.get("body_fields", list(arguments.keys()))
            body = {k: v for k, v in arguments.items() if k in body_fields}
            resp = await client.post(path, json=body)
        elif method == "DELETE":
            resp = await client.delete(path)
        elif method == "PUT":
            body = {k: v for k, v in arguments.items()}
            resp = await client.put(path, json=body)
        else:
            return f"Unsupported HTTP method: {method}"
        
        if resp.status_code == 204:
            return "Operation completed successfully."
        
        return json.dumps(resp.json(), indent=2)
    
    except Exception as e:
        return f"Error calling {tool_name}: {e}"


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Call a tool by dispatching to the API.
    
    This is a generic implementation that routes tool calls to the
    appropriate API endpoints based on the tool's routing metadata.
    """
    async with httpx.AsyncClient(base_url=AGENT_DRIVE_URL, headers=_headers(), timeout=60) as client:
        # Special handling for tools that need client-side logic
        if name == "upload_file":
            # File upload requires special handling (multipart form data)
            file_path = Path(arguments["path"])
            if not file_path.exists():
                return [TextContent(type="text", text=f"Error: File not found: {file_path}")]
            
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "application/octet-stream")}
                response = await client.post("/v1/files", files=files)
            
            result = response.json()
            # If kb specified, add file to knowledge base after upload
            if arguments.get("kb") and response.status_code in (200, 201):
                kb_id = await _resolve_kb_id(client, arguments["kb"])
                if kb_id:
                    file_id = result.get("id") or result.get("file_id")
                    if file_id:
                        await client.post(f"/v1/knowledge-bases/{kb_id}/files", json={"file_ids": [file_id]})
                        result["added_to_kb"] = kb_id
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "download_file":
            # Download requires special handling (streaming + local caching)
            from agentdrive_mcp.local_files import (
                is_cached,
                is_stale,
                read_manifest,
                save_file,
                open_native,
                AGENTDRIVE_FILES_DIR,
            )

            file_id = arguments["file_id"]
            should_open = arguments.get("open", False)

            # Check cache
            if is_cached(file_id):
                meta_resp = await client.get(f"/v1/files/{file_id}")
                meta = meta_resp.json()
                remote_updated = meta.get("updated_at", "")
                if not is_stale(file_id, remote_updated):
                    manifest = read_manifest()
                    entry = manifest["files"][file_id]
                    local_path = AGENTDRIVE_FILES_DIR / entry["local_path"]
                    if should_open:
                        open_native(local_path)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps({
                                "local_path": str(local_path),
                                "filename": entry["filename"],
                                "file_size": entry["file_size"],
                                "already_cached": True,
                            }),
                        )
                    ]

            # Fetch metadata
            meta_resp = await client.get(f"/v1/files/{file_id}")
            if meta_resp.status_code != 200:
                return [TextContent(type="text", text=meta_resp.text)]
            meta = meta_resp.json()

            # Stream download
            async with client.stream("GET", f"/v1/files/{file_id}/download") as dl_resp:
                if dl_resp.status_code != 200:
                    text = await dl_resp.aread()
                    return [TextContent(type="text", text=text.decode())]
                chunks = []
                async for chunk in dl_resp.aiter_bytes():
                    chunks.append(chunk)

            # Save locally
            result = save_file(
                file_id,
                iter(chunks),
                {
                    "filename": meta["filename"],
                    "file_size": meta["file_size"],
                    "content_type": meta["content_type"],
                    "remote_updated_at": meta.get("updated_at", ""),
                },
            )

            if should_open:
                open_native(Path(result["local_path"]))

            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "search":
            # Search needs special handling for KB resolution
            body = {"query": arguments["query"], "top_k": arguments.get("top_k", 5)}
            if arguments.get("kb"):
                kb_id = await _resolve_kb_id(client, arguments["kb"])
                if not kb_id:
                    return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
                if "articles_only" in arguments:
                    body["articles_only"] = arguments["articles_only"]
                response = await client.post(f"/v1/knowledge-bases/{kb_id}/search", json=body)
            else:
                response = await client.post("/v1/search", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "get_knowledge_base":
            # KB lookup needs name resolution
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            response = await client.get(f"/v1/knowledge-bases/{kb_id}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "delete_knowledge_base":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            response = await client.delete(f"/v1/knowledge-bases/{kb_id}")
            if response.status_code == 204:
                return [TextContent(type="text", text="Knowledge base deleted successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "add_files_to_kb":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/files", json={"file_ids": arguments["file_ids"]})
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "remove_files_from_kb":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/files/remove", json={"file_ids": arguments["file_ids"]})
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "search_kb":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            body = {"query": arguments["query"], "top_k": arguments.get("top_k", 5),
                    "articles_only": arguments.get("articles_only", False)}
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/search", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "get_article":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            response = await client.get(f"/v1/knowledge-bases/{kb_id}/articles/{arguments['article_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "list_articles":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            params = {}
            if "category" in arguments:
                params["category"] = arguments["category"]
            if "article_type" in arguments:
                params["article_type"] = arguments["article_type"]
            params["limit"] = arguments.get("limit", 50)
            params["offset"] = arguments.get("offset", 0)
            response = await client.get(f"/v1/knowledge-bases/{kb_id}/articles", params=params)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "compile_kb":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            params = {}
            if arguments.get("force"):
                params["force"] = "true"
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/compile", params=params)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "health_check":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            params = {}
            if arguments.get("quick"):
                params["quick"] = "true"
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/health-check", params=params)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "repair_kb":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/repair", json={"apply": arguments["apply"]})
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        elif name == "derive_article":
            kb_id = await _resolve_kb_id(client, arguments["kb"])
            if not kb_id:
                return [TextContent(type="text", text=f"Knowledge base '{arguments['kb']}' not found")]
            body = {"title": arguments["title"], "content": arguments["content"]}
            if "source_ids" in arguments:
                body["source_ids"] = arguments["source_ids"]
            response = await client.post(f"/v1/knowledge-bases/{kb_id}/articles/derived", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        
        else:
            # Generic dispatch for all other tools
            result = await _dispatch_tool_call(client, name, arguments)
            return [TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="agent-drive",
            server_version="0.1.1",
            capabilities=ServerCapabilities(tools={"listChanged": False}),
        )
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
