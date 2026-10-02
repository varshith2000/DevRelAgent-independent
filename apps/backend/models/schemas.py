"""
Pydantic Models for DevRelAgent

Organized by domain:
- Perception models
- Memory models  
- Code search models
- Document search models (for team)
- Tool I/O models
- Action models
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ============== Perception Models ==============

class PerceptionResult(BaseModel):
    """Result of analyzing user input."""
    user_input: str
    intent: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    tool_hint: Optional[str] = None
    repo_url: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score for intent classification")
    fallback_suggestions: List[Dict[str, Any]] = Field(default_factory=list, description="Fallback suggestions when confidence is low")


# ============== Memory Models ==============

class MemoryItem(BaseModel):
    """Item stored in semantic memory."""
    text: str
    type: Literal["tool_output", "fact", "query", "code_chunk", "system"] = "fact"
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())
    tool_name: Optional[str] = None
    user_query: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class RepositoryState(BaseModel):
    """State of the currently indexed repository."""
    repo_url: Optional[str] = None
    repo_name: Optional[str] = None
    local_path: Optional[str] = None
    is_cloned: bool = False
    is_indexed: bool = False
    file_count: int = 0
    chunk_count: int = 0
    last_indexed: Optional[str] = None


# ============== Code Chunk Models ==============

class CodeChunk(BaseModel):
    """Represents a chunk of code (function, class, or text block)."""
    content: str
    file_path: str
    chunk_type: Literal["function", "class", "method", "text"] = "text"
    name: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    language: str = "python"
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Result from code search."""
    chunk: CodeChunk
    score: float
    rank: int


# ============== Document Search Models (For Team) ==============

class DocumentChunk(BaseModel):
    """A chunk of document content (for team to implement)."""
    content: str
    source: str                    # file path, URL, etc.
    source_type: Literal["pdf", "word", "text", "image", "web", "swagger"] = "text"
    page_number: Optional[int] = None
    chunk_index: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentSearchResult(BaseModel):
    """Result from document search."""
    chunk: DocumentChunk
    score: float
    rank: int


class IndexStatus(BaseModel):
    """Status of a document index."""
    source: str
    source_type: str
    chunk_count: int = 0
    last_indexed: Optional[str] = None
    is_ready: bool = False


# ============== Tool I/O Models ==============

class CloneRepositoryInput(BaseModel):
    """Input for clone_repository tool."""
    repo_url: str


class CloneRepositoryOutput(BaseModel):
    """Output from clone_repository tool."""
    success: bool
    local_path: str
    message: str


class IndexRepositoryInput(BaseModel):
    """Input for index_repository tool."""
    repo_path: Optional[str] = None


class IndexRepositoryOutput(BaseModel):
    """Output from index_repository tool."""
    success: bool
    file_count: int
    chunk_count: int
    message: str


class SearchCodeInput(BaseModel):
    """Input for search_code tool."""
    query: str
    top_k: int = 5


class SearchCodeOutput(BaseModel):
    """Output from search_code tool."""
    results: List[Dict[str, Any]]
    total_found: int


class GetFileContentInput(BaseModel):
    """Input for get_file_content tool."""
    file_path: str


class GetFileContentOutput(BaseModel):
    """Output from get_file_content tool."""
    content: str
    file_path: str
    line_count: int


class ToolCallResult(BaseModel):
    """Result of executing a tool."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool = True
    error: Optional[str] = None


# ============== API Models ==============

class ChatRequest(BaseModel):
    """Chat API request."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat API response."""
    response: str
    session_id: str
    tool_calls: List[ToolCallResult] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ChatStreamChunk(BaseModel):
    """Single chunk in streaming response."""
    type: Literal["token", "tool_call", "error", "done", "explanation"] = "token"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    session_id: str
    explanation: Optional['ToolExplanation'] = None  # Forward reference


class SessionContext(BaseModel):
    """Conversation session context."""
    session_id: str
    messages: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tool_call_history: List[ToolCallResult] = Field(default_factory=list)


class StreamChatRequest(BaseModel):
    """Streaming chat request."""
    message: str
    session_id: Optional[str] = None
    include_tool_calls: bool = True
    stream_tokens: bool = True


# ============== Explain-Before-Act Models ==============

class ToolExplanation(BaseModel):
    """Explanation of what a tool will do before execution."""
    tool_name: str
    action: str
    parameters: Dict[str, Any]
    reasoning: str
    expected_outcome: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    requires_approval: bool = False
    risk_level: Optional[Literal["low", "medium", "high", "critical"]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "tool_name": "clickhouse_query",
                "action": "Query ClickHouse database with natural language",
                "parameters": {"natural_query": "Show recent errors"},
                "reasoning": "To retrieve recent error information from the database for analysis",
                "expected_outcome": "A list of recent error logs with timestamps and error messages",
                "confidence": 0.9,
                "requires_approval": False,
                "risk_level": "low"
            }
        }


