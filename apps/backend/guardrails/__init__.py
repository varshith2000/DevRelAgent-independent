"""Guardrails package for DevRelAgent."""

from guardrails.input_guard import (
    InputGuardrail,
    GuardrailResult,
    TopicClassifier,
    PIIScrubber,
    PromptInjectionDetector,
    TopicCategory,
    get_input_guardrail,
    set_input_guardrail,
    validate_input,
)

from guardrails.output_guard import (
    OutputGuardrail,
    OutputValidationResult,
    SQLSafetyValidator,
    ResponseGroundingChecker,
    HITLGateEnforcer,
    OutputPIIChecker,
    GroundingStatus,
    get_output_guardrail,
    set_output_guardrail,
    validate_output,
)

from guardrails.tool_guard import (
    ToolGuardrail,
    ToolExecutionResult,
    ToolCategory,
    RateLimiter,
    TimeoutWrapper,
    ScopeEnforcer,
    CircuitBreaker,
    RateLimitConfig,
    TimeoutConfig,
    ScopeConfig,
    CircuitBreakerConfig,
    get_tool_guardrail,
    set_tool_guardrail,
    with_tool_guardrail,
    ToolExecutionError,
    RateLimitExceeded,
    ScopeViolation,
)

from guardrails.sql_guard import (
    SQLGuard,
    SQLViolation,
    SQLViolationType,
    is_safe_sql,
    validate_and_sanitize_sql,
    get_sql_guard,
)

__all__ = [
    # Input guardrails
    "InputGuardrail",
    "GuardrailResult",
    "TopicClassifier",
    "PIIScrubber",
    "PromptInjectionDetector",
    "TopicCategory",
    "get_input_guardrail",
    "set_input_guardrail",
    "validate_input",
    
    # Output guardrails
    "OutputGuardrail",
    "OutputValidationResult",
    "SQLSafetyValidator",
    "ResponseGroundingChecker",
    "HITLGateEnforcer",
    "OutputPIIChecker",
    "GroundingStatus",
    "get_output_guardrail",
    "set_output_guardrail",
    "validate_output",
    
    # Tool guardrails
    "ToolGuardrail",
    "ToolExecutionResult",
    "ToolCategory",
    "RateLimiter",
    "TimeoutWrapper",
    "ScopeEnforcer",
    "CircuitBreaker",
    "RateLimitConfig",
    "TimeoutConfig",
    "ScopeConfig",
    "CircuitBreakerConfig",
    "get_tool_guardrail",
    "set_tool_guardrail",
    "with_tool_guardrail",
    "ToolExecutionError",
    "RateLimitExceeded",
    "ScopeViolation",
    
    # SQL guard (legacy)
    "SQLGuard",
    "SQLViolation",
    "SQLViolationType",
    "is_safe_sql",
    "validate_and_sanitize_sql",
    "get_sql_guard",
]
