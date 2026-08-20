"""Application configuration via pydantic-settings."""

import os

from pydantic_settings import BaseSettings

# Local-development default; override with POSTGRES_PASSWORD or DOC_SVC_DATABASE_URL.
_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "otterworks_dev")


class Settings(BaseSettings):
    app_name: str = "document-service"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = (
        f"postgresql+asyncpg://otterworks:{_DB_PASSWORD}@localhost:5432/otterworks"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    sns_topic_arn: str = ""
    aws_endpoint_url: str = ""
    aws_region: str = "us-east-1"
    sns_enabled: bool = False

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_enabled: bool = False

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:4200"]

    model_config = {"env_prefix": "DOC_SVC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
