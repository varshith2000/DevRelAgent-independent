"""
Tool Guardrails — Rate limiting, timeout wrapper, scope restriction

Production-grade tool execution protection for DevRelAgent.

Features:
- Rate limiting per tool and per user
- Timeout wrapper with graceful degradation
- Scope restriction (URL, file path, operation limits)
- Circuit breaker pattern for failing tools
- Resource usage tracking
- Audit logging for compliance

Usage:
    from guardrails.tool_guard import ToolGuardrail, get_tool_guardrail

    guard = get_tool_guardrail()

    # Rate-limited execution
    result = await guard.execute_with_rate_limit(tool_name, handler, arguments)

    # Timeout-wrapped execution
    result = await guard.execute_with_timeout(tool_name, handler, arguments, timeout=30)

    # Scope-restricted execution
    result = await guard.execute_with_scope_check(tool_name, handler, arguments, scope)
"""

import asyncio
import functools
import hashlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from shared.state import SharedState, get_shared_state, scoped_key

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Tool categories for scope restriction."""

    DATABASE_QUERY = "database_query"
    DATABASE_WRITE = "database_write"
    CODE_READ = "code_read"
    CODE_WRITE = "code_write"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK_READ = "network_read"
    NETWORK_WRITE = "network_write"
    BROWSER = "browser"
    GITHUB = "github"
    GRAFANA = "grafana"
    EXTERNAL_API = "external_api"
    SYSTEM = "system"


@dataclass
class ToolExecutionResult:
    """Result of tool execution with guardrails."""

    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    rate_limited: bool = False
    timeout_occurred: bool = False
    scope_violation: bool = False
    circuit_breaker_open: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "rate_limited": self.rate_limited,
            "timeout_occurred": self.timeout_occurred,
            "scope_violation": self.scope_violation,
            "circuit_breaker_open": self.circuit_breaker_open,
            "metadata": self.metadata,
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_second: float = 10.0
    requests_per_minute: int = 100
    requests_per_hour: int = 1000
    burst_size: int = 20


@dataclass
class TimeoutConfig:
    """Configuration for timeout wrapper."""

    default_timeout_seconds: float = 30.0
    max_timeout_seconds: float = 120.0
    min_timeout_seconds: float = 1.0
    timeout_retry_count: int = 0


@dataclass
class ScopeConfig:
    """Configuration for scope restriction."""

    allowed_categories: Set[ToolCategory] = field(default_factory=set)
    allowed_urls: Set[str] = field(default_factory=set)
    allowed_paths: Set[str] = field(default_factory=set)
    blocked_operations: Set[str] = field(default_factory=set)
    max_result_size_bytes: int = 10 * 1024 * 1024  # 10MB


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3


class RateLimiter:
    """
    Token bucket rate limiter for tool execution.

    Implements sliding window rate limiting with burst support.
    """

    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        state: Optional[SharedState] = None,
    ):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration
            state: Shared state backend (defaults to the configured one)
        """
        self.config = config or RateLimitConfig()
        self._state = state

        # Statistics
        self.stats = {
            "total_requests": 0,
            "rate_limited": 0,
            "tokens_consumed": 0,
        }

    @property
    def _store(self) -> SharedState:
        return self._state or get_shared_state()

    def _bucket_key(self, scope: str) -> str:
        return scoped_key("toolguard", scope, "bucket")

    def _minute_key(self, scope: str) -> str:
        return scoped_key("toolguard", scope, "minute")

    def _hour_key(self, scope: str) -> str:
        return scoped_key("toolguard", scope, "hour")

    def _load_bucket(self, scope: str) -> Dict[str, Any]:
        """Read the shared token bucket, refilling it for elapsed time."""
        now = time.time()
        bucket = self._store.get_json(self._bucket_key(scope)) or {}
        tokens = float(bucket.get("tokens", self.config.burst_size))
        last_update = float(bucket.get("last_update", now))
        tokens = min(
            tokens + max(0.0, now - last_update) * self.config.requests_per_second,
            self.config.burst_size,
        )
        return {"tokens": tokens, "last_update": now}

    def _save_bucket(self, scope: str, bucket: Dict[str, Any]) -> None:
        self._store.set_json(self._bucket_key(scope), bucket, 3600)

    async def acquire(self, key: str = "default", project_id: Optional[str] = None) -> bool:
        """
        Try to acquire a rate limit token.

        Args:
            key: Rate limit key (tool name, user ID, etc.)
            project_id: Tenant scope; each project has its own budget

        Returns:
            True if token acquired, False if rate limited
        """
        self.stats["total_requests"] += 1
        scope = scoped_key(project_id, key)
        bucket = self._load_bucket(scope)

        # Check per-second rate (token bucket)
        if bucket["tokens"] < 1:
            self.stats["rate_limited"] += 1
            return False

        # Check per-minute and per-hour sliding windows
        if self._store.count(self._minute_key(scope), 60) >= self.config.requests_per_minute:
            self.stats["rate_limited"] += 1
            return False

        if self._store.count(self._hour_key(scope), 3600) >= self.config.requests_per_hour:
            self.stats["rate_limited"] += 1
            return False

        # Consume token
        bucket["tokens"] -= 1
        self._save_bucket(scope, bucket)
        self._store.record(self._minute_key(scope), 60)
        self._store.record(self._hour_key(scope), 3600)
        self.stats["tokens_consumed"] += 1

        return True

    async def wait_for_token(
        self,
        key: str = "default",
        timeout: float = 10.0,
        project_id: Optional[str] = None,
    ) -> bool:
        """
        Wait for a rate limit token.

        Args:
            key: Rate limit key
            timeout: Maximum time to wait
            project_id: Tenant scope

        Returns:
            True if token acquired, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.acquire(key, project_id=project_id):
                return True
            await asyncio.sleep(0.1)  # Wait 100ms before retry

        return False

    def get_wait_time(self, key: str = "default", project_id: Optional[str] = None) -> float:
        """
        Get estimated wait time for token.

        Args:
            key: Rate limit key
            project_id: Tenant scope

        Returns:
            Estimated wait time in seconds
        """
        bucket = self._load_bucket(scoped_key(project_id, key))

        if bucket["tokens"] >= 1:
            return 0.0

        tokens_needed = 1 - bucket["tokens"]
        return tokens_needed / self.config.requests_per_second

    def reset(self, key: Optional[str] = None, project_id: Optional[str] = None):
        """Reset shared rate limit state for a scope."""
        if not key:
            logger.warning("RateLimiter.reset() needs a key when using shared state")
            return
        scope = scoped_key(project_id, key)
        self._store.delete(self._bucket_key(scope))
        self._store.delete(self._minute_key(scope))
        self._store.delete(self._hour_key(scope))


class TimeoutWrapper:
    """
    Timeout wrapper for tool execution.

    Provides async timeout with graceful error handling.
    """

    def __init__(self, config: Optional[TimeoutConfig] = None):
        """
        Initialize timeout wrapper.

        Args:
            config: Timeout configuration
        """
        self.config = config or TimeoutConfig()

        # Statistics
        self.stats = {
            "total_executions": 0,
            "timeouts": 0,
            "retries": 0,
            "total_execution_time_ms": 0.0,
        }

    async def execute_with_timeout(
        self,
        handler: Callable[..., Awaitable[Any]],
        *args,
        timeout_seconds: Optional[float] = None,
        retry_count: Optional[int] = None,
        **kwargs,
    ) -> ToolExecutionResult:
        """
        Execute handler with timeout.

        Args:
            handler: Async handler to execute
            *args: Positional arguments for handler
            timeout_seconds: Override default timeout
            retry_count: Override default retry count
            **kwargs: Keyword arguments for handler

        Returns:
            ToolExecutionResult with outcome
        """
        timeout = timeout_seconds or self.config.default_timeout_seconds
        retries = retry_count or self.config.timeout_retry_count

        # Clamp timeout to valid range
        timeout = max(
            self.config.min_timeout_seconds, min(timeout, self.config.max_timeout_seconds)
        )

        attempt = 0
        last_error: Optional[str] = None

        while attempt <= retries:
            attempt += 1
            self.stats["total_executions"] += 1

            if attempt > 1:
                self.stats["retries"] += 1

            start_time = time.time()

            try:
                # Execute with timeout
                result = await asyncio.wait_for(handler(*args, **kwargs), timeout=timeout)

                execution_time_ms = (time.time() - start_time) * 1000
                self.stats["total_execution_time_ms"] += execution_time_ms

                return ToolExecutionResult(
                    success=True,
                    result=result,
                    execution_time_ms=execution_time_ms,
                )

            except asyncio.TimeoutError:
                execution_time_ms = (time.time() - start_time) * 1000
                self.stats["timeouts"] += 1
                self.stats["total_execution_time_ms"] += execution_time_ms

                last_error = f"Timeout after {timeout:.1f}s"
                logger.warning(f"Tool execution timeout: {timeout:.1f}s")

                if attempt <= retries:
                    logger.info(f"Retrying tool execution ({attempt}/{retries})")
                    await asyncio.sleep(0.5 * attempt)  # Exponential backoff

            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                self.stats["total_execution_time_ms"] += execution_time_ms

                return ToolExecutionResult(
                    success=False,
                    error=str(e),
                    execution_time_ms=execution_time_ms,
                )

        # All retries exhausted
        return ToolExecutionResult(
            success=False,
            error=f"Timeout after {retries + 1} attempts: {last_error}",
            timeout_occurred=True,
        )


class ScopeEnforcer:
    """
    Scope restriction enforcer for tool execution.

    Validates tool arguments against allowed scope.
    """

    def __init__(self, config: Optional[ScopeConfig] = None):
        """
        Initialize scope enforcer.

        Args:
            config: Scope configuration
        """
        self.config = config or ScopeConfig()

        # Statistics
        self.stats = {
            "total_checks": 0,
            "scope_violations": 0,
            "url_blocks": 0,
            "path_blocks": 0,
            "operation_blocks": 0,
        }

    def validate(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        category: Optional[ToolCategory] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate arguments against scope.

        Args:
            tool_name: Name of tool being executed
            arguments: Tool arguments to validate
            category: Optional tool category

        Returns:
            Tuple of (is_valid, violation_reason)
        """
        self.stats["total_checks"] += 1

        # Check category
        if category and self.config.allowed_categories:
            if category not in self.config.allowed_categories:
                self.stats["scope_violations"] += 1
                return False, f"Tool category '{category.value}' not allowed"

        # Check URLs
        url_args = ["url", "repo_url", "base_url", "endpoint"]
        for url_arg in url_args:
            if url_arg in arguments:
                url = str(arguments[url_arg])
                if not self._is_url_allowed(url):
                    self.stats["url_blocks"] += 1
                    self.stats["scope_violations"] += 1
                    return False, f"URL not allowed: {url[:50]}"

        # Check file paths
        path_args = ["path", "file_path", "directory", "repo_path"]
        for path_arg in path_args:
            if path_arg in arguments:
                path = str(arguments[path_arg])
                if not self._is_path_allowed(path):
                    self.stats["path_blocks"] += 1
                    self.stats["scope_violations"] += 1
                    return False, f"Path not allowed: {path}"

        # Check blocked operations
        op_args = ["operation", "action", "method"]
        for op_arg in op_args:
            if op_arg in arguments:
                operation = str(arguments[op_arg]).lower()
                if operation in self.config.blocked_operations:
                    self.stats["operation_blocks"] += 1
                    self.stats["scope_violations"] += 1
                    return False, f"Operation not allowed: {operation}"

        return True, None

    def _is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed."""
        if not self.config.allowed_urls:
            return True  # No restrictions

        url_lower = url.lower()
        return any(allowed.lower() in url_lower for allowed in self.config.allowed_urls)

    def _is_path_allowed(self, path: str) -> bool:
        """Check if file path is allowed."""
        if not self.config.allowed_paths:
            return True  # No restrictions

        # Check for path traversal attempts
        if ".." in path or path.startswith("/etc") or path.startswith("/root"):
            return False

        return any(allowed in path for allowed in self.config.allowed_paths)

    def validate_result_size(self, result: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate result size.

        Args:
            result: Tool execution result

        Returns:
            Tuple of (is_valid, violation_reason)
        """
        try:
            result_bytes = len(str(result).encode("utf-8"))
            if result_bytes > self.config.max_result_size_bytes:
                return False, f"Result size ({result_bytes} bytes) exceeds limit"
            return True, None
        except Exception:
            return True, None  # Can't measure, allow by default


