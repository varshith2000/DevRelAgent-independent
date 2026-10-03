"""Lightweight span tracing with W3C ``traceparent`` propagation.

This is a deliberately small tracer: it generates/propagates W3C trace context
so a request can be followed across replicas and services, records spans
(name, ids, timing, attributes, status) into a bounded in-memory ring, and
emits each span as a structured JSON log line. It is not a replacement for a
full OpenTelemetry SDK — it is the minimum needed to correlate a request, its
agent run and its tool calls without another heavyweight dependency.
"""

from __future__ import annotations

import logging
import random
import secrets
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("observability.tracing")

_TRACEPARENT_VERSION = "00"
_TRACE_ID_HEX = 32
_SPAN_ID_HEX = 16


def new_trace_id() -> str:
    """Return a fresh 16-byte (32 hex char) trace id."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """Return a fresh 8-byte (16 hex char) span id."""
    return secrets.token_hex(8)


def _is_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def parse_traceparent(value: Optional[str]) -> Optional[Tuple[str, str, bool]]:
    """Parse a W3C ``traceparent`` header.

    Returns ``(trace_id, parent_span_id, sampled)`` or ``None`` when the header
    is missing, malformed, or all-zero (the spec's "invalid" trace id).
    """
    if not value:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, flags = parts
    if len(version) != 2 or not _is_hex(version, 2):
        return None
    if not _is_hex(trace_id, _TRACE_ID_HEX) or trace_id == "0" * _TRACE_ID_HEX:
        return None
    if not _is_hex(span_id, _SPAN_ID_HEX) or span_id == "0" * _SPAN_ID_HEX:
        return None
    if not _is_hex(flags, 2):
        return None
    return trace_id.lower(), span_id.lower(), bool(int(flags, 16) & 0x01)


def format_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """Render a W3C ``traceparent`` header value."""
    flags = "01" if sampled else "00"
    return f"{_TRACEPARENT_VERSION}-{trace_id}-{span_id}-{flags}"


@dataclass
class Span:
    """One timed unit of work."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "unset"
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        end = self.end_time if self.end_time is not None else time.time()
        return (end - self.start_time) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "error": self.error,
            "attributes": self.attributes,
        }


class Tracer:
    """Creates spans and keeps a bounded history for inspection/debugging."""

    def __init__(
        self,
        enabled: bool = True,
        sample_rate: float = 1.0,
        max_spans: int = 1000,
    ) -> None:
        self.enabled = enabled
        self.sample_rate = max(0.0, min(1.0, sample_rate))
        self._spans: Deque[Span] = deque(maxlen=max_spans)
        self._lock = threading.Lock()

    def _sampled(self) -> bool:
        if self.sample_rate >= 1.0:
            return True
        return random.random() < self.sample_rate

    def new_trace_id(self) -> str:
        return new_trace_id()

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Span:
        return Span(
            name=name,
            trace_id=trace_id or new_trace_id(),
            span_id=new_span_id(),
            parent_span_id=parent_span_id,
            attributes=dict(attributes or {}),
        )

    def finish_span(
        self,
        span: Span,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> Span:
        span.end_time = time.time()
        span.status = status
        span.error = error
        if self.enabled and self._sampled():
            with self._lock:
                self._spans.append(span)
            logger.info("span", extra={"span": span.to_dict()})
        return span

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Iterator[Span]:
        """Context manager that finishes the span, marking errors on raise."""
        span = self.start_span(name, attributes, trace_id, parent_span_id)
        try:
            yield span
        except Exception as exc:  # record then re-raise
            self.finish_span(span, status="error", error=str(exc))
            raise
        else:
            self.finish_span(span, status="ok")

    def get_recent_spans(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            spans = list(self._spans)[-limit:]
        return [span.to_dict() for span in reversed(spans)]

    def reset(self) -> None:
        with self._lock:
            self._spans.clear()


_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Return the process-wide tracer, configured from settings."""
    global _tracer
    if _tracer is None:
        from config.settings import get_settings

        settings = get_settings()
        _tracer = Tracer(
            enabled=settings.tracing_enabled,
            sample_rate=settings.trace_sample_rate,
        )
    return _tracer


def reset_tracer(tracer: Optional[Tracer] = None) -> None:
    """Replace the cached tracer (tests)."""
    global _tracer
    _tracer = tracer


__all__ = [
    "Span",
    "Tracer",
    "get_tracer",
    "reset_tracer",
    "new_trace_id",
    "new_span_id",
    "parse_traceparent",
    "format_traceparent",
]
