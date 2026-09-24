"""Runtime feature/chaos flags backed by the tenant's Redis."""

import os

import redis as redis_lib

_redis_client: redis_lib.Redis | None = None

FLAG_SLOW_QUERIES = "chaos:document-service:slow_queries"
FLAG_REQUEST_LOG = "chaos:document-service:request_log"
FLAG_RENDER_CACHE = "chaos:document-service:render_cache"


def get_redis() -> redis_lib.Redis:
    """Return a shared Redis client (lazy-initialised)."""
    global _redis_client
    if _redis_client is None:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        _redis_client = redis_lib.Redis(
            host=host, port=port, decode_responses=True, socket_timeout=1,
        )
    return _redis_client


def flag_active(key: str) -> bool:
    """Return True if the given flag is set in Redis."""
    try:
        return bool(get_redis().exists(key))
    except Exception:
        return False
