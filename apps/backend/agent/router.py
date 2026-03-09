"""
Router — Intent Classification

Classifies user queries into intents and selects the appropriate tool/skill.
Uses LLM-based routing for accurate intent classification.
"""

import logging
from typing import Optional, Dict, Any
from models.schemas import PerceptionResult
from agent.llm_provider import llm_generate
from tools.registry import get_registry

logger = logging.getLogger(__name__)


# Intent definitions with descriptions and associated tools
INTENT_DEFINITIONS = {
    "database_query": {
        "description": "Query logs, metrics, traces, or other observability data",
        "tools": ["clickhouse_query", "get_error_rate", "get_top_errors", "get_latency_metrics"],
        "examples": [
            "Show me recent errors",
            "What's the error rate for the API?",
            "How many requests failed today?",
            "Show me slow queries",
            "What's the latency distribution?"
        ]
    },
    "search_code": {
        "description": "Search for code, functions, classes, or implementation details",
        "tools": ["code_search"],
        "examples": [
            "Find the authentication code",
            "Where is the rate limiting implemented?",
            "Show me the User model",
            "How does the caching work?"
        ]
    },
    "document_search": {
        "description": "Search documentation, guides, or help content",
        "tools": ["rag_search", "doc_search"],
        "examples": [
            "How do I authenticate?",
            "What's the API for user management?",
            "How do I set up monitoring?",
            "Where's the deployment guide?"
        ]
    },
    "incident_investigation": {
        "description": "Investigate system issues, outages, or performance problems",
        "tools": ["get_error_rate", "get_top_errors", "get_latency_metrics", "correlate_error_with_traces"],
        "examples": [
            "Why is the API slow?",
            "Investigate the recent outage",
            "What's causing high error rates?",
            "Debug the performance issue"
        ]
    },
    "gap_detection": {
        "description": "Find missing documentation or identify areas needing improvement",
        "tools": ["detect_documentation_gaps"],
        "examples": [
            "What documentation is missing?",
            "Are there any gaps in our docs?",
            "What features aren't documented?"
        ]
    },
    "config_generation": {
        "description": "Generate configuration files, setup code, or deployment configs",
        "tools": ["generate_config", "generate_opentelemetry_config"],
        "examples": [
            "Generate an OpenTelemetry config",
            "Create a monitoring dashboard config",
            "Set up logging configuration"
        ]
    },
    "dashboard_management": {
        "description": "Create, modify, or manage monitoring dashboards",
        "tools": ["create_dashboard", "get_dashboard"],
        "examples": [
            "Create a dashboard for API metrics",
            "Set up monitoring for the database",
            "Build a service health dashboard"
        ]
    },
    "ticket_management": {
        "description": "Create issues, tickets, or feature requests",
        "tools": ["create_structured_ticket", "create_gap_tickets", "draft_github_issue"],
        "examples": [
            "Create a bug report",
            "File a feature request",
            "Report missing documentation"
        ]
    },
    "status_check": {
        "description": "Check system health, status, or current state",
        "tools": ["get_error_rate", "get_top_errors"],
        "examples": [
            "How's the system doing?",
            "Check service health",
            "What's the current status?"
        ]
    },
    "unknown": {
        "description": "Unclear or unsupported request",
        "tools": [],
        "examples": [
            "Tell me a joke",
            "What's the weather?",
            "Unrelated questions"
        ]
    }
}


def classify_intent(perception: PerceptionResult) -> str:
    """
    Classify the intent using LLM-based routing for accurate classification.

    Args:
        perception: Analyzed user input

    Returns:
        Intent name to execute
    """
    # If we have a clear tool hint from perception, use it
    if perception.tool_hint and perception.tool_hint in INTENT_DEFINITIONS:
        logger.info(f"Using tool hint: {perception.tool_hint}")
        return perception.tool_hint

    # Use LLM for intent classification
    try:
        intent = _classify_with_llm(perception.user_input)
        logger.info(f"LLM classified intent: {intent}")
        return intent
    except Exception as e:
        logger.warning(f"LLM classification failed: {e}, falling back to keyword matching")
        return _classify_with_keywords(perception.user_input)


def _classify_with_llm(user_input: str) -> str:
    """
    Use LLM to classify the user's intent.

    Args:
        user_input: The user's query

    Returns:
        Classified intent name
    """
    # Build the intent classification prompt
    intent_options = []
    for intent_name, intent_data in INTENT_DEFINITIONS.items():
        examples = "\n".join(f"  - {example}" for example in intent_data["examples"][:2])  # Limit examples
        intent_options.append(f"- {intent_name}: {intent_data['description']}\n{examples}")

    intent_list = "\n".join(intent_options)

    system_prompt = """You are an expert intent classifier for a DevRel (Developer Relations) agent.
Your job is to classify user queries into the most appropriate intent category.

Analyze the user's query and respond with ONLY the intent name (one word from the list below).
Do not explain your reasoning - just return the intent name.

Available intents:
{intent_list}

If the query doesn't match any intent well, respond with "unknown"."""

    user_prompt = f"""Classify this user query into one of the available intents:

Query: "{user_input}"

Intent:"""

    # Call LLM for classification
    response = llm_generate(
        prompt=user_prompt,
        system=system_prompt,
        max_tokens=50
    )

    # Clean and validate response
    intent = response.strip().lower()

    # Validate against known intents
    if intent in INTENT_DEFINITIONS:
        return intent
    else:
        logger.warning(f"LLM returned unknown intent: {intent}, using unknown")
        return "unknown"


def _classify_with_keywords(user_input: str) -> str:
    """
    Fallback keyword-based intent classification.

    Args:
        user_input: The user's query

    Returns:
        Classified intent name
    """
    query_lower = user_input.lower()

    # Check each intent's keywords
    for intent_name, intent_data in INTENT_DEFINITIONS.items():
        if intent_name == "unknown":
            continue

        # Check examples and keywords
        all_keywords = []
        all_keywords.extend(intent_data["examples"])
        if "keywords" in intent_data:
            all_keywords.extend(intent_data["keywords"])

        for keyword in all_keywords:
            if keyword.lower() in query_lower:
                return intent_name

    return "unknown"


def get_tools_for_intent(intent: str) -> list:
    """
    Get the recommended tools for a given intent.

    Args:
        intent: Intent name

    Returns:
        List of tool names
    """
    if intent in INTENT_DEFINITIONS:
        return INTENT_DEFINITIONS[intent]["tools"]
    return []


def get_intent_description(intent: str) -> str:
    """
    Get the description for a given intent.

    Args:
        intent: Intent name

    Returns:
        Intent description
    """
    if intent in INTENT_DEFINITIONS:
        return INTENT_DEFINITIONS[intent]["description"]
    return "Unknown intent"
