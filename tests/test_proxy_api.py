"""Integration tests for the core Gateway reverse proxy endpoint."""

import pytest
from tests.conftest import TEST_API_KEY_RAW


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client):
    """Verify health endpoint probe."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AIFlow-Gateway"
    assert "dependencies" in data


@pytest.mark.asyncio
async def test_proxy_cold_and_warm_cache_lifecycle(async_client):
    """Verify Cold Miss -> Cache Set -> Warm Hit lifecycle with telemetry headers."""
    headers = {"X-API-Key": TEST_API_KEY_RAW}
    payload = {
        "prompt": "Explain the Paxos consensus algorithm in distributed systems.",
        "max_tokens": 128,
        "temperature": 0.7,
        "model": "gpt-4o-mini",
    }

    # 1. First execution: Cold cache miss
    res1 = await async_client.post("/api/v1/gateway/execute", headers=headers, json=payload)
    assert res1.status_code == 200
    data1 = res1.json()

    assert data1["cached"] is False
    assert data1["cache_type"] is None
    assert res1.headers.get("X-Cache") == "MISS"
    assert "X-Request-ID" in res1.headers
    assert "X-Latency-Ms" in res1.headers
    assert "X-RateLimit-Remaining" in res1.headers

    # 2. Second execution (identical prompt): Cache HIT
    res2 = await async_client.post("/api/v1/gateway/execute", headers=headers, json=payload)
    assert res2.status_code == 200
    data2 = res2.json()

    assert data2["cached"] is True
    assert data2["cache_type"] in ["exact", "semantic"]
    assert res2.headers.get("X-Cache") == "HIT"
    assert data2["content"] == data1["content"]


@pytest.mark.asyncio
async def test_proxy_rate_limit_enforcement(async_client, mock_redis):
    """Verify that exceeding rate limit returns 429 with Retry-After header."""
    headers = {"X-API-Key": TEST_API_KEY_RAW}
    payload = {"prompt": "Quick stress test prompt."}

    # The seeded test key has rate_limit_rpm = 60 (capacity = 72)
    # Perform 72 requests to exhaust capacity
    for _ in range(72):
        res = await async_client.post("/api/v1/gateway/execute", headers=headers, json=payload)
        assert res.status_code == 200

    # 73rd request must be blocked by rate limiter
    res_blocked = await async_client.post("/api/v1/gateway/execute", headers=headers, json=payload)
    assert res_blocked.status_code == 429
    assert res_blocked.headers.get("Retry-After") is not None
    assert res_blocked.headers.get("X-RateLimit-Remaining") == "0"
