"""Key/value session storage with TTL.

The interface is deliberately tiny (``get``/``set``/``delete``/``keys``) and
synchronous, because the callers are FastAPI handlers that may run in a
threadpool. ``SESSION_BACKEND=redis`` shares state across replicas; the
in-memory backend keeps a single-process deployment dependency-free.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Dict, List, Optional, Protocol, Tuple

from config.settings import get_settings

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    """Storage for short-lived, namespaced values (JSON strings)."""

    def get(self, key: str) -> Optional[str]:  # pragma: no cover - protocol
        ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None:  # pragma: no cover
        ...

    def delete(self, key: str) -> None:  # pragma: no cover
        ...

    def keys(self, prefix: str) -> List[str]:  # pragma: no cover
        ...


class MemorySessionStore:
    """Process-local store with lazy expiry. For development and tests."""

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, str]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str) -> Optional[str]:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at and expires_at < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            return self._live(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds else 0.0
        with self._lock:
            self._data[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self, prefix: str) -> List[str]:
        with self._lock:
            live = [k for k in list(self._data) if self._live(k) is not None]
        return [k for k in live if k.startswith(prefix)]

    def clear(self) -> None:
        """Drop everything (tests)."""
        with self._lock:
            self._data.clear()


class RedisSessionStore:
    """Redis-backed store, shared by every replica."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        value = self._client.get(key)
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(key, value, ex=ttl_seconds or None)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def keys(self, prefix: str) -> List[str]:
        return [key for key in self._client.scan_iter(match=f"{prefix}*", count=100)]


_store: Optional[SessionStore] = None


def reset_session_store(store: Optional[SessionStore] = None) -> None:
    """Forget the cached store, optionally installing a replacement (tests)."""
    global _store
    _store = store


def get_session_store() -> SessionStore:
    """Return the configured store, falling back to memory if Redis is down."""
    global _store
    if _store is not None:
        return _store

    settings = get_settings()
    backend = (settings.session_backend or "memory").lower()
    if backend == "redis":
        try:
            store: SessionStore = RedisSessionStore(settings.redis_url)
            store.set("devrel:healthcheck", json.dumps({"ok": True}), 5)
            _store = store
            logger.info("Session store: Redis (%s)", settings.redis_url)
            return _store
        except Exception as exc:  # redis missing or unreachable
            logger.warning("Redis session backend unavailable (%s); using memory", exc)

    _store = MemorySessionStore()
    logger.info("Session store: in-memory (single process)")
    return _store
