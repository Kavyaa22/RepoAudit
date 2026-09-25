"""Request ID / timing middleware."""

from __future__ import annotations

import asyncio
import time
import uuid

from starlette.datastructures import MutableHeaders

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware:
    """Pure ASGI middleware for adding timing and request ID headers cleanly without BaseHTTPMiddleware stream cancellation errors."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request ID from headers
        headers_dict = dict(scope.get("headers", []))
        raw_req_id = headers_dict.get(b"x-request-id", b"")
        request_id = raw_req_id.decode("latin1") if raw_req_id else str(uuid.uuid4())
        start = time.perf_counter()

        async def send_wrapper(message: dict) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = request_id
                elapsed_ms = (time.perf_counter() - start) * 1000
                headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
                logger.debug(
                    "%s %s -> %s (%.1fms) [%s]",
                    scope.get("method"),
                    scope.get("path"),
                    message.get("status"),
                    elapsed_ms,
                    request_id,
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except (asyncio.CancelledError, KeyboardInterrupt):
            # Gracefully handle server shutdown or client disconnection
            pass

