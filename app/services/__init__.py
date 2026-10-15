"""Service layer for Redis connection pooling, distributed rate limiting, semantic caching, and upstream execution."""

from app.services.redis_client import (
    redis_pool,
    init_redis_pool,
    close_redis_pool,
    get_redis,
    check_redis_health,
)
from app.services.rate_limiter import RedisTokenBucketRateLimiter
from app.services.semantic_cache import SemanticCacheService
from app.services.mock_upstream import MockUpstreamService

__all__ = [
    "redis_pool",
    "init_redis_pool",
    "close_redis_pool",
    "get_redis",
    "check_redis_health",
    "RedisTokenBucketRateLimiter",
    "SemanticCacheService",
    "MockUpstreamService",
]
