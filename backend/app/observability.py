"""Request IDs and JSON request logs."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id", "method", "path", "status_code", "duration_ms",
            "inference_ms", "source", "degraded",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("iomido")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False


async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    response.headers["X-Request-ID"] = request_id
    logging.getLogger("iomido").info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response
