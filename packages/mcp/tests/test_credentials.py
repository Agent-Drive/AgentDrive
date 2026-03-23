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