class CircuitBreaker:
    """
    Circuit breaker for tool execution.

    Prevents cascading failures by temporarily blocking failing tools.
    """

    class State(Enum):
        CLOSED = "closed"  # Normal operation
        OPEN = "open"  # Blocking calls
        HALF_OPEN = "half_open"  # Testing recovery

    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        state: Optional[SharedState] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
            state: Shared state backend (defaults to the configured one)
        """
        self.config = config or CircuitBreakerConfig()
        self._state_store = state

        # Statistics
        self.stats = {
            "total_calls": 0,
            "circuit_opens": 0,
            "rejected_calls": 0,
            "successful_recoveries": 0,
        }

    @property
    def _store(self) -> SharedState:
        return self._state_store or get_shared_state()

    def _key(self, tool_name: str, project_id: Optional[str]) -> str:
        return scoped_key("toolguard", project_id, tool_name, "circuit")

    def _blank(self) -> Dict[str, Any]:
        return {
            "state": self.State.CLOSED.value,
            "failure_count": 0,
            "success_count": 0,
            "last_failure_time": None,
            "half_open_calls": 0,
        }

    def _load(self, tool_name: str, project_id: Optional[str]) -> Dict[str, Any]:
        """Read shared breaker state (creating a closed one if absent)."""
        state = self._blank()
        raw = self._store.get_json(self._key(tool_name, project_id))
        if raw:
            state.update(raw)
        return state

    def _save(self, tool_name: str, project_id: Optional[str], state: Dict[str, Any]) -> None:
        self._store.set_json(self._key(tool_name, project_id), state, 3600)

    def call_success(self, tool_name: str, project_id: Optional[str] = None):
        """Record successful call."""
        state = self._load(tool_name, project_id)
        state["failure_count"] = 0
        state["success_count"] += 1
        current = self.State(state["state"])

        if current == self.State.HALF_OPEN:
            state["half_open_calls"] += 1

            # Check if we should close the circuit
            if state["success_count"] >= self.config.success_threshold:
                state["state"] = self.State.CLOSED.value
                state["success_count"] = 0
                self.stats["successful_recoveries"] += 1
                logger.info(f"Circuit breaker CLOSED for {tool_name}")

        elif current == self.State.CLOSED:
            # Reset failure count on success
            state["failure_count"] = max(0, state["failure_count"] - 1)

        self._save(tool_name, project_id, state)

    def call_failure(self, tool_name: str, project_id: Optional[str] = None):
        """Record failed call."""
        state = self._load(tool_name, project_id)
        state["failure_count"] += 1
        state["last_failure_time"] = time.time()
        current = self.State(state["state"])

        if current == self.State.HALF_OPEN:
            # Immediately open on failure in half-open state
            state["state"] = self.State.OPEN.value
            state["half_open_calls"] = 0
            self.stats["circuit_opens"] += 1
            logger.warning(f"Circuit breaker OPEN for {tool_name} (failure in half-open)")

        elif current == self.State.CLOSED:
            # Check if we should open the circuit
            if state["failure_count"] >= self.config.failure_threshold:
                state["state"] = self.State.OPEN.value
                self.stats["circuit_opens"] += 1
                logger.warning(f"Circuit breaker OPEN for {tool_name} (threshold reached)")

        self._save(tool_name, project_id, state)

    def can_execute(self, tool_name: str, project_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check if tool can execute.

        Args:
            tool_name: Name of tool
            project_id: Tenant scope

        Returns:
            Tuple of (can_execute, reason)
        """
        self.stats["total_calls"] += 1
        state = self._load(tool_name, project_id)
        current = self.State(state["state"])

        if current == self.State.CLOSED:
            return True, "circuit_closed"

        elif current == self.State.OPEN:
            # Check if timeout has elapsed
            if state["last_failure_time"]:
                elapsed = time.time() - state["last_failure_time"]
                if elapsed >= self.config.timeout_seconds:
                    # Transition to half-open
                    state["state"] = self.State.HALF_OPEN.value
                    state["half_open_calls"] = 0
                    self._save(tool_name, project_id, state)
                    return True, "circuit_half_open"

            self.stats["rejected_calls"] += 1
            return False, "circuit_open"

        else:  # HALF_OPEN
            # Allow limited calls in half-open state
            if state["half_open_calls"] < self.config.half_open_max_calls:
                return True, "circuit_half_open"
            else:
                self.stats["rejected_calls"] += 1
                return False, "circuit_half_open_limit"

    def get_state(self, tool_name: str, project_id: Optional[str] = None) -> State:
        """Get current state for tool."""
        return self.State(self._load(tool_name, project_id)["state"])

    def reset(self, tool_name: Optional[str] = None, project_id: Optional[str] = None):
        """Reset circuit breaker state for a tool."""
        if tool_name:
            self._save(tool_name, project_id, self._blank())
        else:
            logger.warning("CircuitBreaker.reset() needs a tool name with shared state")


