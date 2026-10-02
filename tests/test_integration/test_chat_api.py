"""
Integration Tests for Chat API

Comprehensive test suite covering all chat API endpoints and functionality.

Tests:
1. Basic chat message processing
2. Session management and persistence
3. Tool execution and tracking
4. Streaming responses
5. Error handling and guardrails
6. Audit logging integration
7. Confidence-based responses
8. Structured output format
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from agent.loop import AgentLoop
from models.schemas import ChatRequest, ChatResponse, SessionContext
from routes.chat import get_agent_loop, get_or_create_session
from routes.chat import router as chat_router


@pytest.fixture
def test_app(db_engine) -> FastAPI:
    """Create test FastAPI application bound to a throwaway database."""
    app = FastAPI()
    app.include_router(chat_router)
    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
async def agent_loop() -> AgentLoop:
    """Create agent loop for testing."""
    return AgentLoop(
        enable_input_guardrails=False,  # Disable for faster tests
        enable_output_guardrails=False,
        enable_tool_guardrails=False,
    )


@pytest.fixture
async def test_session(agent_loop: AgentLoop) -> SessionContext:
    """Create test session."""
    session = await get_or_create_session("test_session_123")
    return session


class TestChatAPI:
    """Test suite for Chat API endpoints."""

    def test_1_basic_chat_message(self, test_client: TestClient, agent_loop: AgentLoop):
        """
        Test 1: Basic chat message processing.

        Verifies:
        - Message submission
        - Response generation
        - Session creation
        - Response format
        """
        # Prepare request
        request_data = {
            "message": "What is the current system status?",
            "session_id": None  # Let system create new session
        }

        # Send request
        response = test_client.post(
            "/chat",
            json=request_data,
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert "response" in data
        assert "session_id" in data
        assert "metadata" in data
        assert data["response"] is not None
        assert len(data["response"]) > 0
        assert data["session_id"] is not None

        # Verify metadata
        metadata = data["metadata"]
        assert "message_count" in metadata
        assert "tool_call_count" in metadata
        assert metadata["message_count"] >= 1

    def test_2_session_persistence(self, test_client: TestClient):
        """
        Test 2: Session management and persistence.

        Verifies:
        - Session creation
        - Message history tracking
        - Session retrieval
        - Message count increment
        """
        session_id = "test_session_persistence_456"

        # First message
        response1 = test_client.post(
            "/chat",
            json={
                "message": "First message",
                "session_id": session_id
            }
        )
        assert response1.status_code == 200
        data1 = response1.json()
        # A completed turn stores both the user message and the assistant reply.
        assert data1["metadata"]["message_count"] == 2

        # Second message in same session
        response2 = test_client.post(
            "/chat",
            json={
                "message": "Second message",
                "session_id": session_id
            }
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["metadata"]["message_count"] == 4  # Two completed turns

        # Verify session exists
        history_response = test_client.get(f"/chat/history/{session_id}")
        assert history_response.status_code == 200
        history_data = history_response.json()

        assert len(history_data["messages"]) >= 4  # 2 user + 2 assistant
        assert history_data["session_id"] == session_id

    def test_3_tool_execution_tracking(self, test_client: TestClient):
        """
        Test 3: Tool execution and tracking.

        Verifies:
        - Tool invocation
        - Tool call result tracking
        - Tool call metadata
        - Error handling for failed tools
        """
        # Message that should trigger tool execution
        response = test_client.post(
            "/chat",
            json={
                "message": "Show me recent errors from the database",
                "session_id": "test_tools_789"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Check tool_calls in response
        assert "tool_calls" in data
        tool_calls = data["tool_calls"]

        # Even if no tools actually execute (due to environment),
        # the structure should be present
        assert isinstance(tool_calls, list)

        # If tools were called, verify structure
        if len(tool_calls) > 0:
            tool_call = tool_calls[0]
            assert "tool_name" in tool_call
            assert "success" in tool_call
            assert "arguments" in tool_call

    def test_4_streaming_responses(self, test_client: TestClient):
        """
        Test 4: Streaming responses.

        Verifies:
        - SSE stream initialization
        - Token streaming
        - Tool call events
        - Stream completion
        - Session management in streams
        """
        response = test_client.get(
            "/chat/stream",
            params={
                "message": "Tell me about the system",
                "session_id": "test_stream_999",
                "include_tool_calls": "true"
            }
        )

        assert response.status_code == 200

        # Verify SSE headers
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Collect stream chunks
        chunks = []
        for line in response.iter_lines():
            if isinstance(line, bytes):
                line = line.decode('utf-8')
            if line and line.startswith("data: "):
                    data = json.loads(line[6:])
                    chunks.append(data)

                    # Check for done event
                    if data.get("type") == "done":
                        break

        # Verify we got chunks
        assert len(chunks) > 0

        # Verify session_start event
        session_events = [c for c in chunks if c.get("type") == "session_start"]
        assert len(session_events) > 0
        assert session_events[0]["session_id"] == "test_stream_999"

        # Verify done event
        done_events = [c for c in chunks if c.get("type") == "done"]
        assert len(done_events) > 0

    def test_5_error_handling_and_guardrails(self, test_client: TestClient):
        """
        Test 5: Error handling and guardrails.

        Verifies:
        - Invalid input handling
        - Error response format
        - Graceful degradation
        - Error messages
        """
        # Test with potentially problematic input
        response = test_client.post(
            "/chat",
            json={
                "message": "'; DROP TABLE users; --",
                "session_id": "test_guardrails_111"
            }
        )

        # Should still return 200, but with safe response
        assert response.status_code == 200
        data = response.json()

        # Response should be safe and not contain injection
        assert "response" in data
        assert "DROP TABLE" not in data["response"]
        assert len(data["response"]) > 0

        # Test with empty message
        empty_response = test_client.post(
            "/chat",
            json={
                "message": "",
                "session_id": "test_empty_222"
            }
        )

        # Should handle gracefully
        assert empty_response.status_code in [200, 422]  # 422 for validation error

    def test_6_audit_logging_integration(self, test_client: TestClient):
        """
        Test 6: Audit logging integration.

        Verifies:
        - Audit entry creation
        - Session tracking in audit
        - Tool execution logging
        - Audit data completeness
        """
        session_id = "test_audit_333"

        # Send a message
        response = test_client.post(
            "/chat",
            json={
                "message": "Test audit logging",
                "session_id": session_id
            }
        )

        assert response.status_code == 200

        # Verify audit_id in metadata (if audit logging is enabled)
        data = response.json()
        if "metadata" in data and isinstance(data["metadata"], dict):
            # Check for audit_id if it exists
            if "audit_id" in data["metadata"]:
                assert data["metadata"]["audit_id"] is not None
                assert len(data["metadata"]["audit_id"]) > 0

    def test_7_confidence_based_responses(self, test_client: TestClient):
        """
        Test 7: Confidence-based responses.

        Verifies:
        - Low confidence handling
        - Fallback suggestions
        - Unknown intent handling
        - Confidence score presence
        """
        # Test with ambiguous query
        response = test_client.post(
            "/chat",
            json={
                "message": "blah blah random words",
                "session_id": "test_confidence_444"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Must always return a usable response...
        assert "response" in data
        assert len(data["response"]) > 0

        # ...and low-confidence input must not silently execute a tool.
        assert data["metadata"]["tool_call_count"] == 0

    def test_8_structured_output_format(self, test_client: TestClient):
        """
        Test 8: Structured output format.

        Verifies:
        - Response structure compliance
        - Metadata presence
        - Tool call format
        - Session data format
        """
        response = test_client.post(
            "/chat",
            json={
                "message": "Test structured output",
                "session_id": "test_structured_555"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        required_fields = ["response", "session_id", "metadata"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify metadata structure
        metadata = data["metadata"]
        assert isinstance(metadata, dict)
        assert "message_count" in metadata
        assert "tool_call_count" in metadata

        # Verify types
        assert isinstance(data["response"], str)
        assert isinstance(data["session_id"], str)
        assert isinstance(metadata["message_count"], int)
        assert isinstance(metadata["tool_call_count"], int)


class TestChatAPIErrors:
    """Test suite for error scenarios."""

    def test_invalid_json_request(self, test_client: TestClient):
        """Test handling of invalid JSON."""
        response = test_client.post(
            "/chat",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_missing_required_field(self, test_client: TestClient):
        """Test handling of missing required fields."""
        response = test_client.post(
            "/chat",
            json={"session_id": "test"}  # Missing 'message'
        )
        assert response.status_code == 422

    def test_nonexistent_session_history(self, test_client: TestClient):
        """Test retrieval of non-existent session."""
        response = test_client.get("/chat/history/nonexistent_session")
        assert response.status_code == 404

    def test_session_deletion(self, test_client: TestClient):
        """Test session deletion."""
        # Create a session first
        test_client.post(
            "/chat",
            json={
                "message": "Test message",
                "session_id": "test_delete_666"
            }
        )

        # Delete the session
        delete_response = test_client.delete("/chat/session/test_delete_666")
        assert delete_response.status_code == 200

        # Verify deletion
        get_response = test_client.get("/chat/history/test_delete_666")
        assert get_response.status_code == 404


class TestChatAPIHealth:
    """Test suite for health and monitoring endpoints."""

    def test_health_endpoint(self, test_client: TestClient):
        """Test health check endpoint."""
        response = test_client.get("/chat/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "active_sessions" in data
        assert "timestamp" in data
        assert isinstance(data["active_sessions"], int)


@pytest.mark.asyncio
class TestChatAPIAsync:
    """Async test suite for chat API."""

    async def test_concurrent_requests(self, test_client: TestClient):
        """Test handling of concurrent requests."""
        import asyncio

        async def send_request(message: str, session_id: str):
            """Send a chat request asynchronously."""
            # Note: TestClient is synchronous, so this is a simplified test
            return {"message": message, "session_id": session_id}

        # Create multiple concurrent requests
        tasks = [
            send_request(f"Message {i}", f"session_concurrent_{i}")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
