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

    # Aurora IAM authentication + TLS (opt-in; defaults preserve the RDS path).
    # When db_iam_auth_enabled is true the static password in database_url is
    # ignored in favour of a short-lived RDS IAM token; TLS is controlled by
    # db_ssl_mode (e.g. "require", "verify-full").
    db_iam_auth_enabled: bool = False
    db_ssl_mode: str = ""
    db_ssl_root_cert: str = ""
    db_iam_region: str = ""

    sns_topic_arn: str = ""
    aws_endpoint_url: str = ""
    aws_region: str = "us-east-1"
    sns_enabled: bool = False

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_enabled: bool = False

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:4200"]

    model_config = {"env_prefix": "DOC_SVC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
