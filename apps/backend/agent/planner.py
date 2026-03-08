"""
ReAct Planner — Multi-Step Reasoning with Chain of Thought

Implements ReAct (Reasoning + Acting) pattern for complex queries that require
multiple tool calls and cross-domain correlation.

Features:
- Chain of Thought prompting for reasoning
- Step-by-step plan generation
- Tool execution with observation
- Context accumulation across steps
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from agent.llm_provider import llm_generate

logger = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    """Single step in the reasoning chain."""
    step_number: int
    thought: str
    action: str
    observation: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_number": self.step_number,
            "thought": self.thought,
            "action": self.action,
            "observation": self.observation,
            "tools_used": self.tools_used,
            "timestamp": self.timestamp.isoformat()
        }


class ReActPlanner:
    """
    Multi-step planner using ReAct (Reasoning + Acting) pattern.

    For complex queries requiring multiple tool calls and cross-domain analysis.
    """

    def __init__(self, tool_registry, llm_provider=None, max_steps: int = 10):
        """
        Initialize the ReAct planner.

        Args:
            tool_registry: Tool registry for executing actions
            llm_provider: LLM provider for generating thoughts/actions
            max_steps: Maximum number of reasoning steps
        """
        self.registry = tool_registry
        self.llm = llm_provider
        self.max_steps = max_steps

        logger.info(f"ReActPlanner initialized with max_steps={max_steps}")

    async def plan(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> List[ReasoningStep]:
        """
        Generate multi-step plan for complex query.

        Args:
            query: User's query/question
            context: Additional context (session, history, etc.)

        Returns:
            List of reasoning steps
        """
        logger.info(f"Starting multi-step planning for query: {query[:100]}...")

        steps = []
        current_context = context.copy()

        for i in range(self.max_steps):
            # Generate thought
            thought = await self._generate_thought(query, current_context, steps)

            # Determine next action
            action = await self._determine_action(thought, current_context)

            step = ReasoningStep(
                step_number=i + 1,
                thought=thought,
                action=action,
                tools_used=self._extract_tools(action)
            )
            steps.append(step)

            # Check if we're done
            if self._is_complete(action):
                logger.info(f"Planning complete after {i + 1} steps")
                break

            # Execute action and get observation
            observation = await self._execute_action(action, current_context)
            step.observation = observation

            # Update context with observation
            current_context = self._update_context(current_context, observation, step)

        logger.info(f"Multi-step planning completed: {len(steps)} steps")
        return steps

    async def _generate_thought(
        self,
        query: str,
        context: Dict[str, Any],
        previous_steps: List[ReasoningStep]
    ) -> str:
        """
        Generate next thought using Chain of Thought.

        Args:
            query: Original query
            context: Current context
            previous_steps: Previous reasoning steps

        Returns:
            Generated thought
        """
        steps_text = self._format_steps(previous_steps)

        prompt = f"""You are analyzing a complex query that requires multi-step reasoning.

Query: {query}

Context: {self._format_context(context)}

Previous Steps:
{steps_text if steps_text else "None (this is the first step)"}

Think step by step about what to do next. Consider:
1. What information do I currently have?
2. What information do I still need to answer the query?
3. Which tools can help me get that information?
4. How can I correlate findings from different sources (logs, metrics, code, docs)?

Provide your thought:"""

        try:
            thought = await llm_generate(
                prompt=prompt,
                max_tokens=500,
                system="You are a reasoning assistant. Think step by step and be specific about what information you need and which tools to use."
            )
            return thought.strip()
        except Exception as e:
            logger.error(f"Failed to generate thought: {e}")
            return "Need to gather more information to answer this query."

    async def _determine_action(self, thought: str, context: Dict[str, Any]) -> str:
        """
        Determine next action based on thought.

        Args:
            thought: Current thought
            context: Current context

        Returns:
            Action description
        """
        available_tools = self.registry.list_tool_names()

        prompt = f"""Based on your thought, determine the next action.

Thought: {thought}

Available tools:
{', '.join(available_tools)}

