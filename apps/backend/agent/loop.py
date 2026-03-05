"""
Agent Loop — Core Cognitive Pipeline with Tool Integration

Implements: Perception → Routing → Memory → Action → Response

This is the main orchestration module. Each cognitive layer is a step:
1. Perception: Parse user query, extract intent and entities
2. Routing: Classify intent, select tool(s) using registry
3. Memory: Check conversation history, KeDB, RAG for context
4. Action: Execute selected tool(s)
5. Response: Generate final response with tool results

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
)
from tools.registry import get_registry, ToolRegistry, ToolCategory

logger = logging.getLogger(__name__)


def log(stage: str, msg: str):
    """Log to stderr."""
    sys.stderr.write(f"[{stage}] {msg}\n")
    sys.stderr.flush()


class AgentLoop:
    """
    Enhanced agent loop with tool integration.

    Features:
    - Intent-based routing to tools
    - Tool execution with error handling
    - Streaming response generation
    - Conversation memory management
    - LLM response synthesis with tool results
    """

    def __init__(
        self,
        max_steps: int = 10,
        tool_registry: Optional[ToolRegistry] = None,
        enable_tools: bool = True,
    ):
        """
        Initialize agent loop.

        Args:
            max_steps: Maximum reasoning steps
            tool_registry: Tool registry (uses default if None)
            enable_tools: Enable/disable tool execution
        """
        self.max_steps = max_steps
        self.enable_tools = enable_tools
        self.registry = tool_registry or get_registry()

        # Register clickhouse_query tool if not already registered
        self._register_default_tools()

        # Per-instance conversation history
        self.conversation_history: List[Dict[str, str]] = []

        logger.info(f"AgentLoop initialized with {len(self.registry.tool_names)} tools")

    def _register_default_tools(self):
        """Register default tools if they haven't been registered yet."""
        # Register ClickHouse query tool
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
                logger.info("✅ Registered clickhouse_query tool")

            except Exception as e:
                logger.warning(f"⚠️ Failed to register clickhouse_query tool: {e}")

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
        Process a user query with tool execution.

        Args:
            user_input: Raw user input text
            session: Optional session context

        Returns:
            Tuple of (response_text, tool_call_results)
        """
        log("agent", f"Processing: {user_input[:100]}...")

        tool_calls: List[ToolCallResult] = []

        try:
            # 1. Perception
            perception = self._perceive(user_input)
            log("agent", f"Intent: {perception.intent}, tool_hint: {perception.tool_hint}")

            # 2. Routing - select tool
            tool_name = self._route_to_tool(perception, session)
            log("agent", f"Routed to tool: {tool_name}")

            # 3. Execute tool if available
            tool_result = None
            if tool_name and self.enable_tools:
                tool_result = await self._execute_tool(tool_name, perception, session)
                if tool_result:
                    tool_calls.append(tool_result)
                    log("agent", f"Tool {tool_name} executed: {tool_result.success}")

            # 4. Generate response with tool results
            response = await self._generate_response(
                user_input,
                perception,
                tool_result,
                session,
            )

            # Update instance history
            self.conversation_history.append({"role": "user", "content": user_input})
            self.conversation_history.append({"role": "assistant", "content": response})

            return response, tool_calls

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

            # 3. Execute tool
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

        elif any(w in user_lower for w in [
            "database", "query", "sql", "logs", "metrics",
            "recent", "errors", "show me", "count", "statistics", "data"
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
        Route intent to appropriate tool.

        Uses the router to classify and the registry to find tools.
        """
        if not self.enable_tools:
            return None

        # First, use tool hint from perception
        if perception.tool_hint:
            tool = self.registry.get(perception.tool_hint)
            if tool and tool.metadata.enabled:
                return perception.tool_hint

        # Fallback to intent-based routing
        tool_name = self.registry.route_by_intent(perception.intent)
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
        Execute a tool with arguments derived from perception.

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

        # Execute
        try:
            execution_result = await self.registry.execute_tool(
                tool_name,
                arguments,
                timeout_seconds=30,
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

        # Add session context if available
        if session:
            arguments["session_id"] = session.session_id

        return arguments

    async def _generate_response(
        self,
        user_input: str,
        perception: PerceptionResult,
        tool_result: Optional[ToolCallResult],
        session: Optional[SessionContext],
    ) -> str:
        """
        Generate response using LLM with tool results.

        Args:
            user_input: Original user input
            perception: Perception result
            tool_result: Result from tool execution
            session: Optional session context

        Returns:
            Generated response string
        """
        try:
            # Build context
            context_parts = [f"User asked: {user_input}"]

            # Add tool results
            if tool_result:
                if tool_result.success:
                    context_parts.append(
                        f"Tool '{tool_result.tool_name}' returned: {self._format_tool_result(tool_result.result)}"
                    )
                else:
                    context_parts.append(
                        f"Tool '{tool_result.tool_name}' failed: {tool_result.error}"
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
                      "If a tool failed, explain what happened and suggest alternatives.",
            )

            return response

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return "I apologize, but I encountered an error generating my response."

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
