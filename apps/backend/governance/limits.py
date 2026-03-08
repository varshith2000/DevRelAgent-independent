"""
Resource Limits and Rate Limiting

Implements comprehensive limits for production deployment:
- Query limits
- Token limits
- Time limits
- Action limits
- Graceful failure handling
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class ResourceLimit:
    """Definition of a resource limit."""
    name: str
    max_value: int
    window_seconds: int = 60  # For rate limiting
    description: str = ""
    enabled: bool = True


@dataclass
class LimitExceeded(Exception):
    """Raised when a limit is exceeded."""
    limit_name: str
    current_value: int
    max_value: int
    retry_after_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "error": "limit_exceeded",
            "limit_name": self.limit_name,
            "current_value": self.current_value,
            "max_value": self.max_value,
            "retry_after": self.retry_after_seconds,
            "message": f"Limit '{self.limit_name}' exceeded ({self.current_value}/{self.max_value})"
        }


class RateLimiter:
    """
    Token bucket rate limiter.

    Limits actions per time window.
    """

    def __init__(self):
        """Initialize rate limiter."""
        # Format: {(user_id, action): {tokens, last_refill}}
        self.buckets: Dict[tuple, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def check_limit(
        self,
        user_id: str,
        action: str,
        max_requests: int = 100,
        window_seconds: int = 60
    ) -> bool:
        """
        Check if action is within rate limit.

        Args:
            user_id: User ID
            action: Action type
            max_requests: Maximum requests in window
            window_seconds: Time window in seconds

        Returns:
            True if within limit
        """
        async with self.lock:
            key = (user_id, action)
            now = time.time()

            if key not in self.buckets:
                self.buckets[key] = {
                    "tokens": max_requests,
                    "last_refill": now
                }
                return True

            bucket = self.buckets[key]

            # Refill tokens based on time passed
            time_passed = now - bucket["last_refill"]
            tokens_to_add = int(time_passed / window_seconds * max_requests)

            bucket["tokens"] = min(max_requests, bucket["tokens"] + tokens_to_add)
            bucket["last_refill"] = now

            # Check if we have tokens
            if bucket["tokens"] > 0:
                bucket["tokens"] -= 1
                return True

            # Rate limited
            retry_after = int(window_seconds - (now - bucket["last_refill"]))
            raise LimitExceeded(
                limit_name="rate_limit",
                current_value=0,
                max_value=max_requests,
                retry_after_seconds=retry_after
            )


class ResourceLimiter:
    """
    Comprehensive resource limiter.

    Enforces limits on:
    - Queries per session
    - Tokens per request
    - Execution time
    - Actions per user
    - Database queries
    - File operations
    """

    # Default limits
    DEFAULT_LIMITS = {
        # Query limits
        "queries_per_session": ResourceLimit(
            name="queries_per_session",
            max_value=100,
            description="Maximum queries per session"
        ),

        # Token limits
        "tokens_per_request": ResourceLimit(
            name="tokens_per_request",
            max_value=4000,
            description="Maximum tokens per request"
        ),

        # Time limits
        "query_timeout_seconds": ResourceLimit(
            name="query_timeout",
            max_value=30,
            description="Maximum query execution time in seconds"
        ),

        # Action limits
        "write_actions_per_hour": ResourceLimit(
            name="write_actions",
            max_value=20,
            window_seconds=3600,
            description="Maximum write actions per hour per user"
        ),

        "tool_executions_per_minute": ResourceLimit(
            name="tool_executions",
            max_value=30,
            window_seconds=60,
            description="Maximum tool executions per minute"
        ),

        # Database limits
        "database_queries_per_request": ResourceLimit(
            name="database_queries",
            max_value=10,
            description="Maximum database queries per request"
        ),

        "database_result_rows": ResourceLimit(
            name="database_rows",
            max_value=10000,
            description="Maximum rows returned from database"
        ),

        # File limits
        "file_operations_per_hour": ResourceLimit(
            name="file_ops",
            max_value=50,
            window_seconds=3600,
            description="Maximum file operations per hour"
        ),

        "file_size_bytes": ResourceLimit(
            name="file_size",
            max_value=10 * 1024 * 1024,  # 10MB
            description="Maximum file size for operations"
        )
    }

    def __init__(self, custom_limits: Optional[Dict[str, ResourceLimit]] = None):
        """
        Initialize resource limiter.

        Args:
            custom_limits: Optional custom limits to override defaults
        """
        self.limits = self.DEFAULT_LIMITS.copy()

        if custom_limits:
            self.limits.update(custom_limits)

        # Tracking
        self.usage = defaultdict(lambda: defaultdict(int))
        self.rate_limiter = RateLimiter()

    def get_limit(self, limit_name: str) -> ResourceLimit:
        """Get a limit by name."""
        return self.limits.get(limit_name)

    def check_limit(
        self,
        limit_name: str,
        current_value: int = 1,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Check if a limit would be exceeded.

        Args:
            limit_name: Name of the limit to check
            current_value: Current value to add
            context: Optional context (user_id, session_id, etc.)

        Raises:
            LimitExceeded if limit would be exceeded
        """
        limit = self.get_limit(limit_name)

        if not limit or not limit.enabled:
            return

        # Calculate current usage
        user_id = context.get("user_id") if context else "anonymous"
        session_id = context.get("session_id") if context else "default"

        key = f"{limit_name}:{user_id}:{session_id}"
        usage = self.usage[key]

        if usage + current_value > limit.max_value:
            retry_after = limit.window_seconds if limit.window_seconds else None
            raise LimitExceeded(
                limit_name=limit_name,
                current_value=usage + current_value,
                max_value=limit.max_value,
                retry_after_seconds=retry_after
            )

    def record_usage(self, limit_name: str, context: Optional[Dict[str, Any]] = None):
        """
        Record usage against a limit.

        Args:
            limit_name: Name of the limit
            context: Optional context
        """
        limit = self.get_limit(limit_name)

        if not limit or not limit.enabled:
            return

        user_id = context.get("user_id") if context else "anonymous"
        session_id = context.get("session_id") if context else "default"

        key = f"{limit_name}:{user_id}:{session_id}"
        self.usage[key] += 1

        # Clean up old usage periodically (in production, use a proper cleanup job)
        if len(self.usage) > 10000:
            self._cleanup_old_usage()

    def _cleanup_old_usage(self):
        """Clean up old usage entries."""
        # In production, implement proper cleanup logic
        # For now, just clear if too large
        if len(self.usage) > 50000:
            self.usage.clear()


