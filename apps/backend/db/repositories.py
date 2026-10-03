"""Tenant-scoped persistence for audit entries and approval decisions.

These helpers are the only place that reads/writes ``audit_records`` and
``approval_records``. They own their short-lived sessions so callers (the audit
logger, the approval guard) do not have to thread a session through.

Every read accepts an optional ``project_id``/``workspace_id`` scope; when one
is given, only that tenant's rows are returned.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models_audit import ApprovalRecord, AuditRecord

logger = logging.getLogger(__name__)


def _new_session() -> Session:
    # Imported lazily so this module stays import-cheap and test-friendly.
    from db.session import get_session_factory

    return get_session_factory()()


def _enum_value(value: Any) -> Any:
    """Store enum members as their primitive value."""
    return getattr(value, "value", value)


# ── Audit records ─────────────────────────────────────────────────────


def record_audit(
    payload: Dict[str, Any],
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    """Persist one (already sanitized) audit entry."""
    session = _new_session()
    try:
        session.add(
            AuditRecord(
                id=str(payload.get("audit_id") or ""),
                workspace_id=workspace_id,
                project_id=project_id,
                session_id=str(payload.get("session_id") or ""),
                user_id=payload.get("user_id"),
                action_type=str(_enum_value(payload.get("action_type")) or ""),
                action_name=payload.get("action_name"),
                tool_name=payload.get("tool_name"),
                approval_decision=_enum_value(payload.get("approval_decision")),
                guardrail_result=_enum_value(payload.get("guardrail_result")),
                error_type=payload.get("error_type"),
                timestamp=str(payload.get("timestamp") or ""),
                payload=payload,
            )
        )
        session.commit()
    finally:
        session.close()


def fetch_audit_payloads(
    *,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100000,
) -> List[Dict[str, Any]]:
    """Return audit payloads for a scope, newest first."""
    session = _new_session()
    try:
        query = select(AuditRecord)
        if project_id is not None:
            query = query.where(AuditRecord.project_id == project_id)
        if workspace_id is not None:
            query = query.where(AuditRecord.workspace_id == workspace_id)
        if session_id is not None:
            query = query.where(AuditRecord.session_id == session_id)
        if start_time:
            query = query.where(AuditRecord.timestamp >= start_time)
        if end_time:
            query = query.where(AuditRecord.timestamp <= end_time)
        query = query.order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc()).limit(limit)
        records = session.scalars(query).all()
        return [dict(record.payload) for record in records]
    finally:
        session.close()


# ── Approval records ──────────────────────────────────────────────────


def create_approval(
    *,
    approval_id: str,
    action_type: str,
    risk_level: str,
    plan: List[str],
    metadata: Dict[str, Any],
    timeout_seconds: int,
    created_at: datetime,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    """Insert a pending approval."""
    session = _new_session()
    try:
        session.add(
            ApprovalRecord(
                id=approval_id,
                workspace_id=workspace_id,
                project_id=project_id,
                action_type=action_type,
                risk_level=risk_level,
                status="pending",
                plan=list(plan),
                metadata_json=dict(metadata or {}),
                timeout_seconds=timeout_seconds,
                created_at=created_at,
            )
        )
        session.commit()
    finally:
        session.close()


def resolve_approval(
    approval_id: str,
    *,
    status: str,
    approved: bool,
    user: Optional[str],
    reason: Optional[str],
    responded_at: datetime,
    duration_seconds: Optional[float],
) -> bool:
    """Record an approval decision. Returns False if the request is unknown."""
    session = _new_session()
    try:
        record = session.get(ApprovalRecord, approval_id)
        if record is None:
            return False
        record.status = status
        record.approved = approved
        record.user = user
        record.reason = reason
        record.responded_at = responded_at
        record.duration_seconds = duration_seconds
        session.commit()
        return True
    finally:
        session.close()


def list_pending_approvals(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return pending approvals, optionally scoped to a project."""
    session = _new_session()
    try:
        query = select(ApprovalRecord).where(ApprovalRecord.status == "pending")
        if project_id is not None:
            query = query.where(ApprovalRecord.project_id == project_id)
        query = query.order_by(ApprovalRecord.created_at)
        records = session.scalars(query).all()
        return [
            {
                "approval_id": record.id,
                "action_type": record.action_type,
                "plan": record.plan or [],
                "risk_level": record.risk_level,
                "metadata": record.metadata_json or {},
                "timeout_seconds": record.timeout_seconds,
                "created_at": record.created_at,
            }
            for record in records
        ]
    finally:
        session.close()


def get_approval_history(
    project_id: Optional[str] = None,
    limit: int = 100,
    action_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return decided approvals, most recent first."""
    session = _new_session()
    try:
        query = select(ApprovalRecord).where(ApprovalRecord.status != "pending")
        if project_id is not None:
            query = query.where(ApprovalRecord.project_id == project_id)
        if action_type:
            query = query.where(ApprovalRecord.action_type == action_type)
        query = query.order_by(ApprovalRecord.created_at.desc()).limit(limit)
        records = session.scalars(query).all()
        return [_history_entry(record) for record in records]
    finally:
        session.close()


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _history_entry(record: ApprovalRecord) -> Dict[str, Any]:
    return {
        "approval_id": record.id,
        "action_type": record.action_type,
        "risk_level": record.risk_level,
        "approved": record.approved,
        "user": record.user,
        "reason": record.reason,
        "created_at": _iso(record.created_at),
        "responded_at": _iso(record.responded_at),
        "duration_seconds": record.duration_seconds,
        "plan": record.plan or [],
        "metadata": record.metadata_json or {},
    }
