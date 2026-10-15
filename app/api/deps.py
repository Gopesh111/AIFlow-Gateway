"""FastAPI dependency injection: Authentication, Database sessions, and Services."""

import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional, Dict, Any

from fastapi import Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.config import settings
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
)
from app.core.security import hash_api_key
from app.db.session import get_db
from app.db.models import ApiKey, User
from app.services.redis_client import get_redis
from app.services.rate_limiter import RedisTokenBucketRateLimiter
from app.services.semantic_cache import SemanticCacheService
from app.services.mock_upstream import MockUpstreamService


async def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RedisTokenBucketRateLimiter:
    """Provide Redis token-bucket rate limiter."""
    return RedisTokenBucketRateLimiter(redis)


async def get_semantic_cache(redis: Redis = Depends(get_redis)) -> SemanticCacheService:
    """Provide semantic caching service."""
    return SemanticCacheService(redis)


async def get_upstream_service() -> MockUpstreamService:
    """Provide mock upstream LLM service."""
    return MockUpstreamService()


async def validate_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ApiKey:
    """Validate incoming client API Key with fast Redis cache lookup and DB fallback.

    Args:
        x_api_key: Value passed in X-API-Key request header.
        db: Async database session.
        redis: Async Redis connection.

    Returns:
        Validated ApiKey model instance.

    Raises:
        AuthenticationException: If key is missing or invalid.
        AuthorizationException: If key is revoked or expired.
    """
    if not x_api_key:
        raise AuthenticationException("Missing 'X-API-Key' authentication header.")

    key_hash = hash_api_key(x_api_key)
    redis_cache_key = f"auth:key:{key_hash}"

    # Fast-path: Check Redis auth cache (<2ms)
    try:
        cached_auth = await redis.get(redis_cache_key)
        if cached_auth:
            data = json.loads(cached_auth)
            if data.get("is_revoked"):
                raise AuthorizationException("API key has been revoked.")

            # Create transient ApiKey instance from cached payload
            api_key = ApiKey(
                id=data["id"],
                user_id=data["user_id"],
                hashed_key=key_hash,
                key_prefix=data["key_prefix"],
                name=data["name"],
                rate_limit_rpm=data["rate_limit_rpm"],
                is_revoked=data["is_revoked"],
            )
            return api_key
    except (AuthenticationException, AuthorizationException):
        raise
    except Exception:
        # On Redis read error, seamlessly fall through to PostgreSQL query
        pass

    # Slow-path: Query PostgreSQL database
    query = select(ApiKey).where(ApiKey.hashed_key == key_hash)
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise AuthenticationException("Invalid API key provided.")

    if api_key.is_revoked:
        raise AuthorizationException("API key has been revoked.")

    if api_key.expires_at:
        now = datetime.now(timezone.utc)
        if api_key.expires_at < now:
            raise AuthorizationException("API key has expired.")

    # Populate Redis auth cache with 300s TTL
    try:
        cache_data = {
            "id": str(api_key.id),
            "user_id": str(api_key.user_id),
            "key_prefix": api_key.key_prefix,
            "name": api_key.name,
            "rate_limit_rpm": api_key.rate_limit_rpm,
            "is_revoked": api_key.is_revoked,
        }
        await redis.set(redis_cache_key, json.dumps(cache_data), ex=300)
    except Exception:
        pass

    return api_key


async def validate_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Validate master administrative key for key provisioning and management."""
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise AuthorizationException("Unauthorized administrative access. Invalid X-Admin-Key.")
    return True