Determine the next action. If you have enough information to provide a complete answer, say "COMPLETE: [your answer]".
Otherwise, specify which tool to use with parameters.

Action format:
- For tool use: "USE_TOOL: tool_name [with parameters]"
- For completion: "COMPLETE: [final answer]"

Action:"""

        try:
            action = await llm_generate(
                prompt=prompt,
                max_tokens=300,
                system="You are an action planner. Be specific about which tool to use and with what parameters. Say COMPLETE when you have enough information."
            )
            return action.strip()
        except Exception as e:
            logger.error(f"Failed to determine action: {e}")
            return "COMPLETE: Unable to determine next action"

    async def _execute_action(self, action: str, context: Dict[str, Any]) -> str:
        """
        Execute the action and return observation.

        Args:
            action: Action description
            context: Current context

        Returns:
            Observation from executing the action
        """
        if action.startswith("COMPLETE:"):
            return "Query complete"

        if action.startswith("USE_TOOL:"):
            # Parse tool and parameters
            tool_info = action.replace("USE_TOOL:", "").strip()
            parts = tool_info.split(maxsplit=1)

            if len(parts) < 1:
                return "Invalid action format"

            tool_name = parts[0].strip()
            parameters = self._parse_parameters(parts[1]) if len(parts) > 1 else {}

            try:
                # Execute tool
                result = await self.registry.execute_tool(tool_name, parameters)

                if result.success:
                    return str(result.result)[:500] if result.result else "Tool executed successfully"
                else:
                    return f"Tool execution failed: {result.error}"

            except Exception as e:
                return f"Error executing {tool_name}: {str(e)}"

        return "Unable to execute action"

    def _parse_parameters(self, param_str: str) -> Dict[str, Any]:
        """
        Parse parameters from action string.

        Args:
            param_str: Parameter string

        Returns:
            Dictionary of parameters
        """
        # Simple parsing - in production, use more sophisticated NLP
        params = {}
        if "query=" in param_str or "query :" in param_str:
            # Extract query parameter
            import re
            match = re.search(r'query[:=]\s*["\']?([^"\'\n]+)["\']?', param_str)
            if match:
                params["query"] = match.group(1)

        return params

    def _is_complete(self, action: str) -> bool:
        """Check if action indicates completion."""
        return action.startswith("COMPLETE:")

    def _format_steps(self, steps: List[ReasoningStep]) -> str:
        """Format reasoning steps for prompt."""
        if not steps:
            return ""

        formatted = []
        for step in steps:
            formatted.append(f"Step {step.step_number}:")
            formatted.append(f"  Thought: {step.thought}")
            formatted.append(f"  Action: {step.action}")
            if step.observation:
                formatted.append(f"  Observation: {step.observation[:200]}...")

        return "\n".join(formatted)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context for prompt."""
        if not context:
            return "No additional context"

        formatted = []
        for key, value in context.items():
            if isinstance(value, (str, int, float, bool)):
                formatted.append(f"{key}: {value}")
            elif isinstance(value, list) and len(value) > 0:
                formatted.append(f"{key}: {len(value)} items")
            elif isinstance(value, dict):
                formatted.append(f"{key}: [dict with {len(value)} keys]")

        return "\n".join(formatted)

    def _extract_tools(self, action: str) -> List[str]:
        """Extract tool names from action string."""
        tools = []
        available_tools = self.registry.list_tool_names()

        for tool in available_tools:
            if tool.lower() in action.lower():
                tools.append(tool)

        return tools

    def _update_context(
        self,
        context: Dict[str, Any],
        observation: str,
        step: ReasoningStep
    ) -> Dict[str, Any]:
        """Update context with new observation."""
        new_context = context.copy()

        # Add observation to history
        if "observations" not in new_context:
            new_context["observations"] = []

        new_context["observations"].append({
            "step": step.step_number,
            "action": step.action,
            "observation": observation,
            "timestamp": step.timestamp.isoformat()
        })

        # Keep last 10 observations
        if len(new_context["observations"]) > 10:
            new_context["observations"] = new_context["observations"][-10:]

        return new_context
