"""
Approval Models — Human-in-the-Loop Framework

Pydantic models for approval requests and responses.
Used by the ApprovalGuard middleware to manage HITL workflows.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime
import uuid


class ApprovalRequest(BaseModel):
    """Request for user approval before executing high-risk actions."""

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: Literal["github_issue", "github_pr", "browser_action", "write_operation"]
    plan: List[str] = Field(description="Step-by-step plan of the action")
    risk_level: Literal["low", "medium", "high", "critical"]
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=30, le=1800)
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "action_type": "github_issue",
                "plan": [
                    "Create issue in repo org/repo",
                    "Title: Fix authentication bug",
                    "Labels: bug, high-priority"
                ],
                "risk_level": "medium",
                "metadata": {"repo": "org/repo", "title": "Fix authentication bug"},
                "timeout_seconds": 300
            }
        }


class ApprovalResponse(BaseModel):
    """Response to an approval request."""

    approval_id: str
    approved: bool
    user: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    reason: Optional[str] = Field(default=None, description="Optional reason for rejection")

    class Config:
        json_schema_extra = {
            "example": {
                "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                "approved": True,
                "user": "user@example.com",
                "timestamp": "2026-03-07T10:30:00Z",
                "reason": None
            }
        }


class ApprovalEvent(BaseModel):
    """SSE event emitted when approval is required."""

    type: Literal["approval_required"] = Field(default="approval_required")
    data: ApprovalRequest

    class Config:
        json_schema_extra = {
            "example": {
                "type": "approval_required",
                "data": {
                    "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                    "action_type": "github_issue",
                    "plan": ["Create issue"],
                    "risk_level": "medium",
                    "timeout_seconds": 300
                }
            }
        }


class ApprovalStatus(BaseModel):
    """Current status of all pending approvals."""

    pending_approvals: List[ApprovalRequest] = Field(default_factory=list)
    total_pending: int = Field(default=0)
    last_updated: datetime = Field(default_factory=datetime.now)

    class Config:
        json_schema_extra = {
            "example": {
                "pending_approvals": [],
                "total_pending": 0,
                "last_updated": "2026-03-07T10:30:00Z"
            }
        }
