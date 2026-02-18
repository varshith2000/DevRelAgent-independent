"""
Agent Loop — Core Cognitive Pipeline

Implements: Perception → Routing → Memory → Action

This is the main orchestration module. Each cognitive layer is a step:
1. Perception: Parse user query, extract intent and entities
2. Routing: Classify intent, select tool(s) 
3. Memory: Check conversation history, KeDB, RAG for context
4. Action: Execute selected tool, format response
"""

import sys
from typing import Optional, List, Dict, Any
from agent.llm_provider import llm_generate
from models.schemas import PerceptionResult


def log(stage: str, msg: str):
    """Log to stderr."""
    sys.stderr.write(f"[{stage}] {msg}\n")
    sys.stderr.flush()


class AgentLoop:
    """
    Main agent loop implementing the 4-layer cognitive pipeline.
    
    Usage:
        loop = AgentLoop()
        response = await loop.process("How do I authenticate?")
    """

    def __init__(self, max_steps: int = 10):
        self.max_steps = max_steps
        self.conversation_history: List[Dict[str, str]] = []

    async def process(self, user_input: str) -> str:
        """
        Process a user query through the cognitive pipeline.
        
        Args:
            user_input: Raw user input text
            
        Returns:
            Agent response string
        """
        log("agent", f"Processing: {user_input[:100]}...")

        # 1. Perception
        perception = self._perceive(user_input)
        log("agent", f"Intent: {perception.intent}")

        # 2. Routing (select tool/skill)
        # TODO: Implement proper routing based on intent
        
        # 3. Memory (check context)
        self.conversation_history.append({"role": "user", "content": user_input})

        # 4. Action (execute tool or generate answer)
        response = self._generate_response(user_input, perception)
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    def _perceive(self, user_input: str) -> PerceptionResult:
        """Extract intent, entities, and tool hints from user input."""
        # Simple rule-based perception for now
        import re
        
        user_lower = user_input.lower()
        github_match = re.search(r'https?://github\.com/[\w\-]+/[\w\-]+', user_input)
        
        intent = "general_question"
        tool_hint = None
        entities = []
        repo_url = github_match.group(0) if github_match else None
        
        if repo_url:
            intent = "clone_repo"
            tool_hint = "clone_repository"
            entities = [repo_url]
        elif any(w in user_lower for w in ["index", "build index"]):
            intent = "index_repo"
            tool_hint = "index_repository"
        elif any(w in user_lower for w in ["search", "find", "how does", "where is"]):
            intent = "search_code"
            tool_hint = "search_code"
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

    def _generate_response(self, user_input: str, perception: PerceptionResult) -> str:
        """Generate a response using the LLM."""
        try:
            return llm_generate(
                prompt=f"User asked: {user_input}\nIntent: {perception.intent}\nProvide a helpful response.",
                max_tokens=500,
                system="You are DevRelAgent, an AI-powered developer relations assistant.",
            )
        except Exception as e:
            log("agent", f"LLM generation failed: {e}")
            return f"I encountered an error processing your request. Please try again."
