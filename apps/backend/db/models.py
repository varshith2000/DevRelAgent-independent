"""ORM models: the multi-tenant system of record.

Hierarchy: Workspace (an organization) -> Project (the unit users work in) ->
ApiKey. Users join workspaces through Membership.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# Membership roles, most privileged first.
ROLES = ("owner", "admin", "member", "viewer")
PROJECT_STATUSES = ("active", "archived")


def new_id() -> str:
    """Opaque, URL-safe identifier."""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "default", max_length: int = 100) -> str:
    """Turn arbitrary text into a URL-safe slug.

    Lowercases, collapses every run of non-alphanumeric characters into a single
    hyphen and strips leading/trailing hyphens. Returns ``fallback`` for input
    that has no usable characters.
    """
    slug = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")
    slug = slug[:max_length].strip("-")
    return slug or fallback


class Workspace(Base):
    """An organization. One Clerk organization maps to one workspace."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # Identifier from the identity provider (e.g. Clerk organization id).
    external_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[List["Membership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    projects: Mapped[List["Project"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class User(Base):
    """A person, identified by an external identity-provider subject."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    external_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[List["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Membership(Base):
    """Binds a user to a workspace with a role."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_membership"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class Project(Base):
    """The unit users organize their work in. Everything is scoped to one."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_project_slug"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    workspace: Mapped["Workspace"] = relationship(back_populates="projects")
    api_keys: Mapped[List["ApiKey"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ApiKey(Base):
    """A machine credential scoped to a single project.

    Only the hash is stored; the plaintext key is returned once at creation.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    # First segment of the key, stored in clear so lookups are a single indexed
    # read instead of scanning every hash.
    prefix: Mapped[str] = mapped_column(String(24), index=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    project: Mapped["Project"] = relationship(back_populates="api_keys")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            # SQLite returns naive datetimes; normalise before comparing.
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < utcnow():
                return False
        return True
