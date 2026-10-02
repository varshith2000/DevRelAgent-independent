"""FastAPI dependencies that turn a request into a tenant-scoped context.

Two kinds of caller are supported by the same dependency graph:

1. A machine presenting a project API key (``Authorization: Bearer drk_...``).
   The project is resolved straight from the key; there is no user or role.
2. A person verified by the configured identity provider. Their user,
   workspace, membership and active project are loaded, and created on first
   use so a fresh checkout works with zero seeding.

Everything downstream (routes, services) reads the same :class:`RequestContext`,
so it never needs to know how the caller authenticated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from db.models import ApiKey, Membership, Project, User, Workspace, slugify, utcnow
from db.session import get_session
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.api_keys import resolve_api_key
from auth.provider import AuthError, Principal, get_auth_provider

logger = logging.getLogger(__name__)

_API_KEY_PREFIX = "drk_"


@dataclass
class RequestContext:
    """Everything a route needs to know about the caller."""

    workspace: Workspace
    project: Optional[Project]
    role: Optional[str]
    principal: Optional[Principal]
    user: Optional[User]
    is_api_key: bool = False


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    return token or None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── Provisioning helpers ──────────────────────────────────────────────


def _unique_slug(session: Session, model, base: str, workspace_id: Optional[str] = None) -> str:
    """Return a slug unique within ``model`` (and workspace, when applicable)."""
    candidate = base
    suffix = 2
    while True:
        query = select(model.id).where(model.slug == candidate)
        if workspace_id is not None:
            query = query.where(model.workspace_id == workspace_id)
        if session.scalar(query) is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def _upsert_user(session: Session, principal: Principal) -> User:
    """Find or create the user for this principal, refreshing last login."""
    user = session.scalar(select(User).where(User.email == principal.email))
    if user is None:
        user = User(email=principal.email, name=principal.name, external_id=principal.subject)
        session.add(user)
        logger.info("Provisioned user %s", principal.email)
    else:
        if principal.name and user.name != principal.name:
            user.name = principal.name
        if principal.subject and user.external_id != principal.subject:
            user.external_id = principal.subject
    user.last_login_at = utcnow()
    session.flush()
    return user


def _resolve_workspace(session: Session, principal: Principal, user: User) -> tuple[Workspace, str]:
    """Find or create the caller's workspace and membership; return the role."""
    external_id = (
        principal.workspace_external_id or f"{slugify(principal.email.split('@')[0])}-workspace"
    )

    workspace = session.scalar(select(Workspace).where(Workspace.external_id == external_id))
    created = False
    if workspace is None:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == slugify(external_id)))
    if workspace is None:
        slug = _unique_slug(session, Workspace, slugify(external_id))
        workspace = Workspace(name=_display_name(external_id), slug=slug, external_id=external_id)
        session.add(workspace)
        session.flush()
        created = True
        logger.info("Provisioned workspace %s (%s)", workspace.slug, external_id)

    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace.id, Membership.user_id == user.id
        )
    )
    if membership is None:
        # Whoever creates a workspace owns it; everyone else joining gets member.
        membership = Membership(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner" if created else "member",
        )
        session.add(membership)
        session.flush()
    return workspace, membership.role


def _display_name(value: str) -> str:
    """Humanise an external identifier for a default workspace name."""
    return value.replace("_", " ").replace("-", " ").strip().title() or value


