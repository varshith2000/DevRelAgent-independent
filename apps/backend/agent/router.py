"""
Router — Intent Classification

Classifies user queries into intents and selects the appropriate tool/skill.
"""

from typing import Optional
from models.schemas import PerceptionResult


def classify_intent(perception: PerceptionResult) -> str:
    """
    Classify the intent and determine which tool/skill to use.
    
    Args:
        perception: Analyzed user input
        
    Returns:
        Tool or skill name to execute
    """
    # TODO: Implement LLM-based routing for ambiguous intents
    return perception.tool_hint or "search_code"
