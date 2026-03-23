# One-Line Install Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `curl | sh` install experience that installs the lightweight `agentdrive-mcp` package, authenticates the user via WorkOS, and configures Claude Code's MCP server — all in one command.

**Architecture:** Separate lightweight `agentdrive-mcp` package at `packages/mcp/` with ~5 deps. Shell script detects package manager and installs, then delegates to Python CLI for auth (WorkOS device flow) and MCP config writing (via `claude mcp add` or direct JSON merge).

**Tech Stack:** Python (typer, httpx, mcp, PyJWT), Shell (POSIX sh)

**Spec:** `docs/superpowers/specs/2026-03-23-install-script-design.md`

---

## File Structure

```
packages/mcp/
├── pyproject.toml                     ← CREATE (agentdrive-mcp package config)
├── src/agentdrive_mcp/
│   ├── __init__.py                    ← CREATE (empty)
│   ├── __main__.py                    ← CREATE (python -m agentdrive_mcp)
│   ├── server.py                      ← CREATE (copy from src/agentdrive/mcp/server.py, adapt default URL)
│   ├── credentials.py                 ← CREATE (copy from src/agentdrive/cli/credentials.py)
│   └── cli.py                         ← CREATE (typer app: install, serve, login, status)
└── tests/
    ├── test_credentials.py            ← CREATE (credentials tests)
    └── test_cli.py                    ← CREATE (CLI config writing tests)

scripts/
└── install.sh                         ← CREATE (the curl | sh entry point)
```

---

### Task 1: Package scaffold

**Files:**
- Create: `packages/mcp/pyproject.toml`
- Create: `packages/mcp/src/agentdrive_mcp/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p packages/mcp/src/agentdrive_mcp
mkdir -p packages/mcp/tests
```

- [ ] **Step 2: Create pyproject.toml**

Create `packages/mcp/pyproject.toml`:

```toml
[project]
name = "agentdrive-mcp"
version = "0.1.0"
description = "Agent Drive MCP server for Claude Code"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.28.0",
    "typer>=0.15.0",
]

[project.scripts]
agentdrive-mcp = "agentdrive_mcp.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentdrive_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create __init__.py**

Create `packages/mcp/src/agentdrive_mcp/__init__.py` (empty file).

- [ ] **Step 4: Install package in dev mode**

```bash
cd packages/mcp && uv pip install -e . && cd ../..
```

- [ ] **Step 5: Commit**

```bash
git add packages/mcp/pyproject.toml packages/mcp/src/agentdrive_mcp/__init__.py
git commit -m "chore: scaffold agentdrive-mcp package"
```

---

### Task 2: Credentials module

**Files:**
- Create: `packages/mcp/src/agentdrive_mcp/credentials.py`
- Create: `packages/mcp/tests/test_credentials.py`

- [ ] **Step 1: Write tests**

Create `packages/mcp/tests/test_credentials.py`:

```python
import json
from pathlib import Path

import pytest

from agentdrive_mcp.credentials import (
    load_credentials,
    save_credentials,
    delete_credentials,
)


@pytest.fixture
def tmp_creds(tmp_path, monkeypatch):
    creds_dir = tmp_path / ".agentdrive"
    creds_file = creds_dir / "credentials"
    monkeypatch.setattr("agentdrive_mcp.credentials.CREDENTIALS_DIR", creds_dir)
    monkeypatch.setattr("agentdrive_mcp.credentials.CREDENTIALS_FILE", creds_file)
    return creds_file


def test_save_and_load(tmp_creds):
    save_credentials(api_key="sk-ad-test1234key", email="test@example.com", tenant_id="uuid")
    assert tmp_creds.exists()
    assert oct(tmp_creds.stat().st_mode)[-3:] == "600"
    creds = load_credentials()
    assert creds["api_key"] == "sk-ad-test1234key"
    assert creds["email"] == "test@example.com"


def test_load_missing(tmp_creds):
    assert load_credentials() is None


def test_delete(tmp_creds):
    save_credentials(api_key="x", email="x", tenant_id="x")
    delete_credentials()
    assert not tmp_creds.exists()


def test_delete_missing(tmp_creds):
    delete_credentials()  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/mcp && uv run pytest tests/test_credentials.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Create credentials.py**

Create `packages/mcp/src/agentdrive_mcp/credentials.py` (copy from `src/agentdrive/cli/credentials.py`):

