"""Unit tests for authentication, key hashing, and authorization enforcement."""

import pytest
from app.core.security import hash_api_key, generate_api_key, verify_api_key
from tests.conftest import TEST_API_KEY_RAW


def test_api_key_generation_and_hashing():
    """Verify generated key structure, prefix, and 64-char SHA-256 hash."""
    raw, hashed, prefix = generate_api_key()

    assert raw.startswith("af_live_")
    assert len(raw) == 56
    assert len(hashed) == 64
    assert len(prefix) == 12
    assert prefix == raw[:12]
    assert verify_api_key(raw, hashed) is True
    assert verify_api_key("wrong_key", hashed) is False


@pytest.mark.asyncio
async def test_auth_missing_header_rejected(async_client):
    """Requests without X-API-Key header must be rejected with 401."""
    response = await async_client.post(
        "/api/v1/gateway/execute",
        json={"prompt": "Hello"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_auth_invalid_key_rejected(async_client):
    """Requests with non-existent API key must be rejected with 401."""
    response = await async_client.post(
        "/api/v1/gateway/execute",
        headers={"X-API-Key": "af_live_invalid_non_existent_key_000"},
        json={"prompt": "Hello"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_admin_endpoint_authorization(async_client):
    """Admin endpoints require valid X-Admin-Key header."""
    # 1. Missing header -> 403
    res_no_auth = await async_client.get("/api/v1/admin/keys")
    assert res_no_auth.status_code == 403

    # 2. Valid header -> 200
    res_auth = await async_client.get(
        "/api/v1/admin/keys",
        headers={"X-Admin-Key": "af_master_admin_secret_key_prod_2026"},
    )
    assert res_auth.status_code == 200
    assert isinstance(res_auth.json(), list)
