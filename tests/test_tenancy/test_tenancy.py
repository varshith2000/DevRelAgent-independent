"""Phase 1: identity, workspace/project scoping and project API keys."""

import pytest

DEV_WORKSPACE = {"X-Dev-Workspace": "dev-workspace"}


def test_dev_caller_is_provisioned_with_workspace_and_project(api_client):
    response = api_client.get("/auth/me", headers=DEV_WORKSPACE)
    assert response.status_code == 200

    me = response.json()
    assert me["authenticated"] is True
    assert me["is_api_key"] is False
    assert me["email"] == "dev@localhost"
    assert me["workspace_slug"] == "dev-workspace"
    # The creator of a fresh workspace owns it.
    assert me["role"] == "owner"
    assert me["project_id"]
    assert me["project_slug"] == "default"


def test_identity_headers_are_honoured(api_client):
    me = api_client.get(
        "/auth/me",
        headers={
            "X-Dev-User-Email": "alice@example.com",
            "X-Dev-User-Name": "Alice",
            "X-Dev-Workspace": "alice-team",
        },
    ).json()
    assert me["email"] == "alice@example.com"
    assert me["name"] == "Alice"
    assert me["workspace_slug"] == "alice-team"


def test_workspaces_are_isolated(api_client):
    one = api_client.get("/auth/me", headers={"X-Dev-Workspace": "team-one"}).json()
    two = api_client.get("/auth/me", headers={"X-Dev-Workspace": "team-two"}).json()

    assert one["workspace_id"] != two["workspace_id"]

    created = api_client.post(
        "/projects", json={"name": "Alpha"}, headers={"X-Dev-Workspace": "team-one"}
    )
    assert created.status_code == 201

    listed = api_client.get("/projects", headers={"X-Dev-Workspace": "team-two"}).json()
    assert all(p["id"] != created.json()["id"] for p in listed)


def test_upsert_user_retries_after_unique_constraint():
    from unittest.mock import MagicMock

    from auth.deps import _upsert_user
    from sqlalchemy.exc import IntegrityError

    principal = type("Principal", (), {"email": "dup@example.com", "name": "Dup User", "subject": "sub-dup"})()
    existing = type("User", (), {"id": "u-dup", "email": "dup@example.com", "name": "Dup User", "external_id": "sub-dup", "last_login_at": None})()
    session = MagicMock()

    session.scalar.side_effect = [None, existing]
    session.flush.side_effect = [IntegrityError("INSERT", {}, "UNIQUE constraint failed"), None]

    result = _upsert_user(session, principal)

    assert result is existing
    assert session.rollback.called


def test_cannot_read_another_workspaces_project(api_client):
    project = api_client.post(
        "/projects", json={"name": "Secret"}, headers={"X-Dev-Workspace": "ws-a"}
    ).json()

    response = api_client.get(f"/projects/{project['id']}", headers={"X-Dev-Workspace": "ws-b"})
    assert response.status_code == 404


def test_project_slugs_are_unique_per_workspace(api_client):
    headers = {"X-Dev-Workspace": "slug-ws"}
    first = api_client.post("/projects", json={"name": "Alpha"}, headers=headers).json()
    second = api_client.post("/projects", json={"name": "Alpha"}, headers=headers).json()

    assert first["slug"] == "alpha"
    assert second["slug"] == "alpha-2"


