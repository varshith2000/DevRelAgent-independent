"""Persistence layer (Phase 1).

The backend keeps its own system of record (workspaces, users, memberships,
projects, API keys) separate from the telemetry it reads from customer
datasources. SQLite is the zero-infrastructure default; point ``DATABASE_URL``
at Postgres/Supabase for a real deployment.
"""

from db.base import Base
from db.models import ApiKey, Membership, Project, User, Workspace
from db.models_audit import ApprovalRecord, AuditRecord
from db.session import get_engine, get_session, init_db, reset_engine

__all__ = [
    "Base",
    "Workspace",
    "User",
    "Membership",
    "Project",
    "ApiKey",
    "AuditRecord",
    "ApprovalRecord",
    "get_engine",
    "get_session",
    "init_db",
    "reset_engine",
]
