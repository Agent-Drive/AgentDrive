# Design: Publish agentdrive-mcp to PyPI

**Issue:** #7
**Date:** 2026-03-24

## Goal

Publish `agentdrive-mcp` to PyPI so users can install via `uvx agentdrive-mcp`, `pipx install agentdrive-mcp`, or `pip install agentdrive-mcp`. Unblocks the install script at `https://api.agentdrive.so/install.sh`.

## Package Details

- **Name:** `agentdrive-mcp`
- **Source:** `packages/mcp/`
- **Build backend:** `hatchling`
- **Version:** `0.1.0` (in `packages/mcp/pyproject.toml`)
- **Entry point:** `agentdrive-mcp = "agentdrive_mcp.cli:app"`
- **Dependencies:** `mcp>=1.0.0`, `httpx>=0.28.0`, `typer>=0.15.0`
- **Python:** `>=3.10`

## Versioning Strategy

**Manual + CI guard.** Version lives in `packages/mcp/pyproject.toml`. On tag-triggered publishes, CI validates the tag matches the pyproject.toml version. Workflow fails if they diverge.

Release flow: bump version in `packages/mcp/pyproject.toml` → commit → push tag `v0.2.0` → CI validates match → builds → publishes.

## Workflow Design

**File:** `.github/workflows/publish.yml`

### Triggers

- **Tag push:** `v*` — primary release path
- **Manual dispatch:** `workflow_dispatch` — retry/recovery path, no inputs needed

### Job: `publish`

**Runs on:** `ubuntu-latest`
**Environment:** `pypi` (required for OIDC trusted publisher)
**Permissions:** `id-token: write`, `contents: read`

**Steps:**

1. **Checkout** — `actions/checkout@v4`
2. **Setup Python** — `actions/setup-python@v5` with Python 3.12
3. **Extract version** — read version from `packages/mcp/pyproject.toml`
4. **Validate tag** (tag trigger only) — fail if tag `vX.Y.Z` doesn't match pyproject.toml version `X.Y.Z`
5. **Install build** — `pip install build`
6. **Build** — `python -m build packages/mcp/` (produces sdist + wheel in `packages/mcp/dist/`)
7. **Publish** — `pypa/gh-action-pypi-publish@release/v1` with `packages-dir: packages/mcp/dist/`, using OIDC trusted publisher (no API tokens)

### Version Validation Logic

```
tag_version = strip 'v' prefix from git tag
pkg_version = extract version from packages/mcp/pyproject.toml
if tag_version != pkg_version: fail with error message
```

On `workflow_dispatch`, this step is skipped — it builds and publishes whatever version is in pyproject.toml.

## Prerequisites (Manual)

These must be done before the first publish:

1. **PyPI account** — log in at pypi.org
2. **Register package name** — create a pending publisher for `agentdrive-mcp`
3. **Trusted publisher config:**
   - Repository: `Agent-Drive/AgentDrive`
   - Workflow: `publish.yml`
   - Environment: `pypi`

## Verification

After first publish:

- `pip install agentdrive-mcp` installs successfully
- `uvx agentdrive-mcp --help` shows CLI commands
- `curl -fsSL https://api.agentdrive.so/install.sh | sh` completes full install flow

## Out of Scope

- TestPyPI staging (can be added later if needed)
- Automated version bumping
- GitHub Release creation (can be added as a follow-up)
