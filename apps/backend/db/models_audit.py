"""Durable, tenant-scoped audit trail and approval records.

These replace the process-local caches that used to hold audit entries and
approval decisions: both are now rows in the system of record, scoped to a
workspace and project, so they survive restarts and never leak across tenants.

The full sanitized payload is kept as JSON while the filterable fields are
promoted to columns for indexing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AuditRecord(Base):
    """One audited action, owned by a workspace/project."""

    __tablename__ = "audit_records"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[str] = mapped_column(String(120), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(320), index=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    action_name: Mapped[Optional[str]] = mapped_column(String(200))
    tool_name: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    approval_decision: Mapped[Optional[str]] = mapped_column(String(20))
    guardrail_result: Mapped[Optional[str]] = mapped_column(String(20))
    error_type: Mapped[Optional[str]] = mapped_column(String(120))
    # ISO-8601 timestamp string, kept as text so it round-trips exactly.
    timestamp: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # Tamper-evident hash chain, one independent chain per project/workspace.
    chain_scope: Mapped[str] = mapped_column(String(80), default="global", index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    entry_hash: Mapped[str] = mapped_column(String(64), default="", index=True)


class ApprovalRecord(Base):
    """A human-in-the-loop approval request and its outcome."""

    __tablename__ = "approval_records"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    # pending | approved | rejected | timeout
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean)
    user: Mapped[Optional[str]] = mapped_column(String(200))
    reason: Mapped[Optional[str]] = mapped_column(String(1000))
    plan: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(default=300)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[float]] = mapped_column()
