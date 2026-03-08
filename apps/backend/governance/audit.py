"""
Governance Module — Auditability and User Tracking

Implements enterprise-grade governance features:
- User action tracking
- Audit logging
- Tenant isolation
- Data access tracking
- Approval history
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
import hashlib

logger = logging.getLogger(__name__)

# Storage paths
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "data/audit")
TENANT_CONFIG_PATH = os.getenv("TENANT_CONFIG_PATH", "data/tenants")


@dataclass
class AuditEvent:
    """Single audit event."""
    event_id: str = field(default_factory=lambda: f"evt_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Event details
    event_type: Literal[
        "query_received",
        "tool_executed",
        "data_accessed",
        "action_approved",
        "action_rejected",
        "investigation_created",
        "investigation_updated",
        "config_changed",
        "error_occurred"
    ]

    # User information
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None

    # Event data
    details: Dict[str, Any] = field(default_factory=dict)

    # IP and metadata
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    # Request context
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id
        }

    def get_hash(self) -> str:
        """Get hash of event for integrity checking."""
        data_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()


class AuditLogger:
    """
    Enterprise-grade audit logger.

    Tracks:
    - Who asked what
    - What data was accessed
    - What actions were taken
    - What was approved/rejected
    """

    def __init__(self, storage_path: str = AUDIT_LOG_PATH):
        """Initialize audit logger."""
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        # In-memory buffer for recent events
        self.event_buffer: List[AuditEvent] = []
        self.buffer_size = 1000

    def log_event(self, event: AuditEvent):
        """
        Log an audit event.

        Args:
            event: Audit event to log
        """
        try:
            # Add to buffer
            self.event_buffer.append(event)

            # Trim buffer if needed
            if len(self.event_buffer) > self.buffer_size:
                self.event_buffer = self.event_buffer[-self.buffer_size:]

            # Write to file
            date_str = datetime.now().strftime("%Y-%m-%d")
            file_path = os.path.join(self.storage_path, f"audit_{date_str}.jsonl")

            with open(file_path, 'a') as f:
                f.write(json.dumps(event.to_dict()) + "\n")

            logger.debug(f"Logged audit event: {event.event_type} - {event.event_id}")

        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

    def log_query(self, user_id: str, query: str, session_id: Optional[str] = None, **kwargs):
        """Log user query."""
        event = AuditEvent(
            event_type="query_received",
            user_id=user_id,
            session_id=session_id,
            details={
                "query": query,
                "query_length": len(query)
            },
            **kwargs
        )
        self.log_event(event)

    def log_tool_execution(
        self,
        user_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        session_id: Optional[str] = None,
        **kwargs
    ):
        """Log tool execution."""
        event = AuditEvent(
            event_type="tool_executed",
            user_id=user_id,
            session_id=session_id,
            details={
                "tool_name": tool_name,
                "arguments": self._sanitize_arguments(arguments),
                "success": result.get("success", False),
                "execution_time_ms": result.get("execution_time_ms"),
                "error": result.get("error")
            },
            **kwargs
        )
        self.log_event(event)

    def log_data_access(
        self,
        user_id: str,
        data_source: str,
        access_type: Literal["read", "write", "delete"],
        data_description: str,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """Log data access."""
        event = AuditEvent(
            event_type="data_accessed",
            user_id=user_id,
            session_id=session_id,
            details={
                "data_source": data_source,
                "access_type": access_type,
                "data_description": data_description
            },
            **kwargs
        )
        self.log_event(event)

    def log_approval_decision(
        self,
        user_id: str,
        action_type: str,
        approved: bool,
        reason: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """Log approval decision."""
        event = AuditEvent(
            event_type="action_approved" if approved else "action_rejected",
            user_id=user_id,
            session_id=session_id,
            details={
                "action_type": action_type,
                "approved": approved,
                "reason": reason
            },
            **kwargs
        )
        self.log_event(event)

    def get_user_history(
        self,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit history for a user.

        Args:
            user_id: User ID to get history for
            limit: Maximum number of events

        Returns:
            List of audit events for user
        """
        try:
            events = []
            date_files = sorted(
                Path(self.storage_path).glob("audit_*.jsonl"),
                reverse=True
            )

            for date_file in date_files:
                if len(events) >= limit:
                    break

                with open(date_file, 'r') as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            if event.get("user_id") == user_id:
                                events.append(event)
                                if len(events) >= limit:
                                    break
                        except json.JSONDecodeError:
                            continue

            return events[:limit]

        except Exception as e:
            logger.error(f"Failed to get user history: {e}")
            return []

    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize arguments for audit logging."""
        sanitized = {}

        sensitive_keys = ["password", "token", "secret", "key", "auth"]

        for key, value in arguments.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_arguments(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_arguments(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                sanitized[key] = str(value)[:200] if len(str(value)) > 200 else value

        return sanitized

    def get_audit_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get audit summary for date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Audit summary statistics
        """
        try:
            if not start_date:
                start_date = (datetime.now()).strftime("%Y-%m-%d")
            if not end_date:
                end_date = (datetime.now()).strftime("%Y-%m-%d")

            # Parse dates
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            summary = {
                "total_events": 0,
                "by_type": {},
                "by_user": {},
                "by_hour": {},
                "approvals_granted": 0,
                "approvals_rejected": 0
            }

            # Scan audit files
            current_date = start
            while current_date <= end:
                file_path = os.path.join(
                    self.storage_path,
                    f"audit_{current_date.strftime('%Y-%m-%d')}.jsonl"
                )

                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        for line in f:
                            try:
                                event = json.loads(line)
                                summary["total_events"] += 1

                                # Count by type
                                event_type = event.get("event_type", "unknown")
                                summary["by_type"][event_type] = summary["by_type"].get(event_type, 0) + 1

                                # Count by user
                                user = event.get("user_id", "anonymous")
                                summary["by_user"][user] = summary["by_user"].get(user, 0) + 1

                                # Count approvals
                                if event_type == "action_approved":
                                    summary["approvals_granted"] += 1
                                elif event_type == "action_rejected":
                                    summary["approvals_rejected"] += 1

                            except json.JSONDecodeError:
                                continue

                current_date += timedelta(days=1)

            return {
                "success": True,
                "summary": summary,
                "date_range": {
                    "start": start_date,
                    "end": end_date
                }
            }

        except Exception as e:
            logger.error(f"Failed to get audit summary: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class TenantManager:
    """
    Multi-tenant management and isolation.

    Implements tenant isolation for enterprise deployments.
    """

    def __init__(self, config_path: str = TENANT_CONFIG_PATH):
        """Initialize tenant manager."""
        self.config_path = config_path
        Path(config_path).mkdir(parents=True, exist_ok=True)

        self.tenants: Dict[str, Dict[str, Any]] = {}
        self._load_tenants()

    def _load_tenants(self):
        """Load tenant configurations."""
        try:
            tenant_file = os.path.join(self.config_path, "tenants.json")

            if os.path.exists(tenant_file):
                with open(tenant_file, 'r') as f:
                    self.tenants = json.load(f)

                logger.info(f"Loaded {len(self.tenants)} tenants")

        except Exception as e:
            logger.error(f"Failed to load tenants: {e}")
            self.tenants = {}

    def _save_tenants(self):
        """Save tenant configurations."""
        try:
            tenant_file = os.path.join(self.config_path, "tenants.json")

            with open(tenant_file, 'w') as f:
                json.dump(self.tenants, f, indent=2)

            logger.debug(f"Saved {len(self.tenants)} tenants")

        except Exception as e:
            logger.error(f"Failed to save tenants: {e}")

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new tenant.

        Args:
            tenant_id: Unique tenant ID
            name: Tenant name
            settings: Tenant settings

        Returns:
            Creation result
        """
        try:
            if tenant_id in self.tenants:
                return {
                    "success": False,
                    "error": f"Tenant '{tenant_id}' already exists"
                }

            # Create tenant config
            self.tenants[tenant_id] = {
                "tenant_id": tenant_id,
                "name": name,
                "created_at": datetime.now().isoformat(),
                "settings": settings,
                "isolation": {
                    "database_schema": f"tenant_{tenant_id}",
                    "file_storage": f"/tenants/{tenant_id}",
                    "queue_prefix": f"{tenant_id}:"
                }
            }

            # Create tenant directory
            tenant_dir = os.path.join(self.config_path, tenant_id)
            Path(tenant_dir).mkdir(parents=True, exist_ok=True)

            # Save tenants
            self._save_tenants()

            logger.info(f"Created tenant: {tenant_id}")

            return {
                "success": True,
                "tenant_id": tenant_id,
                "tenant": self.tenants[tenant_id]
            }

        except Exception as e:
            logger.error(f"Failed to create tenant: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant configuration."""
        return self.tenants.get(tenant_id)

    def list_tenants(self) -> List[Dict[str, Any]]:
        """List all tenants."""
        return list(self.tenants.values())

    def is_user_in_tenant(self, user_id: str, tenant_id: str) -> bool:
        """
        Check if user belongs to tenant.

        Args:
            user_id: User ID to check
            tenant_id: Tenant ID

        Returns:
            True if user is in tenant
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False

        users = tenant.get("settings", {}).get("users", [])
        return user_id in users

    def get_tenant_for_user(self, user_id: str) -> Optional[str]:
        """Get tenant ID for a user."""
        for tenant_id, tenant_config in self.tenants.items():
            users = tenant_config.get("settings", {}).get("users", [])
            if user_id in users:
                return tenant_id
        return None


class GovernanceManager:
    """
    Main governance manager combining audit and tenant management.

    Features:
    - Complete audit trail
    - User action tracking
    - Multi-tenant isolation
    - Data access logging
    """

    def __init__(self):
        """Initialize governance manager."""
        self.audit_logger = AuditLogger()
        self.tenant_manager = TenantManager()

    def track_user_action(
        self,
        user_id: str,
        action: str,
        details: Dict[str, Any],
        tenant_id: Optional[str] = None
    ):
        """
        Track user action for audit.

        Args:
            user_id: User ID
            action: Action performed
            details: Action details
            tenant_id: Optional tenant ID
        """
        self.audit_logger.log_event(
            AuditEvent(
                event_type="action_approved",
                user_id=user_id,
                tenant_id=tenant_id,
                details={
                    "action": action,
                    **details
                }
            )
        )

    def check_permission(
        self,
        user_id: str,
        action: str,
        resource: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission for action.

        Args:
            user_id: User ID
            action: Action to check
            resource: Optional resource

        Returns:
            True if user has permission
        """
        # TODO: Implement permission checking logic
        # For now, allow all actions
        return True

    def get_user_audit_trail(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get complete audit trail for user.

        Args:
            user_id: User ID
            tenant_id: Optional tenant ID to filter by
            limit: Maximum events

        Returns:
            User audit trail
        """
        events = self.audit_logger.get_user_history(user_id, limit)

        # Filter by tenant if specified
        if tenant_id:
            events = [e for e in events if e.get("tenant_id") == tenant_id]

        return {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "total_events": len(events),
            "events": events,
            "metadata": {
                "limit": limit,
                "filtered": tenant_id is not None
            }
        }


# Global singleton
_governance_manager: Optional[GovernanceManager] = None


def get_governance_manager() -> GovernanceManager:
    """Get the global governance manager instance."""
    global _governance_manager
    if _governance_manager is None:
        _governance_manager = GovernanceManager()
    return _governance_manager


def set_governance_manager(manager: GovernanceManager):
    """Set a custom governance manager instance."""
    global _governance_manager
    _governance_manager = manager


# Add timedelta import at the top
from datetime import timedelta
