"""
Chat API Routes — Conversation endpoint with streaming support

Provides REST API for conversing with the DevRelAgent.
Supports both regular responses and SSE streaming.

Routes:
- POST /chat - Regular chat endpoint
- GET /chat/stream - SSE streaming endpoint
- GET /chat/history/{session_id} - Get conversation history
- DELETE /chat/session/{session_id} - Clear session

Usage:
    import httpx

    # Regular request
    response = await httpx.post("http://localhost:8000/chat", json={
        "message": "How do I authenticate?"
    })
    data = response.json()

    # Streaming request
    async with httpx.stream("GET", "http://localhost:8000/chat/stream", params={
        "message": "How do I authenticate?"
    }) as response:
        async for chunk in response.aiter_lines():
            if chunk.startswith("data: "):
                data = json.loads(chunk[6:])
                print(data["content"])
"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.loop import AgentLoop
from audit.logger import get_audit_logger
from audit.schemas import ActionType, AuditEntry, DataAccessed
from models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    SessionContext,
    ToolCallResult,
)
from tools.registry import get_registry

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/chat", tags=["chat"])

# Session storage (in production, use Redis or database)
_sessions: Dict[str, SessionContext] = {}
_session_lock = asyncio.Lock()


# Session management
async def get_or_create_session(session_id: Optional[str]) -> SessionContext:
    """Get existing session or create new one."""
    async with _session_lock:
        if session_id and session_id in _sessions:
            session = _sessions[session_id]
            session.last_activity = datetime.now()
            return session

        # Create new session
        new_session_id = session_id or str(uuid.uuid4())
        session = SessionContext(session_id=new_session_id)
        _sessions[new_session_id] = session
        logger.info(f"Created new session: {new_session_id}")
        return session


async def cleanup_old_sessions(max_age_minutes: int = 60):
    """Clean up inactive sessions."""
    async with _session_lock:
        now = datetime.now()
        to_remove = []

        for session_id, session in _sessions.items():
            age = (now - session.last_activity).total_seconds() / 60
            if age > max_age_minutes:
                to_remove.append(session_id)

        for session_id in to_remove:
            del _sessions[session_id]
            logger.info(f"Cleaned up session: {session_id}")


# Agent loop singleton
_agent_loop: Optional[AgentLoop] = None


def get_agent_loop() -> AgentLoop:
    """Get or create agent loop instance."""
    global _agent_loop
    if _agent_loop is None:
        _agent_loop = AgentLoop()
    return _agent_loop


# ============== Endpoints ==============

@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.

    Processes user message and returns agent response.
    Tool calls are executed and included in the response.

    Args:
        request: Chat request with message and optional session_id

    Returns:
        ChatResponse with agent response and tool call results
    """
    try:
        # Get or create session
        session = await get_or_create_session(request.session_id)

        # Get agent loop
        agent = get_agent_loop()

        # Create audit entry
        audit_logger = await get_audit_logger()
        audit_entry = AuditEntry(
            session_id=session.session_id,
            action_type=ActionType.CHAT,
            action_name="chat_message",
            input_text=request.message,
        )

        # Add user message to history
        session.messages.append({
            "role": "user",
            "content": request.message,
            "timestamp": datetime.now().isoformat(),
        })

        # Process through agent
        logger.info(f"Processing message for session {session.session_id}: {request.message[:100]}...")

        start_time = datetime.now()
        response_text, tool_calls = await agent.process_with_tools(request.message, session)
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        # Update audit entry with results
        audit_entry.output_text = response_text
        audit_entry.total_processing_time_ms = processing_time

        # Add tool call information to audit
        if tool_calls:
            for tool_call in tool_calls:
                data_accessed = []
                if hasattr(tool_call, 'tool_name') and tool_call.tool_name == 'clickhouse_query':
                    data_accessed.append(DataAccessed(
                        source="clickhouse",
                        query_type="read"
                    ))

                # Update audit entry with tool call details
                await audit_logger.log(AuditEntry(
                    session_id=session.session_id,
                    action_type=ActionType.TOOL_CALL,
                    action_name="tool_execution",
                    input_text=request.message,
                    tool_name=tool_call.get('tool_name') if isinstance(tool_call, dict) else getattr(tool_call, 'tool_name', None),
                    tool_arguments=tool_call.get('arguments') if isinstance(tool_call, dict) else getattr(tool_call, 'arguments', None),
                    tool_success=tool_call.get('success', True) if isinstance(tool_call, dict) else getattr(tool_call, 'success', True),
                    data_accessed=data_accessed,
                    parent_audit_id=audit_entry.audit_id,
                ))

        # Log the main chat entry
        await audit_logger.log(audit_entry)

        # Add assistant response to history
        session.messages.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
        })

        # Track tool calls in session
        if tool_calls:
            session.tool_call_history.extend(tool_calls)

        # Build response
        return ChatResponse(
            response=response_text,
            session_id=session.session_id,
            tool_calls=tool_calls or [],
            metadata={
                "message_count": len(session.messages),
                "tool_call_count": len(tool_calls) if tool_calls else 0,
                "audit_id": audit_entry.audit_id,
            },
        )

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    except Exception as e:
        logger.error(f"Chat processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@router.get("/stream")
async def chat_stream(
    message: str = Query(..., description="User message"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    include_tool_calls: bool = Query(True, description="Include tool call events"),
) -> StreamingResponse:
    """
    Server-Sent Events (SSE) streaming chat endpoint.

    Streams tokens and tool call events in real-time.

    Event types:
    - token: Single response token
    - tool_call: Tool being executed
    - error: Error occurred
    - done: Stream complete

    Args:
        message: User message
        session_id: Optional session ID
        include_tool_calls: Whether to stream tool execution events

    Returns:
        StreamingResponse with SSE events
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        try:
            # Get or create session
            session = await get_or_create_session(session_id)

            # Get agent loop
            agent = get_agent_loop()

            # Add user message to history
            session.messages.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.now().isoformat(),
            })

            # Send session ID first
            yield _format_sse({
                "type": "session_start",
                "session_id": session.session_id,
            })

            # Process through agent with streaming
            tool_calls = []

            async for chunk in agent.process_stream(message, session):
                if chunk["type"] == "token":
                    yield _format_sse(ChatStreamChunk(
                        type="token",
                        content=chunk["content"],
                        session_id=session.session_id,
                    ).dict())

                elif chunk["type"] == "tool_call" and include_tool_calls:
                    tool_calls.append(chunk["data"])
                    yield _format_sse(ChatStreamChunk(
                        type="tool_call",
                        tool_name=chunk["data"]["tool_name"],
                        tool_result=chunk["data"],
                        session_id=session.session_id,
                    ).dict())

                elif chunk["type"] == "error":
                    yield _format_sse(ChatStreamChunk(
                        type="error",
                        error=chunk["error"],
                        session_id=session.session_id,
                    ).dict())

                elif chunk["type"] == "done":
                    # Add to session history
                    if chunk.get("response"):
                        session.messages.append({
                            "role": "assistant",
                            "content": chunk["response"],
                            "timestamp": datetime.now().isoformat(),
                        })

                    # Track tool calls
                    if tool_calls:
                        session.tool_call_history.extend(tool_calls)

                    # Send done event
                    yield _format_sse(ChatStreamChunk(
                        type="done",
                        session_id=session.session_id,
                        content=chunk.get("response", ""),
                    ).dict())

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield _format_sse(ChatStreamChunk(
                type="error",
                error=str(e),
                session_id=session_id or "unknown",
            ).dict())

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


def _format_sse(data: dict) -> str:
    """Format data as Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


@router.get("/history/{session_id}")
async def get_history(session_id: str) -> SessionContext:
    """
    Get conversation history for a session.

    Args:
        session_id: Session ID

    Returns:
        SessionContext with full conversation history
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    return _sessions[session_id]


@router.delete("/session/{session_id}")
async def delete_session(session_id: str) -> Dict[str, str]:
    """
    Delete a session and clear its history.

    Args:
        session_id: Session ID to delete

    Returns:
        Confirmation message
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    async with _session_lock:
        del _sessions[session_id]

    logger.info(f"Deleted session: {session_id}")
    return {"message": f"Session {session_id} deleted"}


@router.get("/sessions")
async def list_sessions() -> Dict[str, List[Dict[str, Any]]]:
    """
    List all active sessions.

    Returns:
        Dictionary with session information
    """
    sessions = []

    for session in _sessions.values():
        sessions.append({
            "session_id": session.session_id,
            "message_count": len(session.messages),
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "tool_call_count": len(session.tool_call_history),
        })

    return {
        "sessions": sessions,
        "total_count": len(sessions),
    }


@router.post("/sessions/cleanup")
async def cleanup_sessions(
    max_age_minutes: int = Query(60, description="Maximum session age in minutes")
) -> Dict[str, int]:
    """
    Manually trigger cleanup of old sessions.

    Args:
        max_age_minutes: Delete sessions inactive for this long

    Returns:
        Count of cleaned up sessions
    """
    before_count = len(_sessions)
    await cleanup_old_sessions(max_age_minutes)
    after_count = len(_sessions)

    cleaned = before_count - after_count

    return {
        "cleaned_count": cleaned,
        "remaining_count": after_count,
    }


# Health check for chat service
@router.get("/health")
async def chat_health() -> Dict[str, Any]:
    """Health check for chat service."""
    return {
        "status": "healthy",
        "active_sessions": len(_sessions),
        "agent_ready": _agent_loop is not None,
        "timestamp": datetime.now().isoformat(),
    }


# Background task for periodic cleanup
async def start_cleanup_task(interval_minutes: int = 10):
    """Start background cleanup task."""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        await cleanup_old_sessions()
        logger.info("Session cleanup completed")
