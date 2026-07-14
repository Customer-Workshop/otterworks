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

    sns_topic_arn: str = ""
    aws_endpoint_url: str = ""
    aws_region: str = "us-east-1"
    sns_enabled: bool = False

    # Event delivery backend: "sns" (default, in-cluster consumer path on main)
    # or "eventbridge" (serverless EventBridge -> SQS -> Lambda path). Selecting
    # eventbridge only changes the transport; the message content is identical.
    event_backend: str = "sns"
    eventbridge_bus_name: str = ""
    eventbridge_source: str = "otterworks.document-service"

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_enabled: bool = False

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:4200"]

    model_config = {"env_prefix": "DOC_SVC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