class ToolGuardrail:
    """
    Main tool guardrail combining all protection mechanisms.

    Usage:
        guard = ToolGuardrail()

        # Execute with all protections
        result = await guard.execute(
            tool_name="clickhouse_query",
            handler=clickhouse_handler,
            arguments={"query": "SELECT * FROM logs"},
            category=ToolCategory.DATABASE_QUERY,
        )
    """

    def __init__(
        self,
        enable_rate_limit: bool = True,
        enable_timeout: bool = True,
        enable_scope_check: bool = True,
        enable_circuit_breaker: bool = True,
        rate_limit_config: Optional[RateLimitConfig] = None,
        timeout_config: Optional[TimeoutConfig] = None,
        scope_config: Optional[ScopeConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize tool guardrail.

        Args:
            enable_rate_limit: Enable rate limiting
            enable_timeout: Enable timeout wrapper
            enable_scope_check: Enable scope restriction
            enable_circuit_breaker: Enable circuit breaker
            rate_limit_config: Rate limit configuration
            timeout_config: Timeout configuration
            scope_config: Scope configuration
            circuit_breaker_config: Circuit breaker configuration
        """
        self.enable_rate_limit = enable_rate_limit
        self.enable_timeout = enable_timeout
        self.enable_scope_check = enable_scope_check
        self.enable_circuit_breaker = enable_circuit_breaker

        self.rate_limiter = RateLimiter(rate_limit_config)
        self.timeout_wrapper = TimeoutWrapper(timeout_config)
        self.scope_enforcer = ScopeEnforcer(scope_config)
        self.circuit_breaker = CircuitBreaker(circuit_breaker_config)

        # Audit log
        self.audit_log: List[Dict[str, Any]] = []

        # Statistics
        self.stats = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "rate_limited": 0,
            "timeout": 0,
            "scope_violation": 0,
            "circuit_breaker_rejected": 0,
        }

    async def execute(
        self,
        tool_name: str,
        handler: Callable[..., Awaitable[Any]],
        arguments: Dict[str, Any],
        category: Optional[ToolCategory] = None,
        timeout_seconds: Optional[float] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ToolExecutionResult:
        """
        Execute tool with all guardrails.

        Args:
            tool_name: Name of tool
            handler: Async handler function
            arguments: Tool arguments
            category: Tool category
            timeout_seconds: Override timeout
            user_id: User ID for rate limiting
            project_id: Tenant scope; limits and breakers are per project

        Returns:
            ToolExecutionResult with outcome
        """
        self.stats["total_executions"] += 1

        start_time = time.time()
        rate_limit_key = f"{tool_name}:{user_id}" if user_id else tool_name

        # 1. Circuit breaker check
        if self.enable_circuit_breaker:
            can_exec, cb_reason = self.circuit_breaker.can_execute(tool_name, project_id=project_id)
            if not can_exec:
                self.stats["circuit_breaker_rejected"] += 1
                result = ToolExecutionResult(
                    success=False,
                    error=f"Circuit breaker: {cb_reason}",
                    circuit_breaker_open=True,
                )
                self._log_audit(tool_name, arguments, result)
                return result

        # 2. Rate limit check
        if self.enable_rate_limit:
            if not await self.rate_limiter.acquire(rate_limit_key, project_id=project_id):
                self.stats["rate_limited"] += 1
                wait_time = self.rate_limiter.get_wait_time(rate_limit_key, project_id=project_id)
                result = ToolExecutionResult(
                    success=False,
                    error=f"Rate limited. Try again in {wait_time:.1f}s",
                    rate_limited=True,
                )
                self._log_audit(tool_name, arguments, result)
                return result

        # 3. Scope check
        if self.enable_scope_check:
            is_valid, violation = self.scope_enforcer.validate(tool_name, arguments, category)
            if not is_valid:
                self.stats["scope_violation"] += 1
                result = ToolExecutionResult(
                    success=False,
                    error=f"Scope violation: {violation}",
                    scope_violation=True,
                )
                self._log_audit(tool_name, arguments, result)
                return result

        # 4. Execute with timeout
        if self.enable_timeout:
            result = await self.timeout_wrapper.execute_with_timeout(
                handler,
                arguments,
                timeout_seconds=timeout_seconds,
            )
        else:
            # Execute without timeout
            try:
                start_exec = time.time()
                exec_result = await handler(arguments)
                execution_time_ms = (time.time() - start_exec) * 1000
                result = ToolExecutionResult(
                    success=True,
                    result=exec_result,
                    execution_time_ms=execution_time_ms,
                )
            except Exception as e:
                execution_time_ms = (time.time() - start_exec) * 1000
                result = ToolExecutionResult(
                    success=False,
                    error=str(e),
                    execution_time_ms=execution_time_ms,
                )

        # 5. Update circuit breaker
        if self.enable_circuit_breaker:
            if result.success:
                self.circuit_breaker.call_success(tool_name, project_id=project_id)
            else:
                self.circuit_breaker.call_failure(tool_name, project_id=project_id)

        # Update stats
        if result.success:
            self.stats["successful"] += 1
        else:
            self.stats["failed"] += 1
            if result.timeout_occurred:
                self.stats["timeout"] += 1

        # Audit log
        self._log_audit(tool_name, arguments, result)

        return result

    def _log_audit(self, tool_name: str, arguments: Dict[str, Any], result: ToolExecutionResult):
        """Log execution to audit trail."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "arguments": {
                k: v if len(str(v)) < 100 else f"{str(v)[:100]}..." for k, v in arguments.items()
            },
            "success": result.success,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
            "rate_limited": result.rate_limited,
            "timeout_occurred": result.timeout_occurred,
            "scope_violation": result.scope_violation,
            "circuit_breaker_open": result.circuit_breaker_open,
        }
        self.audit_log.append(entry)

        # Keep audit log manageable
        if len(self.audit_log) > 10000:
            self.audit_log = self.audit_log[-10000:]

    def get_audit_log(
        self,
        tool_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries.

        Args:
            tool_name: Filter by tool name
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        entries = self.audit_log

        if tool_name:
            entries = [e for e in entries if e["tool_name"] == tool_name]

        return list(reversed(entries[-limit:]))

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            "executions": self.stats,
            "rate_limiter": self.rate_limiter.stats,
            "timeout": self.timeout_wrapper.stats,
            "scope": self.scope_enforcer.stats,
            "circuit_breaker": self.circuit_breaker.stats,
        }

    def reset_stats(self):
        """Reset all statistics."""
        self.stats = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "rate_limited": 0,
            "timeout": 0,
            "scope_violation": 0,
            "circuit_breaker_rejected": 0,
        }
        self.rate_limiter.stats = {
            "total_requests": 0,
            "rate_limited": 0,
            "tokens_consumed": 0,
        }
        self.timeout_wrapper.stats = {
            "total_executions": 0,
            "timeouts": 0,
            "retries": 0,
            "total_execution_time_ms": 0.0,
        }
        self.scope_enforcer.stats = {
            "total_checks": 0,
            "scope_violations": 0,
            "url_blocks": 0,
            "path_blocks": 0,
            "operation_blocks": 0,
        }
        self.circuit_breaker.stats = {
            "total_calls": 0,
            "circuit_opens": 0,
            "rejected_calls": 0,
            "successful_recoveries": 0,
        }


