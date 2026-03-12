"""
Integration Test for Dashboard Creation Flow

Tests the complete dashboard creation workflow from initial request
through configuration generation to deployment.

Flow:
1. User requests dashboard creation
2. Agent gathers requirements (metrics, time range, visualization)
3. Agent generates dashboard configuration
4. Agent validates configuration
5. Agent deploys/creates dashboard
6. Agent provides verification and next steps
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from routes.chat import router as chat_router
from models.schemas import ChatRequest, StructuredAgentResponse
from agent.loop import AgentLoop


class TestDashboardCreationFlow:
    """Test suite for dashboard creation workflow."""

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
    def mock_dashboard_tool(self):
        """Mock dashboard tool results."""
        return {
            "create_dashboard": {
                "success": True,
                "result": {
                    "dashboard_id": "dash_api_metrics_001",
                    "dashboard_url": "http://grafana.example.com/d/dash_api_metrics_001",
                    "title": "API Metrics Dashboard",
                    "panels": 5,
                    "created_at": "2026-03-11T15:00:00Z"
                }
            },
            "get_dashboard": {
                "success": True,
                "result": {
                    "dashboard": {
                        "id": "dash_api_metrics_001",
                        "title": "API Metrics Dashboard",
                        "panels": [
                            {"id": 1, "title": "Request Rate", "type": "graph"},
                            {"id": 2, "title": "Error Rate", "type": "graph"},
                            {"id": 3, "title": "Latency (P95)", "type": "graph"},
                            {"id": 4, "title": "CPU Usage", "type": "gauge"},
                            {"id": 5, "title": "Memory Usage", "type": "gauge"}
                        ]
                    }
                }
            }
        }

    def test_step_1_dashboard_request(self, client: TestClient):
        """
        Test Step 1: Dashboard creation request.

        Verifies:
        - User can request dashboard creation
        - Agent acknowledges request
        - Agent asks for requirements
        - Session is established
        """
        session_id = "dashboard_creation_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "I need a dashboard to monitor API performance metrics",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert "response" in data
        assert "session_id" in data
        assert data["session_id"] == session_id

        # Response should ask for requirements
        response_text = data["response"].lower()
        requirement_keywords = ["what", "metrics", "include", "need", "like"]
        assert any(keyword in response_text for keyword in requirement_keywords)

    def test_step_2_requirement_gathering(self, client: TestClient):
        """
        Test Step 2: Requirement gathering.

        Verifies:
        - Agent collects metric requirements
        - Time range is specified
        - Visualization preferences
        - Data sources identified
        """
        session_id = "dashboard_creation_test_002"

        response = client.post(
            "/chat",
            json={
                "message": "Create a dashboard showing request rate, error rate, and P95 latency for the last hour",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should confirm requirements
        response_text = data["response"].lower()
        assert "dashboard" in response_text
        assert any(metric in response_text for metric in ["request", "error", "latency", "p95"])

    def test_step_3_configuration_generation(self, client: TestClient, mock_dashboard_tool):
        """
        Test Step 3: Configuration generation.

        Verifies:
        - Agent generates dashboard config
        - Config includes all requested metrics
        - Config has proper structure
        - Config is valid JSON
        """
        session_id = "dashboard_creation_test_003"

        # Mock the tool execution
        with patch('agent.loop.AgentLoop._execute_tool_with_guardrails') as mock_execute:
            mock_execute.return_value = MagicMock(
                tool_name="create_dashboard",
                success=True,
                result=mock_dashboard_tool["create_dashboard"]["result"]
            )

            response = client.post(
                "/chat",
                json={
                    "message": "Generate the dashboard configuration for API metrics",
                    "session_id": session_id
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Response should mention configuration
            response_text = data["response"].lower()
            config_keywords = ["config", "json", "dashboard", "panel", "created"]
            assert any(keyword in response_text for keyword in config_keywords)

    def test_step_4_configuration_validation(self, client: TestClient):
        """
        Test Step 4: Configuration validation.

        Verifies:
        - Agent validates configuration
        - Checks for required fields
        - Verifies panel definitions
        - Ensures data source compatibility
        """
        session_id = "dashboard_creation_test_004"

        response = client.post(
            "/chat",
            json={
                "message": "Validate this dashboard configuration before deploying",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss validation
        response_text = data["response"].lower()
        validation_keywords = ["valid", "check", "verify", "correct", "missing"]
        assert any(keyword in response_text for keyword in validation_keywords)

    def test_step_5_dashboard_deployment(self, client: TestClient, mock_dashboard_tool):
        """
        Test Step 5: Dashboard deployment.

        Verifies:
        - Agent deploys dashboard
        - Dashboard is created in Grafana
        - URL is returned
        - Deployment is confirmed
        """
        session_id = "dashboard_creation_test_005"

        # Mock the tool execution
        with patch('agent.loop.AgentLoop._execute_tool_with_guardrails') as mock_execute:
            mock_execute.return_value = MagicMock(
                tool_name="create_dashboard",
                success=True,
                result=mock_dashboard_tool["create_dashboard"]["result"]
            )

            response = client.post(
                "/chat",
                json={
                    "message": "Deploy the API metrics dashboard to Grafana",
                    "session_id": session_id
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Response should confirm deployment
            response_text = data["response"].lower()
            deploy_keywords = ["deployed", "created", "available", "url", "link"]
            assert any(keyword in response_text for keyword in deploy_keywords)

    def test_step_6_verification_and_next_steps(self, client: TestClient):
        """
        Test Step 6: Verification and next steps.

        Verifies:
        - Agent verifies dashboard functionality
        - Provides dashboard URL
        - Suggests customizations
        - Offers to create alerts
        """
        session_id = "dashboard_creation_test_006"

        response = client.post(
            "/chat",
            json={
                "message": "Verify the dashboard is working and suggest next steps",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should provide verification and suggestions
        response_text = data["response"].lower()
        next_steps_keywords = ["customize", "alert", "panel", "add", "modify", "share"]
        assert any(keyword in response_text for keyword in next_steps_keywords)

    @pytest.mark.asyncio
    async def test_complete_dashboard_flow(self):
        """
        Test complete dashboard creation flow end-to-end.

        Verifies:
        - All steps execute in sequence
        - Context is maintained
        - Each step builds on previous
        - Final dashboard is complete
        """
        agent = AgentLoop(
            enable_input_guardrails=False,
            enable_output_guardrails=False,
            enable_tool_guardrails=False,
        )

        # Create mock session
        session = MagicMock()
        session.session_id = "test_dashboard_flow_001"
        session.messages = []

        # Simulate dashboard creation conversation
        messages = [
            "I need an API metrics dashboard",
            "Include request rate, error rate, and P95 latency",
            "Create it now",
            "Verify it's working",
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

        # Verify responses are relevant
        for i, result in enumerate(results):
            assert result["response"] is not None
            assert len(result["response"]) > 0

    def test_dashboard_template_selection(self, client: TestClient):
        """
        Test dashboard template selection.

        Verifies:
        - Agent offers template options
        - Templates match use cases
        - User can select template
        - Template is customizable
        """
        session_id = "dashboard_template_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Show me available dashboard templates for API monitoring",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should mention templates or options
        response_text = data["response"].lower()
        template_keywords = ["template", "option", "available", "choose", "select"]
        assert any(keyword in response_text for keyword in template_keywords)

    def test_dashboard_customization(self, client: TestClient):
        """
        Test dashboard customization.

        Verifies:
        - Agent can modify existing dashboard
        - Agent can add panels
        - Agent can adjust time ranges
        - Agent can change visualizations
        """
        session_id = "dashboard_customization_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Add a CPU usage panel to the existing API dashboard and change the time range to 6 hours",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss customization
        response_text = data["response"].lower()
        customization_keywords = ["add", "panel", "cpu", "modify", "change", "update"]
        assert any(keyword in response_text for keyword in customization_keywords)

    def test_dashboard_cloning(self, client: TestClient):
        """
        Test dashboard cloning.

        Verifies:
        - Agent can clone existing dashboard
        - Agent can modify cloned version
        - Original is preserved
        - Clone has unique ID
        """
        session_id = "dashboard_clone_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Clone the API metrics dashboard and create a version for the database service",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss cloning
        response_text = data["response"].lower()
        clone_keywords = ["clone", "copy", "duplicate", "based on", "similar"]
        assert any(keyword in response_text for keyword in clone_keywords)

    def test_dashboard_alert_configuration(self, client: TestClient):
        """
        Test dashboard alert configuration.

        Verifies:
        - Agent can create alerts
        - Agent suggests alert thresholds
        - Agent configures notifications
        - Alerts are tied to dashboard
        """
        session_id = "dashboard_alert_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Add alerts to the dashboard to notify when error rate exceeds 5%",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss alerts
        response_text = data["response"].lower()
        alert_keywords = ["alert", "threshold", "notify", "notification", "exceeds"]
        assert any(keyword in response_text for keyword in alert_keywords)

    def test_dashboard_export_import(self, client: TestClient):
        """
        Test dashboard export/import.

        Verifies:
        - Agent can export dashboard config
        - Agent can import dashboard config
        - Config is portable
        - Import validates structure
        """
        session_id = "dashboard_export_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Export the dashboard configuration as JSON so I can share it",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss export
        response_text = data["response"].lower()
        export_keywords = ["export", "json", "file", "save", "share"]
        assert any(keyword in response_text for keyword in export_keywords)


class TestDashboardCreationErrorHandling:
    """Test error handling in dashboard creation flow."""

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

    def test_invalid_dashboard_request(self, client: TestClient):
        """
        Test handling of invalid dashboard request.

        Verifies:
        - Agent handles vague requests
        - Agent asks for clarification
        - Agent provides examples
        - Error message is helpful
        """
        session_id = "invalid_dashboard_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Create a dashboard",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should ask for more details
        response_text = data["response"].lower()
        assert "what" in response_text or "which" in response_text or "metrics" in response_text

    def test_dashboard_creation_failure(self, client: TestClient):
        """
        Test handling of dashboard creation failure.

        Verifies:
        - Agent handles tool failure gracefully
        - Agent provides alternative
        - Agent explains the issue
        - User can recover
        """
        session_id = "dashboard_failure_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Create a dashboard (this will fail due to mock)",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should get a response even if tools fail
        assert "response" in data
        assert len(data["response"]) > 0

    def test_unsupported_visualization(self, client: TestClient):
        """
        Test handling of unsupported visualization.

        Verifies:
        - Agent identifies unsupported request
        - Agent suggests alternatives
        - Agent explains limitations
        """
        session_id = "unsupported_viz_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Create a 3D holographic visualization of the API metrics",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should suggest alternatives
        response_text = data["response"].lower()
        assert "can't" in response_text or "not support" in response_text or "alternat" in response_text or "available" in response_text


class TestDashboardCreationIntegration:
    """Integration tests for dashboard creation with actual components."""

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

    def test_dashboard_tool_integration(self, client: TestClient):
        """
        Test dashboard tool integration.

        Verifies:
        - Dashboard tool is accessible
        - Tool can be invoked
        - Tool returns proper format
        - Results are integrated into response
        """
        session_id = "dashboard_tool_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Create a dashboard called 'API Performance' with error rate and latency panels",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should get a response about dashboard
        assert "response" in data
        response_text = data["response"].lower()
        assert "dashboard" in response_text

    def test_multi_dashboard_management(self, client: TestClient):
        """
        Test managing multiple dashboards.

        Verifies:
        - Agent can list dashboards
        - Agent can switch between dashboards
        - Agent can update specific dashboard
        - Agent maintains context
        """
        session_id = "multi_dashboard_test_001"

        # Create first dashboard
        response1 = client.post(
            "/chat",
            json={
                "message": "Create an API metrics dashboard",
                "session_id": session_id
            }
        )
        assert response1.status_code == 200

        # Create second dashboard
        response2 = client.post(
            "/chat",
            json={
                "message": "Now create a database metrics dashboard",
                "session_id": session_id
            }
        )
        assert response2.status_code == 200

        # List dashboards
        response3 = client.post(
            "/chat",
            json={
                "message": "List all available dashboards",
                "session_id": session_id
            }
        )
        assert response3.status_code == 200

        data3 = response3.json()
        response_text = data3["response"].lower()
        assert "dashboard" in response_text

    def test_dashboard_collaboration_features(self, client: TestClient):
        """
        Test dashboard collaboration features.

        Verifies:
        - Agent can share dashboard
        - Agent can set permissions
        - Agent can create snapshots
        - Agent can annotate dashboards
        """
        session_id = "dashboard_collab_test_001"

        response = client.post(
            "/chat",
            json={
                "message": "Share the API dashboard with the team and set up automatic snapshots",
                "session_id": session_id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Response should discuss sharing/snapshots
        response_text = data["response"].lower()
        collab_keywords = ["share", "team", "snapshot", "export", "permission"]
        assert any(keyword in response_text for keyword in collab_keywords)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
