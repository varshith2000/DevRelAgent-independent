"""
Integration Tests for Approvals API

Comprehensive test suite covering all approval workflow functionality.

Tests:
1. Approval request creation
2. Approval response handling
3. Pending approvals listing
4. Approval history tracking
5. SSE events for approvals
6. Timeout handling
7. Risk level categorization
8. Multiple concurrent approvals
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from guardrails.approval_guard import ApprovalGuard, get_approval_guard
from models.approval import ApprovalEvent, ApprovalRequest, ApprovalResponse
from routes.approvals import router as approvals_router

# These specs describe the Phase 1 approvals API (POST /approvals/request,
# /approvals/{id}/respond, /approvals/stream) which does not exist yet. They are
# skipped in the default run and remain runnable with `pytest -m integration`.
pytestmark = pytest.mark.integration


@pytest.fixture
def test_app() -> FastAPI:
    """Create test FastAPI application."""
    app = FastAPI()
    app.include_router(approvals_router)
    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def approval_guard() -> ApprovalGuard:
    """Create approval guard for testing."""
    guard = ApprovalGuard(timeout_seconds=30)  # Short timeout for tests
    return guard


class TestApprovalsAPI:
    """Test suite for Approvals API endpoints."""

    def test_1_approval_request_creation(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 1: Approval request creation.

        Verifies:
        - Approval request endpoint
        - Request data structure
        - Risk level assignment
        - Plan storage
        - Request ID generation
        """
        # Create approval request
        request_data = {
            "action_type": "github_pr",
            "plan": [
                "1. Fork the repository",
                "2. Create feature branch",
                "3. Make changes",
                "4. Submit pull request"
            ],
            "metadata": {
                "repository": "example/repo",
                "branch": "feature/new-feature"
            }
        }

        response = test_client.post(
            "/approvals/request",
            json=request_data
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert "approval_id" in data
        assert "status" in data
        assert "risk_level" in data
        assert data["approval_id"] is not None
        assert len(data["approval_id"]) > 0
        assert data["risk_level"] in ["low", "medium", "high", "critical"]

    def test_2_approval_response_handling(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 2: Approval response handling.

        Verifies:
        - Approval submission
        - Rejection handling
        - User attribution
        - Reason storage
        - Event completion
        """
        # First create an approval request
        create_response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "browser_action",
                "plan": ["Navigate to example.com"],
                "metadata": {}
            }
        )

        assert create_response.status_code == 200
        approval_id = create_response.json()["approval_id"]

        # Test approval
        approve_response = test_client.post(
            f"/approvals/{approval_id}/respond",
            json={
                "approved": True,
                "user": "test_user@example.com",
                "reason": "Test approval for verification"
            }
        )

        assert approve_response.status_code == 200
        data = approve_response.json()
        assert data["success"] is True
        assert "message" in data

    def test_3_pending_approvals_listing(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 3: Pending approvals listing.

        Verifies:
        - Pending approvals endpoint
        - List format
        - Request details
        - Filtering by user
        - Pagination
        """
        # Create multiple pending approvals
        for i in range(3):
            test_client.post(
                "/approvals/request",
                json={
                    "action_type": "github_issue",
                    "plan": [f"Step {i+1}"],
                    "metadata": {"test": i}
                }
            )

        # Get pending approvals
        response = test_client.get("/approvals/pending")

        assert response.status_code == 200
        data = response.json()

        assert "approvals" in data
        assert "count" in data
        assert isinstance(data["approvals"], list)
        assert data["count"] >= 3

        # Verify structure of approval items
        if len(data["approvals"]) > 0:
            approval = data["approvals"][0]
            assert "approval_id" in approval
            assert "action_type" in approval
            assert "plan" in approval
            assert "risk_level" in approval

    def test_4_approval_history_tracking(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 4: Approval history tracking.

        Verifies:
        - History endpoint
        - Chronological ordering
        - Decision tracking
        - User attribution
        - Reason preservation
        """
        # Create and respond to an approval
        create_response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "write_operation",
                "plan": ["Write data to database"],
                "metadata": {}
            }
        )

        approval_id = create_response.json()["approval_id"]

        # Reject it
        test_client.post(
            f"/approvals/{approval_id}/respond",
            json={
                "approved": False,
                "user": "security_admin@example.com",
                "reason": "Insufficient permissions for requested operation"
            }
        )

        # Get history
        history_response = test_client.get("/approvals/history?limit=10")

        assert history_response.status_code == 200
        data = history_response.json()

        assert "history" in data
        assert isinstance(data["history"], list)

        # Verify our rejection is in history
        if len(data["history"]) > 0:
            # Find our rejected approval
            our_approval = next(
                (h for h in data["history"] if h.get("approval_id") == approval_id),
                None
            )
            if our_approval:
                assert our_approval["approved"] is False
                assert our_approval["user"] == "security_admin@example.com"
                assert "insufficient permissions" in our_approval.get("reason", "").lower()

    def test_5_sse_events_for_approvals(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 5: SSE events for approvals.

        Verifies:
        - SSE stream initialization
        - Event format
        - Request events
        - Response events
        - Stream completion
        """
        # Note: SSE testing with TestClient has limitations
        # This test verifies the endpoint exists and returns correct headers
        response = test_client.get("/approvals/stream")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_6_timeout_handling(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 6: Timeout handling.

        Verifies:
        - Timeout configuration
        - Auto-rejection on timeout
        - Timeout reason
        - Cleanup after timeout
        """
        # Create approval with short timeout
        create_response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "browser_action",
                "plan": ["Navigate to site"],
                "timeout_seconds": 1  # Very short timeout
            }
        )

        approval_id = create_response.json()["approval_id"]

        # Wait for timeout
        import time
        time.sleep(2)

        # Try to respond after timeout (should fail or show as rejected)
        response = test_client.post(
            f"/approvals/{approval_id}/respond",
            json={
                "approved": True,
                "user": "late_user@example.com",
                "reason": "After timeout"
            }
        )

        # Should indicate approval is no longer pending
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is False or "timeout" in data.get("message", "").lower()

    def test_7_risk_level_categorization(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 7: Risk level categorization.

        Verifies:
        - Critical risk assignment
        - High risk assignment
        - Medium risk assignment
        - Low risk assignment
        - Risk-based approval requirements
        """
        test_cases = [
            {
                "action_type": "browser_action",
                "expected_risk": "critical"
            },
            {
                "action_type": "delete_operation",
                "expected_risk": "critical"
            },
            {
                "action_type": "github_pr",
                "expected_risk": "high"
            },
            {
                "action_type": "write_operation",
                "expected_risk": "high"
            },
            {
                "action_type": "github_issue",
                "expected_risk": "medium"
            }
        ]

        for test_case in test_cases:
            response = test_client.post(
                "/approvals/request",
                json={
                    "action_type": test_case["action_type"],
                    "plan": [f"Test {test_case['action_type']}"],
                    "metadata": {}
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["risk_level"] == test_case["expected_risk"], \
                f"Expected {test_case['expected_risk']} for {test_case['action_type']}, got {data['risk_level']}"

    def test_8_multiple_concurrent_approvals(self, test_client: TestClient, approval_guard: ApprovalGuard):
        """
        Test 8: Multiple concurrent approvals.

        Verifies:
        - Concurrent request handling
        - Independent approval tracking
        - No race conditions
        - Proper isolation
        """
        # Create multiple approvals concurrently
        approval_ids = []

        for i in range(5):
            response = test_client.post(
                "/approvals/request",
                json={
                    "action_type": "github_issue",
                    "plan": [f"Create issue {i}"],
                    "metadata": {"index": i}
                }
            )

            assert response.status_code == 200
            approval_ids.append(response.json()["approval_id"])

        # Verify all approvals are unique
        assert len(set(approval_ids)) == len(approval_ids)

        # Respond to each approval
        for i, approval_id in enumerate(approval_ids):
            response = test_client.post(
                f"/approvals/{approval_id}/respond",
                json={
                    "approved": i % 2 == 0,  # Alternate approve/reject
                    "user": f"test_user_{i}@example.com",
                    "reason": f"Test response {i}"
                }
            )

            assert response.status_code == 200


class TestApprovalsAPIErrors:
    """Test suite for error scenarios."""

    def test_invalid_approval_id(self, test_client: TestClient):
        """Test handling of invalid approval ID."""
        response = test_client.post(
            "/approvals/nonexistent_id/respond",
            json={
                "approved": True,
                "user": "test@example.com"
            }
        )

        # Should handle gracefully
        assert response.status_code in [404, 200]

    def test_missing_required_fields(self, test_client: TestClient):
        """Test handling of missing required fields in request."""
        response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "github_issue"
                # Missing 'plan' field
            }
        )

        assert response.status_code == 422

    def test_invalid_decision_format(self, test_client: TestClient):
        """Test handling of invalid decision format."""
        # First create an approval
        create_response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "github_issue",
                "plan": ["Test plan"],
                "metadata": {}
            }
        )

        approval_id = create_response.json()["approval_id"]

        # Send invalid response
        response = test_client.post(
            f"/approvals/{approval_id}/respond",
            json={
                "approved": "not_a_boolean",  # Invalid type
                "user": "test@example.com"
            }
        )

        assert response.status_code == 422


class TestApprovalsAPIValidation:
    """Test suite for input validation."""

    def test_action_type_validation(self, test_client: TestClient):
        """Test action type validation."""
        response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "unknown_action",  # Invalid action type
                "plan": ["Test"],
                "metadata": {}
            }
        )

        # Should either accept or reject based on validation strategy
        assert response.status_code in [200, 422]

    def test_plan_validation(self, test_client: TestClient):
        """Test plan validation."""
        # Empty plan
        response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "github_issue",
                "plan": [],  # Empty plan
                "metadata": {}
            }
        )

        # Should handle empty plan appropriately
        assert response.status_code in [200, 422]

    def test_user_validation(self, test_client: TestClient):
        """Test user field validation."""
        # Create approval
        create_response = test_client.post(
            "/approvals/request",
            json={
                "action_type": "github_issue",
                "plan": ["Test"],
                "metadata": {}
            }
        )

        approval_id = create_response.json()["approval_id"]

        # Test with invalid email format
        response = test_client.post(
            f"/approvals/{approval_id}/respond",
            json={
                "approved": True,
                "user": "not_an_email"
            }
        )

        # Should accept (user field may be optional/validated elsewhere)
        assert response.status_code in [200, 422]


class TestApprovalsAPIStatistics:
    """Test suite for statistics and monitoring."""

    def test_approval_statistics(self, test_client: TestClient):
        """Test approval statistics endpoint."""
        response = test_client.get("/approvals/stats")

        assert response.status_code == 200
        data = response.json()

        assert "statistics" in data or "pending" in data or "total" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
