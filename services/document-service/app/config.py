"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "document-service"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = (
        "postgresql+asyncpg://otterworks:otterworks_dev@localhost:5432/otterworks"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Aurora Serverless v2 resilience (scale-to-zero resume). pre_ping validates
    # a pooled connection before use (drops stale connections after a resume);
    # pool_recycle bounds connection age. connect_retries retries the initial
    # connect so init_db() survives a paused cluster waking up. Defaults are safe
    # for the RDS before-state; deploy-dev.sh raises retries when DB_BACKEND=aurora.
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 1800
    db_connect_retries: int = 0
    db_connect_retry_interval: float = 2.0

    sns_topic_arn: str = ""
    aws_endpoint_url: str = ""
    aws_region: str = "us-east-1"
    sns_enabled: bool = False

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_enabled: bool = False

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:4200"]

    model_config = {"env_prefix": "DOC_SVC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
