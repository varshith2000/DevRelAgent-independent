"""
Limits Module - Production-Grade Rate Limiting

Provides token-based and action-based rate limiting for API usage.

Usage:
    from limits.rate_limiter import get_rate_limiter, rate_limit

    limiter = await get_rate_limiter()

    # Check rate limit
    result = await limiter.check_action_rate_limit(
        user_id="user123",
        action="chat",
        token_count=100
    )

    # Or use decorator
    @rate_limit(action="chat", user_id_param="session_id")
    async def chat_endpoint(message: str, session_id: str):
        return response
"""

from .rate_limiter import (
    RateLimiter,
    RateLimitResult,
    RateLimitRule,
    TokenCounter,
    get_rate_limiter,
    rate_limit,
)

__all__ = [
    "RateLimiter",
    "RateLimitRule",
    "RateLimitResult",
    "TokenCounter",
    "get_rate_limiter",
    "rate_limit",
]
