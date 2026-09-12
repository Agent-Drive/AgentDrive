# tests/test_config.py
import os

def test_settings_loads_defaults():
    from agentdrive.config import Settings
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.max_upload_bytes == 32 * 1024 * 1024
    assert s.environment == "development"

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://custom:custom@db/mydb")
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    from agentdrive.config import Settings
    s = Settings()
    assert s.s3_bucket == "my-bucket"


def test_settings_loads_s3_aws_aliases(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", "railway-bucket")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://t3.storage.railway.app")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "auto")
    from agentdrive.config import Settings
    s = Settings()
    assert s.s3_bucket == "railway-bucket"
    assert s.s3_endpoint_url == "https://t3.storage.railway.app"
    assert s.s3_access_key_id == "key"
    assert s.s3_secret_access_key == "secret"
    assert s.s3_region == "auto"
