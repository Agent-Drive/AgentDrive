"""MCP tool discovery endpoint.

This router provides dynamic tool discovery for the MCP server.
Instead of hardcoding Tool definitions in the MCP server, it fetches
the tool list from this API endpoint at startup.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["mcp"])

# Tool definitions - single source of truth for MCP tools
# When adding new tools, register them here and the MCP server will auto-discover them
MCP_TOOLS = [
    {
        "name": "upload_file",
        "description": "Upload a file to Agent Drive for processing and semantic indexing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file on disk"},
                "kb": {"type": "string", "description": "Optional knowledge base name or ID to add the file to after upload"},
            },
            "required": ["path"],
        },
        "_http": {"method": "POST", "path": "/v1/files", "param_mapping": {"path": "file"}},
    },
    {
        "name": "search",
        "description": "Search across all uploaded files using natural language. Optionally scope to a knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
                "kb": {"type": "string", "description": "Optional knowledge base name or ID to search within"},
            },
            "required": ["query"],
        },
        "_http": {"method": "POST", "path": "/v1/search", "body_fields": ["query", "top_k"]},
    },
    {
        "name": "get_file_status",
        "description": "Check the processing status of an uploaded file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "File ID returned from upload"},
            },
            "required": ["file_id"],
        },
        "_http": {"method": "GET", "path_template": "/v1/files/{file_id}"},
    },
    {
        "name": "list_files",
        "description": "List all files uploaded to Agent Drive.",
        "inputSchema": {"type": "object", "properties": {}},
        "_http": {"method": "GET", "path": "/v1/files"},
    },
    {
        "name": "delete_file",
        "description": "Delete a file and all its chunks from Agent Drive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "File ID to delete"},
            },
            "required": ["file_id"],
        },
        "_http": {"method": "DELETE", "path_template": "/v1/files/{file_id}"},
    },
    {
        "name": "get_chunk",
        "description": "Get a specific chunk by ID with full content and provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {"type": "string", "description": "Chunk ID"},
            },
            "required": ["chunk_id"],
        },
        "_http": {"method": "GET", "path_template": "/v1/chunks/{chunk_id}"},
    },
    {
        "name": "download_file",
        "description": "Download a file from Agent Drive to local disk. Optionally open it in the native OS application.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID of the file to download"},
                "open": {"type": "boolean", "description": "Open the file in the native app after download (default: false)", "default": False},
            },
            "required": ["file_id"],
        },
        "_http": {"method": "GET", "path_template": "/v1/files/{file_id}/download"},
    },
    {
        "name": "create_api_key",
        "description": "Create a new API key for your tenant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name for the key (e.g. 'production', 'ci')"},
            },
        },
        "_http": {"method": "POST", "path": "/v1/api-keys"},
    },
    {
        "name": "list_api_keys",
        "description": "List all API keys for your tenant.",
        "inputSchema": {"type": "object", "properties": {}},
        "_http": {"method": "GET", "path": "/v1/api-keys"},
    },
    {
        "name": "revoke_api_key",
        "description": "Revoke an API key by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key_id": {"type": "string", "description": "UUID of the key to revoke"},
            },
            "required": ["key_id"],
        },
        "_http": {"method": "DELETE", "path_template": "/v1/api-keys/{key_id}"},
    },
    # Knowledge base tools
    {
        "name": "create_knowledge_base",
        "description": "Create a new knowledge base to organize files and generate synthesized knowledge articles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name for the knowledge base"},
                "description": {"type": "string", "description": "Optional description"},
            },
            "required": ["name"],
        },
        "_http": {"method": "POST", "path": "/v1/knowledge-bases"},
    },
    {
        "name": "list_knowledge_bases",
        "description": "List all knowledge bases.",
        "inputSchema": {"type": "object", "properties": {}},
        "_http": {"method": "GET", "path": "/v1/knowledge-bases"},
    },
    {
        "name": "get_knowledge_base",
        "description": "Get details of a knowledge base by name or ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
            },
            "required": ["kb"],
        },
        "_http": {"method": "GET", "path_template": "/v1/knowledge-bases/{kb_id}", "requires_resolution": True},
    },
    {
        "name": "delete_knowledge_base",
        "description": "Delete a knowledge base. Articles are deleted but files are kept.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
            },
            "required": ["kb"],
        },
        "_http": {"method": "DELETE", "path_template": "/v1/knowledge-bases/{kb_id}", "requires_resolution": True},
    },
    {
        "name": "add_files_to_kb",
        "description": "Add files to a knowledge base. Triggers compilation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "file_ids": {"type": "array", "items": {"type": "string"}, "description": "List of file IDs to add"},
            },
            "required": ["kb", "file_ids"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/files", "requires_resolution": True},
    },
    {
        "name": "remove_files_from_kb",
        "description": "Remove files from a knowledge base. Affected articles are marked stale.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "file_ids": {"type": "array", "items": {"type": "string"}, "description": "List of file IDs to remove"},
            },
            "required": ["kb", "file_ids"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/files/remove", "requires_resolution": True},
    },
    {
        "name": "search_kb",
        "description": "Search within a knowledge base. Returns both chunks and synthesized articles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Number of results", "default": 5},
                "articles_only": {"type": "boolean", "description": "Only return articles", "default": False},
            },
            "required": ["kb", "query"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/search", "requires_resolution": True},
    },
    {
        "name": "get_article",
        "description": "Get a specific article from a knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "article_id": {"type": "string", "description": "Article ID"},
            },
            "required": ["kb", "article_id"],
        },
        "_http": {"method": "GET", "path_template": "/v1/knowledge-bases/{kb_id}/articles/{article_id}", "requires_resolution": True},
    },
    {
        "name": "list_articles",
        "description": "List articles in a knowledge base with optional filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "category": {"type": "string"},
                "article_type": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
            },
            "required": ["kb"],
        },
        "_http": {"method": "GET", "path_template": "/v1/knowledge-bases/{kb_id}/articles", "requires_resolution": True},
    },
    {
        "name": "compile_kb",
        "description": "Trigger compilation of a knowledge base to generate/update articles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "force": {"type": "boolean", "description": "Force full recompilation", "default": False},
            },
            "required": ["kb"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/compile", "requires_resolution": True},
    },
    {
        "name": "health_check",
        "description": "Run health analysis on a knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "quick": {"type": "boolean", "description": "Quick mode (cheap checks only)", "default": False},
            },
            "required": ["kb"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/health-check", "requires_resolution": True},
    },
    {
        "name": "repair_kb",
        "description": "Execute repair actions on a knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "apply": {"type": "array", "items": {"type": "string"}, "description": "Actions to apply (e.g. 'stale', 'gaps')"},
            },
            "required": ["kb", "apply"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/repair", "requires_resolution": True},
    },
    {
        "name": "derive_article",
        "description": "File a Q&A output back into a knowledge base as a derived article.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb": {"type": "string", "description": "Knowledge base name or ID"},
                "title": {"type": "string"},
                "content": {"type": "string", "description": "Article content in markdown"},
                "source_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional chunk/article IDs that informed this"},
            },
            "required": ["kb", "title", "content"],
        },
        "_http": {"method": "POST", "path_template": "/v1/knowledge-bases/{kb_id}/articles/derived", "requires_resolution": True},
    },
]


@router.get("/mcp/tools")
async def list_mcp_tools():
    """Return MCP tool definitions for dynamic discovery.
    
    The MCP server fetches this endpoint at startup to get the current
    list of available tools, instead of hardcoding them.
    
    Returns tool definitions in MCP-compatible schema format.
    The `_http` field is internal metadata for the MCP server to route
    tool calls to the appropriate API endpoints.
    """
    # Return tools without internal _http metadata for public API
    public_tools = []
    for tool in MCP_TOOLS:
        tool_copy = {k: v for k, v in tool.items() if not k.startswith("_")}
        public_tools.append(tool_copy)
    return {"tools": public_tools}


@router.get("/mcp/tools/full")
async def list_mcp_tools_full():
    """Return full MCP tool definitions including internal routing metadata.
    
    This endpoint includes the `_http` field with routing information
    for the MCP server to dispatch tool calls.
    
    Note: This endpoint should only be called by trusted MCP servers
    as it exposes internal API routing information.
    """
    return {"tools": MCP_TOOLS}
