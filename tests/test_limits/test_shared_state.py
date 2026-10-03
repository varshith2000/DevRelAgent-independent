"""Phase 3: guardrail/limit state is shared across replicas and scoped per tenant."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_shared_state():
    from shared.state import reset_shared_state

    reset_shared_state(None)
    yield
    reset_shared_state(None)


@pytest.mark.asyncio
async def test_rate_limit_windows_are_shared_across_instances():
    from limits.rate_limiter import RateLimiter, RateLimitRule
    from shared.state import MemorySharedState, reset_shared_state

    reset_shared_state(MemorySharedState())
    rule = RateLimitRule(name="tool_calls_per_minute", max_requests=2, window_seconds=60)

    # Two limiter instances stand in for two replicas.
    replica_a = RateLimiter(rules=[rule])
    replica_b = RateLimiter(rules=[rule])

    assert (await replica_a.check_action_rate_limit("user", "tool_call")).allowed is True
    assert (await replica_a.check_action_rate_limit("user", "tool_call")).allowed is True

    # The third request is refused even though replica_b has seen nothing itself.
    assert (await replica_b.check_action_rate_limit("user", "tool_call")).allowed is False


@pytest.mark.asyncio
async def test_rate_limits_are_scoped_per_project():
    from limits.rate_limiter import RateLimiter, RateLimitRule
    from shared.state import MemorySharedState, reset_shared_state

    reset_shared_state(MemorySharedState())
    rule = RateLimitRule(name="tool_calls_per_minute", max_requests=1, window_seconds=60)
    limiter = RateLimiter(rules=[rule])

    assert (
        await limiter.check_action_rate_limit("user", "tool_call", project_id="p1")
    ).allowed is True
    assert (
        await limiter.check_action_rate_limit("user", "tool_call", project_id="p1")
    ).allowed is False
    # A different tenant gets its own budget.
    assert (
        await limiter.check_action_rate_limit("user", "tool_call", project_id="p2")
    ).allowed is True


def test_circuit_breaker_state_is_shared_and_scoped():
    from shared.state import MemorySharedState, reset_shared_state
    from tools.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

    reset_shared_state(MemorySharedState())
    config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60)

    replica_a = CircuitBreaker("clickhouse_query", config, scope="p1")
    replica_b = CircuitBreaker("clickhouse_query", config, scope="p1")

    replica_a.record_failure("boom")
    replica_a.record_failure("boom")

    assert replica_a.can_execute() is False
    # replica_b never saw a failure itself, but the circuit is shared.
    assert replica_b.can_execute() is False

    # ...and another tenant is unaffected.
    other = CircuitBreaker("clickhouse_query", config, scope="p2")
    assert other.can_execute() is True


@pytest.mark.asyncio
async def test_tool_guard_rate_limit_is_shared_and_scoped():
    from guardrails.tool_guard import RateLimitConfig
    from guardrails.tool_guard import RateLimiter as ToolRateLimiter
    from shared.state import MemorySharedState, reset_shared_state

    reset_shared_state(MemorySharedState())
    config = RateLimitConfig(
        requests_per_second=0.0,
        burst_size=5,
        requests_per_minute=1,
        requests_per_hour=100,
    )

    replica_a = ToolRateLimiter(config)
    replica_b = ToolRateLimiter(config)

    assert await replica_a.acquire("tool", project_id="p1") is True
    assert await replica_b.acquire("tool", project_id="p1") is False
    assert await replica_b.acquire("tool", project_id="p2") is True


def test_tool_guard_circuit_breaker_is_shared_and_scoped():
    from guardrails.tool_guard import (
        CircuitBreaker as ToolCircuitBreaker,
    )
    from guardrails.tool_guard import (
        CircuitBreakerConfig as ToolCircuitBreakerConfig,
    )
    from shared.state import MemorySharedState, reset_shared_state

    reset_shared_state(MemorySharedState())
    config = ToolCircuitBreakerConfig(failure_threshold=2, timeout_seconds=60)

    replica_a = ToolCircuitBreaker(config)
    replica_b = ToolCircuitBreaker(config)

    replica_a.call_failure("browser_action", project_id="p1")
    replica_a.call_failure("browser_action", project_id="p1")

    allowed, reason = replica_b.can_execute("browser_action", project_id="p1")
    assert allowed is False
    assert reason == "circuit_open"

    assert replica_b.can_execute("browser_action", project_id="p2")[0] is True


def test_shared_state_defaults_to_memory():
    from shared.state import MemorySharedState, get_shared_state

    assert isinstance(get_shared_state(), MemorySharedState)


def test_shared_state_falls_back_when_redis_unreachable(monkeypatch):
    from config.settings import reset_settings_cache
    from shared.state import MemorySharedState, get_shared_state, reset_shared_state

    monkeypatch.setenv("SESSION_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    reset_settings_cache()
    reset_shared_state()
    try:
        assert isinstance(get_shared_state(), MemorySharedState)
    finally:
        reset_settings_cache()
        reset_shared_state(None)
