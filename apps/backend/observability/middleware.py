"""Request observability middleware.

For every HTTP request this middleware:

* assigns (or honours) a request id and sets it on the logging context var,
* parses/creates W3C trace context and starts an ``http.server`` span,
* records request counters and a latency histogram, and
* echoes ``X-Request-Id`` and ``traceparent`` back on the response.

It is a pure ASGI middleware (no response buffering) so it stays safe in front
of the SSE streaming endpoints.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Dict, List, Optional, Tuple

from config.settings import get_settings
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from observability.logging import request_id_var, span_id_var, tenant_var, trace_id_var
from observability.metrics import get_metrics
from observability.tracing import format_traceparent, get_tracer, parse_traceparent

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX_ID_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_INT_RE = re.compile(r"\b\d+\b")

HTTP_REQUESTS = "devrel_http_requests_total"
HTTP_DURATION = "devrel_http_request_duration_seconds"
HTTP_IN_FLIGHT = "devrel_http_requests_in_flight"


def template_path(path: str) -> str:
    """Collapse high-cardinality path segments so metric labels stay bounded."""
    normalized = _UUID_RE.sub("{id}", path or "/")
    normalized = _HEX_ID_RE.sub("{id}", normalized)
    normalized = _INT_RE.sub("{id}", normalized)
    return normalized or "/"


def _lower_headers(scope: Scope) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key, value in scope.get("headers", []):
        headers[key.decode("latin-1").lower()] = value.decode("latin-1")
    return headers


class ObservabilityMiddleware:
    """Attach request/trace context and record HTTP metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        headers = _lower_headers(scope)

        request_id = headers.get("x-request-id") or uuid.uuid4().hex
        traceparent = parse_traceparent(headers.get("traceparent"))
        if traceparent is not None:
            trace_id, parent_span_id, _sampled = traceparent
        else:
            trace_id, parent_span_id = get_tracer().new_trace_id(), None

        method = scope.get("method", "-")
        path = scope.get("path", "/")
        project = headers.get("x-project-id") or headers.get("x-project-slug") or "-"

        tracer = get_tracer()
        span = tracer.start_span(
            "http.server",
            attributes={"http.method": method, "http.path": path},
            trace_id=trace_id,
            parent_span_id=parent_span_id,
        )

        tokens = [
            request_id_var.set(request_id),
            trace_id_var.set(trace_id),
            span_id_var.set(span.span_id),
            tenant_var.set(project),
        ]

        metrics = get_metrics() if settings.metrics_enabled else None
        in_flight = metrics.gauge(HTTP_IN_FLIGHT, "In-flight HTTP requests") if metrics else None
        requests = (
            metrics.counter(
                HTTP_REQUESTS,
                "Total HTTP requests",
                ("method", "path", "status", "project"),
            )
            if metrics
            else None
        )
        duration = (
            metrics.histogram(
                HTTP_DURATION,
                "HTTP request duration in seconds",
                ("method", "path"),
            )
            if metrics
            else None
        )

        if in_flight is not None:
            in_flight.inc()
        start = time.perf_counter()
        status_holder: Dict[str, int] = {"status": 500}
        failed: Optional[BaseException] = None

        async def send_with_context(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message.get("status", 500))
                extra: List[Tuple[bytes, bytes]] = [
                    (b"x-request-id", request_id.encode("latin-1")),
                    (b"x-trace-id", trace_id.encode("latin-1")),
                    (
                        b"traceparent",
                        format_traceparent(trace_id, span.span_id).encode("latin-1"),
                    ),
                ]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except BaseException as exc:  # noqa: BLE001 - record then propagate
            failed = exc
            raise
        finally:
            elapsed = time.perf_counter() - start
            status = status_holder["status"]
            if requests is not None and duration is not None:
                route = template_path(path)
                requests.inc(
                    labels={
                        "method": method,
                        "path": route,
                        "status": str(status),
                        "project": project,
                    }
                )
                duration.observe(elapsed, labels={"method": method, "path": route})
            if in_flight is not None:
                in_flight.dec()
            if settings.tracing_enabled:
                tracer.finish_span(
                    span,
                    status="error" if (failed is not None or status >= 500) else "ok",
                    error=str(failed) if failed is not None else None,
                )
            for var, token in zip((request_id_var, trace_id_var, span_id_var, tenant_var), tokens):
                var.reset(token)


__all__ = ["ObservabilityMiddleware", "template_path"]
