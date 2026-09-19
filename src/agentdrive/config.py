# src/agentdrive/config.py
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive"
    s3_bucket: str = Field(default="", validation_alias=AliasChoices("S3_BUCKET", "AWS_S3_BUCKET_NAME"))
    s3_endpoint_url: str = Field(default="", validation_alias=AliasChoices("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL"))
    s3_access_key_id: str = Field(default="", validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"))
    s3_secret_access_key: str = Field(default="", validation_alias=AliasChoices("S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"))
    s3_region: str = Field(default="auto", validation_alias=AliasChoices("S3_REGION", "AWS_DEFAULT_REGION"))
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    enrichment_api_key: str = ""
    enrichment_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    enrichment_model: str = "gemini-3.6-flash"
    environment: str = "development"
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


settings = Settings()
