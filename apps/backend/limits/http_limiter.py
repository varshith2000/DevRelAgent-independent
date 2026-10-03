"""HTTP edge rate limiting.

A coarse, always-on limit that sits in front of every endpoint, complementing
the finer-grained tool/action limits enforced deeper in the stack. Counters
live in the shared state backend, so all replicas share one budget, and keys
are scoped by project (when the caller sends ``X-Project-Id`` /
``X-Project-Slug``) and by identity (API key, bearer token, dev user or IP).

This is a *pure ASGI* middleware on purpose: it never buffers the response
body, so it cannot break the SSE streaming endpoints the way a
``BaseHTTPMiddleware`` wrapper can.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict

from config.settings import get_settings
from shared.state import get_shared_state, scoped_key
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


def _lower_headers(scope: Scope) -> Dict[str, str]:
    """Flatten the raw ASGI headers into a lowercase-keyed dict."""
    headers: Dict[str, str] = {}
    for key, value in scope.get("headers", []):
        headers[key.decode("latin-1").lower()] = value.decode("latin-1")
    return headers


def client_identity(scope: Scope) -> str:
    """Derive a stable, non-secret identity for rate-limit bucketing.

    Raw credentials are never used as keys; bearer tokens are hashed and API
    keys are truncated so nothing sensitive lands in the shared store.
    """
    headers = _lower_headers(scope)

    api_key = headers.get("x-api-key")
    authorization = headers.get("authorization")
    dev_user = headers.get("x-dev-user-email")

    if api_key:
        ident = f"key:{api_key[:12]}"
    elif authorization:
        digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:16]
        ident = f"auth:{digest}"
    elif dev_user:
        ident = f"user:{dev_user}"
    else:
        client = scope.get("client")
        host = client[0] if client else "unknown"
        ident = f"ip:{host}"

    project = headers.get("x-project-id") or headers.get("x-project-slug") or ""
    return scoped_key(project, ident)


class HttpRateLimitMiddleware:
    """Reject requests that exceed the shared edge budget with ``429``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        if not settings.http_rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in set(settings.http_rate_limit_exempt_list) or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        limit = max(1, settings.http_rate_limit_requests)
        window = max(1, settings.http_rate_limit_window_seconds)
        key = scoped_key("http", client_identity(scope))

        try:
            count = get_shared_state().record(key, window)
        except Exception as exc:  # never let limiter outages take the API down
            logger.warning("HTTP rate limiter unavailable (%s); allowing request", exc)
            await self.app(scope, receive, send)
            return

        remaining = max(0, limit - count)

        if count > limit:
            response = JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=429,
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-ratelimit-limit", str(limit).encode("latin-1")))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


def install_http_rate_limit(app: ASGIApp) -> None:
    """Attach the limiter to a FastAPI/Starlette app."""
    app.add_middleware(HttpRateLimitMiddleware)  # type: ignore[attr-defined]


__all__ = ["HttpRateLimitMiddleware", "client_identity", "install_http_rate_limit"]