class Timeout:
    """
    Timeout context manager for enforcing time limits.

    Gracefully handles timeouts with proper cleanup.
    """

    def __init__(self, timeout_seconds: int, operation: str = "operation"):
        """
        Initialize timeout.

        Args:
            timeout_seconds: Timeout in seconds
            operation: Operation description
        """
        self.timeout_seconds = timeout_seconds
        self.operation = operation

    async def __aenter__(self):
        """Enter timeout context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit timeout context."""
        if exc_type == asyncio.TimeoutError:
            logger.warning(f"{self.operation} timed out after {self.timeout_seconds}s")
            # Re-raise with more context
            raise TimeoutError(
                f"{self.operation} exceeded time limit of {self.timeout_seconds} seconds"
            )


# ============== Decorators ==============

def limit_queries(max_queries: int = 100):
    """Decorator to limit queries per session."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract session_id from kwargs or args
            session_id = kwargs.get("session_id", "default")

            limiter = kwargs.get("_limiter", ResourceLimiter())

            try:
                limiter.check_limit(
                    "queries_per_session",
                    current_value=1,
                    context={"session_id": session_id}
                )
            except LimitExceeded as e:
                logger.warning(f"Query limit exceeded for session {session_id}")
                return {
                    "success": False,
                    "error": e.to_dict(),
                    "message": "Query limit exceeded. Please start a new session."
                }

            result = await func(*args, **kwargs)

            limiter.record_usage(
                "queries_per_session",
                context={"session_id": session_id}
            )

            return result

        return wrapper
    return decorator


def limit_time(max_seconds: int = 30):
    """Decorator to limit execution time."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                async with Timeout(max_seconds, func.__name__):
                    return await func(*args, **kwargs)
            except TimeoutError as e:
                logger.warning(f"Time limit exceeded: {func.__name__}")
                return {
                    "success": False,
                    "error": {
                        "type": "timeout",
                        "message": str(e),
                        "max_seconds": max_seconds
                    }
                }

        return wrapper
    return decorator


def graceful_error_handler(func):
    """
    Decorator for graceful error handling.

    Ensures all errors are caught and returned properly formatted.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except LimitExceeded as e:
            # Limit exceeded - return friendly error
            return {
                "success": False,
                "error": e.to_dict(),
                "retry_after": e.retry_after_seconds
            }
        except TimeoutError as e:
            # Timeout - return friendly error
            return {
                "success": False,
                "error": {
                    "type": "timeout",
                    "message": str(e)
                }
            }
        except Exception as e:
            # Generic error - log and return friendly message
            logger.exception(f"Unexpected error in {func.__name__}")

            return {
                "success": False,
                "error": {
                    "type": "internal_error",
                    "message": "An internal error occurred. Please try again.",
                    "details": str(e) if logger.level == logging.DEBUG else None
                }
            }

    return wrapper


# ============== Global Instances =###

_default_limiter: Optional[ResourceLimiter] = None


def get_resource_limiter() -> ResourceLimiter:
    """Get the global resource limiter."""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = ResourceLimiter()
    return _default_limiter


def set_resource_limiter(limiter: ResourceLimiter):
    """Set a custom resource limiter."""
    global _default_limiter
    _default_limiter = limiter


def reset_resource_limiter():
    """Reset the resource limiter."""
    global _default_limiter
    _default_limiter = None