# ============== Structured Agent Outputs (Phase 5) ==============

class EvidenceItem(BaseModel):
    """Single piece of evidence supporting an observation."""
    source: str = Field(description="Source of evidence (e.g., 'clickhouse', 'logs', 'traces')")
    data: Dict[str, Any] = Field(description="Raw evidence data")
    timestamp: Optional[str] = Field(default=None, description="When evidence was collected")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence in this evidence")

    class Config:
        json_schema_extra = {
            "example": {
                "source": "clickhouse",
                "data": {"error_rate": 15.5, "service": "api"},
                "timestamp": "2026-03-07T10:30:00Z",
                "confidence": 0.95
            }
        }


class AgentObservation(BaseModel):
    """
    Structured observation from agent investigation.

    Enforces consistent output format for all agent findings.
    """
    observation_id: str = Field(default_factory=lambda: f"obs_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Core observation fields
    observation_type: Literal["anomaly", "pattern", "insight", "correlation", "trend"]
    title: str = Field(description="Short, descriptive title")
    description: str = Field(description="Detailed description of the observation")

    # Evidence supporting the observation
    evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Supporting evidence from various sources"
    )

    # Impact assessment
    impact: Literal["critical", "high", "medium", "low", "informational"] = "medium"
    affected_services: List[str] = Field(default_factory=list, description="Services affected by this observation")
    affected_users: Optional[int] = Field(default=None, description="Estimated number of affected users")

    # Confidence and certainty
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence in this observation")
    certainty_level: Literal["confirmed", "likely", "possible", "uncertain"] = "possible"

    # Suggested actions
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Actionable recommendations based on this observation"
    )
    priority: Literal["immediate", "urgent", "normal", "low"] = "normal"

    # Metadata
    investigation_id: Optional[str] = Field(default=None, description="Associated investigation ID")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "observation_type": "anomaly",
                "title": "API error rate spike",
                "description": "API service error rate increased from 2% to 15% in the last 30 minutes",
                "evidence": [
                    {
                        "source": "clickhouse",
                        "data": {"error_rate_before": 2.0, "error_rate_after": 15.0},
                        "timestamp": "2026-03-07T10:30:00Z",
                        "confidence": 0.95
                    }
                ],
                "impact": "high",
                "affected_services": ["api"],
                "affected_users": 5000,
                "confidence": 0.9,
                "certainty_level": "confirmed",
                "suggested_actions": [
                    "Investigate recent API deployments",
                    "Check API service health",
                    "Review API error logs for patterns"
                ],
                "priority": "urgent"
            }
        }


class InvestigationState(BaseModel):
    """State of an investigation."""
    investigation_id: str
    title: str
    description: str

    # Timeline
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = Field(default=None)

    # Status
    status: Literal["open", "in_progress", "awaiting_info", "completed", "closed"] = "open"
    priority: Literal["critical", "high", "medium", "low"] = "medium"

    # Investigation scope
    initial_query: str = Field(description="Initial user query that started investigation")
    services_involved: List[str] = Field(default_factory=list)
    time_range_start: Optional[str] = Field(default=None)
    time_range_end: Optional[str] = Field(default=None)

    # Findings
    observations: List[AgentObservation] = Field(default_factory=list)
    total_observations: int = Field(default=0)

    # Actions taken
    actions_taken: List[str] = Field(default_factory=list, description="Actions already performed")
    pending_actions: List[str] = Field(default_factory=list, description="Actions yet to be performed")

    # Resolution
    root_cause: Optional[str] = Field(default=None, description="Identified root cause")
    resolution: Optional[str] = Field(default=None, description="How the issue was resolved")
    resolution_status: Optional[Literal["resolved", "mitigated", "investigating", "false_positive"]] = Field(default=None)

    # Metrics
    tools_used: List[str] = Field(default_factory=list)
    queries_executed: int = Field(default=0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Metadata
    assigned_to: Optional[str] = Field(default=None, description="Who is investigating")
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "investigation_id": "inv_20260307_001",
                "title": "API latency degradation",
                "description": "Investigate increased P95 latency in API service",
                "status": "in_progress",
                "priority": "high",
                "initial_query": "Why is the API slow?",
                "services_involved": ["api", "database"],
                "observations": [],
                "actions_taken": ["Checked error rate", "Analyzed latency metrics"],
                "confidence_score": 0.7
            }
        }


