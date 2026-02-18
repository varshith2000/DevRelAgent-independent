"""
Tool Registry — Registration and selection of agent tools

TODO: Implement tool registration framework for Phase 1
- Register tools with name, description, and handler
- LLM function calling schema generation
- Tool selection based on intent
"""

from typing import Dict, Any, Callable, Optional, List


class ToolRegistry:
    """
    Registry of available tools the agent can call.
    
    Usage:
        registry = ToolRegistry()
        registry.register("search_code", search_code_fn, "Search code semantically")
        tool = registry.get("search_code")
    """

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, handler: Callable, description: str = "", schema: Optional[Dict] = None):
        """Register a tool."""
        self._tools[name] = {
            "name": name,
            "handler": handler,
            "description": description,
            "schema": schema or {},
        }

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools."""
        return [{"name": t["name"], "description": t["description"]} for t in self._tools.values()]

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())


# Singleton
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
