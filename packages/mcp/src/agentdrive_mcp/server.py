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
    return [
        Tool(name="upload_file", description="Upload a file to Agent Drive for processing and semantic indexing.",
             inputSchema={"type": "object", "properties": {
                 "path": {"type": "string", "description": "Absolute path to the file on disk"},
                 "kb": {"type": "string", "description": "Optional knowledge base name or ID to add the file to after upload"},
             }, "required": ["path"]}),
        Tool(name="search", description="Search across all uploaded files using natural language. Optionally scope to a knowledge base.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Natural language search query"},
                 "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
                 "kb": {"type": "string", "description": "Optional knowledge base name or ID to search within"},
             }, "required": ["query"]}),
        Tool(name="get_file_status", description="Check the processing status of an uploaded file.",
             inputSchema={"type": "object", "properties": {
                 "file_id": {"type": "string", "description": "File ID returned from upload"},
             }, "required": ["file_id"]}),
        Tool(name="list_files", description="List all files uploaded to Agent Drive.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="delete_file", description="Delete a file and all its chunks from Agent Drive.",
             inputSchema={"type": "object", "properties": {
                 "file_id": {"type": "string", "description": "File ID to delete"},
             }, "required": ["file_id"]}),
        Tool(name="get_chunk", description="Get a specific chunk by ID with full content and provenance.",
             inputSchema={"type": "object", "properties": {
                 "chunk_id": {"type": "string", "description": "Chunk ID"},
             }, "required": ["chunk_id"]}),
        Tool(
            name="download_file",
            description="Download a file from Agent Drive to local disk. Optionally open it in the native OS application.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "UUID of the file to download",
                    },
                    "open": {
                        "type": "boolean",
                        "description": "Open the file in the native app after download (default: false)",
                        "default": False,
                    },
                },
                "required": ["file_id"],
            },
        ),
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
        # Knowledge base tools
        Tool(name="create_knowledge_base", description="Create a new knowledge base to organize files and generate synthesized knowledge articles.",
             inputSchema={"type": "object", "properties": {
                 "name": {"type": "string", "description": "Name for the knowledge base"},
                 "description": {"type": "string", "description": "Optional description"},
             }, "required": ["name"]}),
        Tool(name="list_knowledge_bases", description="List all knowledge bases.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_knowledge_base", description="Get details of a knowledge base by name or ID.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
             }, "required": ["kb"]}),
        Tool(name="delete_knowledge_base", description="Delete a knowledge base. Articles are deleted but files are kept.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
             }, "required": ["kb"]}),
        Tool(name="add_files_to_kb", description="Add files to a knowledge base. Triggers compilation.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "file_ids": {"type": "array", "items": {"type": "string"}, "description": "List of file IDs to add"},
             }, "required": ["kb", "file_ids"]}),
        Tool(name="remove_files_from_kb", description="Remove files from a knowledge base. Affected articles are marked stale.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "file_ids": {"type": "array", "items": {"type": "string"}, "description": "List of file IDs to remove"},
             }, "required": ["kb", "file_ids"]}),
        Tool(name="search_kb", description="Search within a knowledge base. Returns both chunks and synthesized articles.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "query": {"type": "string", "description": "Search query"},
                 "top_k": {"type": "integer", "description": "Number of results", "default": 5},
                 "articles_only": {"type": "boolean", "description": "Only return articles", "default": False},
             }, "required": ["kb", "query"]}),
        Tool(name="get_article", description="Get a specific article from a knowledge base.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "article_id": {"type": "string", "description": "Article ID"},
             }, "required": ["kb", "article_id"]}),
        Tool(name="list_articles", description="List articles in a knowledge base with optional filters.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "category": {"type": "string"},
                 "article_type": {"type": "string"},
                 "limit": {"type": "integer", "default": 50},
                 "offset": {"type": "integer", "default": 0},
             }, "required": ["kb"]}),
        Tool(name="compile_kb", description="Trigger compilation of a knowledge base to generate/update articles.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "force": {"type": "boolean", "description": "Force full recompilation", "default": False},
             }, "required": ["kb"]}),
        Tool(name="health_check", description="Run health analysis on a knowledge base.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "quick": {"type": "boolean", "description": "Quick mode (cheap checks only)", "default": False},
             }, "required": ["kb"]}),
        Tool(name="repair_kb", description="Execute repair actions on a knowledge base.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "apply": {"type": "array", "items": {"type": "string"}, "description": "Actions to apply (e.g. 'stale', 'gaps')"},
             }, "required": ["kb", "apply"]}),
        Tool(name="derive_article", description="File a Q&A output back into a knowledge base as a derived article.",
             inputSchema={"type": "object", "properties": {
                 "kb": {"type": "string", "description": "Knowledge base name or ID"},
                 "title": {"type": "string"},
                 "content": {"type": "string", "description": "Article content in markdown"},
                 "source_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional chunk/article IDs that informed this"},
             }, "required": ["kb", "title", "content"]}),
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
        elif name == "search":
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
        elif name == "get_file_status":
            response = await client.get(f"/v1/files/{arguments['file_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "list_files":
            response = await client.get("/v1/files")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "delete_file":
            response = await client.delete(f"/v1/files/{arguments['file_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="File deleted successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "get_chunk":
            response = await client.get(f"/v1/chunks/{arguments['chunk_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "download_file":
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

            # Stream download (collects into memory — acceptable for typical file sizes)
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
        # Knowledge base tools
        elif name == "create_knowledge_base":
            body: dict = {"name": arguments["name"]}
            if "description" in arguments:
                body["description"] = arguments["description"]
            response = await client.post("/v1/knowledge-bases", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "list_knowledge_bases":
            response = await client.get("/v1/knowledge-bases")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "get_knowledge_base":
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
            params: dict = {}
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
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


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
