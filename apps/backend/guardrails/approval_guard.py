"""
Approval Guard — Human-in-the-Loop Middleware

Ensures high-risk actions require explicit user approval before execution.
Integrates with SSE streaming to request approvals from the frontend.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from models.approval import ApprovalEvent, ApprovalRequest, ApprovalResponse

logger = logging.getLogger(__name__)


class ApprovalGuard:
    """
    Middleware requiring approval for high-risk actions.

    Features:
    - Action-based approval requirements
    - Async wait for user approval/responses
    - Timeout handling with automatic rejection
    - Approval history logging
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

        # Pending approvals waiting for responses
        self.pending_approvals: Dict[str, ApprovalRequest] = {}

        # Async events for signaling when approval is received
        self.approval_events: Dict[str, asyncio.Event] = {}

        # Stored responses (populated by approval endpoint)
        self.approval_responses: Dict[str, ApprovalResponse] = {}

        # Approval history for audit logging
        self.approval_history: List[Dict[str, Any]] = []

        # SSE event queue for emitting approval requests
        self.sse_queue: Optional[asyncio.Queue] = None

        logger.info("✅ ApprovalGuard initialized")

    def requires_approval(self, action: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if an action requires approval.

        Args:
            action: Action/tool name to check
            context: Optional context for the action

        Returns:
            True if action requires approval
        """
        return action in self.ACTIONS_REQUIRING_APPROVAL

    def get_risk_level(self, action: str) -> Optional[Literal["low", "medium", "high", "critical"]]:
        """
        Get the risk level for an action.

        Args:
            action: Action/tool name

        Returns:
            Risk level or None if action doesn't require approval
        """
        return self.ACTIONS_REQUIRING_APPROVAL.get(action)

    async def request_approval(
        self,
        action_type: str,
        plan: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None
    ) -> ApprovalResponse:
        """
        Request approval for an action and wait for response.

        Args:
            action_type: Type of action requiring approval
            plan: Step-by-step plan of the action
            metadata: Additional context about the action
            timeout_seconds: Override default timeout

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
                reason="Action does not require approval"
            )

        # Create approval request
        request = ApprovalRequest(
            approval_id=approval_id,
            action_type=action_type,
            plan=plan,
            risk_level=risk_level,
            metadata=metadata or {},
            timeout_seconds=timeout_seconds or self.timeout_seconds
        )

        # Store pending approval
        self.pending_approvals[approval_id] = request
        self.approval_events[approval_id] = asyncio.Event()

        # Emit SSE event for frontend
        await self._emit_approval_request(request)

        logger.info(f"⏳ Approval requested: {approval_id} for {action_type}")

        # Wait for response with timeout
        timeout = request.timeout_seconds
        try:
            await asyncio.wait_for(
                self.approval_events[approval_id].wait(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # Timeout - auto reject
            logger.warning(f"⏰ Approval timeout: {approval_id}")

            # Clean up
            del self.pending_approvals[approval_id]
            del self.approval_events[approval_id]

            # Create rejection response
            response = ApprovalResponse(
                approval_id=approval_id,
                approved=False,
                reason=f"Approval timeout after {timeout} seconds"
            )

            # Log to history
            self._log_to_history(request, response)

            return response

        # Get response (set by approval endpoint)
        response = self.approval_responses.get(approval_id)

        if not response:
            # Shouldn't happen, but handle gracefully
            logger.error(f"❌ Approval response missing: {approval_id}")
            response = ApprovalResponse(
                approval_id=approval_id,
                approved=False,
                reason="Internal error: approval response not found"
            )

        # Clean up
        del self.pending_approvals[approval_id]
        del self.approval_events[approval_id]
        del self.approval_responses[approval_id]

        # Log to history
        self._log_to_history(request, response)

        logger.info(f"✅ Approval {'granted' if response.approved else 'denied'}: {approval_id}")

        return response

    async def respond_to_approval(
        self,
        approval_id: str,
        approved: bool,
        user: Optional[str] = None,
        reason: Optional[str] = None
    ) -> bool:
        """
        Handle approval response from frontend.

        Called by the approval API endpoint when user approves/rejects.

        Args:
            approval_id: ID of the approval request
            approved: True if approved, False if rejected
            user: Optional user identifier
            reason: Optional reason for rejection

        Returns:
            True if response was recorded successfully
        """
        if approval_id not in self.approval_events:
            logger.warning(f"⚠️ Approval not found or already processed: {approval_id}")
            return False

        # Store response
        response = ApprovalResponse(
            approval_id=approval_id,
            approved=approved,
            user=user,
            reason=reason
        )

        self.approval_responses[approval_id] = response

        # Signal waiting coroutine
        self.approval_events[approval_id].set()

        logger.info(f"📝 Approval response recorded: {approval_id} - {approved}")

        return True

    def list_pending_approvals(self) -> List[ApprovalRequest]:
        """
        List all currently pending approvals.

        Returns:
            List of pending approval requests
        """
        return list(self.pending_approvals.values())

    def get_approval_history(
        self,
        limit: int = 100,
        action_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get approval history.

        Args:
            limit: Maximum number of history entries to return
            action_type: Filter by specific action type

        Returns:
            List of approval history entries
        """
        history = self.approval_history

        if action_type:
            history = [h for h in history if h.get("action_type") == action_type]

        # Return most recent first
        return list(reversed(history[-limit:]))

    def set_sse_queue(self, queue: asyncio.Queue):
        """
        Set the SSE queue for emitting approval events.

        Called during initialization to connect to the SSE streaming system.

        Args:
            queue: Async queue for SSE events
        """
        self.sse_queue = queue
        logger.info("📡 SSE queue connected to ApprovalGuard")

    async def _emit_approval_request(self, request: ApprovalRequest):
        """
        Emit SSE event for approval request.

        Args:
            request: Approval request to emit
        """
        if self.sse_queue:
            event = ApprovalEvent(type="approval_required", data=request)
            try:
                await self.sse_queue.put(event)
                logger.debug(f"📤 Emitted approval event: {request.approval_id}")
            except Exception as e:
                logger.error(f"❌ Failed to emit approval event: {e}")
        else:
            logger.warning("⚠️ SSE queue not set, approval event not emitted")

    def _log_to_history(self, request: ApprovalRequest, response: ApprovalResponse):
        """
        Log approval to history for audit trail.

        Args:
            request: Original approval request
            response: Approval response
        """
        entry = {
            "approval_id": request.approval_id,
            "action_type": request.action_type,
            "risk_level": request.risk_level,
            "approved": response.approved,
            "user": response.user,
            "reason": response.reason,
            "created_at": request.created_at.isoformat(),
            "responded_at": response.timestamp.isoformat(),
            "duration_seconds": (response.timestamp - request.created_at).total_seconds(),
            "plan": request.plan,
            "metadata": request.metadata
        }

        self.approval_history.append(entry)

        # Keep history manageable
        if len(self.approval_history) > 1000:
            self.approval_history = self.approval_history[-1000:]


# Global singleton instance
_approval_guard: Optional[ApprovalGuard] = None


def get_approval_guard() -> ApprovalGuard:
    """
    Get the global ApprovalGuard instance.

    Returns:
        The singleton ApprovalGuard instance
    """
    global _approval_guard
    if _approval_guard is None:
        _approval_guard = ApprovalGuard()
    return _approval_guard


def set_approval_guard(guard: ApprovalGuard):
    """
    Set a custom ApprovalGuard instance (useful for testing).

    Args:
        guard: ApprovalGuard instance to use
    """
    global _approval_guard
    _approval_guard = guard


def reset_approval_guard():
    """Reset the global approval guard (mainly for testing)."""
    global _approval_guard
    _approval_guard = None
