"""
Tool Registry — Registration and selection of agent tools

Production-grade tool registry with:
- Tool registration with name, description, and handler
- OpenAI/Anthropic function calling schema generation
- Intent-based tool selection
- Parameter validation
- Async and sync execution
- Tool categories and metadata
- Tool health monitoring

Usage:
    from tools.registry import ToolRegistry, get_registry, tool

    @tool(
        name="search_code",
        description="Search code semantically",
        parameters={"query": {"type": "string", "description": "Search query"}}
    )
    def search_code(query: str, top_k: int = 5):
        # Tool implementation
        pass

    registry = get_registry()
    result = await registry.execute_tool("search_code", {"query": "authentication"})
"""

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    ParamSpec,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')
P = ParamSpec('P')


class ToolCategory(Enum):
    """Categories of tools for organization."""
    CODE_SEARCH = "code_search"
    DOCUMENT_SEARCH = "document_search"
    DATABASE_QUERY = "database_query"
    SYSTEM = "system"
    MEMORY = "memory"
    UTILITY = "utility"
    API = "api"


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling schema format."""
        schema = {
            "type": self.type,
            "description": self.description,
        }

        if self.enum:
            schema["enum"] = self.enum

        if not self.required and self.default is not None:
            schema["default"] = self.default

        return schema


@dataclass
class ToolMetadata:
    """Metadata about a tool."""
    name: str
    description: str
    category: ToolCategory = ToolCategory.UTILITY
    version: str = "1.0.0"
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    timeout_seconds: int = 30
    async_executable: bool = False
    enabled: bool = True
    requires_approval: bool = False
    approval_action_type: Optional[str] = None
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    read_only: bool = True


@dataclass
class ToolExecutionResult:
    """Result of executing a tool."""
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class Tool:
    """
    Represents a tool that can be called by the agent.

    Wraps a function handler with metadata and parameter definitions.
    """

    def __init__(
        self,
        name: str,
        handler: Union[Callable, Callable[..., Awaitable]],
        description: str = "",
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
        metadata: Optional[ToolMetadata] = None,
    ):
        """
        Initialize a tool.

        Args:
            name: Unique tool name
            handler: Function to execute (sync or async)
            description: What the tool does
            parameters: Parameter definitions in OpenAI schema format
            metadata: Additional tool metadata
        """
        self.name = name
        self.handler = handler
        self.description = description or f"Execute {name}"
        self.metadata = metadata or ToolMetadata(name=name, description=description)

        # Parse parameters
        self.parameters: Dict[str, ToolParameter] = {}
        if parameters:
            for param_name, param_def in parameters.items():
                self.parameters[param_name] = ToolParameter(
                    name=param_name,
                    type=param_def.get("type", "string"),
                    description=param_def.get("description", ""),
                    required=param_def.get("required", True),
                    default=param_def.get("default"),
                    enum=param_def.get("enum"),
                )

        # Detect if handler is async
        self.is_async = inspect.iscoroutinefunction(handler)
        self.metadata.async_executable = self.is_async

        # Extract parameters from function signature if not provided
        if not self.parameters:
            self._extract_parameters_from_signature()

    def _extract_parameters_from_signature(self):
        """Extract parameter definitions from function signature."""
        sig = inspect.signature(self.handler)

        # Debug logging
        logger.info(f"Extracting parameters for tool '{self.name}'")
        logger.info(f"Function signature: {sig}")
        logger.info(f"Function parameters: {list(sig.parameters.keys())}")

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                annotation_str = str(param.annotation)
                if "int" in annotation_str.lower():
                    param_type = "integer"
                elif "float" in annotation_str.lower() or "double" in annotation_str.lower():
                    param_type = "number"
                elif "bool" in annotation_str.lower():
                    param_type = "boolean"
                elif "list" in annotation_str.lower() or "dict" in annotation_str.lower():
                    param_type = "object"

            required = param.default == inspect.Parameter.empty
            default = None if required else param.default

            logger.info(f"  Parameter '{param_name}': type={param_type}, required={required}, default={default}")

            self.parameters[param_name] = ToolParameter(
                name=param_name,
                type=param_type,
                required=required,
                default=default,
            )

    async def execute(
        self,
        arguments: Dict[str, Any],
        timeout_seconds: Optional[int] = None,
    ) -> ToolExecutionResult:
        """
        Execute the tool with arguments.

        Args:
            arguments: Keyword arguments for the tool
            timeout_seconds: Override default timeout

        Returns:
            ToolExecutionResult with outcome
        """
        start_time = datetime.now()

        try:
            # Validate required parameters
            missing_params = [
                name for name, param in self.parameters.items()
                if param.required and name not in arguments
            ]

            if missing_params:
                logger.error(f"Tool {self.name} - Missing required parameters: {missing_params}")
                logger.error(f"Tool {self.name} - Available parameters: {list(self.parameters.keys())}")
                logger.error(f"Tool {self.name} - Required parameters: {[name for name, param in self.parameters.items() if param.required]}")
                logger.error(f"Tool {self.name} - Provided arguments: {list(arguments.keys())}")
                raise ValueError(f"Missing required parameters: {missing_params}")

            # Filter out unexpected arguments to avoid TypeError
            # Only pass arguments that the handler accepts
            import inspect
            sig = inspect.signature(self.handler)
            valid_params = set(sig.parameters.keys())

            # Keep only arguments that are in the handler's signature
            filtered_arguments = {
                k: v for k, v in arguments.items()
                if k in valid_params
            }

            # Log if we filtered any arguments (for debugging)
            if len(filtered_arguments) < len(arguments):
                filtered_keys = set(arguments.keys()) - set(filtered_arguments.keys())
                logger.warning(f"Tool {self.name}: Filtered unexpected parameters: {filtered_keys}")
                logger.debug(f"Tool {self.name}: Handler signature params: {valid_params}")
                logger.debug(f"Tool {self.name}: Provided arguments: {set(arguments.keys())}")

            # Execute with timeout
            timeout = timeout_seconds or self.metadata.timeout_seconds

            if self.is_async:
                result = await asyncio.wait_for(
                    self.handler(**filtered_arguments),
                    timeout=timeout,
                )
            else:
                # Run sync function in executor to avoid blocking
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self.handler(**filtered_arguments)),
                    timeout=timeout,
                )

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return ToolExecutionResult(
                tool_name=self.name,
                success=True,
                result=result,
                execution_time_ms=execution_time,
            )

        except asyncio.TimeoutError:
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=f"Tool execution exceeded timeout ({timeout}s)",
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Tool {self.name} execution failed: {e}")
            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )

    def to_openai_schema(self) -> dict:
        """
        Generate OpenAI function calling schema.

        Returns:
            Dictionary in OpenAI function format
        """
        properties = {}
        required = []

        for param_name, param in self.parameters.items():
            properties[param_name] = param.to_openai_schema()
            if param.required:
                required.append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_anthropic_schema(self) -> dict:
        """
        Generate Anthropic tool use schema.

        Returns:
            Dictionary in Anthropic tool format
        """
        input_schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for param_name, param in self.parameters.items():
            input_schema["properties"][param_name] = param.to_openai_schema()
            if param.required:
                input_schema["required"].append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": input_schema,
        }

    def __repr__(self) -> str:
        return f"Tool(name={self.name}, category={self.metadata.category.value})"


class ToolRegistry:
    """
    Production-grade tool registry.

    Features:
    - Tool registration and management
    - Intent-to-tool mapping
    - Multi-provider schema generation (OpenAI, Anthropic)
    - Tool execution with error handling
    - Tool health monitoring
    - Tool categories and filtering
    """

    # Intent keywords mapped to tool names for routing
    INTENT_KEYWORDS: Dict[str, List[str]] = {
        "code_search": [
            "search code", "find code", "code", "function", "class",
            "implementation", "how does", "where is", "locate",
            "source code", "repository", "show me the"
        ],
        "document_search": [
            "search docs", "documentation", "readme", "guide", "how to",
            "authenticate", "authorization", "api docs"
        ],
        "clickhouse_query": [
            "database", "query", "sql", "logs", "metrics", "recent",
            "error rate", "latency", "performance data", "observability",
            "clickhouse", "monitoring data"
        ],
    }

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._intent_to_tool: Dict[str, str] = {}
        self._execution_stats: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: Optional[str] = None,
        description: str = "",
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
        category: ToolCategory = ToolCategory.UTILITY,
        **metadata_kwargs
    ):
        """
        Decorator for registering tools.

        Usage:
            @registry.register(name="my_tool", description="Does something")
            def my_function(arg1: str, arg2: int = 5):
                return {"result": "done"}

        Args:
            name: Tool name (default: function name)
            description: Tool description
            parameters: Parameter definitions
            category: Tool category
            **metadata_kwargs: Additional metadata
        """
        def decorator(func: Callable):
            tool_name = name or func.__name__

            metadata = ToolMetadata(
                name=tool_name,
                description=description,
                category=category,
                **metadata_kwargs
            )

            tool = Tool(
                name=tool_name,
                handler=func,
                description=description,
                parameters=parameters,
                metadata=metadata,
            )

            self._tools[tool_name] = tool
            self._execution_stats[tool_name] = {
                "calls": 0,
                "errors": 0,
                "total_time_ms": 0,
            }

            logger.info(f"Registered tool: {tool_name} ({category.value})")
            return func

        return decorator

    def register_tool(self, tool: Tool) -> None:
        """
        Register an existing Tool instance.

        Args:
            tool: Tool instance to register
        """
        self._tools[tool.name] = tool
        self._execution_stats[tool.name] = {
            "calls": 0,
            "errors": 0,
            "total_time_ms": 0,
        }
        logger.info(f"Registered tool: {tool.name}")

    def register_manual(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
        requires_approval: bool = False,
        approval_action_type: Optional[str] = None,
        risk_level: Literal["low", "medium", "high", "critical"] = "low",
        read_only: bool = True,
        category: ToolCategory = ToolCategory.UTILITY,
        **kwargs
    ) -> None:
        """
        Manually register a tool (non-decorator).

        Args:
            name: Tool name
            handler: Function to call
            description: Tool description
            parameters: Parameter definitions
            requires_approval: Whether tool requires approval before execution
            approval_action_type: Action type for approval (default: tool name)
            risk_level: Risk level for approval (low/medium/high/critical)
            read_only: Whether tool is read-only (no side effects)
            category: Tool category
            **kwargs: Additional metadata
        """
        # Add approval metadata to kwargs
        kwargs.update({
            "requires_approval": requires_approval,
            "approval_action_type": approval_action_type,
            "risk_level": risk_level,
            "read_only": read_only
        })

        tool = Tool(
            name=name,
            handler=handler,
            description=description,
            parameters=parameters,
            metadata=ToolMetadata(
                name=name,
                description=description,
                category=category,
                **kwargs
            ),
        )

        self.register_tool(tool)

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        enabled_only: bool = True,
    ) -> List[Tool]:
        """
        List all registered tools.

        Args:
            category: Filter by category
            enabled_only: Only return enabled tools

        Returns:
            List of tools
        """
        tools = list(self._tools.values())

        if category:
            tools = [t for t in tools if t.metadata.category == category]

        if enabled_only:
            tools = [t for t in tools if t.metadata.enabled]

        return tools

    def list_tool_names(self, **kwargs) -> List[str]:
        """Get list of tool names."""
        return [t.name for t in self.list_tools(**kwargs)]

    @property
    def tool_names(self) -> List[str]:
        """All tool names."""
        return list(self._tools.keys())

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        timeout_seconds: Optional[int] = None,
    ) -> ToolExecutionResult:
        """
        Execute a tool by name with automatic approval enforcement.

        Args:
            name: Tool name
            arguments: Tool arguments
            timeout_seconds: Override timeout

        Returns:
            ToolExecutionResult
        """
        tool = self.get(name)

        if not tool:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' not found",
            )

        if not tool.metadata.enabled:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' is disabled",
            )

        # Automatic approval enforcement for write operations
        if tool.metadata.requires_approval and not tool.metadata.read_only:
            from guardrails.approval_guard import get_approval_guard

            approval_guard = get_approval_guard()

            # Auto-generate plan from tool description and arguments
            plan = self._generate_approval_plan(tool, arguments)

            # Request approval
            try:
                approval = await approval_guard.request_approval(
                    action_type=tool.metadata.approval_action_type or name,
                    plan=plan,
                    metadata={
                        "tool": name,
                        "arguments": self._sanitize_arguments(arguments),
                        "risk_level": tool.metadata.risk_level
                    },
                    timeout_seconds=timeout_seconds or tool.metadata.timeout_seconds
                )

                if not approval.approved:
                    logger.info(f"Tool '{name}' execution rejected: {approval.reason}")
                    return ToolExecutionResult(
                        tool_name=name,
                        success=False,
                        error=f"Action not approved: {approval.reason or 'No reason provided'}",
                    )

            except Exception as e:
                logger.error(f"Approval check failed for tool '{name}': {e}")
                return ToolExecutionResult(
                    tool_name=name,
                    success=False,
                    error=f"Approval check failed: {str(e)}",
                )

        # Update stats
        self._execution_stats[name]["calls"] += 1

        result = await tool.execute(arguments, timeout_seconds)

        # Update stats
        if not result.success:
            self._execution_stats[name]["errors"] += 1
        if result.execution_time_ms:
            self._execution_stats[name]["total_time_ms"] += result.execution_time_ms

        return result

    def route_by_intent(self, intent: str) -> Optional[str]:
        """
        Route an intent to the appropriate tool.

        Args:
            intent: User intent description

        Returns:
            Tool name or None
        """
        # Direct intent to tool mapping (priority order)
        INTENT_TO_TOOL = {
            "search_code": "search_code",
            "database_query": "clickhouse_query",
            "document_search": "rag_search",
            "incident_investigation": "get_error_rate",
            "gap_detection": "detect_documentation_gaps",
            "config_generation": "generate_config",
            "dashboard_management": "create_grafana_dashboard",
            "ticket_management": "draft_github_issue",
            "status_check": "get_error_rate",
        }

        # First try direct mapping
        if intent in INTENT_TO_TOOL:
            tool_name = INTENT_TO_TOOL[intent]
            if tool_name in self._tools:
                return tool_name

        # Fallback: check if any tool name matches the intent
        if intent in self._tools:
            return intent

        return None

    def _generate_approval_plan(self, tool: 'Tool', arguments: Dict[str, Any]) -> List[str]:
        """
        Generate step-by-step plan from tool metadata and arguments.

        Args:
            tool: Tool instance
            arguments: Tool arguments

        Returns:
            List of plan steps
        """
        plan = [
            f"Tool: {tool.name}",
            f"Action: {tool.description}",
            f"Risk Level: {tool.metadata.risk_level}",
        ]

        # Add category info
        if tool.metadata.category != ToolCategory.UTILITY:
            plan.append(f"Category: {tool.metadata.category.value}")

        # Add argument details (sanitized)
        if arguments:
            plan.append("Parameters:")
            for key, value in arguments.items():
                # Sanitize sensitive values
                if self._is_sensitive_parameter(key):
                    plan.append(f"  {key}: [REDACTED]")
                else:
                    # Truncate long values
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    plan.append(f"  {key}: {value_str}")

        return plan

    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize arguments for logging/metadata by redacting sensitive values.

        Args:
            arguments: Original arguments

        Returns:
            Sanitized arguments dictionary
        """
        sanitized = {}
        for key, value in arguments.items():
            if self._is_sensitive_parameter(key):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_arguments(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_arguments(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 200:
                    sanitized[key] = value_str[:200] + "..."
                else:
                    sanitized[key] = value
        return sanitized

    def _is_sensitive_parameter(self, param_name: str) -> bool:
        """
        Check if a parameter name indicates sensitive data.

        Args:
            param_name: Parameter name to check

        Returns:
            True if parameter appears to be sensitive
        """
        sensitive_keywords = [
            "password", "passwd", "pwd",
            "token", "api_key", "apikey", "api-key",
            "secret", "private_key", "private-key",
            "credential", "auth",
            "session", "cookie"
        ]

        param_lower = param_name.lower()
        return any(keyword in param_lower for keyword in sensitive_keywords)

    def get_openai_schemas(self, **kwargs) -> List[dict]:
        """Get all tools as OpenAI function schemas."""
        return [t.to_openai_schema() for t in self.list_tools(**kwargs)]

    def get_anthropic_schemas(self, **kwargs) -> List[dict]:
        """Get all tools as Anthropic tool schemas."""
        return [t.to_anthropic_schema() for t in self.list_tools(**kwargs)]

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get execution statistics for all tools."""
        return self._execution_stats.copy()

    def clear_stats(self):
        """Clear all execution statistics."""
        for name in self._execution_stats:
            self._execution_stats[name] = {
                "calls": 0,
                "errors": 0,
                "total_time_ms": 0,
            }

    def enable_tool(self, name: str) -> bool:
        """Enable a tool."""
        tool = self.get(name)
        if tool:
            tool.metadata.enabled = True
            return True
        return False

    def disable_tool(self, name: str) -> bool:
        """Disable a tool."""
        tool = self.get(name)
        if tool:
            tool.metadata.enabled = False
            return True
        return False

    def __repr__(self) -> str:
        enabled = sum(1 for t in self._tools.values() if t.metadata.enabled)
        return f"ToolRegistry(tools={len(self._tools)}, enabled={enabled})"


# Convenience decorator
def tool(
    name: Optional[str] = None,
    description: str = "",
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    category: ToolCategory = ToolCategory.UTILITY,
    requires_approval: bool = False,
    approval_action_type: Optional[str] = None,
    risk_level: Literal["low", "medium", "high", "critical"] = "low",
    read_only: bool = True,
    **kwargs
):
    """
    Convenience decorator for registering tools.

    Usage:
        @tool(
            name="my_tool",
            description="Does something",
            requires_approval=False,
            read_only=True
        )
        def my_function(arg1: str):
            return {"result": "done"}

    Args:
        name: Tool name (default: function name)
        description: Tool description
        parameters: Parameter definitions in OpenAI schema format
        category: Tool category
        requires_approval: Whether tool requires approval before execution
        approval_action_type: Action type for approval (default: tool name)
        risk_level: Risk level for approval (low/medium/high/critical)
        read_only: Whether tool is read-only (no side effects)
        **kwargs: Additional metadata
    """
    registry = get_registry()

    # Add approval metadata to kwargs
    kwargs.update({
        "requires_approval": requires_approval,
        "approval_action_type": approval_action_type,
        "risk_level": risk_level,
        "read_only": read_only
    })

    return registry.register(
        name=name,
        description=description,
        parameters=parameters,
        category=category,
        **kwargs
    )


# Singleton instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry():
    """Reset the global registry (mainly for testing)."""
    global _registry
    _registry = None
