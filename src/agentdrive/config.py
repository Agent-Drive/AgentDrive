# src/agentdrive/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive"
    gcs_bucket: str = "agentdrive-files"
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    enrichment_api_key: str = ""
    enrichment_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    enrichment_model: str = "gemini-2.5-flash"
    environment: str = "development"
    max_upload_bytes: int = 32 * 1024 * 1024  # 32MB
    workos_api_key: str = ""
    workos_client_id: str = ""
    auto_provision_tenants: bool = True
    ingestion_workers: int = 3
    ingestion_timeout_seconds: int = 900
    reaper_threshold_minutes: int = 10
    max_retries: int = 3

    docai_processor_id: str = "56e834cb46b24724"
    docai_location: str = "us"
    gcp_project_id: str = "agent-drive-491013"
    docai_batch_timeout_seconds: int = 1800
    max_signed_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5GB
    signed_url_expiry_hours: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
