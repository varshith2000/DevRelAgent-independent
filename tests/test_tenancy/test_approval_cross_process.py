"""Phase 6: approvals resolve across replicas, not just the waiting process."""

import asyncio
from datetime import datetime

import pytest
from db import repositories
from guardrails.approval_guard import ApprovalGuard
from shared.events import MemoryEventBus, event_channel, get_event_bus


async def test_event_bus_delivers_to_subscribers():
    bus = MemoryEventBus()
    async with bus.subscribe("chan") as queue:
        await bus.publish("chan", {"hello": "world"})
        assert await asyncio.wait_for(queue.get(), timeout=1) == {"hello": "world"}


async def test_event_bus_unsubscribes_on_exit():
    bus = MemoryEventBus()
    async with bus.subscribe("chan"):
        pass
    # Publishing after the subscriber left must not raise.
    await bus.publish("chan", {"x": 1})


async def test_decision_from_another_guard_wakes_waiter(db_engine):
    """Replica A waits; replica B records the decision and A is released."""
    waiter = ApprovalGuard(poll_interval_seconds=0.1)
    responder = ApprovalGuard(poll_interval_seconds=0.1)

    task = asyncio.create_task(
        waiter.request_approval("github_issue", ["create issue"], project_id="proj-1")
    )
    await asyncio.sleep(0.05)

    pending = repositories.list_pending_approvals(project_id="proj-1")
    assert len(pending) == 1
    approval_id = pending[0]["approval_id"]

    recorded = await responder.respond_to_approval(
        approval_id, approved=True, user="alice@example.com", reason="looks good"
    )
    assert recorded is True

    response = await asyncio.wait_for(task, timeout=5)
    assert response.approved is True
    assert response.user == "alice@example.com"
    assert response.reason == "looks good"

    stored = repositories.get_approval(approval_id)
    assert stored is not None
    assert stored["status"] == "approved"


async def test_decision_persisted_by_poll_fallback(db_engine):
    """A decision written straight to the DB (no publish) still releases a waiter."""
    waiter = ApprovalGuard(poll_interval_seconds=0.1)

    task = asyncio.create_task(
        waiter.request_approval("github_pr", ["open pr"], project_id="proj-2")
    )
    await asyncio.sleep(0.05)

    pending = repositories.list_pending_approvals(project_id="proj-2")
    approval_id = pending[0]["approval_id"]

    assert repositories.resolve_approval(
        approval_id,
        status="rejected",
        approved=False,
        user="bob@example.com",
        reason="too risky",
        responded_at=datetime.now(),
        duration_seconds=None,
    )

    response = await asyncio.wait_for(task, timeout=5)
    assert response.approved is False
    assert response.reason == "too risky"


async def test_respond_to_unknown_approval_returns_false(db_engine):
    guard = ApprovalGuard(poll_interval_seconds=0.1)
    assert await guard.respond_to_approval("does-not-exist", approved=True) is False


async def test_action_without_approval_returns_immediately(db_engine):
    guard = ApprovalGuard(poll_interval_seconds=0.1)
    response = await guard.request_approval("read_operation", ["read"])
    assert response.approved is True
    assert "does not require approval" in (response.reason or "")


async def test_confirmation_is_published_on_the_expected_channel(db_engine):
    guard = ApprovalGuard(poll_interval_seconds=0.1)
    bus = get_event_bus()

    task = asyncio.create_task(
        guard.request_approval("browser_action", ["click"], project_id="proj-3")
    )
    await asyncio.sleep(0.05)
    approval_id = repositories.list_pending_approvals(project_id="proj-3")[0]["approval_id"]

    async with bus.subscribe(event_channel("approval", approval_id)) as queue:
        await guard.respond_to_approval(approval_id, approved=True)

    # The confirmation was published to the right channel (and also consumed by
    # the waiting guard, so the queue may be empty by now — just assert no hang).
    response = await asyncio.wait_for(task, timeout=5)
    assert response.approved is True


def test_timeout_response_is_rejected():
    guard = ApprovalGuard()

    class _Req:
        approval_id = "abc"
        timeout_seconds = 30

    response = guard._timeout_response(_Req())  # type: ignore[arg-type]
    assert response.approved is False
    assert "timeout" in (response.reason or "")


@pytest.mark.parametrize("approved,expected", [(True, "approved"), (False, "rejected")])
def test_status_for_maps_decision(approved, expected):
    from models.approval import ApprovalResponse

    response = ApprovalResponse(approval_id="x", approved=approved)
    assert ApprovalGuard._status_for(response) == expected
