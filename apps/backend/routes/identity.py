"""Identity endpoint: everything the UI needs to know about the caller."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from auth.deps import RequestContext, get_request_context
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class MeResponse(BaseModel):
    """The caller's identity and the tenant scope they are operating in."""

    authenticated: bool
    is_api_key: bool
    subject: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    user_id: Optional[str] = None
    workspace_id: str
    workspace_name: str
    workspace_slug: str
    role: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    project_slug: Optional[str] = None
    server_time: datetime


@router.get("/me", response_model=MeResponse)
def read_me(context: RequestContext = Depends(get_request_context)) -> MeResponse:
    """Return the resolved identity, workspace and active project."""
    return MeResponse(
        authenticated=context.principal is not None,
        is_api_key=context.is_api_key,
        subject=context.principal.subject if context.principal else None,
        email=context.principal.email if context.principal else None,
        name=context.principal.name if context.principal else None,
        user_id=context.user.id if context.user else None,
        workspace_id=context.workspace.id,
        workspace_name=context.workspace.name,
        workspace_slug=context.workspace.slug,
        role=context.role,
        project_id=context.project.id if context.project else None,
        project_name=context.project.name if context.project else None,
        project_slug=context.project.slug if context.project else None,
        server_time=datetime.now().astimezone(),
    )
