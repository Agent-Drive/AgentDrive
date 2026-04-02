# src/agentdrive/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive"
    gcs_bucket: str = "agentdrive-files"
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    anthropic_api_key: str = ""
    environment: str = "development"
    max_upload_bytes: int = 32 * 1024 * 1024  # 32MB
    workos_api_key: str = ""
    workos_client_id: str = ""
    auto_provision_tenants: bool = True
    ingestion_workers: int = 3
    ingestion_timeout_seconds: int = 900
    reaper_threshold_minutes: int = 10
    max_retries: int = 3

    docai_processor_id: str = ""
    docai_location: str = "us"
    gcp_project_id: str = ""
    docai_batch_timeout_seconds: int = 1800
    max_signed_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5GB
    signed_url_expiry_hours: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