class LearningMemory(BaseModel):
    """
    Learning from past investigations.

    Stores patterns and solutions for future reference.
    """
    memory_id: str = Field(default_factory=lambda: f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Pattern information
    pattern_type: Literal["error_pattern", "performance_pattern", "anomaly_pattern", "success_pattern"]
    pattern_name: str = Field(description="Short, memorable name for this pattern")
    pattern_description: str = Field(description="Detailed description of the pattern")

    # When this pattern applies
    trigger_conditions: List[str] = Field(
        description="Conditions that trigger this pattern recognition"
    )
    applicable_services: List[str] = Field(default_factory=list)

    # Solution/Action
    solution: str = Field(description="How this pattern was resolved or should be handled")
    solution_steps: List[str] = Field(default_factory=list, description="Step-by-step solution")

    # Effectiveness
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    times_applied: int = Field(default=0)
    times_successful: int = Field(default=0)

    # References
    source_investigation_ids: List[str] = Field(default_factory=list)
    related_observations: List[str] = Field(default_factory=list)

    # Validation
    validated: bool = Field(default=False)
    last_validated: Optional[str] = Field(default=None)

    class Config:
        json_schema_extra = {
            "example": {
                "pattern_type": "error_pattern",
                "pattern_name": "Database connection pool exhaustion",
                "pattern_description": "High error rate with 'connection timeout' messages during peak load",
                "trigger_conditions": [
                    "Error rate > 10%",
                    "Database service",
                    "Contains 'connection timeout'"
                ],
                "applicable_services": ["database"],
                "solution": "Increase connection pool size and implement connection retries",
                "solution_steps": [
                    "Increase max_connections in database config",
                    "Add retry logic with exponential backoff",
                    "Monitor connection pool metrics"
                ],
                "success_rate": 0.85,
                "times_applied": 10,
                "times_successful": 8
            }
        }


class DeckUIUpdate(BaseModel):
    """
    Update for dashboard UI (The Deck).

    Structured format for UI updates.
    """
    update_type: Literal["alert", "status", "metric", "progress", "completion"]
    title: str
    message: str

    # Priority and urgency
    priority: Literal["critical", "high", "medium", "low", "info"] = "info"

    # Associated data
    investigation_id: Optional[str] = Field(default=None)
    observation_ids: List[str] = Field(default_factory=list)

    # UI elements
    show_in_dashboard: bool = Field(default=True)
    dashboard_section: Optional[Literal["alerts", "status", "metrics", "investigations"]] = Field(default=None)

    # Actionable items
    action_buttons: List[Dict[str, str]] = Field(default_factory=list)
    related_links: List[Dict[str, str]] = Field(default_factory=list)

    # Metadata
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = Field(default=None)
    tags: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "update_type": "alert",
                "title": "API Error Rate Spike",
                "message": "API error rate increased to 15% in the last 30 minutes",
                "priority": "high",
                "investigation_id": "inv_20260307_001",
                "dashboard_section": "alerts",
                "action_buttons": [
                    {"label": "View Details", "action": "navigate", "target": "/investigations/inv_20260307_001"},
                    {"label": "Start Investigation", "action": "investigate", "target": "/investigate?query=api+errors"}
                ]
            }
        }


class StructuredAgentResponse(BaseModel):
    """
    Complete structured response from agent.

    Enforces consistent output format for all agent responses.
    """
    response_id: str = Field(default_factory=lambda: f"resp_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Query information
    query: str = Field(description="Original user query")
    query_type: Literal["investigation", "question", "action", "analysis"] = "question"

    # Main response
    summary: str = Field(description="Brief summary of findings or response")
    detailed_explanation: str = Field(description="Detailed explanation")

    # Observations (structured)
    observations: List[AgentObservation] = Field(default_factory=list)

    # Investigation state (if applicable)
    investigation: Optional[InvestigationState] = Field(default=None)

    # Tools and data sources used
    tools_used: List[str] = Field(default_factory=list)
    data_sources: List[str] = Field(default_factory=list)

    # Confidence and certainty
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    certainty_level: Literal["confirmed", "likely", "possible", "uncertain", "unknown"] = "possible"

    # Next steps / Actions
    next_steps: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)

    # Supporting data
    supporting_data: Dict[str, Any] = Field(default_factory=dict)

    # UI updates
    ui_updates: List[DeckUIUpdate] = Field(default_factory=list)

    # Metadata
    response_time_ms: Optional[int] = Field(default=None)
    tokens_used: Optional[int] = Field(default=None)
    tags: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Why is the API slow?",
                "query_type": "investigation",
                "summary": "API P95 latency increased from 200ms to 850ms due to database query performance",
                "detailed_explanation": "Analysis shows database queries are taking 3x longer than baseline...",
                "observations": [
                    {
                        "observation_type": "anomaly",
                        "title": "Database latency spike",
                        "description": "Database P95 increased from 150ms to 450ms",
                        "impact": "high",
                        "confidence": 0.9
                    }
                ],
                "confidence": 0.85,
                "certainty_level": "likely",
                "next_steps": [
                    "Analyze slow query logs",
                    "Check database performance metrics"
                ]
            }
        }
