# src/agentdrive/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive"
    gcs_bucket: str = "agentdrive-files"
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    environment: str = "development"
    max_upload_bytes: int = 32 * 1024 * 1024  # 32MB

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