```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path

CREDENTIALS_DIR = Path.home() / ".agentdrive"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials"


def save_credentials(api_key: str, email: str, tenant_id: str) -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "api_key": api_key,
        "email": email,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(CREDENTIALS_FILE, 0o600)


def load_credentials() -> dict | None:
    if not CREDENTIALS_FILE.exists():
        return None
    return json.loads(CREDENTIALS_FILE.read_text())


def delete_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
```

- [ ] **Step 4: Run tests**

Run: `cd packages/mcp && uv run pytest tests/test_credentials.py -v`
Expected: PASS (all 4)

- [ ] **Step 5: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/credentials.py packages/mcp/tests/test_credentials.py
git commit -m "feat(mcp-pkg): add credentials module"
```

---

### Task 3: MCP server

**Files:**
- Create: `packages/mcp/src/agentdrive_mcp/server.py`
- Create: `packages/mcp/src/agentdrive_mcp/__main__.py`

- [ ] **Step 1: Create server.py**

Copy `src/agentdrive/mcp/server.py` to `packages/mcp/src/agentdrive_mcp/server.py` with one change: default URL is `https://api.agentdrive.so` instead of `http://localhost:8080`.

```python
import json
import os
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
    import sys
    print("Error: No API key found. Run 'agentdrive-mcp login' or set AGENT_DRIVE_API_KEY.", file=sys.stderr)

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
```

- [ ] **Step 2: Create __main__.py**

Create `packages/mcp/src/agentdrive_mcp/__main__.py`:

```python
import asyncio
from agentdrive_mcp.server import main

asyncio.run(main())
```

- [ ] **Step 3: Verify import works**

Run: `cd packages/mcp && uv run python -c "from agentdrive_mcp.server import server; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/server.py packages/mcp/src/agentdrive_mcp/__main__.py
git commit -m "feat(mcp-pkg): add MCP stdio server"
```

---

### Task 4: CLI — login, serve, status commands

**Files:**
- Create: `packages/mcp/src/agentdrive_mcp/cli.py`

- [ ] **Step 1: Create cli.py**

Create `packages/mcp/src/agentdrive_mcp/cli.py`:

