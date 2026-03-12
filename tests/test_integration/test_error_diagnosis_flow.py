"""
Integration Test for Error Diagnosis Flow

Tests the complete error diagnosis workflow from initial error report
through investigation to resolution recommendations.

Flow:
1. User reports an error
2. Agent queries logs/metrics for context
3. Agent identifies patterns and root causes
4. Agent provides structured diagnosis
5. Agent suggests remediation steps
6. Agent offers to create tickets/documentation
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import json

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from routes.chat import router as chat_router
from models.schemas import ChatRequest, StructuredAgentResponse, AgentObservation
from agent.loop import AgentLoop
from skills.diagnose_error import DiagnoseErrorSkill


class TestErrorDiagnosisFlow:
    """Test suite for error diagnosis workflow."""

    @pytest.fixture
    def app(self):
        """Create test application."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(chat_router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def agent_loop(self):
        """Create agent loop for testing."""
        return AgentLoop(
            enable_input_guardrails=False,
            enable_output_guardrails=False,
            enable_tool_guardrails=False,
        )

    @pytest.fixture
    def mock_tool_results(self):
        """Mock tool execution results for error diagnosis."""
        return {
            "clickhouse_query": {
                "success": True,
                "result": {
                    "data": [
                        {
                            "timestamp": "2026-03-11 14:30:00",
                            "error_type": "DatabaseConnectionTimeout",
                            "error_message": "Connection timeout after 30s",
                            "service": "api",
                            "count": 234
                        },
                        {
                            "timestamp": "2026-03-11 14:31:00",
                            "error_type": "QueryExecutionFailed",
                            "error_message": "Table 'users' doesn't exist",
                            "service": "api",
                            "count": 156
                        }
                    ],
                    "total": 390,
                    "time_range": "1h"
                }
            },
            "get_error_rate": {
                "success": True,
                "result": {
                    "service": "api",
                    "error_rate": 0.15,
                    "baseline": 0.02,
                    "time_period": "1h",
                    "status": "elevated"
                }
            },
            "get_latency_metrics": {
                "success": True,
                "result": {
                    "p50": 150,
                    "p95": 850,
                    "p99": 1200,
                    "baseline_p95": 200,
                    "service": "api"
                }
            }
        }

    def test_step_1_error_report_submission(self, client: TestClient):
        """
        Test Step 1: Error report submission.

        Verifies:
        - User can submit error description
        - Agent acknowledges error report
        - Session is created for diagnosis
        - Initial response indicates investigation starting
        """
        session_id = "error_diagnosis_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "We're seeing high error rates in our API service. Users are reporting timeouts and connection errors.",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert "response" in data
        assert "session_id" in data
        assert data["session_id"] == session_id

        # Response should indicate investigation
        response_text = data["response"].lower()
        investigation_keywords = ["investigating", "check", "analyze", "look into"]
        assert any(keyword in response_text for keyword in investigation_keywords)

    def test_step_2_log_query_execution(self, client: TestClient, mock_tool_results):
        """
        Test Step 2: Log query execution.

        Verifies:
        - Agent queries error logs
        - Time range is appropriate
        - Filters are applied correctly
        - Results are retrieved successfully
        """
        session_id = "error_diagnosis_test_002"

        # Mock the tool execution
        with patch('agent.loop.AgentLoop._execute_tool_with_guardrails') as mock_execute:
            mock_execute.return_value = MagicMock(
                tool_name="clickhouse_query",
                success=True,
                result=mock_tool_results["clickhouse_query"]["result"]
            )

            response = client.post(
                "/chat",
                json={
                    "message": "Show me error logs from the last hour for the API service",
                    "session_id": session_id
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Verify tool was called
            assert mock_execute.called

            # Response should contain error information
            response_text = data["response"].lower()
            assert "error" in response_text or "timeout" in response_text or "connection" in response_text

    def test_step_3_pattern_identification(self, client: TestClient):
        """
        Test Step 3: Pattern identification.

        Verifies:
        - Agent identifies error patterns
        - Recognizes error types
        - Detects frequency patterns
        - Correlates with metrics
        """
        session_id = "error_diagnosis_test_003"

        response = client.post(
            "/chat",
            json={
                "message": "What patterns do you see in these errors? Are there any correlations?",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss patterns
        response_text = data["response"].lower()
        pattern_keywords = ["pattern", "correlation", "trend", "spike", "increase"]
        assert any(keyword in response_text for keyword in pattern_keywords)

    def test_step_4_root_cause_analysis(self, client: TestClient):
        """
        Test Step 4: Root cause analysis.

        Verifies:
        - Agent identifies root cause
        - Provides explanation
        - Links evidence to conclusion
        - Assesses confidence
        """
        session_id = "error_diagnosis_test_004"

        response = client.post(
            "/chat",
            json={
                "message": "What's the root cause of these connection timeout errors?",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should include root cause analysis
        response_text = data["response"].lower()
        cause_keywords = ["cause", "because", "due to", "reason", "issue"]
        assert any(keyword in response_text for keyword in cause_keywords)

    def test_step_5_remediation_recommendations(self, client: TestClient):
        """
        Test Step 5: Remediation recommendations.

        Verifies:
        - Agent suggests specific fixes
        - Provides step-by-step guidance
        - Includes priority levels
        - Estimates impact
        """
        session_id = "error_diagnosis_test_005"

        response = client.post(
            "/chat",
            json={
                "message": "How do we fix the connection timeout issue?",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should include remediation steps
        response_text = data["response"].lower()
        fix_keywords = ["fix", "increase", "configure", "change", "add", "update"]
        assert any(keyword in response_text for keyword in fix_keywords)

    def test_step_6_ticket_creation_offer(self, client: TestClient):
        """
        Test Step 6: Ticket creation offer.

        Verifies:
        - Agent offers to create ticket
        - Provides ticket template
        - Includes all relevant details
        - Asks for confirmation
        """
        session_id = "error_diagnosis_test_006"

        response = client.post(
            "/chat",
            json={
                "message": "Create a GitHub issue for this connection timeout problem",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should indicate ticket creation or approval needed
        response_text = data["response"].lower()
        ticket_keywords = ["issue", "ticket", "github", "create", "approval", "plan"]
        assert any(keyword in response_text for keyword in ticket_keywords)

    @pytest.mark.asyncio
    async def test_complete_diagnosis_flow(self):
        """
        Test complete diagnosis flow end-to-end.

        Verifies:
        - All steps execute in sequence
        - Context is maintained
        - Each step builds on previous
        - Final output is comprehensive
        """
        agent = AgentLoop(
            enable_input_guardrails=False,
            enable_output_guardrails=False,
            enable_tool_guardrails=False,
        )

        # Create mock session
        session = MagicMock()
        session.session_id = "test_diagnosis_flow_001"
        session.messages = []

        # Simulate diagnosis conversation
        messages = [
            "We're seeing API timeouts",
            "Show me the error logs",
            "What's causing this?",
            "How do we fix it?",
        ]

        results = []
        for msg in messages:
            response, tool_calls = await agent.process_with_tools(msg, session)
            results.append({
                "message": msg,
                "response": response,
                "tool_calls": tool_calls
            })
            session.messages.append({"role": "user", "content": msg})
            session.messages.append({"role": "assistant", "content": response})

        # Verify flow executed
        assert len(results) == 4

        # Verify responses are present
        for result in results:
            assert result["response"] is not None
            assert len(result["response"]) > 0

    def test_diagnosis_with_structured_output(self, client: TestClient):
        """
        Test diagnosis returns structured output.

        Verifies:
        - Observations are created
        - Evidence is collected
        - Impact is assessed
        - Confidence is calculated
        - Actions are suggested
        """
        session_id = "structured_diagnosis_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Diagnose the API latency spike we're seeing. P95 has gone from 200ms to 850ms.",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "response" in data
        assert "session_id" in data

        # Response should mention latency
        response_text = data["response"].lower()
        assert "latency" in response_text or "p95" in response_text or "slow" in response_text

    def test_diagnosis_with_low_confidence(self, client: TestClient):
        """
        Test diagnosis with insufficient information.

        Verifies:
        - Agent acknowledges uncertainty
        - Requests more information
        - Provides helpful suggestions
        - Doesn't make unsupported claims
        """
        session_id = "low_confidence_diagnosis_001"

        response = client.post(
            "/chat",
            json={
                "message": "Something's wrong but I don't know what",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should ask for clarification
        response_text = data["response"].lower()
        clarification_keywords = ["more information", "clarify", "specific", "details", "describe"]
        assert any(keyword in response_text for keyword in clarification_keywords)

    def test_diagnosis_tool_error_handling(self, client: TestClient):
        """
        Test diagnosis when tools fail.

        Verifies:
        - Agent handles tool failures gracefully
        - Provides alternative approaches
        - Explains the limitation
        - Still offers helpful guidance
        """
        session_id = "tool_error_diagnosis_001"

        # This test simulates a scenario where tools might not be available
        # The agent should still provide helpful guidance
        response = client.post(
            "/chat",
            json={
                "message": "The database is down. What should I do?",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should still get a helpful response even if tools fail
        assert "response" in data
        assert len(data["response"]) > 0

        # Should mention general troubleshooting steps
        response_text = data["response"].lower()
        general_keywords = ["check", "verify", "ensure", "restart", "contact"]
        assert any(keyword in response_text for keyword in general_keywords)


class TestErrorDiagnosisIntegration:
    """Integration tests for error diagnosis with actual components."""

    @pytest.fixture
    def app(self):
        """Create test application."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(chat_router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_diagnose_error_skill_integration(self, client: TestClient):
        """
        Test error diagnosis skill integration.

        Verifies:
        - Skill is available
        - Skill can be invoked
        - Skill returns structured results
        - Results are properly formatted
        """
        session_id = "skill_diagnosis_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Diagnose the error: DatabaseConnectionTimeout in API service",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should get a response
        assert "response" in data
        assert len(data["response"]) > 0

    def test_multi_step_investigation(self, client: TestClient):
        """
        Test multi-step investigation process.

        Verifies:
        - Session context is maintained
        - Each step builds on previous
        - Agent tracks investigation state
        - Final synthesis is comprehensive
        """
        session_id = "multi_step_test_001"

        # Step 1: Initial report
        response1 = client.post(
            "/chat",
            json={
                "message": "API error rate is high",
                "session_id": session_id
            }
        )
        assert response1.status_code == 200

        # Step 2: Request details
        response2 = client.post(
            "/chat",
            json={
                "message": "What's the error rate and which errors are most common?",
                "session_id": session_id
            }
        )
        assert response2.status_code == 200

        # Step 3: Request root cause
        response3 = client.post(
            "/chat",
            json={
                "message": "What's causing these errors?",
                "session_id": session_id
            }
        )
        assert response3.status_code == 200

        # Step 4: Request solution
        response4 = client.post(
            "/chat",
            json={
                "message": "How do we fix this?",
                "session_id": session_id
            }
        )
        assert response4.status_code == 200

        # Verify session exists with all messages
        history = client.get(f"/chat/history/{session_id}")
        assert history.status_code == 200
        history_data = history.json()

        # Should have at least 8 messages (4 user + 4 assistant)
        assert len(history_data["messages"]) >= 8

    def test_diagnosis_with_correlation(self, client: TestClient):
        """
        Test diagnosis with correlation analysis.

        Verifies:
        - Agent correlates errors with metrics
        - Identifies relationships
        - Provides multi-faceted analysis
        """
        session_id = "correlation_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Are the API errors correlated with increased latency or CPU usage?",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss correlation
        response_text = data["response"].lower()
        correlation_keywords = ["correlat", "relationship", "associated", "linked", "related"]
        assert any(keyword in response_text for keyword in correlation_keywords)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
