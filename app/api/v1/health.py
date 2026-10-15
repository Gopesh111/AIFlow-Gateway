"""Health and diagnostics probe endpoint."""

import time
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, status, Response

from app.db.session import check_db_health
from app.services.redis_client import check_redis_health

router = APIRouter()

START_TIME = time.time()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check probe for Gateway, PostgreSQL, and Redis",
)
async def health_check(response: Response) -> Dict[str, Any]:
    """Inspect system health and dependency availability.

    Returns 200 OK when healthy, 503 SERVICE UNAVAILABLE if Postgres or Redis is down.
    """
    db_alive = await check_db_health()
    redis_alive = await check_redis_health()

    is_healthy = db_alive and redis_alive

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    uptime_seconds = int(time.time() - START_TIME)

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "AIFlow-Gateway",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_seconds,
        "dependencies": {
            "postgresql": "up" if db_alive else "down",
            "redis": "up" if redis_alive else "down",
        },
    }
