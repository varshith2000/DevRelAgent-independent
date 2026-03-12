"""
Agent Loop — Core Cognitive Pipeline with Tool Integration and Guardrails

Implements: Guardrails → Perception → Routing → Memory → Action → Response → Guardrails

This is the main orchestration module. Each cognitive layer is a step:
0. Guardrails: Input validation (topic, PII, injection detection)
1. Perception: Parse user query, extract intent and entities
2. Routing: Classify intent, select tool(s) using registry
3. Memory: Check conversation history, KeDB, RAG for context
4. Action: Execute selected tool(s) with tool guardrails
5. Response: Generate final response with tool results
6. Output Guardrails: Validate response (SQL safety, grounding, HITL)

Usage:
    from agent.loop import AgentLoop

    loop = AgentLoop()
    response, tool_calls = await loop.process_with_tools("How do I authenticate?")

    # Or with streaming
    async for chunk in loop.process_stream("Show recent errors"):
        print(chunk)
"""

import asyncio
import logging
import sys
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime
import re

from agent.llm_provider import llm_generate
from agent.router import classify_intent
from models.schemas import (
    PerceptionResult,
    SessionContext,
    ToolCallResult,
    StructuredAgentResponse,
    AgentObservation,
    EvidenceItem,
)
from tools.registry import get_registry, ToolRegistry, ToolCategory

# Import guardrails
from guardrails.input_guard import (
    get_input_guardrail,
    InputGuardrail,
    GuardrailResult as InputGuardrailResult,
    TopicCategory,
)
from guardrails.output_guard import (
    get_output_guardrail,
    OutputGuardrail,
    OutputValidationResult,
    GroundingStatus,
)
from guardrails.tool_guard import (
    get_tool_guardrail,
    ToolGuardrail,
    ToolExecutionResult as GuardedToolResult,
    ToolCategory as GuardToolCategory,
)

logger = logging.getLogger(__name__)


def log(stage: str, msg: str):
    """Log to stderr."""
    sys.stderr.write(f"[{stage}] {msg}\n")
    sys.stderr.flush()


