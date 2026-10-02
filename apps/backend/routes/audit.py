"""
Audit Trail API Routes - Production-Grade Audit API

Provides REST API endpoints for querying and managing the audit trail.

Routes:
- GET /audit/recent - Get recent audit entries
- GET /audit/session/{session_id} - Get audit trail for a session
- POST /audit/query - Query audit trail with filters
- GET /audit/summary - Get audit summary statistics
- POST /audit/export - Export audit trail
- GET /audit/export/file/{filename} - Download exported file
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from audit.logger import get_audit_logger
from audit.schemas import AuditEntry, AuditExport, AuditFilter, AuditSummary
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/recent", response_model=List[AuditEntry])
async def get_recent_entries(
    limit: int = Query(50, ge=1, le=500, description="Maximum entries to return"),
) -> List[AuditEntry]:
    """
    Get recent audit entries from the in-memory cache.

    This endpoint provides fast access to the most recent audit entries
    without querying the file storage. Useful for dashboards and real-time monitoring.

    Args:
        limit: Maximum number of entries to return (1-500)

    Returns:
        List of recent audit entries
    """
    try:
        audit_logger = await get_audit_logger()
        entries = await audit_logger.get_recent(limit=limit)

        logger.info(f"Retrieved {len(entries)} recent audit entries")
        return entries

    except Exception as e:
        logger.error(f"Failed to retrieve recent entries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve entries: {str(e)}")


@router.get("/session/{session_id}", response_model=List[AuditEntry])
async def get_session_audit_trail(
    session_id: str,
    limit: int = Query(100, ge=1, le=10000, description="Maximum entries to return"),
) -> List[AuditEntry]:
    """
    Get complete audit trail for a specific session.

    This endpoint retrieves all audit entries associated with a session,
    providing a complete history of actions taken during that session.

    Use cases:
    - Investigating user behavior
    - Debugging session issues
    - Compliance reporting
    - User activity analysis

    Args:
        session_id: Session identifier
        limit: Maximum entries to return (1-10000)

    Returns:
        List of audit entries for the session
    """
    try:
        audit_logger = await get_audit_logger()
        entries = await audit_logger.query_session(session_id=session_id, limit=limit)

        logger.info(f"Retrieved {len(entries)} entries for session {session_id}")
        return entries

    except Exception as e:
        logger.error(f"Failed to retrieve session audit trail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session audit trail: {str(e)}"
        )


@router.post("/query", response_model=List[AuditEntry])
async def query_audit_trail(
    filters: AuditFilter,
) -> List[AuditEntry]:
    """
    Query audit trail with advanced filters.

    This endpoint provides powerful querying capabilities for the audit trail,
    allowing complex filter combinations for comprehensive analysis.

    Use cases:
    - Compliance reporting
    - Security investigations
    - Usage analytics
    - Performance monitoring
    - Error analysis

    Args:
        filters: Query filter criteria

    Returns:
        List of matching audit entries
    """
    try:
        audit_logger = await get_audit_logger()
        entries = await audit_logger.query(filters=filters)

        logger.info(
            f"Query returned {len(entries)} entries with filters: "
            f"action_types={filters.action_types}, "
            f"tool_name={filters.tool_name}, "
            f"start_time={filters.start_time}"
        )
        return entries

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid filters: {str(e)}")

    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/summary", response_model=AuditSummary)
async def get_audit_summary(
    start_time: Optional[str] = Query(
        None,
        description="Start time (ISO format), defaults to 24 hours ago"
    ),
    end_time: Optional[str] = Query(
        None,
        description="End time (ISO format), defaults to now"
    ),
) -> AuditSummary:
    """
    Get audit summary statistics for a time period.

    This endpoint provides aggregated statistics and insights about
    system activity, including:
    - Total entries, sessions, and users
    - Activity by action type and tool
    - Approval and guardrail statistics
    - Data access patterns
    - Performance metrics
    - Error statistics

    Use cases:
    - Executive dashboards
    - Usage reports
    - Performance monitoring
    - Security summaries

    Args:
        start_time: Start of period (ISO format)
        end_time: End of period (ISO format)

    Returns:
        Audit summary with statistics
    """
    try:
        audit_logger = await get_audit_logger()
        summary = await audit_logger.get_summary(start_time=start_time, end_time=end_time)

        logger.info(
            f"Generated summary for period {start_time} to {end_time}: "
            f"{summary.total_entries} entries"
        )
        return summary

    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")


@router.post("/export")
async def export_audit_trail(
    export_config: AuditExport,
) -> Dict[str, str]:
    """
    Export audit trail for a session.

    This endpoint exports the audit trail for a specific session
    in either JSON or CSV format. Exported files are stored on the
    server and can be downloaded using the returned file path.

    Use cases:
    - Compliance reporting
    - Audit trail archiving
    - External analysis
    - Data sharing

    Args:
        export_config: Export configuration

    Returns:
        Download information with file path
    """
    try:
        audit_logger = await get_audit_logger()

        # Generate export
        file_path = await audit_logger.export(export_config)

        # Generate download URL
        filename = os.path.basename(file_path)
        download_url = f"/audit/export/file/{filename}"

        logger.info(f"Exported audit trail for session {export_config.session_id} to {file_path}")

        return {
            "status": "success",
            "session_id": export_config.session_id,
            "format": export_config.format,
            "file_path": file_path,
            "download_url": download_url,
            "filename": filename,
        }

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid export config: {str(e)}")

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/export/file/{filename}")
async def download_export_file(
    filename: str,
) -> FileResponse:
    """
    Download an exported audit trail file.

    Args:
        filename: Name of the exported file

    Returns:
        File download response
    """
    try:
        # Security: Validate filename to prevent directory traversal
        if not filename.startswith("audit_export_"):
            raise HTTPException(status_code=400, detail="Invalid filename")

        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        audit_logger = await get_audit_logger()
        file_path = os.path.join(audit_logger.storage_path, "exports", filename)

        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Export file not found")

        # Determine content type
        if filename.endswith(".json"):
            media_type = "application/json"
        elif filename.endswith(".csv"):
            media_type = "text/csv"
        else:
            media_type = "application/octet-stream"

        logger.info(f"Downloading export file: {filename}")

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to download export file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_session_audit_trail(
    session_id: str,
) -> Dict[str, str]:
    """
    Delete audit trail for a session (requires admin privileges).

    This endpoint should be protected with authentication/authorization
    in production. Only administrators should be able to delete audit entries.

    Args:
        session_id: Session identifier

    Returns:
        Confirmation message
    """
    try:
        audit_logger = await get_audit_logger()

        # In production, implement proper deletion logic
        # For now, just log the request
        logger.warning(f"Delete request for session audit trail: {session_id}")

        return {
            "status": "not_implemented",
            "message": "Audit trail deletion not implemented. Audit entries must be retained for compliance.",
        }

    except Exception as e:
        logger.error(f"Failed to delete session audit trail: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


@router.get("/stats")
async def get_audit_stats() -> Dict[str, Any]:
    """
    Get quick audit statistics for dashboard display.

    Returns lightweight statistics suitable for real-time dashboard updates.

    Returns:
        Quick statistics dictionary
    """
    try:
        audit_logger = await get_audit_logger()

        # Get recent entries for stats
        recent = await audit_logger.get_recent(limit=1000)

        # Calculate quick stats
        stats = {
            "total_recent_entries": len(recent),
            "unique_sessions": len(set(e.session_id for e in recent)),
            "unique_users": len(set(e.user_id for e in recent if e.user_id)),
            "actions_by_type": {},
            "tools_used": {},
            "recent_errors": 0,
            "timestamp": datetime.now().isoformat(),
        }

        # Count by action type
        for entry in recent:
            action_type = entry.action_type.value
            stats["actions_by_type"][action_type] = stats["actions_by_type"].get(action_type, 0) + 1

            if entry.tool_name:
                stats["tools_used"][entry.tool_name] = stats["tools_used"].get(entry.tool_name, 0) + 1

            if entry.error_type:
                stats["recent_errors"] += 1

        logger.debug(f"Generated quick stats: {stats['total_recent_entries']} entries")
        return stats

    except Exception as e:
        logger.error(f"Failed to generate stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate stats: {str(e)}")


@router.get("/health")
async def audit_health() -> Dict[str, Any]:
    """
    Health check for audit system.

    Returns:
        Health status information
    """
    try:
        audit_logger = await get_audit_logger()

        # Count recent entries in cache
        cache_size = len(await audit_logger.get_recent(limit=10000))

        # Check storage directory
        storage_exists = os.path.exists(audit_logger.storage_path)

        # Count audit files
        file_count = 0
        if storage_exists:
            file_count = len([f for f in os.listdir(audit_logger.storage_path) if f.endswith(".jsonl")])

        return {
            "status": "healthy" if storage_exists else "unhealthy",
            "cache_size": cache_size,
            "storage_path": audit_logger.storage_path,
            "storage_exists": storage_exists,
            "audit_file_count": file_count,
            "clickhouse_enabled": audit_logger.enable_clickhouse,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