def test_project_update_and_archive(api_client):
    headers = {"X-Dev-Workspace": "lifecycle-ws"}
    project = api_client.post("/projects", json={"name": "Lifecycle"}, headers=headers).json()

    renamed = api_client.patch(
        f"/projects/{project['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    archived = api_client.post(f"/projects/{project['id']}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None

    active = api_client.get("/projects", headers=headers).json()
    assert all(p["id"] != project["id"] for p in active)

    every = api_client.get("/projects?include_archived=true", headers=headers).json()
    assert any(p["id"] == project["id"] for p in every)


def test_workspace_creation_and_membership(api_client):
    created = api_client.post("/workspaces", json={"name": "My Team"}, headers=DEV_WORKSPACE)
    assert created.status_code == 201
    assert created.json()["slug"] == "my-team"
    assert created.json()["role"] == "owner"

    workspaces = api_client.get("/workspaces", headers=DEV_WORKSPACE).json()
    assert "my-team" in {w["slug"] for w in workspaces}

    members = api_client.get("/workspaces/current/members", headers=DEV_WORKSPACE)
    assert members.status_code == 200
    assert any(m["email"] == "dev@localhost" and m["role"] == "owner" for m in members.json())


def test_api_key_lifecycle_and_scoping(api_client):
    headers = {"X-Dev-Workspace": "key-ws"}
    project = api_client.post("/projects", json={"name": "Keyed"}, headers=headers).json()

    created = api_client.post(
        f"/projects/{project['id']}/api-keys", json={"name": "ci"}, headers=headers
    )
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("drk_")
    assert body["prefix"] in body["key"]
    assert "key_hash" not in body  # the hash must never leave the server

    auth = {"Authorization": f"Bearer {body['key']}"}
    me = api_client.get("/auth/me", headers=auth).json()
    assert me["is_api_key"] is True
    assert me["project_id"] == project["id"]
    assert me["workspace_id"] == project["workspace_id"]

    # A machine credential must not be able to administer workspaces.
    assert api_client.post("/projects", json={"name": "nope"}, headers=auth).status_code == 403

    revoked = api_client.delete(f"/projects/{project['id']}/api-keys/{body['id']}", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    assert api_client.get("/auth/me", headers=auth).status_code == 401


def test_unknown_api_key_is_rejected(api_client):
    response = api_client.get(
        "/auth/me", headers={"Authorization": "Bearer drk_deadbeef_notarealkey"}
    )
    assert response.status_code == 401


def test_api_keys_are_scoped_to_their_project(api_client):
    headers = {"X-Dev-Workspace": "apikey-scope-ws"}
    project = api_client.post("/projects", json={"name": "One"}, headers=headers).json()
    other = api_client.post("/projects", json={"name": "Two"}, headers=headers).json()
    key = api_client.post(
        f"/projects/{project['id']}/api-keys", json={"name": "k"}, headers=headers
    ).json()

    # The key's project wins over any header the caller sends.
    me = api_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {key['key']}", "X-Project-Id": other["id"]},
    ).json()
    assert me["project_id"] == project["id"]


def test_session_cleanup_is_admin_only_scoped_and_validated(api_client):
    from datetime import datetime, timedelta

    from models.schemas import SessionContext
    from routes.chat import _session_key, save_session
    from sessions.store import MemorySessionStore, reset_session_store

    store = MemorySessionStore()
    reset_session_store(store)

    owner_headers = {
        "X-Dev-Workspace": "cleanup-shared-ws",
        "X-Dev-User-Email": "owner@cleanup.test",
        "X-Dev-User-Name": "Owner",
    }
    owner_me = api_client.get("/auth/me", headers=owner_headers).json()
    member_headers = {
        **owner_headers,
        "X-Dev-User-Email": "member@cleanup.test",
        "X-Dev-User-Name": "Member",
    }
    member_me = api_client.get("/auth/me", headers=member_headers).json()
    assert member_me["role"] == "member"

    other_me = api_client.get(
        "/auth/me",
        headers={"X-Dev-Workspace": "cleanup-other-ws", "X-Dev-User-Email": "other@cleanup.test"},
    ).json()
    project_a = owner_me["project_id"]
    project_b = other_me["project_id"]
    save_session(project_a, SessionContext(
        session_id="old-in-a", last_activity=datetime.now() - timedelta(hours=2)
    ))
    save_session(project_a, SessionContext(session_id="fresh-in-a"))
    save_session(project_b, SessionContext(
        session_id="old-in-b", last_activity=datetime.now() - timedelta(hours=2)
    ))

    denied = api_client.post("/chat/sessions/cleanup", headers=member_headers)
    assert denied.status_code == 403
    invalid_age = api_client.post("/chat/sessions/cleanup?max_age_minutes=0", headers=owner_headers)
    assert invalid_age.status_code == 422

    cleaned = api_client.post("/chat/sessions/cleanup?max_age_minutes=60", headers=owner_headers)
    assert cleaned.status_code == 200
    assert cleaned.json() == {"cleaned_count": 1, "remaining_count": 1}
    assert store.get(_session_key(project_a, "old-in-a")) is None
    assert store.get(_session_key(project_a, "fresh-in-a")) is not None
    assert store.get(_session_key(project_b, "old-in-b")) is not None


@pytest.mark.asyncio
async def test_sessions_are_isolated_per_project(db_engine):
    from routes.chat import get_or_create_session, list_project_sessions, save_session

    session = await get_or_create_session(None, "project-a")
    save_session("project-a", session)

    assert [s.session_id for s in list_project_sessions("project-a")] == [session.session_id]
    assert list_project_sessions("project-b") == []


def test_clerk_provider_requires_configuration(monkeypatch):
    from auth.provider import AuthError, get_auth_provider, reset_auth_provider
    from config.settings import reset_settings_cache

    monkeypatch.setenv("AUTH_PROVIDER", "clerk")
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)

    reset_settings_cache()
    reset_auth_provider()
    try:
        with pytest.raises(AuthError):
            get_auth_provider()
    finally:
        reset_settings_cache()
        reset_auth_provider()
