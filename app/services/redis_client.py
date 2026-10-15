"""Asynchronous Redis connection pooling and client management."""

from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from redis.asyncio import Redis, ConnectionPool

from app.config import settings
from app.core.logger import get_logger

logger = get_logger("aiflow.redis")

# Global Connection Pool
redis_pool: Optional[ConnectionPool] = None


def init_redis_pool() -> ConnectionPool:
    """Initialize Redis connection pool."""
    global redis_pool
    if redis_pool is None:
        logger.info(f"Connecting to Redis at {settings.REDIS_URL} (max_connections={settings.REDIS_POOL_SIZE})")
        redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_POOL_SIZE,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return redis_pool


async def close_redis_pool() -> None:
    """Gracefully disconnect and release all connections in pool."""
    global redis_pool
    if redis_pool is not None:
        logger.info("Closing Redis connection pool.")
        await redis_pool.disconnect()
        redis_pool = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Dependency injection yielding an active async Redis client instance."""
    pool = redis_pool or init_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()


async def check_redis_health() -> bool:
    """Perform PING health check against Redis server."""
    try:
        pool = redis_pool or init_redis_pool()
        client = Redis(connection_pool=pool)
        pong = await client.ping()
        await client.close()
        return bool(pong)
    except Exception as exc:
        logger.error(f"Redis health check failed: {exc}")
        return False