```python
import json
import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path

import httpx
import typer

from agentdrive_mcp.credentials import delete_credentials, load_credentials, save_credentials

app = typer.Typer(name="agentdrive-mcp", help="Agent Drive MCP for Claude Code")

DEFAULT_API_URL = "https://api.agentdrive.so"
WORKOS_API_BASE = "https://api.workos.com"


def _get_api_url() -> str:
    return os.environ.get("AGENT_DRIVE_URL", DEFAULT_API_URL)


def _do_login(api_url: str) -> dict:
    """Run WorkOS device flow login. Returns {"api_key", "email", "tenant_id"}."""
    with httpx.Client(timeout=30) as client:
        config_resp = client.get(f"{api_url}/auth/config")
        if config_resp.status_code != 200:
            typer.echo(f"Error: could not reach Agent Drive at {api_url}", err=True)
            raise typer.Exit(1)
        client_id = config_resp.json()["client_id"]

        resp = client.post(
            f"{WORKOS_API_BASE}/user_management/authorize/device",
            json={"client_id": client_id},
        )
        if resp.status_code != 200:
            typer.echo(f"Error starting device auth: {resp.text}", err=True)
            raise typer.Exit(1)
        data = resp.json()

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data.get("verification_uri_complete", data["verification_uri"])
    interval = data.get("interval", 5)

    typer.echo(f"\n  Your code: {user_code}")
    typer.echo(f"  Press Enter to open browser, or visit: {verification_uri}")
    input()
    webbrowser.open(verification_uri)

    typer.echo("Waiting for authentication...")
    with httpx.Client(timeout=30) as client:
        for _ in range(60):
            time.sleep(interval)
            resp = client.post(
                f"{WORKOS_API_BASE}/user_management/authenticate",
                json={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if resp.status_code == 200:
                token_data = resp.json()
                access_token = token_data["access_token"]

                exchange_resp = httpx.post(
                    f"{api_url}/auth/exchange",
                    json={"access_token": access_token},
                    timeout=30,
                )
                if exchange_resp.status_code != 200:
                    typer.echo(f"Error exchanging token: {exchange_resp.text}", err=True)
                    raise typer.Exit(1)

                result = exchange_resp.json()
                save_credentials(
                    api_key=result["api_key"],
                    email=result["email"],
                    tenant_id=result["tenant_id"],
                )
                typer.echo(f"\n  Logged in as {result['email']}")
                typer.echo("  API key stored in ~/.agentdrive/credentials")
                return result

            error = resp.json().get("error", "")
            if error == "slow_down":
                interval += 5
            elif error in ("access_denied", "expired_token"):
                typer.echo(f"Login failed: {error}", err=True)
                raise typer.Exit(1)

    typer.echo("Login timed out. Please try again.", err=True)
    raise typer.Exit(1)


def _write_mcp_config(method: str, api_url: str) -> None:
    """Write MCP config to ~/.claude.json using claude CLI or direct JSON merge."""
    if method == "uvx":
        command = "uvx"
        args = ["agentdrive-mcp", "serve"]
    else:
        command = "agentdrive-mcp"
        args = ["serve"]

    # Try claude mcp add first (safest)
    if shutil.which("claude"):
        try:
            cmd = [
                "claude", "mcp", "add", "agent-drive",
                "--scope", "user",
                "-e", f"AGENT_DRIVE_URL={api_url}",
                "--", command, *args,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # fall through to manual JSON

    # Fallback: direct JSON merge
    config_path = Path.home() / ".claude.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["agent-drive"] = {
        "command": command,
        "args": args,
        "env": {
            "AGENT_DRIVE_URL": api_url,
        },
    }

    config_path.write_text(json.dumps(config, indent=2))


@app.command()
def install(
    method: str = typer.Option("uvx", help="Install method: uvx, pipx, or pip"),
):
    """Full setup: authenticate + configure Claude Code MCP."""
    api_url = _get_api_url()

    # Step 1: Login
    _do_login(api_url)

    # Step 2: Write MCP config
    typer.echo("\n  Configuring Claude Code MCP...")
    _write_mcp_config(method, api_url)

    # Step 3: Validate
    creds = load_credentials()
    if creds:
        with httpx.Client(timeout=10) as client:
            try:
                resp = client.get(
                    f"{api_url}/health",
                    headers={"Authorization": f"Bearer {creds['api_key']}"},
                )
                if resp.status_code == 200:
                    typer.echo("  Connection verified.")
            except httpx.ConnectError:
                typer.echo("  Warning: could not verify connection (server may not be reachable).")

    typer.echo("\n  ✓ Agent Drive installed. Restart Claude Code to use.")


@app.command()
def serve():
    """Start the MCP stdio server (called by Claude Code)."""
    import asyncio
    from agentdrive_mcp.server import main
    asyncio.run(main())


@app.command()
def login():
    """Authenticate with Agent Drive (re-login)."""
    api_url = _get_api_url()
    _do_login(api_url)
    typer.echo("  Ready to use!")


@app.command()
def status():
    """Show current authentication and config status."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run 'agentdrive-mcp login' to authenticate.")
        raise typer.Exit(1)
    typer.echo(f"  Email:     {creds['email']}")
    typer.echo(f"  Tenant:    {creds['tenant_id']}")
    typer.echo(f"  Key:       {creds['api_key'][:14]}...")
    typer.echo(f"  Since:     {creds.get('created_at', 'unknown')}")

    # Check MCP config
    config_path = Path.home() / ".claude.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if "mcpServers" in config and "agent-drive" in config["mcpServers"]:
            typer.echo("  MCP:       configured in ~/.claude.json")
        else:
            typer.echo("  MCP:       not configured (run 'agentdrive-mcp install')")
    else:
        typer.echo("  MCP:       ~/.claude.json not found")


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Verify CLI loads**

Run: `cd packages/mcp && uv run agentdrive-mcp --help`
Expected: Shows install, serve, login, status commands

- [ ] **Step 3: Commit**

```bash
git add packages/mcp/src/agentdrive_mcp/cli.py
git commit -m "feat(mcp-pkg): add CLI with install, serve, login, status commands"
```

---

### Task 5: CLI config writing tests

**Files:**
- Create: `packages/mcp/tests/test_cli.py`

- [ ] **Step 1: Write tests for MCP config writing**

Create `packages/mcp/tests/test_cli.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentdrive_mcp.cli import _write_mcp_config


@pytest.fixture
def tmp_claude_config(tmp_path, monkeypatch):
    config_path = tmp_path / ".claude.json"
    monkeypatch.setattr("agentdrive_mcp.cli.Path.home", lambda: tmp_path)
    # Patch shutil.which to return None (no claude CLI)
    monkeypatch.setattr("agentdrive_mcp.cli.shutil.which", lambda x: None)
    return config_path


