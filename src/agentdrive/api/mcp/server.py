from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from agentdrive.api.dependencies import _tenant_from_api_key
from agentdrive.api.mcp import tools as mcp_tools
from agentdrive.api.mcp.deps import mcp_session
from agentdrive.api.mcp.oauth import WorkOSOAuthProvider
from agentdrive.config import settings


def _public_base_url() -> str:
    return settings.public_base_url.rstrip("/")


async def _current_tenant(session):
    access = get_access_token()
    if access is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    tenant = await _tenant_from_api_key(session, access.token)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant


async def _run_tool(fn, *args, **kwargs) -> str:
    try:
        async with mcp_session() as session:
            tenant = await _current_tenant(session)
            return await fn(session, tenant, *args, **kwargs)
    except HTTPException as exc:
        return f"Error ({exc.status_code}): {exc.detail}"


def create_mcp_server() -> tuple[FastMCP, WorkOSOAuthProvider]:
    issuer = _public_base_url()
    provider = WorkOSOAuthProvider(public_base_url=issuer)
    mcp = FastMCP(
        "agent-drive",
        instructions="Hosted Agent Drive MCP. Search, list, upload, and download tenant files.",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer),
            resource_server_url=AnyHttpUrl(f"{issuer}/mcp"),
            client_registration_options=ClientRegistrationOptions(enabled=True),
        ),
        streamable_http_path="/mcp",
        stateless_http=False,
        json_response=False,
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool(structured_output=False)
    async def search(query: str, top_k: int = 5) -> str:
        """Search across all uploaded files using natural language."""
        return await _run_tool(mcp_tools.search, query, top_k=top_k)

    @mcp.tool(structured_output=False)
    async def list_files() -> str:
        """List all files uploaded to Agent Drive."""
        return await _run_tool(mcp_tools.list_files)

    @mcp.tool(structured_output=False)
    async def get_file_status(file_id: str) -> str:
        """Check the processing status of an uploaded file."""
        return await _run_tool(mcp_tools.get_file_status, file_id)

    @mcp.tool(structured_output=False)
    async def delete_file(file_id: str) -> str:
        """Delete a file and all its chunks from Agent Drive."""
        return await _run_tool(mcp_tools.delete_file, file_id)

    @mcp.tool(structured_output=False)
    async def start_upload(
        filename: str,
        file_size: int,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """Create a signed upload URL. PUT the file to upload_url, then call complete_upload."""
        return await _run_tool(mcp_tools.start_upload, filename, file_size, mime_type=mime_type)

    @mcp.tool(structured_output=False)
    async def complete_upload(file_id: str) -> str:
        """Mark a signed upload complete after the client PUTs bytes to the signed URL."""
        return await _run_tool(mcp_tools.complete_upload, file_id)

    @mcp.tool(structured_output=False)
    async def download_file(file_id: str) -> str:
        """Return a signed download URL for a file. Does not write to server disk."""
        return await _run_tool(mcp_tools.download_file, file_id)

    return mcp, provider