# Singleton instance
_default_guardrail: Optional[ToolGuardrail] = None


def get_tool_guardrail() -> ToolGuardrail:
    """Get the default tool guardrail instance."""
    global _default_guardrail
    if _default_guardrail is None:
        _default_guardrail = ToolGuardrail()
    return _default_guardrail


def set_tool_guardrail(guardrail: ToolGuardrail):
    """Set a custom tool guardrail instance (useful for testing)."""
    global _default_guardrail
    _default_guardrail = guardrail


# Decorator for tool functions
def with_tool_guardrail(
    tool_name: Optional[str] = None,
    category: Optional[ToolCategory] = None,
    timeout_seconds: Optional[float] = None,
):
    """
    Decorator to wrap tool functions with guardrails.

    Usage:
        @with_tool_guardrail(tool_name="clickhouse_query", category=ToolCategory.DATABASE_QUERY)
        async def clickhouse_handler(arguments):
            ...
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            guardrail = get_tool_guardrail()

            # Extract arguments
            if args and isinstance(args[0], dict):
                arguments = args[0]
            else:
                arguments = kwargs

            # Determine tool name
            name = tool_name or func.__name__

            # Execute with guardrails
            result = await guardrail.execute(
                tool_name=name,
                handler=func,
                arguments=arguments,
                category=category,
                timeout_seconds=timeout_seconds,
            )

            # Raise on failure for decorator pattern
            if not result.success:
                if result.rate_limited:
                    raise RateLimitExceeded(result.error)
                elif result.timeout_occurred:
                    raise TimeoutError(result.error)
                elif result.scope_violation:
                    raise ScopeViolation(result.error)
                else:
                    raise ToolExecutionError(result.error)

            return result.result

        return wrapper

    return decorator


class ToolExecutionError(Exception):
    """Exception for tool execution failures."""

    pass


class RateLimitExceeded(ToolExecutionError):
    """Exception for rate limit exceeded."""

    pass


class ScopeViolation(ToolExecutionError):
    """Exception for scope violation."""

    pass


# CLI for testing
if __name__ == "__main__":
    import asyncio

    async def main():
        guardrail = ToolGuardrail()

        # Mock handler
        async def mock_handler(arguments):
            await asyncio.sleep(0.1)
            return {"result": "success", "data": arguments}

        # Test executions
        test_cases = [
            {"tool": "clickhouse_query", "args": {"query": "SELECT * FROM logs"}},
            {"tool": "clickhouse_query", "args": {"query": "SELECT * FROM errors"}},
            {"tool": "github_tool", "args": {"repo": "owner/repo"}},
        ]

        for test in test_cases:
            print(f"\nExecuting {test['tool']}...")
            result = await guardrail.execute(
                tool_name=test["tool"],
                handler=mock_handler,
                arguments=test["args"],
            )
            print(f"Success: {result.success}")
            if result.error:
                print(f"Error: {result.error}")

        print(f"\nStats: {guardrail.get_stats()}")
        print(f"\nAudit Log: {guardrail.get_audit_log(limit=3)}")

    asyncio.run(main())
