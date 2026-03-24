# Publish agentdrive-mcp to PyPI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a GitHub Actions workflow that builds and publishes the `agentdrive-mcp` package to PyPI on tag push or manual dispatch, with version validation.

**Architecture:** Single workflow file (`.github/workflows/publish.yml`) triggered by `v[0-9]*` tags or `workflow_dispatch`. Uses OIDC trusted publisher — no API tokens. Version in `packages/mcp/pyproject.toml` is validated against the git tag before publish.

**Tech Stack:** GitHub Actions, `python -m build`, `pypa/gh-action-pypi-publish`, `hatchling`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `.github/workflows/publish.yml` | CI workflow: build + publish to PyPI |
| Modify | `packages/mcp/pyproject.toml` | Add `readme`, `license`, `authors`, `urls` metadata for PyPI listing |
| Create | `packages/mcp/LICENSE` | MIT license text |
| Create | `packages/mcp/README.md` | Package README shown on PyPI page |

## Prerequisites (Manual — before first publish)

Before triggering the workflow, ensure these are done per the [design spec](../specs/2026-03-24-pypi-publish-design.md):

- [ ] PyPI account created at pypi.org
- [ ] `agentdrive-mcp` registered as a pending publisher
- [ ] Trusted publisher configured: repo `Agent-Drive/AgentDrive`, workflow `publish.yml`, environment `pypi`

---

### Task 1: Add package metadata to pyproject.toml

**Files:**
- Modify: `packages/mcp/pyproject.toml`

- [ ] **Step 1: Add metadata fields**

Add the following new fields to the existing `[project]` table in `packages/mcp/pyproject.toml`. Do NOT change existing fields (`name`, `version`, `description`, `requires-python`, `dependencies`).

**Add these lines** after `description`:

```toml
readme = "README.md"
license = "MIT"
authors = [{ name = "Agent Drive" }]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
]
```

**Add this new section** after `[project.scripts]`:

```toml
[project.urls]
Homepage = "https://agentdrive.so"
Repository = "https://github.com/Agent-Drive/AgentDrive"
```

- [ ] **Step 2: Create LICENSE file**

Create `packages/mcp/LICENSE` with the MIT license text:

```
MIT License

Copyright (c) 2026 Agent Drive

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Commit**

```bash
git add packages/mcp/pyproject.toml packages/mcp/LICENSE
git commit -m "chore(mcp-pkg): add PyPI metadata and LICENSE"
```

---

### Task 2: Create package README

**Files:**
- Create: `packages/mcp/README.md`

- [ ] **Step 1: Write README.md**

Create `packages/mcp/README.md`:

```markdown
# agentdrive-mcp

MCP server for [Agent Drive](https://agentdrive.so) — file intelligence for AI agents.

## Install

```sh
curl -fsSL https://api.agentdrive.so/install.sh | sh
```

Or install directly:

```sh
uvx agentdrive-mcp install
```

## Commands

| Command | Description |
|---------|-------------|
| `agentdrive-mcp install` | Authenticate and configure MCP |
| `agentdrive-mcp serve` | Start the MCP stdio server |
| `agentdrive-mcp login` | Re-authenticate |
| `agentdrive-mcp status` | Show auth and config status |
```

- [ ] **Step 2: Verify build includes README**

Run from repo root:

```bash
pip install build && python -m build packages/mcp/
```

Expected: `packages/mcp/dist/` contains `agentdrive_mcp-0.1.0.tar.gz` and `agentdrive_mcp-0.1.0-py3-none-any.whl`. Verify the sdist includes README.md:

```bash
tar -tzf packages/mcp/dist/agentdrive_mcp-0.1.0.tar.gz | grep README
```

Expected output: `agentdrive_mcp-0.1.0/README.md`

- [ ] **Step 3: Clean up and commit**

```bash
rm -rf packages/mcp/dist/
git add packages/mcp/README.md
git commit -m "docs(mcp-pkg): add README for PyPI listing"
```

---

### Task 3: Create the publish workflow

**Files:**
- Create: `.github/workflows/publish.yml`

- [ ] **Step 1: Write the workflow file**

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v[0-9]*"
  workflow_dispatch:

concurrency:
  group: pypi-publish
  cancel-in-progress: false

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Extract package version
        id: version
        run: |
          VERSION=$(python -c "import tomllib; print(tomllib.load(open('packages/mcp/pyproject.toml','rb'))['project']['version'])")
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "Package version: $VERSION"

      - name: Validate tag matches package version
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          TAG_VERSION="${GITHUB_REF_NAME#v}"
          PKG_VERSION="${{ steps.version.outputs.version }}"
          if [ "$TAG_VERSION" != "$PKG_VERSION" ]; then
            echo "::error::Tag version ($TAG_VERSION) does not match package version ($PKG_VERSION)"
            exit 1
          fi
          echo "Tag v$TAG_VERSION matches package version $PKG_VERSION"

      - name: Install build
        run: pip install build

      - name: Build package
        run: python -m build packages/mcp/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: packages/mcp/dist/
```

- [ ] **Step 2: Validate workflow syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml'))" && echo "Valid YAML"
```

Expected: `Valid YAML` (requires PyYAML; if not available, skip — GitHub will validate on push).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: add PyPI publish workflow for agentdrive-mcp"
```

---

### Task 4: Local build verification

This task verifies the full build pipeline works locally before relying on CI.

- [ ] **Step 1: Clean build from scratch**

```bash
rm -rf packages/mcp/dist/
pip install build
python -m build packages/mcp/
```

Expected: creates `packages/mcp/dist/agentdrive_mcp-0.1.0.tar.gz` and `packages/mcp/dist/agentdrive_mcp-0.1.0-py3-none-any.whl`

- [ ] **Step 2: Verify wheel contents**

```bash
python -c "
import zipfile, sys
whl = 'packages/mcp/dist/agentdrive_mcp-0.1.0-py3-none-any.whl'
with zipfile.ZipFile(whl) as z:
    names = z.namelist()
    # Check entry point module exists
    assert any('cli.py' in n for n in names), 'cli.py missing from wheel'
    # Check server module exists
    assert any('server.py' in n for n in names), 'server.py missing from wheel'
    print('Wheel contents OK')
    for n in sorted(names):
        print(f'  {n}')
"
```

Expected: `Wheel contents OK` followed by file listing including `agentdrive_mcp/cli.py`, `agentdrive_mcp/server.py`, `agentdrive_mcp/credentials.py`

- [ ] **Step 3: Test install from wheel**

```bash
uv venv /tmp/test-mcp-install
source /tmp/test-mcp-install/bin/activate
pip install packages/mcp/dist/agentdrive_mcp-0.1.0-py3-none-any.whl
agentdrive-mcp --help
deactivate
rm -rf /tmp/test-mcp-install
```

Expected: `agentdrive-mcp --help` shows the CLI with `install`, `serve`, `login`, `status` commands.

- [ ] **Step 4: Clean up dist**

```bash
rm -rf packages/mcp/dist/
```
