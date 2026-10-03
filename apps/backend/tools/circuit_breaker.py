"""
Circuit Breaker Pattern - Production-Grade Fault Tolerance

Implements the Circuit Breaker pattern for tool execution to prevent
cascading failures and improve system resilience.

Features:
- State tracking (Closed, Open, Half-Open)
- Failure threshold configuration
- Recovery timeout handling
- Statistics and monitoring
- Automatic reset on recovery
- Tool-specific configuration
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from shared.state import SharedState, get_shared_state, scoped_key

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: int = 60  # Seconds before trying half-open
    success_threshold: int = 2  # Successes in half-open before closing
    timeout_seconds: int = 30  # Individual request timeout
    monitoring_period: int = 300  # How long to keep stats (seconds)
    half_open_max_calls: int = 3  # Max calls allowed in half-open state


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    timeout_calls: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    current_state: CircuitState = CircuitState.CLOSED
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    failure_rate: float = 0.0
    average_response_time_ms: float = 0.0


class CircuitBreaker:
    """
    Circuit breaker for tool execution fault tolerance.

    Prevents cascading failures by stopping calls to failing tools
    and allowing them time to recover.
    """

    def __init__(
        self,
        tool_name: str,
        config: Optional[CircuitBreakerConfig] = None,
        scope: Optional[str] = None,
        state: Optional[SharedState] = None,
    ):
        """
        Initialize circuit breaker for a tool.

        Args:
            tool_name: Name of the tool this breaker protects
            config: Circuit breaker configuration
            scope: Tenant scope (project id); breakers are keyed per tenant
            state: Shared state backend (defaults to the configured one)
        """
        self.tool_name = tool_name
        self.config = config or CircuitBreakerConfig()
        self.scope = scope
        self._state_store = state

        # State management
        self._state = CircuitState.CLOSED
        self._state_lock = asyncio.Lock()

        # Failure tracking
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        _last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None

        # Response time tracking
        self._response_times: List[float] = []
        self._max_response_times = 100

        # Statistics
        self.stats = CircuitBreakerStats(current_state=CircuitState.CLOSED)

        logger.info(f"✅ CircuitBreaker initialized for tool: {tool_name}")

    @property
    def state(self) -> CircuitState:
        """Get current circuit breaker state (thread-safe)."""
        return self._state

    # ── Shared state ──────────────────────────────────────────────────

    def _shared(self) -> SharedState:
        return self._state_store or get_shared_state()

    def _state_key(self) -> str:
        return scoped_key("breaker", self.scope, self.tool_name)

    def _persist_ttl(self) -> int:
        return max(300, self.config.recovery_timeout * 3)

    def _load(self) -> None:
        """Adopt state written by another replica, if any."""
        try:
            snapshot = self._shared().get_json(self._state_key())
        except Exception as exc:  # backend hiccup must not break execution
            logger.debug(f"CircuitBreaker: state load failed for {self.tool_name}: {exc}")
            return
        if not snapshot:
            return
        try:
            self._state = CircuitState(snapshot["state"])
            self._failure_count = int(snapshot.get("failure_count", 0))
            self._success_count = int(snapshot.get("success_count", 0))
            self._last_failure_time = snapshot.get("last_failure_time")
            self.stats.current_state = self._state
        except Exception as exc:
            logger.debug(f"CircuitBreaker: ignoring bad state snapshot: {exc}")

    def _save(self) -> None:
        """Publish this breaker's state for other replicas."""
        try:
            self._shared().set_json(
                self._state_key(),
                {
                    "state": self._state.value,
                    "failure_count": self._failure_count,
                    "success_count": self._success_count,
                    "last_failure_time": self._last_failure_time,
                    "updated_at": time.time(),
                },
                self._persist_ttl(),
            )
        except Exception as exc:
            logger.debug(f"CircuitBreaker: state save failed for {self.tool_name}: {exc}")

    def can_execute(self) -> bool:
        """
        Check if tool execution is allowed.

        Returns:
            True if execution is allowed, False if circuit is open
        """
        self._load()

        # Auto-reset from half-open to closed if recovery timeout passed
        if self._state == CircuitState.HALF_OPEN:
            if (
                self._last_failure_time
                and time.time() - self._last_failure_time > self.config.recovery_timeout
            ):
                self._transition_to_closed("Recovery timeout elapsed, resetting to closed")

        return self._state != CircuitState.OPEN

    def record_failure(self, error: Optional[str] = None) -> None:
        """
        Record a tool execution failure.

        Args:
            error: Optional error message
        """
        self._load()
        self._failure_count += 1
        self._last_failure_time = time.time()
        self.stats.failed_calls += 1
        self.stats.last_failure_time = datetime.now()
        self.stats.failure_rate = (
            self.stats.failed_calls / self.stats.total_calls if self.stats.total_calls > 0 else 0
        )

        logger.warning(
            f"CircuitBreaker: Failure recorded for {self.tool_name} "
            f"(count: {self._failure_count}/{self.config.failure_threshold})"
        )

        # Check if we should open the circuit
        if self._failure_count >= self.config.failure_threshold:
            self._transition_to_open(f"Failure threshold reached: {self._failure_count} failures")

        self._save()

    def record_success(self, execution_time_ms: Optional[float] = None) -> None:
        """
        Record a tool execution success.

        Args:
            execution_time_ms: Execution time in milliseconds
        """
        self._load()
        self._success_count += 1
        self._last_success_time = time.time()
        self.stats.successful_calls += 1
        self.stats.last_success_time = datetime.now()
        self.stats.failure_rate = (
            self.stats.failed_calls / self.stats.total_calls if self.stats.total_calls > 0 else 0
        )

        # Track response time
        if execution_time_ms is not None:
            self._response_times.append(execution_time_ms)
            if len(self._response_times) > self._max_response_times:
                self._response_times = self._response_times[-self._max_response_times :]
            self.stats.average_response_time_ms = sum(self._response_times) / len(
                self._response_times
            )

        # In half-open state, successes lead back to closed
        if self._state == CircuitState.HALF_OPEN:
            if self._success_count >= self.config.success_threshold:
                self._transition_to_closed(f"Recovered after {self._success_count} successes")

        # Reset failure count in closed state (gradual recovery)
        if self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

        self._save()

    async def execute_with_protection(self, tool_func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute tool function with circuit breaker protection.

        Args:
            tool_func: Tool function to execute
            *args: Positional arguments for tool function
            **kwargs: Keyword arguments for tool function

        Returns:
            Result from tool function

        Raises:
            RuntimeError: If circuit is open
        """
        if not self.can_execute():
            raise RuntimeError(
                f"Circuit breaker is OPEN for tool '{self.tool_name}'. "
                f"Tool execution blocked to prevent cascading failures. "
                f"Will attempt recovery at {datetime.fromtimestamp(self._last_failure_time + self.config.recovery_timeout)}."
            )

        self.stats.total_calls += 1

        # Record start time
        start_time = time.time()

        try:
            # Execute the tool
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(*args, **kwargs)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool_func(*args, **kwargs)),
                    timeout=self.config.timeout_seconds,
                )

            execution_time_ms = (time.time() - start_time) * 1000

            # Record success
            self.record_success(execution_time_ms)

            return result

        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            self._handle_timeout(execution_time_ms)
            raise

        except Exception as e:
            # Record failure
            execution_time_ms = (time.time() - start_time) * 1000
            self.record_failure(str(e))
            raise

    def _handle_timeout(self, execution_time_ms: float) -> None:
        """Handle execution timeout."""
        self.stats.timeout_calls += 1
        self.record_failure("Execution timeout")

        # Timeouts can open circuit faster if multiple occur
        if self.stats.timeout_calls >= 3:
            self._transition_to_open("Multiple execution timeouts")

    def _transition_to_open(self, reason: str) -> None:
        """Transition circuit breaker to open state."""
        if self._state == CircuitState.OPEN:
            return

        old_state = self._state
        self._state = CircuitState.OPEN

        self.stats.current_state = CircuitState.OPEN
        self.stats.state_transitions.append(
            {
                "from": old_state.value,
                "to": CircuitState.OPEN.value,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.error(
            f"CircuitBreaker: {self.tool_name} opened due to: {reason}. "
            f"Tool execution blocked for {self.config.recovery_timeout}s."
        )
        self._save()

    def _transition_to_half_open(self, reason: str) -> None:
        """Transition circuit breaker to half-open state."""
        if self._state == CircuitState.HALF_OPEN:
            return

        old_state = self._state
        self._state = CircuitState.HALF_OPEN

        self.stats.current_state = CircuitState.HALF_OPEN
        self.stats.state_transitions.append(
            {
                "from": old_state.value,
                "to": CircuitState.HALF_OPEN.value,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(
            f"CircuitBreaker: {self.tool_name} transitioned to HALF_OPEN due to: {reason}. "
            f"Testing with max {self.config.half_open_max_calls} calls."
        )
        self._save()

    def _transition_to_closed(self, reason: str) -> None:
        """Transition circuit breaker to closed state."""
        if self._state == CircuitState.CLOSED:
            return

        old_state = self._state
        self._state = CircuitState.CLOSED

        # Reset counters
        self._failure_count = 0
        self._success_count = 0

        self.stats.current_state = CircuitState.CLOSED
        self.stats.state_transitions.append(
            {
                "from": old_state.value,
                "to": CircuitState.CLOSED.value,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(
            f"CircuitBreaker: {self.tool_name} transitioned to CLOSED due to: {reason}. "
            f"Tool execution resumed."
        )
        self._save()

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self._transition_to_closed("Manual reset")

    def get_status(self) -> Dict[str, Any]:
        """
        Get current circuit breaker status.

        Returns:
            Status dictionary
        """
        return {
            "tool_name": self.tool_name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.config.failure_threshold,
            "recovery_timeout": self.config.recovery_timeout,
            "can_execute": self.can_execute(),
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful_calls": self.stats.successful_calls,
                "failed_calls": self.stats.failed_calls,
                "rejected_calls": self.stats.rejected_calls,
                "timeout_calls": self.stats.timeout_calls,
                "failure_rate": self.stats.failure_rate,
                "average_response_time_ms": self.stats.average_response_time_ms,
                "last_failure_time": (
                    self.stats.last_failure_time.isoformat()
                    if self.stats.last_failure_time
                    else None
                ),
                "last_success_time": (
                    self.stats.last_success_time.isoformat()
                    if self.stats.last_success_time
                    else None
                ),
            },
        }


class CircuitBreakerRegistry:
    """
    Registry for managing circuit breakers across tools.

    Provides centralized circuit breaker management and monitoring.
    """

    def __init__(self):
        """Initialize circuit breaker registry."""
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.lock = asyncio.Lock()

        logger.info("✅ CircuitBreakerRegistry initialized")

    async def get_breaker(
        self,
        tool_name: str,
        config: Optional[CircuitBreakerConfig] = None,
        project_id: Optional[str] = None,
    ) -> CircuitBreaker:
        """
        Get or create circuit breaker for a tool within a tenant.

        Args:
            tool_name: Name of the tool
            config: Optional configuration
            project_id: Tenant scope; each project gets its own breaker

        Returns:
            CircuitBreaker instance
        """
        key = scoped_key(project_id, tool_name)
        async with self.lock:
            if key not in self.breakers:
                self.breakers[key] = CircuitBreaker(tool_name, config, scope=project_id)
                logger.info(f"Created circuit breaker for tool: {tool_name} (scope={project_id})")

            return self.breakers[key]

    def has_breaker(self, tool_name: str, project_id: Optional[str] = None) -> bool:
        """Check if a tool has a circuit breaker in this tenant."""
        return scoped_key(project_id, tool_name) in self.breakers

    async def execute_with_breaker(
        self,
        tool_name: str,
        tool_func: Callable,
        *args: Any,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute tool function with circuit breaker protection.

        Args:
            tool_name: Name of the tool
            tool_func: Tool function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from tool function

        Raises:
            RuntimeError: If circuit is open
        """
        breaker = await self.get_breaker(tool_name, project_id=project_id)
        return await breaker.execute_with_protection(tool_func, *args, **kwargs)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all circuit breakers.

        Returns:
            Dictionary of breaker statuses
        """
        return {tool_name: breaker.get_status() for tool_name, breaker in self.breakers.items()}

    def reset_breaker(self, tool_name: str, project_id: Optional[str] = None) -> bool:
        """
        Manually reset a circuit breaker.

        Args:
            tool_name: Name of the tool
            project_id: Tenant scope of the breaker

        Returns:
            True if breaker was found and reset
        """
        key = scoped_key(project_id, tool_name)
        if key in self.breakers:
            self.breakers[key].reset()
            logger.info(f"Manually reset circuit breaker for: {tool_name} (scope={project_id})")
            return True
        return False

    def reset_all_breakers(self) -> None:
        """Reset all circuit breakers to closed state."""
        for tool_name, breaker in self.breakers.items():
            breaker.reset()
        logger.info("Reset all circuit breakers")

    def get_system_stats(self) -> Dict[str, Any]:
        """
        Get system-wide circuit breaker statistics.

        Returns:
            System statistics
        """
        total_breakers = len(self.breakers)
        open_breakers = sum(
            1 for breaker in self.breakers.values() if breaker.state == CircuitState.OPEN
        )
        half_open_breakers = sum(
            1 for breaker in self.breakers.values() if breaker.state == CircuitState.HALF_OPEN
        )

        all_stats = {
            "total_breakers": total_breakers,
            "open_breakers": open_breakers,
            "half_open_breakers": half_open_breakers,
            "closed_breakers": total_breakers - open_breakers - half_open_breakers,
            "timestamp": datetime.now().isoformat(),
        }

        # Aggregate stats
        total_calls = 0
        total_failures = 0
        total_rejected = 0

        for breaker in self.breakers.values():
            stats = breaker.stats
            total_calls += stats.total_calls
            total_failures += stats.failed_calls
            total_rejected += stats.rejected_calls

        all_stats.update(
            {
                "total_calls": total_calls,
                "total_failures": total_failures,
                "total_rejected": total_rejected,
                "system_failure_rate": (total_failures / total_calls if total_calls > 0 else 0),
            }
        )

        return all_stats


# Global singleton
_circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None
_registry_lock = asyncio.Lock()


async def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry instance."""
    global _circuit_breaker_registry

    if _circuit_breaker_registry is None:
        async with _registry_lock:
            if _circuit_breaker_registry is None:
                _circuit_breaker_registry = CircuitBreakerRegistry()

    return _circuit_breaker_registry


def set_circuit_breaker_registry(registry: CircuitBreakerRegistry) -> None:
    """Set a custom circuit breaker registry instance (useful for testing)."""
    global _circuit_breaker_registry
    _circuit_breaker_registry = registry


# Helper function to integrate circuit breaker into tool execution
async def execute_with_circuit_breaker(
    tool_name: str, tool_func: Callable, *args: Any, **kwargs: Any
) -> Any:
    """
    Convenience function to execute tool with circuit breaker protection.

    Usage:
        result = await execute_with_circuit_breaker(
            "clickhouse_query",
            my_query_function,
            natural_query="Show errors"
        )
    """
    registry = await get_circuit_breaker_registry()
    return await registry.execute_with_breaker(tool_name, tool_func, *args, **kwargs)
