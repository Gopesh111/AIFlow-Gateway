"""Unit tests for the Redis Lua distributed token-bucket rate limiter."""

import pytest
from app.services.rate_limiter import RedisTokenBucketRateLimiter
from app.core.exceptions import RateLimitExceededException


@pytest.mark.asyncio
async def test_rate_limiter_allows_under_quota(mock_redis):
    """Verify that requests within quota are permitted and tokens decrement."""
    limiter = RedisTokenBucketRateLimiter(mock_redis)
    key_id = "test_key_01"
    rpm = 60

    result = await limiter.evaluate(identifier=key_id, limit_rpm=rpm, cost=1)

    assert result["allowed"] is True
    assert result["limit"] == 60
    # Capacity is 60 * 1.2 = 72. After 1 request, remaining is 71
    assert result["remaining"] == 71
    assert result["retry_after"] == 0


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_exhausted(mock_redis):
    """Verify that exceeding token capacity raises RateLimitExceededException with retry_after."""
    limiter = RedisTokenBucketRateLimiter(mock_redis)
    key_id = "test_key_exhaust"
    rpm = 10  # Capacity: 12 tokens

    # Exhaust all 12 tokens
    for _ in range(12):
        res = await limiter.evaluate(identifier=key_id, limit_rpm=rpm, cost=1)
        assert res["allowed"] is True

    # 13th request must be rejected with 429
    with pytest.raises(RateLimitExceededException) as exc_info:
        await limiter.evaluate(identifier=key_id, limit_rpm=rpm, cost=1)

    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.code == "RATE_LIMIT_EXCEEDED"
    assert exc.headers["Retry-After"] is not None
    assert int(exc.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_rate_limiter_distinct_keys_isolation(mock_redis):
    """Verify that rate limits on one key do not impact another key."""
    limiter = RedisTokenBucketRateLimiter(mock_redis)
    key_a = "client_alpha"
    key_b = "client_beta"

    # Exhaust key_a (rpm=5 -> capacity=6)
    for _ in range(6):
        await limiter.evaluate(identifier=key_a, limit_rpm=5, cost=1)

    with pytest.raises(RateLimitExceededException):
        await limiter.evaluate(identifier=key_a, limit_rpm=5, cost=1)

    # key_b should still have full quota
    res_b = await limiter.evaluate(identifier=key_b, limit_rpm=5, cost=1)
    assert res_b["allowed"] is True
    assert res_b["remaining"] == 5
