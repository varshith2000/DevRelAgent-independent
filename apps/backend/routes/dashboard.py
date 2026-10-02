"""
Dashboard API Routes — Real-Time Health Monitoring

Provides SSE streaming and REST endpoints for "The Deck" dashboard.
Real-time updates for health alerts, system status, and metrics.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from auth.deps import get_request_context
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from guardrails.approval_guard import get_approval_guard
from scheduler import get_health_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_request_context)]
)


# Global SSE queues for streaming
_alert_streams: List[asyncio.Queue] = []


def _format_sse(data: dict) -> str:
    """Format data as Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


@router.get("/stream")
async def dashboard_stream():
    """
    SSE streaming endpoint for real-time dashboard updates.

    Emits events for:
    - Health alerts (error spikes, anomalies)
    - System status changes
    - Auto-diagnosis results

    Returns:
        StreamingResponse with SSE events
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for dashboard."""
        # Create queue for this stream
        queue = asyncio.Queue()
        _alert_streams.append(queue)

        try:
            # Send initial connection event
            yield _format_sse({
                "type": "connected",
                "timestamp": datetime.now().isoformat()
            })

            # Send current system status
            health_scheduler = get_health_scheduler()
            if health_scheduler:
                status = health_scheduler.get_service_status()
                yield _format_sse({
                    "type": "system_status",
                    "data": status
                })

            # Stream events
            while True:
                try:
                    # Wait for events (with timeout to keep connection alive)
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield _format_sse(event)

                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield _format_sse({
                        "type": "ping",
                        "timestamp": datetime.now().isoformat()
                    })

        except asyncio.CancelledError:
            logger.info("Dashboard stream cancelled")
        except Exception as e:
            logger.error(f"Dashboard stream error: {e}")
            yield _format_sse({
                "type": "error",
                "error": str(e)
            })
        finally:
            # Clean up queue
            if queue in _alert_streams:
                _alert_streams.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/status")
async def get_system_status():
    """
    Get current system status for all services.

    Returns:
        Dictionary mapping service names to status (green/yellow/red)
    """
    health_scheduler = get_health_scheduler()

    if not health_scheduler:
        return {
            "services": {},
            "message": "Health scheduler not initialized"
        }

    status = health_scheduler.get_service_status()

    return {
        "services": status,
        "total": len(status),
        "healthy": sum(1 for s in status.values() if s == "green"),
        "warning": sum(1 for s in status.values() if s == "yellow"),
        "critical": sum(1 for s in status.values() if s == "red"),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of alerts"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    type: Optional[str] = Query(None, description="Filter by alert type")
):
    """
    Get alert history.

    Args:
        limit: Maximum number of alerts to return
        severity: Optional filter by severity (critical, warning, info)
        type: Optional filter by type (error_spike, health_check, anomaly)

    Returns:
        List of alert dictionaries
    """
    health_scheduler = get_health_scheduler()

    if not health_scheduler:
        return {
            "alerts": [],
            "total": 0,
            "message": "Health scheduler not initialized"
        }

    # Get alert history
    alerts = health_scheduler.get_alert_history(limit=limit * 2)  # Get more for filtering

    # Apply filters
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]

    if type:
        alerts = [a for a in alerts if a.get("type") == type]

    # Limit results
    alerts = alerts[:limit]

    return {
        "alerts": alerts,
        "total": len(alerts),
        "filters": {"severity": severity, "type": type}
    }


@router.get("/summary")
async def get_dashboard_summary():
    """
    Get dashboard summary with key metrics.

    Returns:
        Summary with alert counts, service status, and recent activity
    """
    health_scheduler = get_health_scheduler()
    approval_guard = get_approval_guard()

    # Get service status
    services = {}
    service_counts = {"green": 0, "yellow": 0, "red": 0, "unknown": 0}

    if health_scheduler:
        services = health_scheduler.get_service_status()
        for status in services.values():
            if status in service_counts:
                service_counts[status] += 1
            else:
                service_counts["unknown"] += 1

    # Get recent alerts
    recent_alerts = []
    if health_scheduler:
        recent_alerts = health_scheduler.get_alert_history(limit=10)

    # Get pending approvals
    pending_approvals = 0
    if approval_guard:
        pending_approvals = len(approval_guard.list_pending_approvals())

    return {
        "timestamp": datetime.now().isoformat(),
        "services": {
            "status": services,
            "counts": service_counts,
            "total": len(services)
        },
        "alerts": {
            "recent_count": len(recent_alerts),
            "critical_count": sum(1 for a in recent_alerts if a.get("severity") == "critical"),
            "recent": recent_alerts[:5]
        },
        "approvals": {
            "pending": pending_approvals
        }
    }


@router.get("/health")
async def dashboard_health():
    """
    Health check for dashboard services.

    Returns:
        Status of dashboard components
    """
    health_scheduler = get_health_scheduler()

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "scheduler": health_scheduler is not None,
            "alert_streams": len(_alert_streams),
            "approvals": get_approval_guard() is not None
        }
    }


async def emit_dashboard_alert(event: Dict[str, Any]):
    """
    Emit alert to all connected dashboard streams.

    Called by health scheduler to broadcast alerts.

    Args:
        event: Alert event data to emit
    """
    if not _alert_streams:
        return

    for queue in _alert_streams:
        try:
            await queue.put(event)
        except Exception as e:
            logger.error(f"Failed to emit alert to stream: {e}")


def get_alert_stream_count() -> int:
    """
    Get number of active dashboard streams.

    Returns:
        Number of connected SSE streams
    """
    return len(_alert_streams)


@router.post("/test-alert")
async def create_test_alert():
    """
    Create a test alert for debugging the dashboard.

    Returns:
        Success status
    """
    test_alert = {
        "type": "alert",
        "data": {
            "id": f"test-{datetime.now().timestamp()}",
            "type": "error_spike",
            "severity": "warning",
            "service": "test-service",
            "message": "This is a test alert to verify dashboard connectivity",
            "error_rate": 7.5,
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "test": True,
                "diagnosis": "Test diagnosis - no actual issue detected"
            }
        }
    }

    # Emit to all connected streams
    await emit_dashboard_alert(test_alert)

    return {
        "status": "success",
        "message": "Test alert created",
        "active_streams": len(_alert_streams),
        "alert": test_alert["data"]
    }


@router.get("/streams")
async def get_active_streams():
    """
    Get number of active SSE streams.

    Returns:
        Number of connected streams
    """
    return {
        "active_streams": len(_alert_streams),
        "streams": [f"stream_{i}" for i in range(len(_alert_streams))]
    }
