"""Search backend factory."""

from app.config import AppConfig
from app.services.meilisearch_client import MeiliSearchService
from app.services.opensearch_client import OpenSearchService


def build_search_service(config: AppConfig) -> MeiliSearchService | OpenSearchService:
    """Build the configured search backend."""
    if config.search_backend == "opensearch":
        return OpenSearchService(config.opensearch)
    return MeiliSearchService(config.meilisearch)
