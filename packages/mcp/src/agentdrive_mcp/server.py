import json
import os
import sys
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

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


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="upload_file", description="Upload a file to Agent Drive for processing and semantic indexing.",
             inputSchema={"type": "object", "properties": {
                 "path": {"type": "string", "description": "Absolute path to the file on disk"},
                 "collection": {"type": "string", "description": "Collection name (optional)"},
             }, "required": ["path"]}),
        Tool(name="search", description="Search across all uploaded files using natural language.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Natural language search query"},
                 "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
                 "collection": {"type": "string", "description": "Limit search to this collection (optional)"},
             }, "required": ["query"]}),
        Tool(name="get_file_status", description="Check the processing status of an uploaded file.",
             inputSchema={"type": "object", "properties": {
                 "file_id": {"type": "string", "description": "File ID returned from upload"},
             }, "required": ["file_id"]}),
        Tool(name="list_files", description="List all files uploaded to Agent Drive.",
             inputSchema={"type": "object", "properties": {
                 "collection": {"type": "string", "description": "Filter by collection (optional)"},
             }}),
        Tool(name="create_collection", description="Create a named collection to organize files.",
             inputSchema={"type": "object", "properties": {
                 "name": {"type": "string", "description": "Collection name"},
                 "description": {"type": "string", "description": "Collection description (optional)"},
             }, "required": ["name"]}),
        Tool(name="list_collections", description="List all collections.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="delete_file", description="Delete a file and all its chunks from Agent Drive.",
             inputSchema={"type": "object", "properties": {
                 "file_id": {"type": "string", "description": "File ID to delete"},
             }, "required": ["file_id"]}),
        Tool(name="delete_collection", description="Delete a collection.",
             inputSchema={"type": "object", "properties": {
                 "collection_id": {"type": "string", "description": "Collection ID to delete"},
             }, "required": ["collection_id"]}),
        Tool(name="get_chunk", description="Get a specific chunk by ID with full content and provenance.",
             inputSchema={"type": "object", "properties": {
                 "chunk_id": {"type": "string", "description": "Chunk ID"},
             }, "required": ["chunk_id"]}),
        Tool(name="create_api_key", description="Create a new API key for your tenant.",
             inputSchema={"type": "object", "properties": {
                 "name": {"type": "string", "description": "Name for the key (e.g. 'production', 'ci')"},
             }}),
        Tool(name="list_api_keys", description="List all API keys for your tenant.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="revoke_api_key", description="Revoke an API key by ID.",
             inputSchema={"type": "object", "properties": {
                 "key_id": {"type": "string", "description": "UUID of the key to revoke"},
             }, "required": ["key_id"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with httpx.AsyncClient(base_url=AGENT_DRIVE_URL, headers=_headers(), timeout=60) as client:
        if name == "upload_file":
            file_path = Path(arguments["path"])
            if not file_path.exists():
                return [TextContent(type="text", text=f"Error: File not found: {file_path}")]
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "application/octet-stream")}
                data = {}
                if "collection" in arguments:
                    data["collection"] = arguments["collection"]
                response = await client.post("/v1/files", files=files, data=data)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "search":
            body = {"query": arguments["query"], "top_k": arguments.get("top_k", 5)}
            if "collection" in arguments:
                body["collections"] = [arguments["collection"]]
            response = await client.post("/v1/search", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "get_file_status":
            response = await client.get(f"/v1/files/{arguments['file_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "list_files":
            params = {}
            if "collection" in arguments:
                params["collection"] = arguments["collection"]
            response = await client.get("/v1/files", params=params)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "create_collection":
            body = {"name": arguments["name"]}
            if "description" in arguments:
                body["description"] = arguments["description"]
            response = await client.post("/v1/collections", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "list_collections":
            response = await client.get("/v1/collections")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "delete_file":
            response = await client.delete(f"/v1/files/{arguments['file_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="File deleted successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "delete_collection":
            response = await client.delete(f"/v1/collections/{arguments['collection_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="Collection deleted successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "get_chunk":
            response = await client.get(f"/v1/chunks/{arguments['chunk_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "create_api_key":
            body = {}
            if "name" in arguments:
                body["name"] = arguments["name"]
            response = await client.post("/v1/api-keys", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "list_api_keys":
            response = await client.get("/v1/api-keys")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "revoke_api_key":
            response = await client.delete(f"/v1/api-keys/{arguments['key_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="API key revoked successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
