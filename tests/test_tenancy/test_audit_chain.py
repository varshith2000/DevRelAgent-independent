"""Phase 4: tamper-evident audit hash chain."""

from db import repositories
from db.models_audit import AuditRecord


def _payload(audit_id: str) -> dict:
    return {
        "audit_id": audit_id,
        "session_id": "session-1",
        "action_type": "query",
        "timestamp": "2026-10-02T00:00:00+00:00",
    }


def _record(project_id: str, audit_id: str) -> None:
    repositories.record_audit(_payload(audit_id), project_id=project_id)


def _open_session():
    from db.session import get_session_factory

    return get_session_factory()()


def test_chain_verifies_after_appends(db_engine):
    for index in range(3):
        _record("proj-1", f"audit-{index}")

    report = repositories.verify_audit_chain(project_id="proj-1")
    assert report["ok"] is True
    assert report["checked"] == 3
    assert report["legacy"] == 0
    assert report["head"] != repositories.GENESIS_HASH


def test_chains_are_independent_per_project(db_engine):
    _record("proj-1", "a-0")
    _record("proj-2", "b-0")

    first = repositories.verify_audit_chain(project_id="proj-1")
    second = repositories.verify_audit_chain(project_id="proj-2")

    assert first["checked"] == 1 and second["checked"] == 1
    assert first["chain_scope"] == "project:proj-1"
    assert second["chain_scope"] == "project:proj-2"
    assert first["head"] != second["head"]


def test_workspace_chain_when_no_project(db_engine):
    repositories.record_audit(_payload("w-0"), workspace_id="ws-1")
    report = repositories.verify_audit_chain(workspace_id="ws-1")
    assert report["ok"] is True
    assert report["chain_scope"] == "workspace:ws-1"


def test_tampering_with_a_record_is_detected(db_engine):
    for index in range(3):
        _record("proj-1", f"audit-{index}")

    session = _open_session()
    try:
        record = session.get(AuditRecord, "audit-1")
        record.payload = {**record.payload, "action_type": "delete"}
        session.commit()
    finally:
        session.close()

    report = repositories.verify_audit_chain(project_id="proj-1")
    assert report["ok"] is False
    assert report["reason"] == "hash mismatch"
    assert report["broken_at"] == "audit-1"


def test_deleting_a_record_is_detected(db_engine):
    for index in range(3):
        _record("proj-1", f"audit-{index}")

    session = _open_session()
    try:
        session.delete(session.get(AuditRecord, "audit-1"))
        session.commit()
    finally:
        session.close()

    report = repositories.verify_audit_chain(project_id="proj-1")
    assert report["ok"] is False
    assert report["reason"] == "sequence gap"


def test_verify_endpoint_reports_ok_for_fresh_tenant(api_client):
    response = api_client.get("/audit/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checked"] == 0
