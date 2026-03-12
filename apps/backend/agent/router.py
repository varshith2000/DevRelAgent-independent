"""
Router — Intent Classification with Confidence Scoring

Classifies user queries into intents with confidence scores.
Uses LLM-based routing for accurate intent classification with fallback handling.
"""

import logging
from typing import Optional, Dict, Any, Tuple, List
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


def classify_intent(perception: PerceptionResult) -> Tuple[str, float]:
    """
    Classify the intent using LLM-based routing with confidence scoring.

    Args:
        perception: Analyzed user input

    Returns:
        Tuple of (intent_name, confidence_score)
        - intent_name: The classified intent (may be "unknown")
        - confidence_score: Float between 0.0 and 1.0 indicating confidence
    """
    # If we have a clear tool hint from perception, use it with high confidence
    if perception.tool_hint and perception.tool_hint in INTENT_DEFINITIONS:
        logger.info(f"Using tool hint: {perception.tool_hint}")
        return perception.tool_hint, 0.95

    # Use LLM for intent classification with confidence
    try:
        intent, confidence = _classify_with_llm(perception.user_input)
        logger.info(f"LLM classified intent: {intent} with confidence: {confidence:.2f}")
        return intent, confidence
    except Exception as e:
        logger.warning(f"LLM classification failed: {e}, falling back to keyword matching")
        return _classify_with_keywords(perception.user_input)


def _classify_with_llm(user_input: str) -> Tuple[str, float]:
    """
    Use LLM to classify the user's intent with confidence scoring.

    Args:
        user_input: The user's query

    Returns:
        Tuple of (classified_intent_name, confidence_score)
    """
    # Build the intent classification prompt
    intent_options = []
    for intent_name, intent_data in INTENT_DEFINITIONS.items():
        examples = "\n".join(f"  - {example}" for example in intent_data["examples"][:2])  # Limit examples
        intent_options.append(f"- {intent_name}: {intent_data['description']}\n{examples}")

    intent_list = "\n".join(intent_options)

    system_prompt = """You are an expert intent classifier for a DevRel (Developer Relations) agent.
Your job is to classify user queries into the most appropriate intent category and provide a confidence score.

Analyze the user's query and respond with BOTH:
1. The intent name (one word from the list below)
2. A confidence score between 0.0 and 1.0

Format your response as: "intent_name|confidence_score"

For example: "database_query|0.95" or "unknown|0.3"

Confidence scoring guidelines:
- 0.9-1.0: Clear, unambiguous match with multiple supporting keywords
- 0.7-0.9: Good match with relevant keywords but some ambiguity
- 0.5-0.7: Partial match, could be multiple intents
- 0.3-0.5: Weak match, few or no relevant keywords
- 0.0-0.3: No clear match, likely unknown or unsupported

Available intents:
{intent_list}

If the query doesn't match any intent well (confidence < 0.5), use "unknown" as the intent."""

    user_prompt = f"""Classify this user query into one of the available intents with a confidence score:

Query: "{user_input}"

Response format: intent_name|confidence_score

Classification:"""

    # Call LLM for classification
    response = llm_generate(
        prompt=user_prompt,
        system=system_prompt,
        max_tokens=50
    )

    # Parse response
    try:
        parts = response.strip().split("|")
        if len(parts) == 2:
            intent = parts[0].strip().lower()
            confidence = float(parts[1].strip())

            # Clamp confidence to valid range
            confidence = max(0.0, min(1.0, confidence))
        else:
            # Fallback if response format is wrong
            intent = response.strip().lower()
            confidence = 0.5  # Default medium confidence
    except (ValueError, IndexError):
        # Fallback if parsing fails
        intent = response.strip().lower()
        confidence = 0.5  # Default medium confidence

    # Validate against known intents
    if intent in INTENT_DEFINITIONS:
        return intent, confidence
    else:
        logger.warning(f"LLM returned unknown intent: {intent}, using unknown with low confidence")
        return "unknown", 0.2


def _classify_with_keywords(user_input: str) -> Tuple[str, float]:
    """
    Fallback keyword-based intent classification with confidence scoring.

    Args:
        user_input: The user's query

    Returns:
        Tuple of (classified_intent_name, confidence_score)
    """
    query_lower = user_input.lower()

    # Track best match
    best_intent = "unknown"
    best_match_count = 0
    best_confidence = 0.0

    # Check each intent's keywords
    for intent_name, intent_data in INTENT_DEFINITIONS.items():
        if intent_name == "unknown":
            continue

        # Check examples and keywords
        all_keywords = []
        all_keywords.extend(intent_data["examples"])
        if "keywords" in intent_data:
            all_keywords.extend(intent_data["keywords"])

        # Count keyword matches
        match_count = 0
        for keyword in all_keywords:
            if keyword.lower() in query_lower:
                match_count += 1

        # Update best match
        if match_count > best_match_count:
            best_match_count = match_count
            best_intent = intent_name

    # Calculate confidence based on match quality
    if best_match_count == 0:
        confidence = 0.0
    elif best_match_count == 1:
        confidence = 0.4  # Low confidence for single keyword match
    elif best_match_count == 2:
        confidence = 0.6  # Medium confidence
    else:
        confidence = 0.8  # High confidence for multiple matches

    return best_intent, confidence


def get_fallback_suggestions(user_input: str, top_n: int = 3) -> List[Dict[str, Any]]:
    """
    Get fallback suggestions when intent is unknown or confidence is low.

    Args:
        user_input: The user's query
        top_n: Number of suggestions to return

    Returns:
        List of suggested intents with explanations
    """
    query_lower = user_input.lower()

    suggestions = []

    for intent_name, intent_data in INTENT_DEFINITIONS.items():
        if intent_name == "unknown":
            continue

        # Calculate match score
        score = 0.0
        matched_keywords = []

        all_keywords = []
        all_keywords.extend(intent_data["examples"])
        if "keywords" in intent_data:
            all_keywords.extend(intent_data["keywords"])

        for keyword in all_keywords:
            if keyword.lower() in query_lower:
                score += 0.3  # Increment score for each match
                matched_keywords.append(keyword)

        # Add score for partial word matches
        query_words = set(query_lower.split())
        for keyword in all_keywords:
            keyword_words = set(keyword.lower().split())
            overlap = query_words.intersection(keyword_words)
            if overlap:
                score += len(overlap) * 0.1

        # Only include if there's some relevance
        if score > 0:
            suggestions.append({
                "intent": intent_name,
                "description": intent_data["description"],
                "score": min(score, 1.0),  # Cap at 1.0
                "matched_keywords": matched_keywords,
                "examples": intent_data["examples"][:2]  # Show top 2 examples
            })

    # Sort by score and return top N
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return suggestions[:top_n]


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
