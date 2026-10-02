"""
Base Skill Framework

Defines the interface for composable multi-tool workflows.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """Result of skill execution."""
    success: bool
    result: Any
    steps: List[Dict[str, Any]]
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class Skill(ABC):
    """Base class for all skills."""
    
    def __init__(self, name: str, description: str, required_tools: List[str]):
        self.name = name
        self.description = description
        self.required_tools = required_tools
        self.steps = []
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any], **kwargs) -> SkillResult:
        """Execute the skill with given context and parameters."""
        pass
    
    def log_step(self, step_name: str, result: Any, metadata: Optional[Dict[str, Any]] = None):
        """Log a step in the skill execution."""
        step = {
            "step": step_name,
            "result": result,
            "metadata": metadata or {},
            "timestamp": logger.handlers[0].formatter.formatTime(logger.makeRecord(
                name="skill", level=logging.INFO, pathname="", lineno=0,
                msg="", args=(), exc_info=None
            )) if logger.handlers else None
        }
        self.steps.append(step)
        logger.info(f"[{self.name}] {step_name}: {result}")
    
    def clear_steps(self):
        """Clear execution steps."""
        self.steps = []
    
    def get_execution_summary(self) -> str:
        """Get a human-readable summary of execution steps."""
        if not self.steps:
            return "No steps executed."
        
        summary = f"Skill: {self.name}\n"
        for i, step in enumerate(self.steps, 1):
            summary += f"{i}. {step['step']}: {step['result']}\n"
        return summary


class SkillRegistry:
    """Registry for managing skills."""
    
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
    
    def register(self, skill: Skill):
        """Register a skill."""
        self._skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")
    
    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """List all registered skills."""
        return list(self._skills.values())
    
    def list_skill_names(self) -> List[str]:
        """List all skill names."""
        return list(self._skills.keys())
    
    def route_by_intent(self, intent: str) -> Optional[str]:
        """Route intent to appropriate skill."""
        intent_lower = intent.lower()
        
        # Simple intent routing - can be enhanced with ML
        if any(keyword in intent_lower for keyword in ['error', 'issue', 'problem', 'bug', 'fail']):
            return 'diagnose_error'
        elif any(keyword in intent_lower for keyword in ['search', 'find', 'doc', 'documentation']):
            return 'search_docs'
        
        return None


# Global skill registry
_skill_registry = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry."""
    return _skill_registry


def skill(name: str, description: str, required_tools: List[str]):
    """Decorator to register a skill."""
    def decorator(skill_class):
        skill_instance = skill_class(name, description, required_tools)
        get_skill_registry().register(skill_instance)
        return skill_class
    return decorator