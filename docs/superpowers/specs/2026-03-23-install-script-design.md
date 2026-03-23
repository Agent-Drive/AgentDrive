# One-Line Install Script — Design Spec

**Issue:** #3
**Date:** 2026-03-23
**Status:** Approved

## Overview

Users install Agent Drive MCP into Claude Code with a single command:

```bash
curl -fsSL https://agentdrive.so/install.sh | sh
```

A thin shell script installs the lightweight `agentdrive-mcp` Python package, then delegates to its `install` command which handles authentication (WorkOS device flow) and writes the MCP server config into Claude Code's settings.

## User Flow

```
$ curl -fsSL https://agentdrive.so/install.sh | sh

  Detecting package manager... found uv
  Installing agentdrive-mcp... done

  Starting login...

    Your code: ABCD-EFGH
    Press Enter to open browser...

  Waiting for authentication...

    Logged in as rafey@example.com
    API key stored in ~/.agentdrive/credentials

  Configuring Claude Code MCP... done

  ✓ Agent Drive installed. Restart Claude Code to use.
```

One command. Browser opens. User authenticates. Done.

## Architecture

```
curl | sh
    │
    ▼
install.sh (shell)
    │
    ├─ Detect uv or pip
    ├─ Install agentdrive-mcp package
    └─ Run: agentdrive-mcp install
                │
                ▼
        agentdrive-mcp install (Python)
                │
                ├─ 1. Auth: GET /auth/config → client_id
                │         WorkOS device flow → browser
                │         POST /auth/exchange → sk-ad- key
                │         Save to ~/.agentdrive/credentials
                │
                ├─ 2. Read ~/.claude.json (or create)
                │
                ├─ 3. Merge MCP config (preserve existing servers)
                │
                ├─ 4. Validate: GET /health with auth
                │
                └─ 5. Print success message
```

## Package Structure

```
/Users/rafey/Development/Rafey/AgentDrive/
├── src/agentdrive/              ← existing (server-side, heavy deps)
│
├── packages/mcp/                ← NEW (lightweight client package)
│   ├── pyproject.toml           ← "agentdrive-mcp", ~5 deps
│   ├── src/agentdrive_mcp/
│   │   ├── __init__.py
│   │   ├── server.py            ← MCP stdio server (httpx client)
│   │   ├── credentials.py       ← read/write ~/.agentdrive/credentials
│   │   ├── cli.py               ← typer app: install, serve, login, status
│   │   └── __main__.py          ← python -m agentdrive_mcp
│   └── tests/
│
├── scripts/
│   └── install.sh               ← the curl | sh entry point
│
└── pyproject.toml               ← existing (full server package)
```

## `agentdrive-mcp` Package

### Dependencies (lightweight)

| Package | Purpose |
|---------|---------|
| mcp>=1.0.0 | MCP protocol + stdio transport |
| httpx>=0.28.0 | HTTP client for Agent Drive API |
| typer>=0.15.0 | CLI framework |
| PyJWT>=2.8.0 | JWT decoding for WorkOS token |

No torch, docling, SQLAlchemy, voyage, cohere, or any server-side deps.

### pyproject.toml

```toml
[project]
name = "agentdrive-mcp"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.28.0",
    "typer>=0.15.0",
    "PyJWT>=2.8.0",
]

[project.scripts]
agentdrive-mcp = "agentdrive_mcp.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentdrive_mcp"]
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `agentdrive-mcp install` | Full setup: login + write MCP config |
| `agentdrive-mcp serve` | Start MCP stdio server (called by Claude Code) |
| `agentdrive-mcp login` | Just the auth flow (re-login without reconfiguring) |
| `agentdrive-mcp status` | Show current auth + config status |

### Code

`server.py` and `credentials.py` are copies of the existing code from the main package — not imports. This keeps the MCP package fully independent with no import chain to heavy deps. Both files are small (~160 lines and ~30 lines respectively).

## Shell Script (`install.sh`)

```bash
#!/bin/sh
set -e

# Ensure stdin is from terminal (not the pipe)
exec < /dev/tty

echo "Installing Agent Drive MCP..."

INSTALL_METHOD=""

# Detect package manager: uvx > pipx > pip --user
if command -v uvx >/dev/null 2>&1; then
    echo "  Detected uv"
    INSTALL_METHOD="uvx"
    uvx --force-reinstall agentdrive-mcp install --method uvx
elif command -v pipx >/dev/null 2>&1; then
    echo "  Detected pipx"
    INSTALL_METHOD="pipx"
    pipx install --force agentdrive-mcp
    agentdrive-mcp install --method pipx
elif command -v pip >/dev/null 2>&1; then
    echo "  Detected pip"
    INSTALL_METHOD="pip"
    pip install --user --quiet agentdrive-mcp
    agentdrive-mcp install --method pip
else
    echo "Error: uv, pipx, or pip required. Install uv: https://docs.astral.sh/uv/"
    exit 1
