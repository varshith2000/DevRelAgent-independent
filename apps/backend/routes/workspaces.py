"""Workspaces, projects and project API keys.

Every endpoint is tenant-scoped: a project is only ever resolved through the
caller's current workspace, so one tenant can never address another's data by
guessing an id.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from auth.api_keys import generate_key
from auth.deps import RequestContext, get_current_user, get_request_context, require_role
from db.models import ApiKey, Membership, Project, User, Workspace, slugify
from db.session import get_session
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspaces"])

_ADMIN_ROLES = ("owner", "admin")


# ── Schemas ───────────────────────────────────────────────────────────


class WorkspaceRead(BaseModel):
    id: str
    name: str
    slug: str
    external_id: Optional[str] = None
    created_at: datetime
    role: Optional[str] = None


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=120)


class MemberRead(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    role: str


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    archived_at: Optional[datetime] = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prefix: str
    scopes: List[str]
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


class ApiKeyCreated(ApiKeyRead):
    # The plaintext key, returned exactly once at creation.
    key: str


def _workspace_read(workspace: Workspace, role: Optional[str]) -> WorkspaceRead:
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        external_id=workspace.external_id,
        created_at=workspace.created_at,
        role=role,
    )


def _get_project(session: Session, workspace: Workspace, project_id: str) -> Project:
    project = session.scalar(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ── Workspaces ────────────────────────────────────────────────────────


@router.get("/workspaces", response_model=List[WorkspaceRead])
def list_workspaces(
    context: RequestContext = Depends(get_request_context),
    session: Session = Depends(get_session),
) -> List[WorkspaceRead]:
    """List every workspace the caller belongs to."""
    if context.user is None:
        raise HTTPException(status_code=403, detail="This endpoint requires a user identity")

    rows = session.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == context.user.id)
        .order_by(Workspace.created_at)
    ).all()
    return [_workspace_read(workspace, role) for workspace, role in rows]


@router.get("/workspaces/current", response_model=WorkspaceRead)
def get_current_workspace(context: RequestContext = Depends(get_request_context)) -> WorkspaceRead:
    """The workspace this request is scoped to."""
    return _workspace_read(context.workspace, context.role)


@router.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkspaceRead:
    """Create a workspace; the creator becomes its owner."""
    base_slug = slugify(payload.slug or payload.name, fallback="workspace")
    slug = base_slug
    suffix = 2
    while session.scalar(select(Workspace.id).where(Workspace.slug == slug)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    workspace = Workspace(name=payload.name, slug=slug, external_id=None)
    session.add(workspace)
    session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    session.commit()
    logger.info("User %s created workspace %s", user.email, workspace.slug)
    return _workspace_read(workspace, "owner")


@router.get("/workspaces/current/members", response_model=List[MemberRead])
def list_members(
    context: RequestContext = Depends(require_role(*_ADMIN_ROLES)),
    session: Session = Depends(get_session),
) -> List[MemberRead]:
    """List the members of the current workspace (admin and above)."""
    rows = session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == context.workspace.id)
        .order_by(User.email)
    ).all()
    return [
        MemberRead(user_id=user.id, email=user.email, name=user.name, role=role)
        for user, role in rows
    ]


# ── Projects ──────────────────────────────────────────────────────────


@router.get("/projects", response_model=List[ProjectRead])
def list_projects(
    context: RequestContext = Depends(get_request_context),
    session: Session = Depends(get_session),
    include_archived: bool = False,
) -> List[ProjectRead]:
    """List projects in the current workspace."""
    query = select(Project).where(Project.workspace_id == context.workspace.id)
    if not include_archived:
        query = query.where(Project.status == "active")
    projects = session.scalars(query.order_by(Project.created_at)).all()
    return [ProjectRead.model_validate(p) for p in projects]


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    context: RequestContext = Depends(require_role("owner")),
    session: Session = Depends(get_session),
) -> ProjectRead:
    """Create a project in the current workspace."""
    base_slug = slugify(payload.slug or payload.name, fallback="project")
    slug = base_slug
    suffix = 2
    while (
        session.scalar(
            select(Project.id).where(
                Project.workspace_id == context.workspace.id, Project.slug == slug
            )
        )
        is not None
    ):
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    project = Project(
        workspace_id=context.workspace.id,
        name=payload.name,
        slug=slug,
        description=payload.description,
    )
    session.add(project)
    session.commit()
    logger.info("Created project %s in workspace %s", project.slug, context.workspace.slug)
    return ProjectRead.model_validate(project)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    context: RequestContext = Depends(get_request_context),
    session: Session = Depends(get_session),
) -> ProjectRead:
    return ProjectRead.model_validate(_get_project(session, context.workspace, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    context: RequestContext = Depends(require_role(*_ADMIN_ROLES)),
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = _get_project(session, context.workspace, project_id)
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    session.commit()
    return ProjectRead.model_validate(project)


@router.post("/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: str,
    context: RequestContext = Depends(require_role(*_ADMIN_ROLES)),
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = _get_project(session, context.workspace, project_id)
    if project.status != "archived":
        project.status = "archived"
        project.archived_at = datetime.now(timezone.utc)
        session.commit()
    return ProjectRead.model_validate(project)


# ── Project API keys ──────────────────────────────────────────────────


@router.get("/projects/{project_id}/api-keys", response_model=List[ApiKeyRead])
def list_api_keys(
    project_id: str,
    context: RequestContext = Depends(require_role(*_ADMIN_ROLES)),
    session: Session = Depends(get_session),
) -> List[ApiKeyRead]:
    project = _get_project(session, context.workspace, project_id)
    keys = session.scalars(
        select(ApiKey).where(ApiKey.project_id == project.id).order_by(ApiKey.created_at)
    ).all()
    return [ApiKeyRead.model_validate(k) for k in keys]


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    project_id: str,
    payload: ApiKeyCreate,
    context: RequestContext = Depends(require_role(*_ADMIN_ROLES)),
    session: Session = Depends(get_session),
) -> ApiKeyCreated:
    """Mint a project API key. The plaintext ``key`` is shown only here."""
    project = _get_project(session, context.workspace, project_id)
    plaintext, prefix, key_hash = generate_key()
    api_key = ApiKey(
        project_id=project.id,
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    session.add(api_key)
    session.commit()
    logger.info("Created API key %s for project %s", api_key.id, project.slug)
    return ApiKeyCreated(**ApiKeyRead.model_validate(api_key).model_dump(), key=plaintext)


@router.delete("/projects/{project_id}/api-keys/{key_id}", response_model=ApiKeyRead)
def revoke_api_key(
    project_id: str,
    key_id: str,
    context: RequestContext = Depends(require_role(*_ADMIN_ROLES)),
    session: Session = Depends(get_session),
) -> ApiKeyRead:
    """Revoke an API key. Revocation is immediate and terminal."""
    project = _get_project(session, context.workspace, project_id)
    api_key = session.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project.id)
    )
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("Revoked API key %s", api_key.id)
    return ApiKeyRead.model_validate(api_key)
