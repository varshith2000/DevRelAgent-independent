"""
Audit Trail Schemas - Production-Grade Data Models

Defines all audit-related data structures with comprehensive validation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal, Union
from datetime import datetime
from enum import Enum


class ActionType(str, Enum):
    """Types of actions that can be audited."""

    CHAT = "chat"
    TOOL_CALL = "tool_call"
    APPROVAL = "approval"
    GUARDRAIL_BLOCK = "guardrail_block"
    DATA_ACCESS = "data_access"
    CONFIG_CHANGE = "config_change"
    SYSTEM_EVENT = "system_event"


class ApprovalDecision(str, Enum):
    """Possible approval decisions."""

    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    TIMEOUT = "timeout"


class GuardrailResult(str, Enum):
    """Possible guardrail results."""

    PASSED = "passed"
    BLOCKED = "blocked"
    SANITIZED = "sanitized"
    WARNING = "warning"


class DataAccessed(BaseModel):
    """Information about data accessed during an action."""

    source: str = Field(description="Data source (e.g., 'clickhouse', 'github', 'filesystem')")
    tables: List[str] = Field(default_factory=list, description="Database tables accessed")
    columns: List[str] = Field(default_factory=list, description="Columns accessed (if applicable)")
    rows_affected: Optional[int] = Field(default=None, description="Number of rows affected")
    query_type: Optional[Literal["read", "write", "delete", "update"]] = Field(
        default=None, description="Type of query operation"
    )
    sensitive_data: bool = Field(default=False, description="Whether sensitive data was accessed")


class AuditEntry(BaseModel):
    """
    Comprehensive audit entry for tracking all system interactions.

    This is the primary audit log entry that captures complete context
    for every action in the system.
    """

    # Identification
    audit_id: str = Field(
        default_factory=lambda: f"audit_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        description="Unique audit entry ID"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO format timestamp"
    )

    # Session and User Information
    session_id: str = Field(description="Session identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier (if authenticated)")
    tenant_id: Optional[str] = Field(default=None, description="Tenant identifier (if multi-tenant)")
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID for distributed tracing")

    # Action Information
    action_type: ActionType = Field(description="Type of action being audited")
    action_name: Optional[str] = Field(default=None, description="Specific action/tool name")

    # Input/Output
    input_text: Optional[str] = Field(default=None, description="User input or query")
    input_tokens: Optional[int] = Field(default=None, description="Number of input tokens")
    output_text: Optional[str] = Field(default=None, description="Agent response")
    output_tokens: Optional[int] = Field(default=None, description="Number of output tokens")

    # Tool Execution Details
    tool_name: Optional[str] = Field(default=None, description="Name of tool executed")
    tool_arguments: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Arguments passed to tool (sanitized)"
    )
    tool_result: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Result from tool execution"
    )
    tool_execution_time_ms: Optional[int] = Field(
        default=None,
        description="Tool execution time in milliseconds"
    )
    tool_success: Optional[bool] = Field(default=None, description="Whether tool execution succeeded")

    # Approval Information
    approval_decision: Optional[ApprovalDecision] = Field(
        default=None,
        description="Approval decision if action required approval"
    )
    approval_user: Optional[str] = Field(default=None, description="User who made approval decision")
    approval_reason: Optional[str] = Field(default=None, description="Reason for approval/rejection")
    approval_risk_level: Optional[Literal["low", "medium", "high", "critical"]] = Field(
        default=None,
        description="Risk level of the action"
    )

    # Guardrail Information
    guardrail_result: Optional[GuardrailResult] = Field(
        default=None,
        description="Result of guardrail checks"
    )
    guardrail_triggered_by: Optional[List[str]] = Field(
        default_factory=list,
        description="List of guardrails that were triggered"
    )
    guardrail_details: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional guardrail details"
    )

    # Data Access Tracking
    data_accessed: Optional[List[DataAccessed]] = Field(
        default_factory=list,
        description="List of data sources accessed during action"
    )

    # Metadata
    ip_address: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client user agent")
    request_id: Optional[str] = Field(default=None, description="Request ID for tracking")
    parent_audit_id: Optional[str] = Field(default=None, description="Parent audit ID for related entries")

    # Performance Metrics
    total_processing_time_ms: Optional[int] = Field(
        default=None,
        description="Total processing time in milliseconds"
    )
    llm_calls: Optional[int] = Field(default=0, description="Number of LLM calls made")
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for the action/result"
    )

    # Error Information
    error_type: Optional[str] = Field(default=None, description="Type of error if action failed")
    error_message: Optional[str] = Field(default=None, description="Error message if action failed")
    error_stack_trace: Optional[str] = Field(default=None, description="Stack trace for debugging")

    # Additional Metadata
    tags: List[str] = Field(default_factory=list, description="Tags for categorization and filtering")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("input_text", "output_text", "error_message", "error_stack_trace")
    @classmethod
    def truncate_long_strings(cls, v: Optional[str]) -> Optional[str]:
        """Truncate long strings to prevent storage issues."""
        if v and len(v) > 10000:
            return v[:10000] + "... (truncated)"
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
        json_schema_extra = {
            "example": {
                "audit_id": "audit_202603111200001234567890",
                "timestamp": "2026-03-11T12:00:00.123456",
                "session_id": "sess_abc123",
                "user_id": "user@example.com",
                "action_type": "tool_call",
                "action_name": "clickhouse_query",
                "input_text": "Show me recent errors",
                "tool_name": "clickhouse_query",
                "tool_arguments": {"natural_query": "Show me recent errors"},
                "tool_success": True,
                "tool_execution_time_ms": 150,
                "data_accessed": [
                    {
                        "source": "clickhouse",
                        "tables": ["logs", "errors"],
                        "query_type": "read",
                        "rows_affected": 50
                    }
                ],
                "total_processing_time_ms": 200,
                "confidence_score": 0.95
            }
        }


class AuditFilter(BaseModel):
    """
    Filter criteria for querying audit entries.

    Allows flexible querying of the audit trail with various
    filter combinations.
    """

    # Time Range
    start_time: Optional[str] = Field(
        default=None,
        description="Start time (ISO format)"
    )
    end_time: Optional[str] = Field(
        default=None,
        description="End time (ISO format)"
    )

    # Session and User Filters
    session_id: Optional[str] = Field(default=None, description="Filter by session ID")
    user_id: Optional[str] = Field(default=None, description="Filter by user ID")
    tenant_id: Optional[str] = Field(default=None, description="Filter by tenant ID")
    correlation_id: Optional[str] = Field(default=None, description="Filter by correlation ID")

    # Action Filters
    action_types: Optional[List[ActionType]] = Field(
        default=None,
        description="Filter by action types"
    )
    action_name: Optional[str] = Field(default=None, description="Filter by specific action name")
    tool_name: Optional[str] = Field(default=None, description="Filter by tool name")

    # Result Filters
    tool_success: Optional[bool] = Field(default=None, description="Filter by tool success")
    approval_decision: Optional[ApprovalDecision] = Field(
        default=None,
        description="Filter by approval decision"
    )
    guardrail_result: Optional[GuardrailResult] = Field(
        default=None,
        description="Filter by guardrail result"
    )

    # Data Source Filters
    data_source: Optional[str] = Field(default=None, description="Filter by data source accessed")

    # Error Filters
    has_errors: Optional[bool] = Field(default=None, description="Filter entries with/without errors")

    # Pagination
    limit: int = Field(default=100, ge=1, le=10000, description="Maximum results to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    sort_by: Optional[Literal["timestamp", "action_type", "tool_execution_time_ms"]] = Field(
        default="timestamp",
        description="Field to sort by"
    )
    sort_order: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort order"
    )

    # Text Search
    search_text: Optional[str] = Field(
        default=None,
        description="Search in input_text and output_text"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "action_types": ["tool_call", "chat"],
                "tool_name": "clickhouse_query",
                "start_time": "2026-03-11T00:00:00",
                "limit": 50,
                "sort_by": "timestamp",
                "sort_order": "desc"
            }
        }


class AuditExport(BaseModel):
    """Audit export configuration."""

    session_id: str = Field(description="Session ID to export")
    format: Literal["json", "csv"] = Field(
        default="json",
        description="Export format"
    )
    include_metadata: bool = Field(
        default=True,
        description="Include metadata fields"
    )
    include_tool_calls: bool = Field(
        default=True,
        description="Include tool call details"
    )
    include_guardrails: bool = Field(
        default=True,
        description="Include guardrail results"
    )
    include_data_access: bool = Field(
        default=True,
        description="Include data access information"
    )
    sanitize_sensitive_data: bool = Field(
        default=True,
        description="Redact sensitive data in export"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_abc123",
                "format": "json",
                "include_metadata": True,
                "sanitize_sensitive_data": True
            }
        }


class AuditSummary(BaseModel):
    """Summary statistics for audit trail."""

    period_start: str = Field(description="Start of period (ISO format)")
    period_end: str = Field(description="End of period (ISO format)")

    # Total Counts
    total_entries: int = Field(description="Total number of audit entries")
    total_sessions: int = Field(description="Number of unique sessions")
    total_users: int = Field(description="Number of unique users")

    # By Action Type
    by_action_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of entries by action type"
    )

    # By Tool
    by_tool: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of entries by tool name"
    )

    # Approval Statistics
    approvals_requested: int = Field(default=0, description="Total approval requests")
    approvals_granted: int = Field(default=0, description="Approvals granted")
    approvals_rejected: int = Field(default=0, description="Approvals rejected")
    approvals_pending: int = Field(default=0, description="Approvals pending")
    approvals_timeout: int = Field(default=0, description="Approvals that timed out")

    # Guardrail Statistics
    guardrails_triggered: int = Field(default=0, description="Total guardrail triggers")
    guardrails_blocked: int = Field(default=0, description="Actions blocked by guardrails")
    guardrails_passed: int = Field(default=0, description="Actions that passed guardrails")

    # Data Access Statistics
    data_access_count: int = Field(default=0, description="Total data access events")
    by_data_source: Dict[str, int] = Field(
        default_factory=dict,
        description="Data access by source"
    )

    # Performance Statistics
    avg_response_time_ms: Optional[float] = Field(
        default=None,
        description="Average response time in milliseconds"
    )
    avg_tool_execution_time_ms: Optional[float] = Field(
        default=None,
        description="Average tool execution time in milliseconds"
    )

    # Error Statistics
    error_count: int = Field(default=0, description="Total number of errors")
    error_rate: Optional[float] = Field(
        default=None,
        description="Error rate (errors / total entries)"
    )
    by_error_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Errors by type"
    )

    # Top Sessions
    top_sessions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top sessions by activity"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "period_start": "2026-03-11T00:00:00",
                "period_end": "2026-03-11T23:59:59",
                "total_entries": 1523,
                "total_sessions": 45,
                "total_users": 12,
                "by_action_type": {
                    "chat": 856,
                    "tool_call": 512,
                    "approval": 89,
                    "guardrail_block": 66
                },
                "approvals_granted": 45,
                "approvals_rejected": 23,
                "error_count": 12,
                "error_rate": 0.0079
            }
        }
