"""
Rate Limiter - Production-Grade Rate Limiting

Implements token-based and action-based rate limiting for API usage.

Features:
- Token counting for LLM requests
- Action rate limiting per user/session
- Sliding window algorithm
- Configurable limits and time windows
- Distributed support (Redis ready)
- Export metrics for monitoring
"""

import asyncio
import hashlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from shared.state import SharedState, get_shared_state, scoped_key

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limiting rule definition."""

    name: str
    max_requests: int
    window_seconds: int
    max_tokens: Optional[int] = None
    block_duration_seconds: int = 60


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    rule_name: str
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class RateLimitStats:
    """Statistics for rate limiting."""

    total_checks: int = 0
    blocked_requests: int = 0
    allowed_requests: int = 0
    tokens_consumed: int = 0
    by_rule: Dict[str, int] = field(default_factory=dict)


class TokenCounter:
    """
    Count tokens in text for rate limiting.

    Uses a simple estimation algorithm since we don't want to depend
    on the tokenizer library for rate limiting (performance).
    """

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Estimate token count for text.

        Uses a simple approximation: ~4 characters per token for English text,
        adjusted for code and special characters.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        # Base estimation: ~4 characters per token
        base_count = len(text) / 4

        # Adjust for code (more tokens due to density)
        code_indicators = ["def ", "function", "class ", "import ", "=>", "{", "}", "(", ")", ";"]
        code_multiplier = 1.0
        for indicator in code_indicators:
            if indicator in text:
                code_multiplier = 1.5
                break

        # Adjust for special characters (more tokens)
        special_char_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / len(text)
        special_multiplier = 1.0 + min(special_char_ratio * 2, 1.0)

        return int(base_count * code_multiplier * special_multiplier)

    @staticmethod
    def count_tokens_in_messages(messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in a list of messages.

        Args:
            messages: List of message dictionaries

        Returns:
            Total token count
        """
        total = 0
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                content = str(msg)
            total += TokenCounter.count_tokens(content)
        return total


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter backed by shared state.

    Events are recorded in a shared, tenant-namespaced window, so every replica
    enforces the same limit and a restart does not forget it. The backend is
    chosen by :func:`shared.state.get_shared_state`.
    """

    def __init__(self, rule: RateLimitRule, state: Optional[SharedState] = None):
        self.rule = rule
        self._state = state

    @property
    def state(self) -> SharedState:
        return self._state or get_shared_state()

    def _requests_key(self, scope: str) -> str:
        return scoped_key("ratelimit", scope, self.rule.name, "requests")

    def _tokens_key(self, scope: str) -> str:
        return scoped_key("ratelimit", scope, self.rule.name, "tokens")

    async def check(self, scope: str, token_count: int = 1) -> RateLimitResult:
        """
        Check whether a request is allowed, recording it when it is.

        Args:
            scope: Tenant-scoped identifier (e.g. ``project:user``)
            token_count: Number of tokens in this request

        Returns:
            RateLimitResult with decision
        """
        now = time.time()
        window = self.rule.window_seconds
        state = self.state

        # Token budget is a fixed window counter (approximate but shared).
        if self.rule.max_tokens and token_count:
            used = state.incr(self._tokens_key(scope), token_count, window)
            if used > self.rule.max_tokens:
                return RateLimitResult(
                    allowed=False,
                    rule_name=self.rule.name,
                    remaining=max(0, self.rule.max_tokens - used),
                    reset_at=datetime.fromtimestamp(now + window),
                    retry_after=self.rule.block_duration_seconds,
                    reason=f"Token limit exceeded: {used}/{self.rule.max_tokens}",
                )

        count = state.count(self._requests_key(scope), window)
        if count >= self.rule.max_requests:
            return RateLimitResult(
                allowed=False,
                rule_name=self.rule.name,
                remaining=0,
                reset_at=datetime.fromtimestamp(now + window),
                retry_after=self.rule.block_duration_seconds,
                reason=(f"Rate limit exceeded: {count} requests/{self.rule.max_requests} max"),
            )

        recorded = state.record(self._requests_key(scope), window)
        return RateLimitResult(
            allowed=True,
            rule_name=self.rule.name,
            remaining=max(0, self.rule.max_requests - recorded),
            reset_at=datetime.fromtimestamp(now + window),
            retry_after=None,
        )


class RateLimiter:
    """
    Production-grade rate limiter with token counting.

    Features:
    - Multiple rate limit rules
    - Per-user/session tracking
    - Token-based limiting
    - Sliding window algorithm
    - Distributed support (Redis)
    - Statistics and monitoring
    """

    def __init__(
        self,
        rules: Optional[List[RateLimitRule]] = None,
        enable_redis: bool = False,
        redis_url: Optional[str] = None,
    ):
        """
        Initialize rate limiter.

        Args:
            rules: List of rate limit rules (defaults if None)
            enable_redis: Enable Redis for distributed limiting
            redis_url: Redis connection URL
        """
        # Default rules if none provided
        self.rules = rules or [
            RateLimitRule(
                name="chat_requests_per_minute",
                max_requests=60,
                window_seconds=60,
                block_duration_seconds=60,
            ),
            RateLimitRule(
                name="chat_tokens_per_minute",
                max_requests=10000,  # Also limited by requests
                window_seconds=60,
                max_tokens=10000,
                block_duration_seconds=60,
            ),
            RateLimitRule(
                name="tool_calls_per_minute",
                max_requests=30,
                window_seconds=60,
                block_duration_seconds=60,
            ),
            RateLimitRule(
                name="approvals_per_hour",
                max_requests=20,
                window_seconds=3600,
                block_duration_seconds=300,
            ),
        ]

        self.enable_redis = enable_redis
        self.redis_url = redis_url

        # One stateless limiter per rule; the window itself lives in shared state.
        self.limiters: Dict[str, SlidingWindowRateLimiter] = {
            rule.name: SlidingWindowRateLimiter(rule) for rule in self.rules
        }
        # Scopes observed in this process, for lightweight metrics only.
        self.active_scopes: set = set()

        # Statistics
        self.stats = RateLimitStats()

        # Redis client (lazy initialization)
        self._redis_client = None

        logger.info(f"✅ RateLimiter initialized with {len(self.rules)} rules")

    async def check_action_rate_limit(
        self,
        user_id: str,
        action: str = "chat",
        token_count: int = 0,
        project_id: Optional[str] = None,
    ) -> RateLimitResult:
        """
        Check if action is allowed under rate limits.

        Args:
            user_id: User/session identifier
            action: Action type (chat, tool_call, approval, etc.)
            token_count: Number of tokens consumed
            project_id: Tenant scope; limits are enforced per project

        Returns:
            RateLimitResult with decision
        """
        self.stats.total_checks += 1
        scope = scoped_key(project_id, user_id)

        # Find applicable rules
        applicable_rules = self._get_applicable_rules(action)

        # Check each rule
        for rule in applicable_rules:
            result = await self._check_rule(scope, rule, token_count)
            if not result.allowed:
                self.stats.blocked_requests += 1
                logger.warning(
                    f"Rate limit blocked for user={user_id}, action={action}, "
                    f"rule={rule.name}: {result.reason}"
                )
                return result

        self.stats.allowed_requests += 1
        self.stats.tokens_consumed += token_count

        # Return success (using most permissive rule)
        return RateLimitResult(
            allowed=True,
            rule_name=applicable_rules[0].name if applicable_rules else "default",
            remaining=applicable_rules[0].max_requests if applicable_rules else 999999,
            reset_at=datetime.now() + timedelta(seconds=60),
            retry_after=None,
        )

    async def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        return TokenCounter.count_tokens(text)

    async def count_tokens_async(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in a list of messages asynchronously.

        Args:
            messages: List of message dictionaries

        Returns:
            Total token count
        """
        return TokenCounter.count_tokens_in_messages(messages)

    def get_stats(self) -> RateLimitStats:
        """
        Get rate limiting statistics.

        Returns:
            Current statistics
        """
        return self.stats

    def reset_user_limits(self, scope: str) -> None:
        """
        Clear the shared windows for a scope (admin action or testing).

        Args:
            scope: Tenant-scoped identifier, as passed to the check methods
        """
        state = get_shared_state()
        for rule in self.rules:
            state.delete(scoped_key("ratelimit", scope, rule.name, "requests"))
            state.delete(scoped_key("ratelimit", scope, rule.name, "tokens"))
        self.active_scopes.discard(scope)
        logger.info(f"Reset rate limits for scope={scope}")

    def _get_applicable_rules(self, action: str) -> List[RateLimitRule]:
        """Get rules applicable to an action type."""
        action_rule_map = {
            "chat": ["chat_requests_per_minute", "chat_tokens_per_minute"],
            "tool_call": ["tool_calls_per_minute", "chat_tokens_per_minute"],
            "approval": ["approvals_per_hour", "chat_tokens_per_minute"],
            "dashboard": ["tool_calls_per_minute"],
        }

        rule_names = action_rule_map.get(action, [])

        return [rule for rule in self.rules if rule.name in rule_names]

    async def _check_rule(
        self, scope: str, rule: RateLimitRule, token_count: int
    ) -> RateLimitResult:
        """Check a specific rule for a scope."""
        limiter = self.limiters.get(rule.name)
        if limiter is None:
            limiter = SlidingWindowRateLimiter(rule)
            self.limiters[rule.name] = limiter

        if len(self.active_scopes) > 10000:
            self.active_scopes.clear()
        self.active_scopes.add(scope)

        result = await limiter.check(scope, token_count)

        # Update stats
        if result.rule_name not in self.stats.by_rule:
            self.stats.by_rule[result.rule_name] = 0
        if not result.allowed:
            self.stats.by_rule[result.rule_name] += 1

        return result

    async def export_metrics(self) -> Dict[str, Any]:
        """
        Export metrics for monitoring.

        Returns:
            Metrics dictionary
        """
        return {
            "rate_limit_stats": {
                "total_checks": self.stats.total_checks,
                "blocked_requests": self.stats.blocked_requests,
                "allowed_requests": self.stats.allowed_requests,
                "tokens_consumed": self.stats.tokens_consumed,
                "block_rate": (
                    self.stats.blocked_requests / self.stats.total_checks
                    if self.stats.total_checks > 0
                    else 0
                ),
                "by_rule": self.stats.by_rule,
            },
            "active_users": len(self.active_scopes),
            "timestamp": datetime.now().isoformat(),
        }