class AgentLoop:
    """
    Enhanced agent loop with tool integration and guardrails.

    Features:
    - Input guardrails (topic filter, PII scrubber, injection detection)
    - Intent-based routing to tools
    - Tool guardrails (rate limiting, timeout, scope restriction)
    - Tool execution with error handling
    - Output guardrails (SQL safety, grounding check, HITL gate)
    - Streaming response generation
    - Conversation memory management
    - LLM response synthesis with tool results
    - Audit logging for compliance
    """

    def __init__(
        self,
        max_steps: int = 10,
        tool_registry: Optional[ToolRegistry] = None,
        enable_tools: bool = True,
        enable_input_guardrails: bool = True,
        enable_output_guardrails: bool = True,
        enable_tool_guardrails: bool = True,
        input_guardrail: Optional[InputGuardrail] = None,
        output_guardrail: Optional[OutputGuardrail] = None,
        tool_guardrail: Optional[ToolGuardrail] = None,
    ):
        """
        Initialize agent loop with guardrails.

        Args:
            max_steps: Maximum reasoning steps
            tool_registry: Tool registry (uses default if None)
            enable_tools: Enable/disable tool execution
            enable_input_guardrails: Enable input validation
            enable_output_guardrails: Enable output validation
            enable_tool_guardrails: Enable tool execution protection
            input_guardrail: Custom input guardrail (uses default if None)
            output_guardrail: Custom output guardrail (uses default if None)
            tool_guardrail: Custom tool guardrail (uses default if None)
        """
        self.max_steps = max_steps
        self.enable_tools = enable_tools
        self.registry = tool_registry or get_registry()

        # Guardrails
        self.enable_input_guardrails = enable_input_guardrails
        self.enable_output_guardrails = enable_output_guardrails
        self.enable_tool_guardrails = enable_tool_guardrails

        self.input_guardrail = input_guardrail or get_input_guardrail()
        self.output_guardrail = output_guardrail or get_output_guardrail()
        self.tool_guardrail = tool_guardrail or get_tool_guardrail()

        # Register clickhouse_query tool if not already registered
        self._register_default_tools()

        # Per-instance conversation history
        self.conversation_history: List[Dict[str, str]] = []

        # Guardrail statistics
        self.guardrail_stats = {
            "input_validations": 0,
            "input_rejected": 0,
            "output_validations": 0,
            "output_rejected": 0,
            "tool_executions": 0,
            "tool_guardrail_blocks": 0,
        }

        logger.info(f"AgentLoop initialized with {len(self.registry.tool_names)} tools")
        logger.info(f"Input guardrails: {'enabled' if enable_input_guardrails else 'disabled'}")
        logger.info(f"Output guardrails: {'enabled' if enable_output_guardrails else 'disabled'}")
        logger.info(f"Tool guardrails: {'enabled' if enable_tool_guardrails else 'disabled'}")

    def _register_default_tools(self):
        """Register default tools if they haven't been registered yet."""
        tools_registered = []
        tools_failed = []
        
        # 1. Register ClickHouse query tool
        if "clickhouse_query" not in self.registry.tool_names:
            try:
                from tools.clickhouse_tool import get_clickhouse_tool

                ch_tool = get_clickhouse_tool()

                self.registry.register_manual(
                    name="clickhouse_query",
                    handler=lambda natural_query: ch_tool.format_result(
                        ch_tool.query_nl(natural_query)
                    ),
                    description="Query ClickHouse database with natural language",
                    parameters={
                        "natural_query": {
                            "type": "string",
                            "description": "Natural language query for the database",
                        }
                    },
                    category=ToolCategory.DATABASE_QUERY,
                )
                tools_registered.append("clickhouse_query")
                logger.info("[OK] Registered clickhouse_query tool")

            except Exception as e:
                tools_failed.append(f"clickhouse_query: {e}")
                logger.warning(f"[WARNING] Failed to register clickhouse_query tool: {e}")
        
        # 2. Register GitHub tools
        if "draft_github_issue" not in self.registry.tool_names:
            try:
                from tools.github_tool import draft_github_issue

                self.registry.register_manual(
                    name="draft_github_issue",
                    handler=draft_github_issue,
                    description="Draft a GitHub issue with title, body, labels, and assignees (requires HITL approval)",
                    parameters={
                        "repo": {"type": "string", "description": "Repository in format 'owner/repo'"},
                        "title": {"type": "string", "description": "Issue title"},
                        "body": {"type": "string", "description": "Issue body/description in markdown"},
                        "labels": {"type": "array", "description": "List of labels to add"},
                        "assignees": {"type": "array", "description": "List of usernames to assign"}
                    },
                    category=ToolCategory.API,
                    requires_approval=True,
                    approval_action_type="github_issue",
                    read_only=False,
                    risk_level="medium",
                )
                tools_registered.append("draft_github_issue")
                logger.info("[OK] Registered draft_github_issue tool")

            except Exception as e:
                tools_failed.append(f"draft_github_issue: {e}")
                logger.warning(f"[WARNING] Failed to register draft_github_issue tool: {e}")
        
        # 3. Import Grafana tools to trigger @tool decorator registration
        if "create_grafana_dashboard" not in self.registry.tool_names:
            try:
                # Import the module to trigger @tool decorator registration
                from tools import grafana_tool
                tools_registered.append("create_grafana_dashboard")
                logger.info("[OK] Registered create_grafana_dashboard tool")
            except Exception as e:
                tools_failed.append(f"create_grafana_dashboard: {e}")
                logger.warning(f"[WARNING] Failed to register create_grafana_dashboard tool: {e}")

        # 4. Register code search tools (if repos are indexed)
        if "search_code" not in self.registry.tool_names:
            try:
                from tools.code_search.simple_search import search_code

                self.registry.register_manual(
                    name="search_code",
                    handler=search_code,
                    description="Search code semantically using natural language queries",
                    parameters={
                        "query": {"type": "string", "description": "Natural language code search query"},
                        "top_k": {"type": "integer", "description": "Number of results to return"}
                    },
                    category=ToolCategory.CODE_SEARCH,
                )
                tools_registered.append("search_code")
                logger.info("[OK] Registered search_code tool")

            except Exception as e:
                tools_failed.append(f"search_code: {e}")
                logger.warning(f"[WARNING] Failed to register search_code tool: {e}")
        
        # 5. Register gap detection tool
        if "detect_documentation_gaps" not in self.registry.tool_names:
            try:
                from tools.gap_detection_tool import detect_documentation_gaps

                self.registry.register_manual(
                    name="detect_documentation_gaps",
                    handler=detect_documentation_gaps,
                    description="Detect missing documentation or code gaps in the project",
                    parameters={
                        "area": {"type": "string", "description": "Area to check for gaps (e.g., 'authentication', 'api')"}
                    },
                    category=ToolCategory.UTILITY,
                )
                tools_registered.append("detect_documentation_gaps")
                logger.info("[OK] Registered detect_documentation_gaps tool")

            except Exception as e:
                tools_failed.append(f"detect_documentation_gaps: {e}")
                logger.warning(f"[WARNING] Failed to register detect_documentation_gaps tool: {e}")
        
        # 6. Register observability tool
        if "get_error_rate" not in self.registry.tool_names:
            try:
                from tools.observability_tool import get_error_rate

                self.registry.register_manual(
                    name="get_error_rate",
                    handler=get_error_rate,
                    description="Get error rate metrics for a service",
                    parameters={
                        "service_name": {"type": "string", "description": "Name of the service"},
                        "time_range": {"type": "string", "description": "Time range (e.g., '1h', '24h')", "default": "1h"}
                    },
                    category=ToolCategory.DATABASE_QUERY,
                )
                tools_registered.append("get_error_rate")
                logger.info("[OK] Registered get_error_rate tool")

            except Exception as e:
                tools_failed.append(f"get_error_rate: {e}")
                logger.warning(f"[WARNING] Failed to register get_error_rate tool: {e}")
        
        # Log summary
        logger.info(f"[INFO] Tool registration complete: {len(tools_registered)} registered, {len(tools_failed)} failed")
        if tools_failed:
            logger.warning(f"[WARNING] Failed tools: {tools_failed}")

    async def process(
        self,
        user_input: str,
        session: Optional[SessionContext] = None,
    ) -> str:
        """
        Process a user query through the cognitive pipeline.

        Args:
            user_input: Raw user input text
            session: Optional session context

        Returns:
            Agent response string
        """
        response_text, _ = await self.process_with_tools(user_input, session)
        return response_text

    async def process_with_tools(
        self,
        user_input: str,
        session: Optional[SessionContext] = None,
    ) -> tuple[str, Optional[List[ToolCallResult]]]:
        """
        Process a user query with tool execution and guardrails.

        Args:
            user_input: Raw user input text
            session: Optional session context

        Returns:
            Tuple of (response_text, tool_call_results)
        """
        log("agent", f"Processing: {user_input[:100]}...")

        tool_calls: List[ToolCallResult] = []
        input_validation: Optional[InputGuardrailResult] = None

        try:
            # 0. Input Guardrails
            if self.enable_input_guardrails:
                self.guardrail_stats["input_validations"] += 1
                input_validation = await self.input_guardrail.validate(user_input)

                if not input_validation.is_valid:
                    self.guardrail_stats["input_rejected"] += 1
                    logger.warning(f"Input rejected by guardrail: {input_validation.reason}")

                    # Return friendly error message
                    error_response = self._get_guardrail_error_message(input_validation)
                    return error_response, None

                # Use sanitized input
                user_input = input_validation.sanitized_text
                log("guardrail", f"Input validated - Topic: {input_validation.topic}, PII found: {len(input_validation.pii_found)}")

            # 1. Perception
            perception = self._perceive(user_input)
            log("agent", f"Intent: {perception.intent}, tool_hint: {perception.tool_hint}")

            # 2. Routing - select tool
            tool_name = self._route_to_tool(perception, session)
            log("agent", f"Routed to tool: {tool_name}")

            # 3. Explain before act (generate explanation before execution)
            tool_explanation = None
            if tool_name and self.enable_tools:
                tool_explanation = await self._explain_before_act(tool_name, perception, session)
                if tool_explanation:
                    log("agent", f"Tool explanation: {tool_explanation.get('action', 'N/A')}")

            # 4. Execute tool if available (with tool guardrails)
            tool_result = None
            if tool_name and self.enable_tools:
                tool_result = await self._execute_tool_with_guardrails(tool_name, perception, session)
                if tool_result:
                    tool_calls.append(tool_result)
                    log("agent", f"Tool {tool_name} executed: {tool_result.success}")

            # 5. Generate structured response with tool results
            structured_response = await self._generate_structured_response(
                user_input,
                perception,
                tool_result,
                session,
                tool_name,
                tool_explanation,
            )

            # 5. Output Guardrails
            if self.enable_output_guardrails:
                self.guardrail_stats["output_validations"] += 1

                # Build context for grounding check
                context = {
                    "evidence": [str(tc.result) for tc in tool_calls if tc.success and tc.result] if tool_calls else [],
                    "conversation": self.conversation_history[-5:] if self.conversation_history else [],
                }

                output_validation = await self.output_guardrail.validate(
                    response=structured_response.summary,
                    context=context,
                    tool_results=[tc.__dict__ if hasattr(tc, '__dict__') else str(tc) for tc in tool_calls] if tool_calls else None,
                    action=tool_name,
                )

                if not output_validation.is_valid:
                    self.guardrail_stats["output_rejected"] += 1
                    logger.warning(f"Output rejected by guardrail: {output_validation.reason}")

                    # Modify response to indicate validation issue
                    if output_validation.hitl_required:
                        structured_response.summary += "\n\n[Note: This action requires human approval before execution.]"
                    else:
                        structured_response.summary = f"I apologize, but I cannot provide that response due to safety validation: {output_validation.reason}"

                    # Update certainty level based on validation
                    structured_response.certainty_level = "uncertain"

                log("guardrail", f"Output validated - Grounding: {output_validation.grounding_status.value}, SQL Safe: {output_validation.sql_safe}")

            # Update instance history
            self.conversation_history.append({"role": "user", "content": user_input})
            self.conversation_history.append({"role": "assistant", "content": structured_response.summary})

            # Return plain text response for backward compatibility
            return structured_response.summary, tool_calls

        except Exception as e:
            logger.error(f"Agent processing error: {e}")
            error_response = "I encountered an error processing your request. Please try again."
            return error_response, None

    async def process_stream(
        self,
        user_input: str,
        session: Optional[SessionContext] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process with streaming output.

        Yields chunks as:
        - {"type": "token", "content": "..."}
        - {"type": "tool_call", "data": {...}}
        - {"type": "error", "error": "..."}
        - {"type": "done", "response": "..."}

        Args:
            user_input: Raw user input text
            session: Optional session context

        Yields:
            Stream chunks
        """
        log("agent", f"Processing stream: {user_input[:100]}...")

        try:
            # 1. Perception
            perception = self._perceive(user_input)
            yield {"type": "perception", "intent": perception.intent}

            # 2. Routing
            tool_name = self._route_to_tool(perception, session)
            if tool_name:
                yield {"type": "routing", "tool": tool_name}

            # 3. Explain before act
            if tool_name and self.enable_tools:
                explanation = await self._explain_before_act(tool_name, perception, session)
                if explanation:
                    yield {"type": "explanation", "explanation": explanation}

            # 4. Execute tool
            tool_result = None
            if tool_name and self.enable_tools:
                yield {"type": "tool_start", "tool_name": tool_name}

                tool_result = await self._execute_tool(tool_name, perception, session)

                yield {
                    "type": "tool_call",
                    "data": {
                        "tool_name": tool_result.tool_name,
                        "success": tool_result.success,
                        "result": tool_result.result,
                        "error": tool_result.error,
                    } if tool_result else {}
                }

            # 5. Stream response generation
            full_response = ""
            async for token in self._generate_response_stream(
                user_input,
                perception,
                tool_result,
                session,
            ):
                full_response += token
                yield {"type": "token", "content": token}

            # Done
            yield {"type": "done", "response": full_response}

            # 4. Stream response generation
            full_response = ""
            async for token in self._generate_response_stream(
                user_input,
                perception,
                tool_result,
                session,
            ):
                full_response += token
                yield {"type": "token", "content": token}

            # Done
            yield {"type": "done", "response": full_response}

        except Exception as e:
            logger.error(f"Stream processing error: {e}")
            yield {"type": "error", "error": str(e)}

    def _perceive(self, user_input: str) -> PerceptionResult:
        """
        Extract intent, entities, and tool hints from user input.

        Uses rule-based pattern matching combined with context.
        """
        user_lower = user_input.lower()

        # Detect URLs
        github_match = re.search(r'https?://github\.com/[\w\-]+/[\w\-]+', user_input)
        repo_url = github_match.group(0) if github_match else None

        # Detect intents
        intent = "general_question"
        tool_hint = None
        entities = []

        if repo_url:
            intent = "clone_repo"
            tool_hint = "clone_repository"
            entities = [repo_url]

        elif any(w in user_lower for w in ["index", "build index"]):
            intent = "index_repo"
            tool_hint = "index_repository"

        # Check for dashboard creation BEFORE database_query
        # This ensures "Create a dashboard" queries are routed correctly
        elif any(w in user_lower for w in [
            "dashboard", "grafana", "panel", "visualization", "visualize",
            "create dashboard", "build dashboard", "setup dashboard"
        ]):
            intent = "dashboard_management"
            tool_hint = "create_grafana_dashboard"
            entities = [user_input]

        elif any(w in user_lower for w in [
            "database", "query", "sql", "logs", "metrics",
            "recent", "errors", "show me", "show", "count", "statistics", "data",
            "tables", "columns", "rows"
        ]):
            intent = "database_query"
            tool_hint = "clickhouse_query"
            entities = [user_input]

        elif any(w in user_lower for w in [
            "search", "find", "how does", "where is", "locate",
            "function", "class", "implementation"
        ]):
            intent = "search_code"
            tool_hint = "code_search"
            entities = [user_input]

        elif any(w in user_lower for w in [
            "docs", "documentation", "readme", "guide", "how to",
            "authenticate", "authorization", "api docs"
        ]):
            intent = "document_search"
            tool_hint = "rag_search"
            entities = [user_input]

        elif any(w in user_lower for w in ["status", "info"]):
            intent = "get_status"
            tool_hint = "get_repo_status"

        return PerceptionResult(
            user_input=user_input,
            intent=intent,
            entities=entities,
            tool_hint=tool_hint,
            repo_url=repo_url,
        )

    def _route_to_tool(
        self,
        perception: PerceptionResult,
        session: Optional[SessionContext],
    ) -> Optional[str]:
        """
        Route intent to appropriate tool or skill with confidence-based enforcement.

        Uses the router to classify with confidence and the registry to find tools/skills.
        Returns None for unknown intents or low confidence, triggering fallback responses.
        """
        if not self.enable_tools:
            return None

        # Classify intent with confidence
        intent, confidence = classify_intent(perception)

        # Store confidence in perception for later use
        perception.confidence = confidence

        # Handle unknown intent or low confidence
        if intent == "unknown":
            logger.warning(f"Unknown intent detected for: {perception.user_input[:50]}...")
            return None

        # Low confidence threshold (below 0.6)
        if confidence < 0.6:
            logger.warning(f"Low confidence ({confidence:.2f}) for intent '{intent}': {perception.user_input[:50]}...")
            # Store fallback suggestions in perception
            from agent.router import get_fallback_suggestions
            perception.fallback_suggestions = get_fallback_suggestions(perception.user_input)
            return None

        # High confidence routing
        # First, check for skill routing
        from skills import get_skill_registry
        skill_registry = get_skill_registry()

        skill_name = skill_registry.route_by_intent(intent)
        if skill_name:
            skill = skill_registry.get(skill_name)
            if skill:
                return f"skill:{skill_name}"

        # Then, use tool hint from perception
        if perception.tool_hint:
            tool = self.registry.get(perception.tool_hint)
            if tool and tool.metadata.enabled:
                return perception.tool_hint

        # Fallback to intent-based routing for tools
        tool_name = self.registry.route_by_intent(intent)
        if tool_name:
            tool = self.registry.get(tool_name)
            if tool and tool.metadata.enabled:
                return tool_name

        return None

    async def _execute_tool(
        self,
        tool_name: str,
        perception: PerceptionResult,
        session: Optional[SessionContext],
    ) -> Optional[ToolCallResult]:
        """
        Execute a tool or skill with arguments derived from perception.

        Args:
            tool_name: Name of tool/skill to execute (prefixed with 'skill:' for skills)
            perception: Perception result with entities
            session: Optional session context

        Returns:
            ToolCallResult or None
        """
        # Check if this is a skill execution
        if tool_name.startswith("skill:"):
            return await self._execute_skill(tool_name[6:], perception, session)
        
        tool = self.registry.get(tool_name)
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return None

        # Build arguments from perception
        arguments = self._build_tool_arguments(tool_name, perception, session)

        # Execute
        try:
            execution_result = await self.registry.execute_tool(
                tool_name,
                arguments,
                timeout_seconds=30,
            )
            
            # SQL Self-Correction for ClickHouse queries
            if tool_name == "clickhouse_query" and not execution_result.success:
                execution_result = await self._retry_sql_with_correction(
                    tool_name, arguments, execution_result.error
                )

            return ToolCallResult(
                tool_name=tool_name,
                arguments=arguments,
                result=execution_result.result,
                success=execution_result.success,
                error=execution_result.error,
            )

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return ToolCallResult(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                success=False,
                error=str(e),
            )

    async def _execute_tool_with_guardrails(
        self,
        tool_name: str,
        perception: PerceptionResult,
        session: Optional[SessionContext],
    ) -> Optional[ToolCallResult]:
        """
        Execute a tool with tool guardrails (rate limiting, timeout, scope).

        Args:
            tool_name: Name of tool to execute
            perception: Perception result with entities
            session: Optional session context

        Returns:
            ToolCallResult or None
        """
        tool = self.registry.get(tool_name)
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return None

        # Build arguments from perception
        arguments = self._build_tool_arguments(tool_name, perception, session)

        # Get tool category for guardrails
        tool_category = self._get_tool_category(tool_name)

        # Execute with tool guardrails
        if self.enable_tool_guardrails:
            self.guardrail_stats["tool_executions"] += 1

            async def tool_handler(args):
                """Execute the tool."""
                execution_result = await self.registry.execute_tool(
                    tool_name,
                    args,
                    timeout_seconds=30,
                )

                # SQL Self-Correction for ClickHouse queries
                if tool_name == "clickhouse_query" and not execution_result.success:
                    execution_result = await self._retry_sql_with_correction(
                        tool_name, args, execution_result.error
                    )

                return execution_result

            # Execute with guardrails
            guarded_result = await self.tool_guardrail.execute(
                tool_name=tool_name,
                handler=tool_handler,
                arguments=arguments,
                category=tool_category,
                user_id=session.session_id if session else None,
            )

            # Log guardrail blocks
            if not guarded_result.success and (
                guarded_result.rate_limited or
                guarded_result.timeout_occurred or
                guarded_result.scope_violation or
                guarded_result.circuit_breaker_open
            ):
                self.guardrail_stats["tool_guardrail_blocks"] += 1
                logger.warning(
                    f"Tool {tool_name} blocked by guardrail: "
                    f"rate_limited={guarded_result.rate_limited}, "
                    f"timeout={guarded_result.timeout_occurred}, "
                    f"scope_violation={guarded_result.scope_violation}, "
                    f"circuit_breaker={guarded_result.circuit_breaker_open}"
                )

            return ToolCallResult(
                tool_name=tool_name,
                arguments=arguments,
                result=guarded_result.result,
                success=guarded_result.success,
                error=guarded_result.error,
                metadata={
                    "guardrail_info": {
                        "rate_limited": guarded_result.rate_limited,
                        "timeout_occurred": guarded_result.timeout_occurred,
                        "scope_violation": guarded_result.scope_violation,
                        "circuit_breaker_open": guarded_result.circuit_breaker_open,
                        "execution_time_ms": guarded_result.execution_time_ms,
                    }
                }
            )
        else:
            # Execute without guardrails (legacy behavior)
            return await self._execute_tool(tool_name, perception, session)

    def _get_tool_category(self, tool_name: str) -> Optional[GuardToolCategory]:
        """
        Map tool name to guardrail tool category.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolCategory or None
        """
        category_mapping = {
            "clickhouse_query": GuardToolCategory.DATABASE_QUERY,
            "grafana_dashboard": GuardToolCategory.GRAFANA,
            "github_issue": GuardToolCategory.GITHUB,
            "browser_action": GuardToolCategory.BROWSER,
            "code_search": GuardToolCategory.CODE_READ,
            "rag_search": GuardToolCategory.NETWORK_READ,
        }
        return category_mapping.get(tool_name)

    def _get_guardrail_error_message(self, validation_result: InputGuardrailResult) -> str:
        """
        Generate user-friendly error message for guardrail rejection.

        Args:
            validation_result: Input guardrail validation result

        Returns:
            User-friendly error message
        """
        if validation_result.injection_detected:
            return (
                "I'm unable to process that request as it appears to contain "
                "potentially unsafe instructions. Please rephrase your question."
            )

        if validation_result.topic and validation_result.topic == "out_of_scope":
            return (
                "I specialize in developer relations and technical support topics. "
                "I can help with questions about code, documentation, APIs, databases, "
                "observability, and related technical subjects. How can I assist you?"
            )

        if validation_result.pii_found:
            pii_types = set(pii["type"] for pii in validation_result.pii_found)
            sensitive_types = {"aws_key", "private_key", "jwt_token", "api_token"}
            
            if pii_types & sensitive_types:
                return (
                    "I detected sensitive credentials in your message. For security reasons, "
                    "please avoid sharing API keys, tokens, or passwords. "
                    "You can describe your issue without including the actual credentials."
                )

        # Generic rejection message
        return (
            "I'm unable to process that request due to safety guidelines. "
            "Please rephrase your question or contact support for assistance. "
            f"Reason: {validation_result.reason}"
        )

    async def _execute_skill(
        self,
        skill_name: str,
        perception: PerceptionResult,
        session: Optional[SessionContext],
    ) -> Optional[ToolCallResult]:
        """
        Execute a skill with arguments derived from perception.

        Args:
            skill_name: Name of skill to execute
            perception: Perception result with entities
            session: Optional session context

        Returns:
            ToolCallResult or None
        """
        from skills import get_skill_registry
        
        skill_registry = get_skill_registry()
        skill = skill_registry.get(skill_name)
        
        if not skill:
            logger.warning(f"Skill not found: {skill_name}")
            return None

        # Build skill context and arguments
        context = {
            "tool_registry": self.registry,
            "session": session,
            "perception": perception
        }
        
        # Build skill-specific arguments
        kwargs = {}
        
        if skill_name == "diagnose_error":
            # entities is List[str], not objects with .type and .value
            # Try to find a service name in entities, or use empty string
            service_name = ""
            if perception.entities:
                # Use the first entity as service name, or look for common service patterns
                service_name = next((e for e in perception.entities if len(e) > 0), perception.entities[0])

            kwargs = {
                "error_description": perception.user_input,
                "service_name": service_name,
                "time_range": "1h"
            }
        elif skill_name == "search_docs":
            kwargs = {
                "query": perception.user_input,
                "sources": ["docs", "web"],
                "max_results": 3
            }

        # Execute skill
        try:
            skill_result = await skill.execute(context, **kwargs)

            return ToolCallResult(
                tool_name=f"skill:{skill_name}",
                arguments=kwargs,
                result=skill_result.result if skill_result.success else None,
                success=skill_result.success,
                error=skill_result.error,
                metadata={
                    "skill_steps": skill_result.steps,
                    "skill_metadata": skill_result.metadata
                }
            )

        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            return ToolCallResult(
                tool_name=f"skill:{skill_name}",
                arguments=kwargs,
                result=None,
                success=False,
                error=str(e),
            )
    async def _retry_sql_with_correction(
        self,
        tool_name: str,
        original_arguments: Dict[str, Any],
        error_message: str,
        max_retries: int = 3
    ):
        """
        Retry SQL query with LLM-based error correction.

        Args:
            tool_name: Name of the SQL tool
            original_arguments: Original arguments that failed
            error_message: Error message from failed execution
            max_retries: Maximum number of retry attempts

        Returns:
            ToolExecutionResult with corrected query or final error
        """
        from tools.registry import ToolExecutionResult

        for attempt in range(max_retries):
            logger.info(f"SQL correction attempt {attempt + 1}/{max_retries}")

            try:
                # Use LLM to correct the SQL based on error
                corrected_query = await self._correct_sql_with_llm(
                    original_arguments.get("natural_query", ""),
                    error_message
                )

                if not corrected_query:
                    continue

                # Update arguments with corrected query
                corrected_arguments = original_arguments.copy()
                corrected_arguments["natural_query"] = corrected_query

                # Retry execution
                result = await self.registry.execute_tool(
                    tool_name,
                    corrected_arguments,
                    timeout_seconds=30,
                )

                if result.success:
                    logger.info(f"SQL correction successful on attempt {attempt + 1}")
                    # Add metadata about correction
                    if hasattr(result, 'result') and isinstance(result.result, dict):
                        result.result["sql_corrected"] = True
                        result.result["correction_attempts"] = attempt + 1
                    return result
                else:
                    error_message = result.error  # Update error for next attempt

            except Exception as e:
                logger.error(f"SQL correction attempt {attempt + 1} failed: {e}")
                error_message = str(e)

        # All retries failed
        return ToolExecutionResult(
            success=False,
            result=None,
            error=f"SQL correction failed after {max_retries} attempts. Last error: {error_message}"
        )

    async def _correct_sql_with_llm(self, natural_query: str, error_message: str) -> Optional[str]:
        """
        Use LLM to correct SQL based on error message.

        Args:
            natural_query: Original natural language query
            error_message: SQL error message

        Returns:
            Corrected natural language query or None
        """
        try:
            correction_prompt = f"""
            The following natural language query failed when converted to SQL:
            Query: "{natural_query}"
            Error: {error_message}

            Please provide a corrected version of the natural language query that would avoid this error.
            Consider common SQL issues like:
            - Wrong column names
            - Missing table aliases
            - Incorrect syntax
            - Data type mismatches

            Respond with only the corrected natural language query, nothing else.
            """

            # Use the LLM provider to get correction
            if hasattr(self, 'llm_provider') and self.llm_provider:
                response = await self.llm_provider.generate_response(correction_prompt)
                if response and response.strip():
                    return response.strip()

            return None

        except Exception as e:
            logger.error(f"Error correcting SQL with LLM: {e}")
            return None

    def _build_tool_arguments(
        self,
        tool_name: str,
        perception: PerceptionResult,
        session: Optional[SessionContext],
    ) -> Dict[str, Any]:
        """Build arguments for tool execution from perception."""
        arguments = {}

        # Handle ClickHouse query
        if tool_name == "clickhouse_query":
            if perception.entities:
                arguments["natural_query"] = perception.entities[0]
            else:
                arguments["natural_query"] = perception.user_input
            # IMPORTANT: clickhouse_query does NOT accept session_id
            # Never add it regardless of session context
            return arguments

        # Handle code search
        elif tool_name == "code_search":
            if perception.entities:
                arguments["query"] = perception.entities[0]
            else:
                arguments["query"] = perception.user_input
            arguments["top_k"] = 5

        # Handle RAG search
        elif tool_name == "rag_search":
            if perception.entities:
                arguments["query"] = perception.entities[0]
            else:
                arguments["query"] = perception.user_input
            arguments["top_k"] = 3

        # Handle clone repository
        elif tool_name == "clone_repository":
            if perception.repo_url:
                arguments["repo_url"] = perception.repo_url

        # Handle Grafana dashboard creation
        elif tool_name == "create_grafana_dashboard":
            # Pass the full user query as natural_query parameter
            arguments["natural_query"] = perception.user_input

        # Add session context ONLY for tools that explicitly support it
        # Most tools (including clickhouse_query) do NOT need session_id
        if session:
            tool = self.registry.get(tool_name)
            # Only add session_id if the tool explicitly declares it as a parameter
            if tool and tool.parameters:
                param_names = list(tool.parameters.keys())
                logger.debug(f"Tool {tool_name} parameters: {param_names}")
                if "session_id" in tool.parameters:
                    arguments["session_id"] = session.session_id
                    logger.debug(f"Tool {tool_name} accepts session_id parameter")
                else:
                    # Explicitly ensure session_id is NOT in arguments
                    arguments.pop("session_id", None)
            elif tool:
                # No parameters defined - don't add session_id
                arguments.pop("session_id", None)

        return arguments

    async def _generate_response(
        self,
        user_input: str,
        perception: PerceptionResult,
        tool_result: Optional[ToolCallResult],
        session: Optional[SessionContext],
    ) -> str:
        """
        Generate response using LLM with tool results and confidence-based handling.

        Args:
            user_input: Original user input
            perception: Perception result
            tool_result: Result from tool execution
            session: Optional session context

        Returns:
            Generated response string
        """
        try:
            # Handle unknown intent or low confidence
            if hasattr(perception, 'confidence') and perception.confidence < 0.6:
                return self._generate_low_confidence_response(perception, user_input)

            # Build context
            context_parts = [f"User asked: {user_input}"]

            # Add tool results
            if tool_result:
                if tool_result.success:
                    context_parts.append(
                        f"Tool '{tool_result.tool_name}' returned: {self._format_tool_result(tool_result.result)}"
                    )
                else:
                    # Provide clear error context to LLM
                    error_msg = tool_result.error or "Unknown error"
                    context_parts.append(
                        f"Tool '{tool_result.tool_name}' failed with error: {error_msg}. "
                        f"Arguments passed: {list(tool_result.arguments.keys()) if tool_result.arguments else 'none'}."
                    )

            # Add conversation history context
            history_context = self._get_history_context(session)
            if history_context:
                context_parts.append(f"Conversation context: {history_context}")

            context = "\n".join(context_parts)

            # Generate response
            response = llm_generate(
                prompt=f"{context}\n\nProvide a helpful, concise response to the user.",
                max_tokens=800,
                system="You are DevRelAgent, an AI-powered developer relations assistant. "
                      "Be helpful, accurate, and concise. If a tool returned results, summarize them clearly. "
                      "Keep responses under 200 words."
            )

            # If LLM fails, generate a simple fallback response
            if not response or response.strip() == "":
                logger.warning("LLM response generation failed, using fallback")
                return self._generate_fallback_response(user_input, tool_result)

            return response

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._generate_fallback_response(user_input, tool_result)

    def _generate_fallback_response(self, user_input: str, tool_result: Optional[ToolCallResult]) -> str:
        """
        Generate a simple fallback response when LLM is not available.

        Args:
            user_input: Original user input
            tool_result: Result from tool execution

        Returns:
            Fallback response string
        """
        if tool_result and tool_result.success:
            # Tool executed successfully, provide a simple summary
            result = tool_result.result
            if isinstance(result, dict) and 'result_rows' in result:
                rows = result['result_rows']
                columns = result.get('column_names', [])

                if rows:
                    count = len(rows)
                    if count == 1:
                        response = f"I found 1 result for your query about '{user_input}'.\n\n"
                    else:
                        response = f"I found {count} results for your query about '{user_input}'.\n\n"

                    # Show first few results
                    for i, row in enumerate(rows[:3], 1):
                        row_dict = dict(zip(columns, row))
                        response += f"{i}. "
                        if 'timestamp' in row_dict:
                            response += f"[{row_dict['timestamp']}] "
                        if 'service' in row_dict:
                            response += f"{row_dict['service']}: "
                        if 'message' in row_dict:
                            response += f"{row_dict['message']}"
                        elif 'level' in row_dict:
                            response += f"Level: {row_dict['level']}"
                        response += "\n"

                    if count > 3:
                        response += f"\n(Showing 3 of {count} results)"

                    return response

            return f"Query executed successfully. Found results for: {user_input}"

        elif tool_result and not tool_result.success:
            # Tool failed
            error = tool_result.error or "Unknown error"
            return f"I encountered an error while processing your query: {error}"

        else:
            # No tool was executed
            return f"I processed your query about '{user_input}', but I need more information to provide a complete answer."

    async def _generate_structured_response(
        self,
        user_input: str,
        perception: PerceptionResult,
        tool_result: Optional[ToolCallResult],
        session: Optional[SessionContext],
        tool_name: Optional[str],
        tool_explanation: Optional[Dict[str, Any]] = None,
    ) -> StructuredAgentResponse:
        """
        Generate structured response with observations, confidence scoring, and explanation.

        Args:
            user_input: Original user input
            perception: Perception result
            tool_result: Result from tool execution
            session: Optional session context
            tool_name: Name of tool used
            tool_explanation: Optional tool explanation generated before execution

        Returns:
            StructuredAgentResponse with observations and confidence
        """
        try:
            # Handle unknown intent or low confidence
            if hasattr(perception, 'confidence') and perception.confidence < 0.6:
                return self._generate_structured_low_confidence_response(perception, user_input)

            # Generate observations from tool results
            observations = []
            confidence = 0.7  # Base confidence

            if tool_result and tool_result.success:
                # Create observation from tool result
                observation = await self._create_observation_from_tool_result(
                    tool_result,
                    user_input,
                )
                if observation:
                    observations.append(observation)
                    confidence = max(confidence, observation.confidence)

            # Generate response text
            response_text = await self._generate_response(
                user_input,
                perception,
                tool_result,
                session,
            )

            # Add explanation to response if tool requires approval
            if tool_explanation and tool_explanation.get('requires_approval'):
                explanation_text = (
                    f"\n\n**Before executing**, here's what I plan to do:\n"
                    f"- **Action**: {tool_explanation.get('action', 'N/A')}\n"
                    f"- **Reasoning**: {tool_explanation.get('reasoning', 'N/A')}\n"
                    f"- **Expected Outcome**: {tool_explanation.get('expected_outcome', 'N/A')}\n"
                    f"- **Risk Level**: {tool_explanation.get('risk_level', 'unknown').upper()}"
                )
                response_text = explanation_text + "\n\n" + response_text

            # Determine certainty level
            if confidence >= 0.9:
                certainty_level = "confirmed"
            elif confidence >= 0.7:
                certainty_level = "likely"
            elif confidence >= 0.5:
                certainty_level = "possible"
            else:
                certainty_level = "uncertain"

            # Determine query type
            if tool_name:
                query_type = "investigation" if tool_name in ["clickhouse_query", "observability"] else "question"
            else:
                query_type = "question"

            # Build structured response
            structured_response = StructuredAgentResponse(
                query=user_input,
                query_type=query_type,
                summary=response_text,
                detailed_explanation=response_text,  # For now, same as summary
                observations=observations,
                tools_used=[tool_name] if tool_name else [],
                data_sources=["clickhouse"] if tool_name == "clickhouse_query" else [],
                confidence=confidence,
                certainty_level=certainty_level,
                next_steps=[],
                suggested_actions=[],
                supporting_data={
                    "tool_explanation": tool_explanation,
                    "tool_requires_approval": tool_explanation.get('requires_approval', False) if tool_explanation else False,
                    "tool_risk_level": tool_explanation.get('risk_level') if tool_explanation else None,
                } if tool_explanation else {},
            )

            return structured_response

        except Exception as e:
            logger.error(f"Structured response generation failed: {e}")
            # Return minimal structured response on error
            return StructuredAgentResponse(
                query=user_input,
                summary="I encountered an error generating my response.",
                confidence=0.0,
                certainty_level="uncertain",
            )

    async def _create_observation_from_tool_result(
        self,
        tool_result: ToolCallResult,
        user_input: str,
    ) -> Optional[AgentObservation]:
        """
        Create an observation from tool result.

        Args:
            tool_result: Tool execution result
            user_input: Original user query

        Returns:
            AgentObservation or None
        """
        try:
            # Determine observation type based on tool and result
            observation_type = "insight"
            impact = "low"
            confidence = 0.7

            if tool_result.tool_name == "clickhouse_query":
                observation_type = "pattern"
                impact = "medium"
                confidence = 0.8

                # Check if result contains error information
                result_str = str(tool_result.result)
                if "error" in result_str.lower() or "fail" in result_str.lower():
                    observation_type = "anomaly"
                    impact = "high"

            # Create evidence item
            evidence = EvidenceItem(
                source=tool_result.tool_name,
                data={"result": tool_result.result} if tool_result.result else {},
                confidence=confidence,
            )

            # Build observation
            observation = AgentObservation(
                observation_type=observation_type,
                title=f"Analysis from {tool_result.tool_name}",
                description=f"Executed {tool_result.tool_name} to investigate: {user_input[:100]}",
                evidence=[evidence],
                impact=impact,
                confidence=confidence,
                certainty_level="likely" if confidence >= 0.7 else "possible",
                suggested_actions=[],
                priority="normal" if impact == "low" else "urgent",
            )

            return observation

        except Exception as e:
            logger.error(f"Failed to create observation from tool result: {e}")
            return None

    def _generate_structured_low_confidence_response(
        self,
        perception: PerceptionResult,
        user_input: str,
    ) -> StructuredAgentResponse:
        """
        Generate structured response for low confidence or unknown intents.

        Args:
            perception: Perception result with fallback suggestions
            user_input: Original user input

        Returns:
            StructuredAgentResponse with low confidence
        """
        confidence = getattr(perception, 'confidence', 0.0)
        suggestions = getattr(perception, 'fallback_suggestions', [])

        # Build response text
        if confidence < 0.3:
            summary = "I'm unable to determine what you're asking."
        else:
            summary = (
                f"I'm not entirely sure what you need (confidence: {confidence:.0%}). "
                "Could you please clarify your request?"
            )

        # Add fallback suggestions
        if suggestions:
            summary += "\n\nHere are some things I can help you with:"
            for i, suggestion in enumerate(suggestions[:3], 1):
                summary += f"\n{i}. **{suggestion['intent'].replace('_', ' ').title()}**"
                summary += f"\n   - {suggestion['description']}"
                if suggestion.get('examples'):
                    examples = "', '".join(suggestion['examples'][:2])
                    summary += f"\n   - Example: '{examples}'"

        return StructuredAgentResponse(
            query=user_input,
            query_type="question",
            summary=summary,
            detailed_explanation=summary,
            observations=[],
            confidence=confidence,
            certainty_level="uncertain",
            suggested_actions=[s['intent'] for s in suggestions[:3]],
            tags=["low_confidence", "unknown_intent"],
        )

    def _generate_low_confidence_response(
        self,
        perception: PerceptionResult,
        user_input: str,
    ) -> str:
        """
        Generate response for low confidence or unknown intents.

        Provides helpful fallback suggestions when intent is unclear.

        Args:
            perception: Perception result with fallback suggestions
            user_input: Original user input

        Returns:
            Low confidence response with suggestions
        """
        confidence = getattr(perception, 'confidence', 0.0)
        suggestions = getattr(perception, 'fallback_suggestions', [])

        # Build response
        response_parts = []

        if confidence < 0.3:
            # Very low confidence - unknown intent
            response_parts.append("I'm unable to determine what you're asking.")
        else:
            # Low confidence - unclear intent
            response_parts.append(
                f"I'm not entirely sure what you need (confidence: {confidence:.0%}). "
                "Could you please clarify your request?"
            )

        # Add fallback suggestions if available
        if suggestions:
            response_parts.append("\n\nHere are some things I can help you with:")
            for i, suggestion in enumerate(suggestions[:3], 1):
                response_parts.append(f"\n{i}. **{suggestion['intent'].replace('_', ' ').title()}**")
                response_parts.append(f"   - {suggestion['description']}")
                if suggestion.get('examples'):
                    examples = "', '".join(suggestion['examples'][:2])
                    response_parts.append(f"   - Example: '{examples}'")

        return "\n".join(response_parts)

    async def _generate_response_stream(
        self,
        user_input: str,
        perception: PerceptionResult,
        tool_result: Optional[ToolCallResult],
        session: Optional[SessionContext],
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response.

        Note: This is a simplified streaming implementation.
        For true token streaming, you'd need streaming support from your LLM provider.

        Args:
            user_input: Original user input
            perception: Perception result
            tool_result: Result from tool execution
            session: Optional session context

        Yields:
            Response tokens/chunks
        """
        response = await self._generate_response(
            user_input,
            perception,
            tool_result,
            session,
        )

        # Simulate streaming by yielding chunks
        # In production, integrate with actual LLM streaming API
        chunk_size = 20
        for i in range(0, len(response), chunk_size):
            chunk = response[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.01)  # Small delay for realism

    def _format_tool_result(self, result: Any) -> str:
        """Format tool result for LLM context."""
        if isinstance(result, str):
            return result[:500]  # Limit length
        elif isinstance(result, dict):
            return str(result)[:500]
        elif isinstance(result, list):
            if len(result) > 0:
                return f"{len(result)} items, first: {str(result[0])[:200]}"
            return "Empty list"
        else:
            return str(result)[:500]

    def _get_history_context(self, session: Optional[SessionContext]) -> str:
        """Get relevant conversation history as context."""
        if not session or not session.messages:
            return ""

        # Get last 5 messages for context
        recent = session.messages[-5:]
        context_parts = []

        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            context_parts.append(f"{role}: {content}")

        return " | ".join(context_parts)

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history.clear()
        logger.info("Conversation history cleared")

    async def _explain_before_act(
        self,
        tool_name: str,
        perception: PerceptionResult,
        session: Optional[SessionContext]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate explanation before tool execution.

        Args:
            tool_name: Name of tool to be executed
            perception: Perception result with user input and entities
            session: Optional session context

        Returns:
            Tool explanation dictionary or None
        """
        from models.schemas import ToolExplanation

        tool = self.registry.get(tool_name)
        if not tool:
            return None

        # Build tool arguments
        arguments = self._build_tool_arguments(tool_name, perception, session)

        # Generate explanation
        explanation = ToolExplanation(
            tool_name=tool_name,
            action=tool.description,
            parameters=arguments,
            reasoning=self._generate_reasoning(tool, perception),
            expected_outcome=self._predict_outcome(tool, perception),
            requires_approval=tool.metadata.requires_approval,
            risk_level=tool.metadata.risk_level if tool.metadata.requires_approval else None,
            confidence=0.8
        )

        return explanation.dict()

    def _generate_reasoning(self, tool: Any, perception: PerceptionResult) -> str:
        """
        Generate reasoning for why this tool is needed.

        Args:
            tool: Tool instance
            perception: Perception result

        Returns:
            Reasoning string
        """
        reasoning_parts = [
            f"Tool '{tool.name}' was selected based on the user's intent: {perception.intent}",
        ]

        if perception.entities:
            reasoning_parts.append(f"Detected entities: {', '.join(str(e) for e in perception.entities)}")

        reasoning_parts.append(f"Tool category: {tool.metadata.category.value}")
        reasoning_parts.append(f"Tool description: {tool.description}")

        return ". ".join(reasoning_parts)

    def _predict_outcome(self, tool: Any, perception: PerceptionResult) -> str:
        """
        Predict what the tool will return.

        Args:
            tool: Tool instance
            perception: Perception result

        Returns:
            Predicted outcome string
        """
        category = tool.metadata.category.value

        predictions = {
            "database_query": "Query results with data from the database",
            "code_search": "Relevant code snippets matching the search query",
            "document_search": "Relevant documentation sections",
            "api": "API response with operation results",
            "system": "System operation result"
        }

        base_prediction = predictions.get(category, "Operation result")

        if tool.metadata.requires_approval:
            base_prediction += " (pending user approval)"

        return base_prediction
    async def _retry_sql_with_correction(
        self,
        tool_name: str,
        original_arguments: Dict[str, Any],
        error_message: str,
        max_retries: int = 3
    ):
        """
        Retry SQL query with LLM-based error correction.
        
        Args:
            tool_name: Name of the SQL tool
            original_arguments: Original arguments that failed
            error_message: Error message from failed execution
            max_retries: Maximum number of retry attempts
            
        Returns:
            ToolExecutionResult with corrected query or final error
        """
        from tools.registry import ToolExecutionResult
        
        for attempt in range(max_retries):
            logger.info(f"SQL correction attempt {attempt + 1}/{max_retries}")
            
            try:
                # Use LLM to correct the SQL based on error
                corrected_query = await self._correct_sql_with_llm(
                    original_arguments.get("natural_query", ""),
                    error_message
                )
                
                if not corrected_query:
                    continue
                
                # Update arguments with corrected query
                corrected_arguments = original_arguments.copy()
                corrected_arguments["natural_query"] = corrected_query
                
                # Retry execution
                result = await self.registry.execute_tool(
                    tool_name,
                    corrected_arguments,
                    timeout_seconds=30,
                )
                
                if result.success:
                    logger.info(f"SQL correction successful on attempt {attempt + 1}")
                    # Add metadata about correction
                    if hasattr(result, 'result') and isinstance(result.result, dict):
                        result.result["sql_corrected"] = True
                        result.result["correction_attempts"] = attempt + 1
                    return result
                else:
                    error_message = result.error  # Update error for next attempt
                    
            except Exception as e:
                logger.error(f"SQL correction attempt {attempt + 1} failed: {e}")
                error_message = str(e)
        
        # All retries failed
        return ToolExecutionResult(
            success=False,
            result=None,
            error=f"SQL correction failed after {max_retries} attempts. Last error: {error_message}"
        )
    
    async def _correct_sql_with_llm(self, natural_query: str, error_message: str) -> Optional[str]:
        """
        Use LLM to correct SQL based on error message.
        
        Args:
            natural_query: Original natural language query
            error_message: SQL error message
            
        Returns:
            Corrected natural language query or None
        """
        try:
            correction_prompt = f"""
            The following natural language query failed when converted to SQL:
            Query: "{natural_query}"
            Error: {error_message}
            
            Please provide a corrected version of the natural language query that would avoid this error.
            Consider common SQL issues like:
            - Wrong column names
            - Missing table aliases
            - Incorrect syntax
            - Data type mismatches
            
            Respond with only the corrected natural language query, nothing else.
            """
            
            # Use the LLM provider to get correction
            if hasattr(self, 'llm_provider') and self.llm_provider:
                response = await self.llm_provider.generate_response(correction_prompt)
                if response and response.strip():
                    return response.strip()
            
            return None
            
        except Exception as e:
            logger.error(f"Error correcting SQL with LLM: {e}")
            return None