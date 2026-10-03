"""Cross-replica event bus for approval decisions.

An approval decision can arrive on any replica, but the process *waiting* for
it may be a different one. A plain in-process ``asyncio.Event`` cannot bridge
that gap, so decisions are published to a shared channel that every waiting
process subscribes to.

The bus reuses the deployment's ``SESSION_BACKEND`` / ``REDIS_URL`` settings
(same as the session store and the guardrail state), so there is exactly one
place to configure Redis. The memory implementation is process-local and is the
correct fallback for a single replica; the approval guard also polls the system
of record, so a decision still lands even if pub/sub is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, Set

from config.settings import get_settings

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "devrel:events:"


class EventBusError(RuntimeError):
    """Raised when the bus cannot publish or subscribe."""


class EventBus:
    """Publish/subscribe over named channels."""

    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        raise NotImplementedError  # pragma: no cover - interface

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator["asyncio.Queue[Dict[str, Any]]"]:
        raise NotImplementedError  # pragma: no cover - interface
        yield  # pragma: no cover - makes this an async generator


class MemoryEventBus(EventBus):
    """Process-local bus. Correct for a single replica and for tests."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set["asyncio.Queue[Dict[str, Any]]"]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            queue.put_nowait(message)

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator["asyncio.Queue[Dict[str, Any]]"]:
        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(channel, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(channel)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(channel, None)


class RedisEventBus(EventBus):
    """Redis pub/sub, correct across replicas."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis_async

        self._client = redis_async.Redis.from_url(url, decode_responses=True)

    def _channel(self, channel: str) -> str:
        return f"{_CHANNEL_PREFIX}{channel}"

    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        await self._client.publish(self._channel(channel), json.dumps(message, default=str))

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator["asyncio.Queue[Dict[str, Any]]"]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(self._channel(channel))
        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

        async def _reader() -> None:
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        queue.put_nowait(json.loads(message["data"]))
                    except Exception:  # ignore malformed payloads
                        continue
            except asyncio.CancelledError:  # pragma: no cover - normal shutdown
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Event bus reader stopped: %s", exc)

        task = asyncio.create_task(_reader())
        try:
            yield queue
        finally:
            task.cancel()
            try:
                await pubsub.unsubscribe()
            finally:
                await pubsub.close()


_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the configured event bus, defaulting to the memory implementation."""
    global _bus
    if _bus is not None:
        return _bus

    settings = get_settings()
    if (settings.session_backend or "memory").lower() == "redis":
        try:
            _bus = RedisEventBus(settings.redis_url)
            logger.info("Event bus: Redis (%s)", settings.redis_url)
            return _bus
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Redis event bus unavailable (%s); using memory", exc)

    _bus = MemoryEventBus()
    logger.info("Event bus: in-memory (single process)")
    return _bus


def reset_event_bus(bus: Optional[EventBus] = None) -> None:
    """Forget the cached bus, optionally installing a replacement (tests)."""
    global _bus
    _bus = bus


def event_channel(*parts: Optional[str]) -> str:
    """Build a namespaced channel name, skipping empty parts."""
    return ":".join(str(part) for part in parts if part)


__all__ = [
    "EventBus",
    "EventBusError",
    "MemoryEventBus",
    "RedisEventBus",
    "get_event_bus",
    "reset_event_bus",
    "event_channel",
]
