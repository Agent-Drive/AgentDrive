# tests/test_config.py
import os

def test_settings_loads_defaults():
    from agentdrive.config import Settings
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.max_upload_bytes == 32 * 1024 * 1024
    assert s.environment == "development"

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://custom:custom@db/mydb")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    from agentdrive.config import Settings
    s = Settings()
    assert s.gcs_bucket == "my-bucket"
