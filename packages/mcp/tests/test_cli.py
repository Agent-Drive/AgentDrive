import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentdrive_mcp.cli import _write_mcp_config


@pytest.fixture
def tmp_claude_config(tmp_path, monkeypatch):
    config_path = tmp_path / ".claude.json"
    # Patch Path.home() to return tmp_path
    original_home = Path.home
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
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
    assert entry["args"] == ["agentdrive-mcp@latest", "serve"]
    assert entry["env"]["AGENT_DRIVE_URL"] == "https://api.agentdrive.so"


def test_write_config_pip_uses_direct_command(tmp_claude_config):
    _write_mcp_config("pip", "https://api.agentdrive.so")
    config = json.loads(tmp_claude_config.read_text())
    entry = config["mcpServers"]["agent-drive"]
    assert entry["command"] == "agentdrive-mcp"
    assert entry["args"] == ["serve"]


def test_write_config_merges_existing(tmp_claude_config):
    existing = {
        "mcpServers": {
            "other-server": {"command": "npx", "args": ["other"]}
        },
        "someOtherKey": True,
    }
    tmp_claude_config.write_text(json.dumps(existing))

    _write_mcp_config("uvx", "https://api.agentdrive.so")
    config = json.loads(tmp_claude_config.read_text())

    assert "other-server" in config["mcpServers"]
    assert config["mcpServers"]["other-server"]["command"] == "npx"
    assert "agent-drive" in config["mcpServers"]
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
