"""Unit tests for exact hash lookups and semantic caching."""

import pytest
from app.services.semantic_cache import (
    SemanticCacheService,
    compute_sha256,
    cosine_similarity,
)
import numpy as np


def test_compute_sha256_normalization():
    """Verify text whitespace and casing normalization."""
    hash1 = compute_sha256("  What is Raft Consensus?  ")
    hash2 = compute_sha256("what   is raft consensus? ")
    assert hash1 == hash2


def test_cosine_similarity_calculation():
    """Verify cosine similarity calculation between identical and orthogonal vectors."""
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    assert pytest.approx(cosine_similarity(v1, v2), 1e-4) == 1.0
    assert pytest.approx(cosine_similarity(v1, v3), 1e-4) == 0.0


@pytest.mark.asyncio
async def test_exact_cache_hit_and_miss(mock_redis):
    """Verify cache miss on cold prompt, and exact cache hit after storing."""
    cache = SemanticCacheService(mock_redis)
    prompt = "Explain distributed two-phase commit."
    sample_response = {
        "id": "chatcmpl-test1234",
        "content": "Two-phase commit is an atomic commitment protocol.",
        "usage": {"total_tokens": 42},
    }

    # 1. First lookup: Cold cache miss
    cached_val, cache_type = await cache.get(prompt)
    assert cached_val is None
    assert cache_type is None

    # 2. Store response
    await cache.set(prompt, sample_response, ttl=3600)

    # 3. Second lookup: Exact cache hit
    cached_val, cache_type = await cache.get(prompt)
    assert cached_val is not None
    assert cached_val["id"] == "chatcmpl-test1234"
    assert cache_type == "exact"
