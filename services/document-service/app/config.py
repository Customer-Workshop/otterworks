"""Application configuration via pydantic-settings."""

import os
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "document-service"
    app_version: str = "0.1.0"
    debug: bool = False

    # When DOC_SVC_DATABASE_URL is set it overrides this entirely. Otherwise the
    # URL is assembled at instantiation time (see _default_database_url) so the
    # password is read from the environment then — never baked in as a literal.
    database_url: str = ""
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

    @model_validator(mode="after")
    def _default_database_url(self) -> "Settings":
        if not self.database_url:
            password = quote(os.environ.get("POSTGRES_PASSWORD", "otterworks_dev"), safe="")
            self.database_url = (
                f"postgresql+asyncpg://otterworks:{password}@localhost:5432/otterworks"
            )
        return self


settings = Settings()
