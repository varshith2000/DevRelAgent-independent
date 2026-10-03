"""Phase 2: durable, project-scoped audit entries and approval decisions."""

import asyncio
from datetime import datetime

import pytest


@pytest.fixture
def audit_logger(db_engine, tmp_path):
    """Install an isolated audit logger writing to a temp directory."""
    from audit.logger import AuditLogger, reset_audit_logger, set_audit_logger

    instance = AuditLogger(storage_path=str(tmp_path / "audit"), cache_size=100)
    set_audit_logger(instance)
    yield instance
    reset_audit_logger()


@pytest.mark.asyncio
async def test_audit_entries_are_durable_and_project_scoped(audit_logger):
    from audit.schemas import ActionType, AuditEntry, AuditFilter

    await audit_logger.log(
        AuditEntry(
            session_id="s1",
            action_type=ActionType.CHAT,
            action_name="chat_message",
            input_text="hello",
            tenant_id="p1",
            workspace_id="w1",
        )
    )
    await audit_logger.log(
        AuditEntry(
            session_id="s2",
            action_type=ActionType.CHAT,
            input_text="other tenant",
            tenant_id="p2",
            workspace_id="w2",
        )
    )

    # Reads are scoped: a project only ever sees its own entries.
    assert [
        e.session_id for e in await audit_logger.get_recent(project_id="p1", workspace_id="w1")
    ] == ["s1"]
    assert [
        e.session_id
        for e in await audit_logger.query(AuditFilter(tenant_id="p2", workspace_id="w2", limit=10))
    ] == ["s2"]

    summary = await audit_logger.get_summary(project_id="p1", workspace_id="w1")
    assert summary.total_entries == 1


def test_audit_api_is_project_scoped(api_client):
    from audit.schemas import ActionType, AuditEntry
    from db import repositories

    headers = {"X-Dev-Workspace": "audit-ws"}
    project_a = api_client.post("/projects", json={"name": "Audit A"}, headers=headers).json()
    project_b = api_client.post("/projects", json={"name": "Audit B"}, headers=headers).json()

    entry = AuditEntry(
        session_id="sess-a",
        action_type=ActionType.CHAT,
        input_text="keep me",
        tenant_id=project_a["id"],
        workspace_id=project_a["workspace_id"],
    )
    repositories.record_audit(
        entry.model_dump(mode="json"),
        workspace_id=project_a["workspace_id"],
        project_id=project_a["id"],
    )

    scoped_a = api_client.get(
        "/audit/recent", headers={**headers, "X-Project-Id": project_a["id"]}
    ).json()
    assert any(item["session_id"] == "sess-a" for item in scoped_a)

    scoped_b = api_client.get(
        "/audit/recent", headers={**headers, "X-Project-Id": project_b["id"]}
    ).json()
    assert all(item["session_id"] != "sess-a" for item in scoped_b)


def test_approvals_api_is_project_scoped(api_client):
    from db import repositories

    headers = {"X-Dev-Workspace": "appr-ws"}
    project_a = api_client.post("/projects", json={"name": "Appr A"}, headers=headers).json()
    project_b = api_client.post("/projects", json={"name": "Appr B"}, headers=headers).json()

    repositories.create_approval(
        approval_id="appr-a1",
        action_type="github_issue",
        risk_level="medium",
        plan=["Draft issue"],
        metadata={"repo": "org/repo"},
        timeout_seconds=300,
        created_at=datetime.now(),
        workspace_id=project_a["workspace_id"],
        project_id=project_a["id"],
    )

    pending_a = api_client.get(
        "/approvals/pending", headers={**headers, "X-Project-Id": project_a["id"]}
    ).json()
    assert pending_a["total_pending"] == 1
    assert pending_a["pending_approvals"][0]["approval_id"] == "appr-a1"

    pending_b = api_client.get(
        "/approvals/pending", headers={**headers, "X-Project-Id": project_b["id"]}
    ).json()
    assert pending_b["total_pending"] == 0


@pytest.mark.asyncio
async def test_approval_decision_is_persisted_and_scoped(db_engine):
    from guardrails.approval_guard import ApprovalGuard

    guard = ApprovalGuard(timeout_seconds=30)
    task = asyncio.create_task(
        guard.request_approval(
            "github_issue",
            ["Draft issue"],
            project_id="p1",
            workspace_id="w1",
        )
    )
    await asyncio.sleep(0.05)

    pending = guard.list_pending_approvals(project_id="p1")
    assert len(pending) == 1
    assert guard.list_pending_approvals(project_id="p2") == []

    assert await guard.respond_to_approval(pending[0].approval_id, approved=True, user="alice")
    response = await task
    assert response.approved is True

    history_p1 = guard.get_approval_history(project_id="p1")
    assert len(history_p1) == 1
    assert history_p1[0]["approved"] is True
    assert history_p1[0]["user"] == "alice"

    assert guard.get_approval_history(project_id="p2") == []


@pytest.mark.asyncio
async def test_action_without_approval_requirement_is_allowed(db_engine):
    from guardrails.approval_guard import ApprovalGuard

    guard = ApprovalGuard()
    response = await guard.request_approval("read_only", ["Just read"], project_id="p1")
    assert response.approved is True
    assert guard.get_approval_history(project_id="p1") == []
