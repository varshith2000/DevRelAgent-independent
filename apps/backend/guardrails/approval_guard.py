"""
Approval Guard — Human-in-the-Loop Middleware

Ensures high-risk actions require explicit user approval before execution.
Integrates with SSE streaming to request approvals from the frontend.

Approval requests and their outcomes are persisted in the system of record,
scoped to a workspace/project, so the audit trail survives restarts and never
leaks across tenants. The in-process :class:`asyncio.Event` used to *wait* for a
decision is necessarily process-local; resolving an approval from a different
worker still requires a shared signal (tracked as a follow-up).
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from config.settings import get_settings
from models.approval import ApprovalEvent, ApprovalRequest, ApprovalResponse

logger = logging.getLogger(__name__)


class ApprovalGuard:
    """
    Middleware requiring approval for high-risk actions.

    Features:
    - Action-based approval requirements
    - Async wait for user approval/responses
    - Timeout handling with automatic rejection
    - Durable, tenant-scoped approval history
    - SSE event emission for real-time UI updates
    """

    # Actions requiring approval with risk levels
    ACTIONS_REQUIRING_APPROVAL: Dict[str, Literal["low", "medium", "high", "critical"]] = {
        "github_issue": "medium",
        "github_pr": "high",
        "browser_action": "critical",
        "write_operation": "high",
        "delete_operation": "critical",
        "schema_change": "high",
    }

    def __init__(self, timeout_seconds: int = 300):
        """
        Initialize the approval guard.

        Args:
            timeout_seconds: Default timeout for approval requests (default: 5 minutes)
        """
        self.timeout_seconds = timeout_seconds

        # In-flight approvals for this process (needed to wait on decisions).
        self.pending_approvals: Dict[str, ApprovalRequest] = {}
        self.approval_events: Dict[str, asyncio.Event] = {}
        self.approval_responses: Dict[str, ApprovalResponse] = {}

        # SSE event queue for emitting approval requests
        self.sse_queue: Optional[asyncio.Queue] = None

        logger.info("[OK] ApprovalGuard initialized")

    def requires_approval(self, action: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Return True if the action requires human approval."""
        return action in self.ACTIONS_REQUIRING_APPROVAL

    def get_risk_level(self, action: str) -> Optional[Literal["low", "medium", "high", "critical"]]:
        """Return the risk level for an action, or None if it needs no approval."""
        return self.ACTIONS_REQUIRING_APPROVAL.get(action)

    async def request_approval(
        self,
        action_type: str,
        plan: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> ApprovalResponse:
        """
        Request approval for an action and wait for a response.

        Args:
            action_type: Type of action requiring approval
            plan: Step-by-step plan of the action
            metadata: Additional context about the action
            timeout_seconds: Override default timeout
            project_id: Owning project (tenant) for durable storage
            workspace_id: Owning workspace for durable storage

        Returns:
            ApprovalResponse with approved=True/False
        """
        approval_id = str(uuid.uuid4())
        risk_level = self.get_risk_level(action_type)

        if not risk_level:
            # Action doesn't require approval
            return ApprovalResponse(
                approval_id=approval_id,
                approved=True,
                reason="Action does not require approval",
            )

        request = ApprovalRequest(
            approval_id=approval_id,
            action_type=action_type,
            plan=plan,
            risk_level=risk_level,
            metadata=metadata or {},
            timeout_seconds=timeout_seconds or self.timeout_seconds,
        )

        self.pending_approvals[approval_id] = request
        self.approval_events[approval_id] = asyncio.Event()
        self._persist_request(request, project_id, workspace_id)

        await self._emit_approval_request(request)
        logger.info(f"[PENDING] Approval requested: {approval_id} for {action_type}")

        try:
            await asyncio.wait_for(
                self.approval_events[approval_id].wait(), timeout=request.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning(f"[TIMEOUT] Approval timeout: {approval_id}")
            response = ApprovalResponse(
                approval_id=approval_id,
                approved=False,
                reason=f"Approval timeout after {request.timeout_seconds} seconds",
            )
            self._finish(request, status="timeout", response=response)
            return response

        response = self.approval_responses.get(approval_id)
        if not response:
            logger.error(f"[ERROR] Approval response missing: {approval_id}")
            response = ApprovalResponse(
                approval_id=approval_id,
                approved=False,
                reason="Internal error: approval response not found",
            )

        self._finish(request, status="approved" if response.approved else "rejected", response=response)
        logger.info(f"[OK] Approval {'granted' if response.approved else 'denied'}: {approval_id}")
        return response

    async def respond_to_approval(
        self,
        approval_id: str,
        approved: bool,
        user: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Handle an approval response from the frontend.

        Returns True if a waiting request was signalled.
        """
        if approval_id not in self.approval_events:
            logger.warning(f"[WARN] Approval not found or already processed: {approval_id}")
            return False

        self.approval_responses[approval_id] = ApprovalResponse(
            approval_id=approval_id,
            approved=approved,
            user=user,
            reason=reason,
        )
        self.approval_events[approval_id].set()
        logger.info(f"[OK] Approval response recorded: {approval_id} - {approved}")
        return True

    def list_pending_approvals(self, project_id: Optional[str] = None) -> List[ApprovalRequest]:
        """List pending approvals, optionally scoped to a project."""
        try:
            from db import repositories

            rows = repositories.list_pending_approvals(project_id=project_id)
        except Exception as e:
            logger.warning(f"Could not read approvals from database ({e}); using memory")
            return list(self.pending_approvals.values())

        return [
            ApprovalRequest(
                approval_id=row["approval_id"],
                action_type=row["action_type"],
                plan=row["plan"],
                risk_level=row["risk_level"],
                metadata=row["metadata"],
                timeout_seconds=row["timeout_seconds"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_approval_history(
        self,
        limit: int = 100,
        action_type: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get decided approvals for a scope, most recent first."""
        try:
            from db import repositories

            return repositories.get_approval_history(
                project_id=project_id, limit=limit, action_type=action_type
            )
        except Exception as e:
            logger.warning(f"Could not read approval history from database: {e}")
            return []

    def set_sse_queue(self, queue: asyncio.Queue):
        """Set the SSE queue for emitting approval events."""
        self.sse_queue = queue
        logger.info("[OK] SSE queue connected to ApprovalGuard")

    # ── Internals ─────────────────────────────────────────────────────

    def _persist_request(
        self, request: ApprovalRequest, project_id: Optional[str], workspace_id: Optional[str]
    ) -> None:
        try:
            from db import repositories

            repositories.create_approval(
                approval_id=request.approval_id,
                action_type=request.action_type,
                risk_level=request.risk_level,
                plan=request.plan,
                metadata=request.metadata or {},
                timeout_seconds=request.timeout_seconds,
                created_at=request.created_at,
                workspace_id=workspace_id,
                project_id=project_id,
            )
        except Exception as e:
            logger.warning(f"Could not persist approval request: {e}")

    def _finish(self, request: ApprovalRequest, status: str, response: ApprovalResponse) -> None:
        """Release in-process state and record the durable decision."""
        self.pending_approvals.pop(request.approval_id, None)
        self.approval_events.pop(request.approval_id, None)
        self.approval_responses.pop(request.approval_id, None)

        try:
            from db import repositories

            repositories.resolve_approval(
                request.approval_id,
                status=status,
                approved=response.approved,
                user=response.user,
                reason=response.reason,
                responded_at=response.timestamp,
                duration_seconds=(response.timestamp - request.created_at).total_seconds(),
            )
        except Exception as e:
            logger.warning(f"Could not persist approval decision: {e}")

    async def _emit_approval_request(self, request: ApprovalRequest):
        """Emit an SSE event for the approval request."""
        if self.sse_queue:
            event = ApprovalEvent(type="approval_required", data=request)
            try:
                await self.sse_queue.put(event)
                logger.debug(f"[SSE] Emitted approval event: {request.approval_id}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to emit approval event: {e}")
        else:
            logger.warning("[WARN] SSE queue not set, approval event not emitted")


# ── Global singleton ──────────────────────────────────────────────────

_approval_guard: Optional[ApprovalGuard] = None


def get_approval_guard() -> ApprovalGuard:
    """Get the global ApprovalGuard instance."""
    global _approval_guard
    if _approval_guard is None:
        _approval_guard = ApprovalGuard(timeout_seconds=get_settings().approval_timeout_seconds)
    return _approval_guard


def set_approval_guard(guard: ApprovalGuard):
    """Set a custom ApprovalGuard instance (useful for testing)."""
    global _approval_guard
    _approval_guard = guard


def reset_approval_guard():
    """Reset the global approval guard (mainly for testing)."""
    global _approval_guard
    _approval_guard = None