def _resolve_project(
    session: Session, workspace: Workspace, request: Request
) -> tuple[Optional[Project], bool]:
    """Resolve the active project from headers, else the workspace default.

    Returns ``(project, explicit)`` where ``explicit`` is true when the caller
    named a project (so a missing one is a 404 rather than a request to create
    the default).
    """
    # Query parameters mirror the headers so SSE clients (EventSource) can
    # select a project without being able to set request headers.
    header_id = request.headers.get("x-project-id") or request.query_params.get("project_id")
    header_slug = request.headers.get("x-project-slug") or request.query_params.get("project_slug")

    base = select(Project).where(Project.workspace_id == workspace.id)
    if header_id:
        project = session.scalar(base.where(Project.id == header_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project, True
    if header_slug:
        project = session.scalar(base.where(Project.slug == header_slug))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project, True

    project = session.scalar(
        base.where(Project.status == "active").order_by(Project.created_at).limit(1)
    )
    return project, False


def _default_project(session: Session, workspace: Workspace) -> Project:
    """Create the workspace's first project (named after the workspace)."""
    slug = _unique_slug(session, Project, "default", workspace_id=workspace.id)
    project = Project(
        workspace_id=workspace.id,
        name="Default",
        slug=slug,
        description="Created automatically for new workspaces.",
    )
    session.add(project)
    session.flush()
    logger.info("Provisioned default project %s for workspace %s", slug, workspace.slug)
    return project


# ── Core dependency ───────────────────────────────────────────────────


def get_request_context(
    request: Request,
    session: Session = Depends(get_session),
) -> RequestContext:
    """Resolve the caller into a workspace-scoped context."""
    token = _bearer_token(request)

    if token is not None and token.startswith(_API_KEY_PREFIX):
        api_key: Optional[ApiKey] = resolve_api_key(session, token)
        if api_key is None:
            raise _unauthorized("Invalid API key")
        key_project = api_key.project
        return RequestContext(
            workspace=key_project.workspace,
            project=key_project,
            role=None,
            principal=None,
            user=None,
            is_api_key=True,
        )

    try:
        principal = get_auth_provider().authenticate(request)
    except AuthError as exc:
        raise _unauthorized(str(exc)) from exc

    user = _upsert_user(session, principal)
    workspace, role = _resolve_workspace(session, principal, user)
    project, explicit = _resolve_project(session, workspace, request)
    if project is None and not explicit:
        project = _default_project(session, workspace)

    context = RequestContext(
        workspace=workspace,
        project=project,
        role=role,
        principal=principal,
        user=user,
        is_api_key=False,
    )
    session.commit()
    return context


# ── Public dependencies ───────────────────────────────────────────────


def get_current_principal(context: RequestContext = Depends(get_request_context)) -> Principal:
    """The verified human identity. API-key callers have none."""
    if context.principal is None:
        raise HTTPException(status_code=403, detail="This endpoint requires a user identity")
    return context.principal


def get_current_user(context: RequestContext = Depends(get_request_context)) -> User:
    """The persisted user for the current caller."""
    if context.user is None:
        raise HTTPException(status_code=403, detail="This endpoint requires a user identity")
    return context.user


def get_current_workspace(context: RequestContext = Depends(get_request_context)) -> Workspace:
    """The workspace every query in this request must be scoped to."""
    return context.workspace


def get_current_project(context: RequestContext = Depends(get_request_context)) -> Project:
    """The active project for this request."""
    if context.project is None:
        raise HTTPException(status_code=400, detail="No project selected")
    return context.project


def get_api_key_project(context: RequestContext = Depends(get_request_context)) -> Project:
    """The project authenticated by an API key; 401 for user-authenticated calls."""
    if not context.is_api_key or context.project is None:
        raise _unauthorized("This endpoint requires a project API key")
    return context.project


def require_role(*roles: str) -> Callable[..., RequestContext]:
    """Dependency factory requiring the caller to hold one of ``roles``.

    API keys are intentionally denied: machine credentials are for data-plane
    access, not for administering workspaces.
    """
    allowed: List[str] = list(roles)

    def dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        if context.is_api_key:
            raise HTTPException(status_code=403, detail="API keys cannot perform this action")
        if context.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail="This action requires one of: " + ", ".join(allowed),
            )
        return context

    return dependency


__all__ = [
    "RequestContext",
    "get_request_context",
    "get_current_principal",
    "get_current_user",
    "get_current_workspace",
    "get_current_project",
    "get_api_key_project",
    "require_role",
]
