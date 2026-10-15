"""Structured JSON logging with X-Request-ID correlation tracking."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict

# Context variable holding correlation ID across asynchronous task boundaries
request_id_context: ContextVar[str] = ContextVar("request_id_context", default="system")


class JSONFormatter(logging.Formatter):
    """Custom logging formatter outputting single-line JSON records."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_context.get(),
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_logging(level: str = "INFO") -> None:
    """Initialize structured JSON logging for standard library loggers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(stream_handler)

    # Reduce verbosity of third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retrieve named logger."""
    return logging.getLogger(name)
