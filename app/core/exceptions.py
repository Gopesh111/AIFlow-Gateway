"""Domain exception hierarchy and centralized FastAPI error handlers."""

from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.logger import request_id_context, get_logger

logger = get_logger("aiflow.exceptions")


class AIFlowException(Exception):
    """Base exception for all domain-specific errors in AIFlow-Gateway."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_SERVER_ERROR",
        headers: Optional[Dict[str, str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.headers = headers or {}
        self.details = details or {}


class RateLimitExceededException(AIFlowException):
    """Raised when an API Key exhausts its token bucket quota."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please throttle your requests.",
        limit: int = 60,
        remaining: int = 0,
        retry_after: int = 60,
    ) -> None:
        headers = {
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
        }
        details = {
            "limit": limit,
            "remaining": remaining,
            "retry_after_seconds": retry_after,
        }
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMIT_EXCEEDED",
            headers=headers,
            details=details,
        )


class AuthenticationException(AIFlowException):
    """Raised when an API key or bearer token is invalid or missing."""

    def __init__(self, message: str = "Invalid or missing authentication credentials.") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTHENTICATION_FAILED",
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationException(AIFlowException):
    """Raised when an API key is revoked, expired, or unauthorized."""

    def __init__(self, message: str = "API Key is revoked or unauthorized for this operation.") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTHORIZATION_FAILED",
        )


class ResourceNotFoundException(AIFlowException):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "The requested resource was not found.") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
        )


class UpstreamServiceException(AIFlowException):
    """Raised when upstream LLM or backend microservice times out or fails."""

    def __init__(self, message: str = "Upstream service failure or timeout.") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_SERVICE_ERROR",
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform structured error response handlers."""

    @app.exception_handler(AIFlowException)
    async def aiflow_exception_handler(request: Request, exc: AIFlowException) -> JSONResponse:
        req_id = request_id_context.get()
        logger.warning(
            f"Domain exception: {exc.code} - {exc.message} [Request-ID: {req_id}]"
        )
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": req_id,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = request_id_context.get()
        logger.warning(f"Request schema validation failed: {exc.errors()} [Request-ID: {req_id}]")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request parameters or payload structure.",
                    "request_id": req_id,
                    "details": {"validation_errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = request_id_context.get()
        logger.exception(f"Unhandled server error: {str(exc)} [Request-ID: {req_id}]")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred while processing the request.",
                    "request_id": req_id,
                    "details": {},
                }
            },
        )
