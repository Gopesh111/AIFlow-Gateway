"""FastAPI application entrypoint, middleware stack, and lifecycle management."""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.logger import setup_logging, get_logger, request_id_context
from app.core.exceptions import register_exception_handlers
from app.db.session import async_engine
from app.services.redis_client import init_redis_pool, close_redis_pool
from app.api.v1 import v1_router

# Initialize structured logging
setup_logging(level="DEBUG" if settings.DEBUG else "INFO")
logger = get_logger("aiflow.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: initialize Redis connection pool and manage graceful shutdown."""
    logger.info(f"Starting {settings.PROJECT_NAME} in '{settings.ENVIRONMENT}' mode...")
    init_redis_pool()
    yield
    logger.info("Initiating graceful shutdown...")
    await close_redis_pool()
    await async_engine.dispose()
    logger.info("All connections cleanly closed.")


app = FastAPI(
    title="AIFlow-Gateway",
    description="High-Throughput Async API Gateway & Semantic Caching Reverse Proxy for AI Microservices",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Custom Domain Exception Handlers
register_exception_handlers(app)


# Request Correlation & Timing Middleware
@app.middleware("http")
async def correlation_and_timing_middleware(request: Request, call_next):
    """Inject or propagate X-Request-ID and measure request execution latency."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    token = request_id_context.set(req_id)
    t0 = time.perf_counter()

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        logger.exception(f"Unhandled exception during HTTP request processing: {exc}")
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Internal gateway failure.",
                    "request_id": req_id,
                }
            },
        )
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Gateway-Latency-Ms"] = f"{duration_ms:.2f}"
        request_id_context.reset(token)

    return response


# Include Versioned API Routes
app.include_router(v1_router)


@app.get("/", tags=["Root"])
async def root_index() -> dict:
    """Gateway landing probe."""
    return {
        "service": "AIFlow-Gateway",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
    }
