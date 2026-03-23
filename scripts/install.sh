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
