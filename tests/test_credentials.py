import json
from pathlib import Path

import pytest

from agentdrive.cli.credentials import (
    load_credentials,
    save_credentials,
    delete_credentials,
    CREDENTIALS_DIR,
    CREDENTIALS_FILE,
)


@pytest.fixture
def tmp_creds(tmp_path, monkeypatch):
    """Redirect credentials to a temp directory."""
    creds_dir = tmp_path / ".agentdrive"
    creds_file = creds_dir / "credentials"
    monkeypatch.setattr("agentdrive.cli.credentials.CREDENTIALS_DIR", creds_dir)
    monkeypatch.setattr("agentdrive.cli.credentials.CREDENTIALS_FILE", creds_file)
    return creds_file


def test_save_and_load_credentials(tmp_creds):
    save_credentials(
        api_key="sk-ad-test1234restofkey",
        email="test@example.com",
        tenant_id="some-uuid",
    )
    assert tmp_creds.exists()
    assert oct(tmp_creds.stat().st_mode)[-3:] == "600"

    creds = load_credentials()
    assert creds["api_key"] == "sk-ad-test1234restofkey"
    assert creds["email"] == "test@example.com"
    assert creds["tenant_id"] == "some-uuid"


def test_load_credentials_missing(tmp_creds):
    creds = load_credentials()
    assert creds is None


def test_delete_credentials(tmp_creds):
    save_credentials(api_key="sk-ad-x", email="x@x.com", tenant_id="x")
    assert tmp_creds.exists()
    delete_credentials()
    assert not tmp_creds.exists()


def test_delete_credentials_missing(tmp_creds):
    """Should not raise when file doesn't exist."""
    delete_credentials()
