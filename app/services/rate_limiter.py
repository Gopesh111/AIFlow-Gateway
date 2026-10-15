"""Distributed Token-Bucket Rate Limiter utilizing atomic Redis Lua scripts."""

import time
from typing import Dict, Any, Tuple
from redis.asyncio import Redis

from app.config import settings
from app.core.exceptions import RateLimitExceededException
from app.core.logger import get_logger

logger = get_logger("aiflow.rate_limiter")

# Atomic Token-Bucket Lua Script
# Guarantees thread-safe, race-condition-free token refill and consumption in Redis memory.
TOKEN_BUCKET_LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

-- Fetch current bucket state
local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if not tokens or not last_refill then
    -- Cold bucket initialization
    tokens = capacity
    last_refill = now
else
    -- Replenish tokens based on delta time
    local delta = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + (delta * refill_rate))
    last_refill = now
end

local allowed = 0
local retry_after = 0

if tokens >= requested then
    allowed = 1
    tokens = tokens - requested
else
    allowed = 0
    local missing = requested - tokens
    retry_after = math.ceil(missing / refill_rate)
end

-- Save updated state atomically
redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
redis.call('EXPIRE', key, ttl)

return {allowed, math.floor(tokens), retry_after}
"""


class RedisTokenBucketRateLimiter:
    """Atomic distributed token-bucket rate limiter backed by Redis."""

    def __init__(self, redis: Redis) -> None:
        """Initialize rate limiter with Redis client instance."""
        self.redis = redis
        self._script = None

    async def _get_script(self):
        """Register or retrieve cached Lua script SHA."""
        if self._script is None:
            self._script = self.redis.register_script(TOKEN_BUCKET_LUA_SCRIPT)
        return self._script

    async def evaluate(
        self,
        identifier: str,
        limit_rpm: int,
        cost: int = 1,
    ) -> Dict[str, Any]:
        """Evaluate rate limit for a specific API Key or client identifier.

        Args:
            identifier: Unique client ID (e.g., API key ID or IP address).
            limit_rpm: Configured requests-per-minute quota.
            cost: Token cost of the operation (default 1).

        Returns:
            Dictionary containing:
                - allowed: bool
                - limit: int
                - remaining: int
                - retry_after: int

        Raises:
            RateLimitExceededException: If the token bucket is exhausted.
        """
        redis_key = f"rate_limit:{identifier}"
        capacity = int(limit_rpm * settings.RATE_LIMIT_BURST_MULTIPLIER)
        refill_rate = float(limit_rpm) / 60.0  # Tokens replenished per second
        now = time.time()
        # TTL ensures stale rate limit buckets are purged when idle
        ttl = max(int(capacity / refill_rate) * 2, 60)

        script = await self._get_script()
        res = await script(
            keys=[redis_key],
            args=[capacity, refill_rate, now, cost, ttl],
        )

        allowed_flag = int(res[0])
        remaining_tokens = int(res[1])
        retry_after = int(res[2])

        is_allowed = allowed_flag == 1

        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded for key {identifier}: remaining={remaining_tokens}, retry_after={retry_after}s"
            )
            raise RateLimitExceededException(
                message=f"Rate limit exceeded. Quota: {limit_rpm} RPM. Try again in {retry_after} seconds.",
                limit=limit_rpm,
                remaining=remaining_tokens,
                retry_after=retry_after,
            )

        return {
            "allowed": True,
            "limit": limit_rpm,
            "remaining": remaining_tokens,
            "retry_after": 0,
        }
