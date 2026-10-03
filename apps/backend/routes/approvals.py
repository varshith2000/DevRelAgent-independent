"""
Approval API Routes

Endpoints for managing HITL (Human-in-the-Loop) approvals.
Frontend uses these endpoints to respond to approval requests.
"""

import logging
from typing import List, Optional

from auth.deps import RequestContext, get_request_context
from fastapi import APIRouter, Depends, HTTPException, Query
from guardrails.approval_guard import get_approval_guard
from models.approval import ApprovalRequest, ApprovalResponse, ApprovalStatus
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Every approvals endpoint requires an authenticated caller.
router = APIRouter(
    prefix="/approvals", tags=["approvals"], dependencies=[Depends(get_request_context)]
)


# Request/Response models for the API
class ApprovalDecisionRequest(BaseModel):
    """Request model for submitting an approval decision."""
    approved: bool
    user: Optional[str] = None
    reason: Optional[str] = None


class ApprovalListResponse(BaseModel):
    """Response model for listing pending approvals."""
    pending_approvals: List[ApprovalRequest]
    total_pending: int


@router.post("/{approval_id}", response_model=ApprovalResponse)
async def respond_to_approval(
    approval_id: str,
    decision: ApprovalDecisionRequest,
    context: RequestContext = Depends(get_request_context),
):
    """
    Submit an approval decision (approve or reject).

    Called by the frontend when user clicks Approve/Reject buttons.

    Args:
        approval_id: ID of the approval request
        decision: Approval decision with approved flag

    Returns:
        The recorded approval response

    Raises:
        HTTPException: If approval not found or already processed
    """
    approval_guard = get_approval_guard()

    # Check if approval is pending in the caller's tenant
    project_id = context.project.id if context.project else None
    pending = approval_guard.list_pending_approvals(project_id=project_id)
    approval_exists = any(p.approval_id == approval_id for p in pending)

    if not approval_exists:
        raise HTTPException(
            status_code=404,
            detail=f"Approval {approval_id} not found or already processed"
        )

    # Record the response
    success = await approval_guard.respond_to_approval(
        approval_id=approval_id,
        approved=decision.approved,
        user=decision.user,
        reason=decision.reason
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to record approval decision for {approval_id}"
        )

    logger.info(f"✅ Approval decision recorded: {approval_id} - approved={decision.approved}")

    # Return the response
    return ApprovalResponse(
        approval_id=approval_id,
        approved=decision.approved,
        user=decision.user,
        reason=decision.reason
    )


@router.get("/pending", response_model=ApprovalStatus)
async def list_pending_approvals(
    context: RequestContext = Depends(get_request_context),
):
    """
    List currently pending approvals for the caller's project.

    Returns:
        List of currently pending approval requests
    """
    approval_guard = get_approval_guard()
    project_id = context.project.id if context.project else None
    pending = approval_guard.list_pending_approvals(project_id=project_id)

    return ApprovalStatus(
        pending_approvals=pending,
        total_pending=len(pending)
    )


@router.get("/history")
async def get_approval_history(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of history entries"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    context: RequestContext = Depends(get_request_context),
):
    """
    Get approval history for audit trail.

    Args:
        limit: Maximum number of entries to return
        action_type: Optional filter by action type

    Returns:
        List of approval history entries
    """
    approval_guard = get_approval_guard()
    project_id = context.project.id if context.project else None
    history = approval_guard.get_approval_history(
        limit=limit, action_type=action_type, project_id=project_id
    )

    return {
        "history": history,
        "total": len(history),
        "limit": limit
    }


@router.get("/actions")
async def list_actions_requiring_approval():
    """
    List all actions that require approval.

    Returns information about which actions require approval and their risk levels.

    Returns:
        Dictionary of action types and their risk levels
    """
    from guardrails.approval_guard import ApprovalGuard

    return {
        "actions": ApprovalGuard.ACTIONS_REQUIRING_APPROVAL,
        "total": len(ApprovalGuard.ACTIONS_REQUIRING_APPROVAL)
    }


@router.get("/health")
async def approvals_health(
    context: RequestContext = Depends(get_request_context),
):
    """
    Health check for the approval system.

    Returns:
        Status of the approval system
    """
    approval_guard = get_approval_guard()
    project_id = context.project.id if context.project else None
    pending = approval_guard.list_pending_approvals(project_id=project_id)
    history = approval_guard.get_approval_history(limit=1000, project_id=project_id)

    return {
        "status": "healthy",
        "pending_approvals": len(pending),
        "timeout_seconds": approval_guard.timeout_seconds,
        "history_entries": len(history),
    }
