"""Configuration for the Search Service."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MeiliSearchConfig:
    """MeiliSearch connection configuration."""

    url: str = field(default_factory=lambda: os.getenv("MEILISEARCH_URL", "http://localhost:7700"))
    api_key: str = field(default_factory=lambda: os.getenv("MEILISEARCH_API_KEY", ""))
    documents_index: str = field(
        default_factory=lambda: os.getenv("MEILISEARCH_DOCUMENTS_INDEX", "documents")
    )
    files_index: str = field(
        default_factory=lambda: os.getenv("MEILISEARCH_FILES_INDEX", "files")
    )


@dataclass(frozen=True)
class OpenSearchConfig:
    """Amazon OpenSearch (Serverless or managed) connection configuration.

    Mirrors :class:`MeiliSearchConfig` so the two backends are interchangeable
    behind the ``SEARCH_BACKEND`` flag. ``endpoint`` is the collection endpoint
    (e.g. ``https://<id>.us-east-1.aoss.amazonaws.com`` for Serverless, or a
    ``http://host:9200`` OpenSearch node for a local stand-in). When
    ``serverless`` is true the client signs requests with SigV4 for the
    ``aoss`` service; otherwise it connects directly (optionally with basic
    auth for a self-managed node).
    """

    endpoint: str = field(default_factory=lambda: os.getenv("OPENSEARCH_ENDPOINT", "http://localhost:9200"))
    region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    serverless: bool = field(
        default_factory=lambda: os.getenv("OPENSEARCH_SERVERLESS", "false").lower() == "true"
    )
    username: str = field(default_factory=lambda: os.getenv("OPENSEARCH_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD", ""))
    documents_index: str = field(
        default_factory=lambda: os.getenv("OPENSEARCH_DOCUMENTS_INDEX", "documents")
    )
    files_index: str = field(
        default_factory=lambda: os.getenv("OPENSEARCH_FILES_INDEX", "files")
    )


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
class AuthConfig:
    """Authentication configuration for the search service."""

    service_token: str = field(
        default_factory=lambda: os.getenv("SEARCH_SERVICE_TOKEN", "")
    )
    require_auth: bool = field(
        default_factory=lambda: os.getenv("REQUIRE_AUTH", "true").lower() == "true"
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
    # Selects the search backend adapter. "meilisearch" (default, the golden
    # before-state) or "opensearch" (Amazon OpenSearch Serverless / managed).
    search_backend: str = field(
        default_factory=lambda: os.getenv("SEARCH_BACKEND", "meilisearch").lower()
    )
    meilisearch: MeiliSearchConfig = field(default_factory=MeiliSearchConfig)
    opensearch: OpenSearchConfig = field(default_factory=OpenSearchConfig)
    sqs: SQSConfig = field(default_factory=SQSConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