def test_write_config_uvx_creates_file(tmp_claude_config):
    _write_mcp_config("uvx", "https://api.agentdrive.so")
    config = json.loads(tmp_claude_config.read_text())
    assert "mcpServers" in config
    assert "agent-drive" in config["mcpServers"]
    entry = config["mcpServers"]["agent-drive"]
    assert entry["command"] == "uvx"
    assert entry["args"] == ["agentdrive-mcp", "serve"]
    assert entry["env"]["AGENT_DRIVE_URL"] == "https://api.agentdrive.so"


def test_write_config_pip_uses_direct_command(tmp_claude_config):
    _write_mcp_config("pip", "https://api.agentdrive.so")
    config = json.loads(tmp_claude_config.read_text())
    entry = config["mcpServers"]["agent-drive"]
    assert entry["command"] == "agentdrive-mcp"
    assert entry["args"] == ["serve"]


def test_write_config_merges_existing(tmp_claude_config):
    # Pre-existing config with another MCP server
    existing = {
        "mcpServers": {
            "other-server": {"command": "npx", "args": ["other"]}
        },
        "someOtherKey": True,
    }
    tmp_claude_config.write_text(json.dumps(existing))

    _write_mcp_config("uvx", "https://api.agentdrive.so")
    config = json.loads(tmp_claude_config.read_text())

    # Other server preserved
    assert "other-server" in config["mcpServers"]
    assert config["mcpServers"]["other-server"]["command"] == "npx"
    # Our server added
    assert "agent-drive" in config["mcpServers"]
    # Other keys preserved
    assert config["someOtherKey"] is True


def test_write_config_overwrites_existing_agent_drive(tmp_claude_config):
    existing = {
        "mcpServers": {
            "agent-drive": {"command": "old", "args": ["old"]}
        }
    }
    tmp_claude_config.write_text(json.dumps(existing))

    _write_mcp_config("uvx", "https://api.agentdrive.so")
    config = json.loads(tmp_claude_config.read_text())
    assert config["mcpServers"]["agent-drive"]["command"] == "uvx"
```

- [ ] **Step 2: Run tests**

Run: `cd packages/mcp && uv run pytest tests/test_cli.py -v`
Expected: PASS (all 4)

- [ ] **Step 3: Commit**

```bash
git add packages/mcp/tests/test_cli.py
git commit -m "test(mcp-pkg): add MCP config writing tests"
```

---

### Task 6: Install shell script

**Files:**
- Create: `scripts/install.sh`

- [ ] **Step 1: Create install.sh**

Create `scripts/install.sh`:

```bash
#!/bin/sh
set -e

# Ensure stdin is from terminal (not the pipe)
exec < /dev/tty

echo ""
echo "  Installing Agent Drive MCP..."
echo ""

# Detect package manager: uvx > pipx > pip --user
if command -v uvx >/dev/null 2>&1; then
    echo "  Detected uv"
    uvx --force-reinstall agentdrive-mcp install --method uvx
elif command -v pipx >/dev/null 2>&1; then
    echo "  Detected pipx"
    pipx install --force agentdrive-mcp
    agentdrive-mcp install --method pipx
elif command -v pip >/dev/null 2>&1; then
    echo "  Detected pip"
    pip install --user --quiet agentdrive-mcp
    agentdrive-mcp install --method pip
else
    echo "  Error: uv, pipx, or pip required."
    echo "  Install uv: https://docs.astral.sh/uv/"
    exit 1
fi
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/install.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/install.sh
git commit -m "feat: add install.sh for curl | sh one-line install"
```

---

### Task 7: Verify full package

**Files:** None (verification only)

- [ ] **Step 1: Run all package tests**

Run: `cd packages/mcp && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Verify CLI loads**

Run: `cd packages/mcp && uv run agentdrive-mcp --help`
Expected: Shows all 4 commands

- [ ] **Step 3: Verify serve command starts**

Run: `cd packages/mcp && timeout 2 uv run agentdrive-mcp serve 2>&1 || true`
Expected: Starts MCP server (will timeout since no stdin, but should not crash)

- [ ] **Step 4: Verify python -m works**

Run: `cd packages/mcp && timeout 2 uv run python -m agentdrive_mcp 2>&1 || true`
Expected: Same as serve — starts without import errors

- [ ] **Step 5: Verify install.sh syntax**

Run: `sh -n scripts/install.sh && echo "Syntax OK"`
Expected: "Syntax OK"