# Decorator for rate limiting
def rate_limit(
    action: str = "chat",
    user_id_param: Optional[str] = None,
    check_tokens: bool = True,
):
    """
    Decorator for rate limiting function calls.

    Args:
        action: Action type for rate limiting
        user_id_param: Parameter name containing user_id (if any)
        check_tokens: Whether to check token limits

    Usage:
        @rate_limit(action="chat", user_id_param="session_id")
        async def chat_endpoint(message: str, session_id: str):
            return response
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get rate limiter
            limiter = get_rate_limiter()

            # Extract user_id
            user_id = None
            if user_id_param and user_id_param in kwargs:
                user_id = kwargs[user_id_param]
            elif len(args) > 0:
                # Try to get from first argument
                if hasattr(args[0], "user_id"):
                    user_id = args[0].user_id

            if not user_id:
                user_id = "anonymous"

            # Count tokens if requested
            token_count = 0
            if check_tokens:
                # Estimate tokens from arguments
                all_args_str = " ".join(str(arg) for arg in args)
                all_kwargs_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
                token_count = await limiter.count_tokens(all_args_str + " " + all_kwargs_str)

            # Check rate limit
            result = await limiter.check_action_rate_limit(
                user_id=user_id,
                action=action,
                token_count=token_count,
            )

            if not result.allowed:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": result.retry_after,
                        "reset_at": result.reset_at.isoformat(),
                        "rule": result.rule_name,
                        "reason": result.reason,
                    },
                    headers={
                        "Retry-After": str(result.retry_after or 60),
                        "X-RateLimit-Remaining": str(result.remaining),
                        "X-RateLimit-Reset": result.reset_at.isoformat(),
                    },
                )

            # Call the function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Global singleton
_rate_limiter: Optional[RateLimiter] = None
_limiter_lock = asyncio.Lock()


async def get_rate_limiter(
    rules: Optional[List[RateLimitRule]] = None,
    enable_redis: bool = False,
) -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter

    if _rate_limiter is None:
        async with _limiter_lock:
            if _rate_limiter is None:
                _rate_limiter = RateLimiter(
                    rules=rules,
                    enable_redis=enable_redis,
                )

    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Set a custom rate limiter instance (useful for testing)."""
    global _rate_limiter
    _rate_limiter = limiter
