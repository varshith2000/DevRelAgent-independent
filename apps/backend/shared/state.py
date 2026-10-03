"""Shared state for guardrails and limits.

Rate-limit windows, token counters and circuit-breaker state used to live in
per-process dictionaries, so two replicas enforced independent limits and a
restart forgot everything. This module provides one small interface over an
in-memory or Redis backend, and callers namespace their keys by tenant.

Reuses the deployment's shared-store configuration (``SESSION_BACKEND`` /
``REDIS_URL``) so there is exactly one place to configure Redis.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol, Tuple

from config.settings import get_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "devrel:state:"


class SharedState(Protocol):
    """Small, atomic-ish state interface for cross-replica guardrail state."""

    def record(self, key: str, window_seconds: int) -> int:  # pragma: no cover - protocol
        """Append an event and return the number of events in the window."""
        ...

    def count(self, key: str, window_seconds: int) -> int:  # pragma: no cover - protocol
        """Return the number of events currently inside the window."""
        ...

    def incr(self, key: str, amount: int, ttl_seconds: int) -> int:  # pragma: no cover
        """Add ``amount`` to a counter with a TTL and return the new total."""
        ...

    def get(self, key: str) -> Optional[str]:  # pragma: no cover - protocol
        ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None:  # pragma: no cover
        ...

    def delete(self, key: str) -> None:  # pragma: no cover - protocol
        ...

    def get_json(self, key: str) -> Optional[Any]:  # pragma: no cover - protocol
        ...

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:  # pragma: no cover
        ...


class MemorySharedState:
    """Process-local fallback. Correct for a single replica and for tests."""

    def __init__(self) -> None:
        self._windows: Dict[str, List[float]] = {}
        self._values: Dict[str, Tuple[float, str]] = {}
        self._counters: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, window_seconds: int, now: float) -> List[float]:
        events = [t for t in self._windows.get(key, []) if t > now - window_seconds]
        self._windows[key] = events
        return events

    def record(self, key: str, window_seconds: int) -> int:
        now = time.time()
        with self._lock:
            events = self._prune(key, window_seconds, now)
            events.append(now)
            return len(events)

    def count(self, key: str, window_seconds: int) -> int:
        now = time.time()
        with self._lock:
            return len(self._prune(key, window_seconds, now))

    def incr(self, key: str, amount: int, ttl_seconds: int) -> int:
        now = time.time()
        with self._lock:
            expires_at, value = self._counters.get(key, (0.0, 0))
            if expires_at and expires_at < now:
                value = 0
            value += amount
            self._counters[key] = (now + ttl_seconds, value)
            return value

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at and expires_at < time.monotonic():
                self._values.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds else 0.0
        with self._lock:
            self._values[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)
            self._counters.pop(key, None)
            self._windows.pop(key, None)

    def get_json(self, key: str) -> Optional[Any]:
        raw = self.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.set(key, json.dumps(value), ttl_seconds)

    def clear(self) -> None:
        """Drop everything (tests)."""
        with self._lock:
            self._windows.clear()
            self._values.clear()
            self._counters.clear()


class RedisSharedState:
    """Redis-backed shared state, correct across replicas."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def _k(self, key: str) -> str:
        return f"{_KEY_PREFIX}{key}"

    def record(self, key: str, window_seconds: int) -> int:
        redis_key = self._k(key)
        now = time.time()
        member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
        pipe = self._client.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window_seconds)
        results = pipe.execute()
        return int(results[2])

    def count(self, key: str, window_seconds: int) -> int:
        redis_key = self._k(key)
        now = time.time()
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zcard(redis_key)
        return int(pipe.execute()[1])

    def incr(self, key: str, amount: int, ttl_seconds: int) -> int:
        redis_key = self._k(key)
        pipe = self._client.pipeline()
        pipe.incrby(redis_key, amount)
        pipe.expire(redis_key, ttl_seconds)
        return int(pipe.execute()[0])

    def get(self, key: str) -> Optional[str]:
        value = self._client.get(self._k(key))
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(self._k(key), value, ex=ttl_seconds or None)

    def delete(self, key: str) -> None:
        self._client.delete(self._k(key))

    def get_json(self, key: str) -> Optional[Any]:
        raw = self.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.set(key, json.dumps(value), ttl_seconds)


_state: Optional[SharedState] = None


def reset_shared_state(state: Optional[SharedState] = None) -> None:
    """Forget the cached backend, optionally installing a replacement (tests)."""
    global _state
    _state = state


def get_shared_state() -> SharedState:
    """Return the configured shared backend, falling back to memory."""
    global _state
    if _state is not None:
        return _state

    settings = get_settings()
    if (settings.session_backend or "memory").lower() == "redis":
        try:
            backend: SharedState = RedisSharedState(settings.redis_url)
            backend.set("healthcheck", "1", 5)
            _state = backend
            logger.info("Shared state: Redis (%s)", settings.redis_url)
            return _state
        except Exception as exc:
            logger.warning("Redis shared state unavailable (%s); using memory", exc)

    _state = MemorySharedState()
    logger.info("Shared state: in-memory (single process)")
    return _state


def scoped_key(*parts: Optional[str]) -> str:
    """Build a namespaced key, skipping empty parts."""
    return ":".join(str(part) for part in parts if part)
