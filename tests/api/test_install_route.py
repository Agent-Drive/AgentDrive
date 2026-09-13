import pytest
from httpx import ASGITransport, AsyncClient

from agentdrive.main import app


@pytest.mark.asyncio
async def test_install_sh_returns_script():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/install.sh")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "Installing Agent Drive MCP" in response.text


@pytest.mark.asyncio
async def test_install_sh_is_valid_shell():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/install.sh")

    assert response.text.startswith("#!/bin/sh")
