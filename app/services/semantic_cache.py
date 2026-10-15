"""Semantic Caching Engine: Exact SHA-256 hash lookups and dense vector similarity."""

import json
import hashlib
from typing import Optional, Dict, Any, Tuple, List
import numpy as np
from redis.asyncio import Redis

from app.config import settings
from app.core.logger import get_logger

logger = get_logger("aiflow.semantic_cache")

# Lazy-loaded embedding model singleton
_embedding_model = None


def get_embedding_model():
    """Lazy load sentence-transformers model to optimize startup time."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL_NAME}")
            _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        except Exception as exc:
            logger.warning(f"Could not load SentenceTransformer ({exc}). Semantic similarity will fall back to exact hash.")
            _embedding_model = False
    return _embedding_model


def compute_sha256(text: str) -> str:
    """Compute normalized SHA-256 digest of input text."""
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two 1D vectors."""
    dot = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))


class SemanticCacheService:
    """Cache-aside proxy cache combining exact hash lookups and semantic vector matching."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.ttl = settings.SEMANTIC_CACHE_TTL_SECONDS
        self.threshold = settings.SEMANTIC_CACHE_SIMILARITY_THRESHOLD
        self.enabled = settings.SEMANTIC_CACHE_ENABLED

    async def get(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Look up cached response for a prompt.

        Args:
            prompt: User prompt text.

        Returns:
            Tuple of (cached_payload, cache_type) where cache_type is 'exact', 'semantic', or None.
        """
        if not self.enabled:
            return None, None

        prompt_hash = compute_sha256(prompt)

        # 1. Exact Cache Lookup (O(1), <2ms)
        exact_key = f"cache:exact:{prompt_hash}"
        try:
            exact_val = await self.redis.get(exact_key)
            if exact_val:
                logger.info(f"Cache HIT [Exact]: {prompt_hash[:12]}")
                payload = json.loads(exact_val)
                return payload, "exact"
        except Exception as exc:
            logger.warning(f"Redis exact cache read error: {exc}")

        # 2. Semantic Cache Lookup (Vector Similarity)
        model = get_embedding_model()
        if not model:
            return None, None

        try:
            # Generate query embedding
            query_embedding = model.encode(prompt, convert_to_numpy=True)

            # Retrieve active semantic keys
            semantic_index_key = "cache:semantic:index"
            candidate_hashes = await self.redis.smembers(semantic_index_key)

            if not candidate_hashes:
                return None, None

            best_similarity = -1.0
            best_payload = None

            # Scan semantic candidate embeddings
            for cand_hash in candidate_hashes:
                meta_key = f"cache:semantic:{cand_hash}"
                raw_data = await self.redis.get(meta_key)
                if not raw_data:
                    # Clean up expired index reference
                    await self.redis.srem(semantic_index_key, cand_hash)
                    continue

                entry = json.loads(raw_data)
                stored_vec = np.array(entry["embedding"], dtype=np.float32)

                sim = cosine_similarity(query_embedding, stored_vec)
                if sim > best_similarity:
                    best_similarity = sim
                    best_payload = entry["response"]

            if best_similarity >= self.threshold and best_payload is not None:
                logger.info(f"Cache HIT [Semantic: {best_similarity:.4f} >= {self.threshold}]")
                return best_payload, "semantic"

        except Exception as exc:
            logger.warning(f"Semantic cache lookup failure: {exc}")

        return None, None

    async def set(
        self,
        prompt: str,
        response_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """Store query and upstream response in both exact and semantic caches.

        Args:
            prompt: User prompt text.
            response_data: Upstream response payload to persist.
            ttl: Optional TTL override in seconds.
        """
        if not self.enabled:
            return

        cache_ttl = ttl or self.ttl
        prompt_hash = compute_sha256(prompt)
        exact_key = f"cache:exact:{prompt_hash}"

        try:
            # Store exact cache entry
            await self.redis.set(exact_key, json.dumps(response_data), ex=cache_ttl)

            # Store semantic embedding entry
            model = get_embedding_model()
            if model:
                embedding = model.encode(prompt, convert_to_numpy=True).tolist()
                semantic_meta_key = f"cache:semantic:{prompt_hash}"
                semantic_payload = {
                    "prompt": prompt,
                    "embedding": embedding,
                    "response": response_data,
                }
                await self.redis.set(semantic_meta_key, json.dumps(semantic_payload), ex=cache_ttl)
                await self.redis.sadd("cache:semantic:index", prompt_hash)
                # Keep index TTL aligned
                await self.redis.expire("cache:semantic:index", cache_ttl)

        except Exception as exc:
            logger.warning(f"Failed to persist entry to Redis cache: {exc}")
