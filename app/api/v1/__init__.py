"""API Version 1 Routers."""

from fastapi import APIRouter
from app.api.v1.proxy import router as proxy_router
from app.api.v1.admin import router as admin_router
from app.api.v1.health import router as health_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router, tags=["Health"])
v1_router.include_router(proxy_router, tags=["Gateway Proxy"])
v1_router.include_router(admin_router, tags=["Admin"])

__all__ = ["v1_router"]
