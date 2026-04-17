"""Configuration for the Search Service."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OpenSearchConfig:
    """OpenSearch connection configuration."""

    url: str = field(default_factory=lambda: os.getenv("OPENSEARCH_URL", "http://localhost:9200"))
    documents_index: str = field(
        default_factory=lambda: os.getenv("OPENSEARCH_DOCUMENTS_INDEX", "otterworks-documents")
    )
    files_index: str = field(
        default_factory=lambda: os.getenv("OPENSEARCH_FILES_INDEX", "otterworks-files")
    )
    use_ssl: bool = False
    verify_certs: bool = False
    request_timeout: int = 30


@dataclass(frozen=True)
class SQSConfig:
    """SQS consumer configuration."""

    queue_url: str = field(default_factory=lambda: os.getenv("SQS_QUEUE_URL", ""))
    region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    endpoint_url: str = field(default_factory=lambda: os.getenv("AWS_ENDPOINT_URL", ""))
    max_messages: int = 10
    wait_time_seconds: int = 20
    visibility_timeout: int = 60
    enabled: bool = field(
        default_factory=lambda: os.getenv("SQS_ENABLED", "false").lower() == "true"
    )


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    service_name: str = "search-service"
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8087")))
    debug: bool = field(
        default_factory=lambda: os.getenv("FLASK_DEBUG", "false").lower() == "true"
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    opensearch: OpenSearchConfig = field(default_factory=OpenSearchConfig)
    sqs: SQSConfig = field(default_factory=SQSConfig)