fi
```

Notes:
- `exec < /dev/tty` reconnects stdin to the terminal so the login flow's `input()` works when piped via `curl | sh`.
- `uvx --force-reinstall` ensures re-runs pick up the latest version from PyPI.
- `pipx` is preferred over raw `pip` to avoid PEP 668 externally-managed-environment errors on modern macOS/Linux.
- `pip --user` as last resort avoids system Python permission issues.
- The `uvx` path is preferred — it installs and runs in one shot with no global pollution.

## Python Installer (`agentdrive-mcp install`)

### Step 1: Authentication

Same flow as `agentdrive login`:
1. `GET {api_url}/auth/config` → get WorkOS `client_id`
2. `POST https://api.workos.com/user_management/authorize/device` → get device code
3. User authenticates in browser
4. Poll `POST https://api.workos.com/user_management/authenticate` → get access token
5. `POST {api_url}/auth/exchange` → get `sk-ad-` API key
6. Save to `~/.agentdrive/credentials` (JSON, `0o600` permissions)

### Step 2: Write MCP Config

Use `claude mcp add` CLI if available (safest — handles edge cases, concurrent writes, schema validation). Fall back to direct JSON manipulation of `~/.claude.json` if `claude` CLI is not found.

**Primary: `claude mcp add`**
```bash
# uvx install path:
claude mcp add agent-drive --scope user -- uvx agentdrive-mcp serve
# pipx/pip install path:
claude mcp add agent-drive --scope user -- agentdrive-mcp serve
```

Then set the env var:
```bash
claude mcp add agent-drive --scope user -e AGENT_DRIVE_URL=https://api.agentdrive.so -- uvx agentdrive-mcp serve
```

**Fallback: direct JSON merge of `~/.claude.json`**

The MCP config adapts based on how the package was installed:

If installed via `uvx`:
```json
{
  "mcpServers": {
    "agent-drive": {
      "command": "uvx",
      "args": ["agentdrive-mcp", "serve"],
      "env": {
        "AGENT_DRIVE_URL": "https://api.agentdrive.so"
      }
    }
  }
}
```

If installed via `pipx` or `pip`:
```json
{
  "mcpServers": {
    "agent-drive": {
      "command": "agentdrive-mcp",
      "args": ["serve"],
      "env": {
        "AGENT_DRIVE_URL": "https://api.agentdrive.so"
      }
    }
  }
}
```

The `install` command receives the install method (passed as `--method uvx|pipx|pip` from the shell script) and writes the appropriate config.

**No `AGENT_DRIVE_API_KEY` in the config** — the MCP server reads from `~/.agentdrive/credentials` automatically.

**Merge behavior (fallback only):** If `~/.claude.json` exists, read it, add/overwrite only the `agent-drive` key under `mcpServers`, preserve everything else. If file doesn't exist, create it with just the `mcpServers` key.

### Step 3: Validate

Hit `GET {api_url}/health` with the new API key to confirm everything works.

### Step 4: Success

```
✓ Agent Drive installed. Restart Claude Code to use.
```

## Configuration

### Default API URL

`https://api.agentdrive.so` — hardcoded in the MCP config. Can be overridden via `AGENT_DRIVE_URL` env var.

### Credentials

Path: `~/.agentdrive/credentials`
Format: `{"api_key": "sk-ad-...", "email": "...", "tenant_id": "...", "created_at": "..."}`
Permissions: `0o600`

### MCP Config

Path: `~/.claude.json`
Key: `mcpServers.agent-drive`

## Idempotency

Safe to run multiple times:
- Re-authenticates (generates new API key via WorkOS)
- Overwrites `agent-drive` MCP entry
- Preserves all other MCP servers in settings.json
- Old API key remains valid (not revoked) — user can revoke manually via `agentdrive-mcp status` or API

## Platform Support

- macOS (primary)
- Linux
- Windows: not supported by `curl | sh` — separate instructions if needed later

## Prerequisites for Launch

1. Publish `agentdrive-mcp` to PyPI
2. Host `install.sh` at `https://agentdrive.so/install.sh`
3. Deploy Agent Drive API to `https://api.agentdrive.so`
4. WorkOS production environment configured

## Design Decisions

1. **Separate lightweight package** — MCP client is ~5 deps vs 30+ for the full server. Users shouldn't download torch to use an HTTP client.
2. **Hybrid shell + Python** — shell detects environment, Python handles auth + JSON merging. Each language does what it's good at.
3. **Auth via `agentdrive login` flow** — user never sees or handles an API key. Browser auth is seamless.
4. **No API key in MCP config** — credentials file is the single source of truth. MCP config stays clean and shareable.
5. **`uvx` as primary install path** — no global package pollution, runs in isolated environment.
6. **Code duplication over shared imports** — MCP package copies server.py and credentials.py (~200 lines total) to avoid pulling in heavy deps via import chain.
7. **Monorepo** — MCP package lives at `packages/mcp/` in the same repo. Easy to keep in sync with API changes.
