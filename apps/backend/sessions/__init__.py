"""Shared session storage.

Conversation state must survive across worker processes, so it lives behind a
small key/value interface with an in-memory default and a Redis backend for
multi-replica deployments.
"""

from sessions.store import (
    MemorySessionStore,
    RedisSessionStore,
    SessionStore,
    get_session_store,
    reset_session_store,
)

__all__ = [
    "SessionStore",
    "MemorySessionStore",
    "RedisSessionStore",
    "get_session_store",
    "reset_session_store",
]
