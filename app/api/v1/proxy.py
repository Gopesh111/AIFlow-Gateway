"""Core Gateway reverse proxy endpoint with distributed rate limiting and semantic caching."""

import time
import uuid
from typing import Dict, Any
from fastapi import APIRouter, Depends, Response, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.gateway import ProxyRequest, ProxyResponse, TokenUsage, CacheStatus
from app.db.models import ApiKey, RequestLog
from app.db.session import async_session_factory
from app.core.logger import get_logger, request_id_context
from app.services.rate_limiter import RedisTokenBucketRateLimiter
from app.services.semantic_cache import SemanticCacheService
from app.services.mock_upstream import MockUpstreamService
from app.api.deps import (
    validate_api_key,
    get_rate_limiter,
    get_semantic_cache,
    get_upstream_service,
)

logger = get_logger("aiflow.proxy")
router = APIRouter(prefix="/gateway")


async def record_audit_log_background(
    api_key_id: uuid.UUID,
    endpoint: str,
    status_code: int,
    latency_ms: float,
    cache_hit: bool,
    tokens_used: int,
) -> None:
    """Asynchronous background worker persisting audit logs without blocking the response path."""
    try:
        async with async_session_factory() as session:
            log_entry = RequestLog(
                api_key_id=api_key_id,
                endpoint=endpoint,
                status_code=status_code,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
                tokens_used=tokens_used,
            )
            session.add(log_entry)
            await session.commit()
    except Exception as exc:
        logger.error(f"Failed to record background audit log: {exc}")


@router.post(
    "/execute",
    response_model=ProxyResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute proxy completion with rate limiting and semantic caching",
)
async def execute_proxy_request(
    payload: ProxyRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    api_key: ApiKey = Depends(validate_api_key),
    rate_limiter: RedisTokenBucketRateLimiter = Depends(get_rate_limiter),
    semantic_cache: SemanticCacheService = Depends(get_semantic_cache),
    upstream: MockUpstreamService = Depends(get_upstream_service),
) -> ProxyResponse:
    """Handle incoming client inference request.

    Orchestration Sequence:
      1. Rate Limit Enforcement: Atomic Redis Lua token bucket check.
      2. Cache-Aside Interception: Exact SHA-256 and vector similarity lookup.
      3. Upstream Forwarding (On Cache Miss): Simulated non-blocking LLM execution.
      4. Asynchronous Cache Population: Populate Redis cache with 3600s TTL.
      5. Decoupled Audit Logging: Dispatch non-blocking background write to PostgreSQL.
      6. Header Telemetry: Inject X-Request-ID, X-Cache, X-Latency-Ms, X-RateLimit-Remaining.
    """
    start_time = time.perf_counter()
    req_id = request_id_context.get()

    # Step 1: Enforce atomic rate limit
    rate_result = await rate_limiter.evaluate(
        identifier=str(api_key.id),
        limit_rpm=api_key.rate_limit_rpm,
        cost=1,
    )
    remaining_tokens = rate_result["remaining"]

    # Step 2: Check semantic cache
    cached_data, cache_type = await semantic_cache.get(payload.prompt)

    if cached_data is not None:
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Inject telemetry headers
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Cache"] = CacheStatus.HIT.value
        response.headers["X-Cache-Type"] = cache_type or "exact"
        response.headers["X-Latency-Ms"] = f"{latency_ms:.2f}"
        response.headers["X-RateLimit-Limit"] = str(api_key.rate_limit_rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining_tokens)

        # Dispatch async background audit logging
        background_tasks.add_task(
            record_audit_log_background,
            api_key_id=api_key.id,
            endpoint="/api/v1/gateway/execute",
            status_code=200,
            latency_ms=latency_ms,
            cache_hit=True,
            tokens_used=cached_data.get("usage", {}).get("total_tokens", 0),
        )

        return ProxyResponse(
            id=cached_data["id"],
            model=cached_data.get("model", payload.model),
            content=cached_data["content"],
            usage=TokenUsage(**cached_data["usage"]),
            cached=True,
            cache_type=cache_type,
            latency_ms=round(latency_ms, 2),
        )

    # Step 3: Cache Miss - Forward to upstream service
    upstream_result = await upstream.execute(
        prompt=payload.prompt,
        model=payload.model,
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
    )

    # Step 4: Populate cache asynchronously
    background_tasks.add_task(
        semantic_cache.set,
        prompt=payload.prompt,
        response_data=upstream_result,
    )

    latency_ms = (time.perf_counter() - start_time) * 1000.0

    # Inject telemetry headers
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Cache"] = CacheStatus.MISS.value
    response.headers["X-Latency-Ms"] = f"{latency_ms:.2f}"
    response.headers["X-RateLimit-Limit"] = str(api_key.rate_limit_rpm)
    response.headers["X-RateLimit-Remaining"] = str(remaining_tokens)

    # Step 5: Dispatch async background audit logging
    background_tasks.add_task(
        record_audit_log_background,
        api_key_id=api_key.id,
        endpoint="/api/v1/gateway/execute",
        status_code=200,
        latency_ms=latency_ms,
        cache_hit=False,
        tokens_used=upstream_result["usage"]["total_tokens"],
    )

    return ProxyResponse(
        id=upstream_result["id"],
        model=upstream_result["model"],
        content=upstream_result["content"],
        usage=TokenUsage(**upstream_result["usage"]),
        cached=False,
        cache_type=None,
        latency_ms=round(latency_ms, 2),
    )
