"""
Audit Logger - Production-Grade Audit Trail Implementation

Provides comprehensive audit logging with:
- Async file-based storage (ClickHouse integration optional)
- In-memory caching for recent entries
- Query and export capabilities
- Automatic data sanitization
- Performance monitoring
"""

import asyncio
import csv
import io
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import hashlib

from .schemas import (
    AuditEntry,
    AuditFilter,
    AuditExport,
    AuditSummary,
    ActionType,
    ApprovalDecision,
    GuardrailResult,
    DataAccessed,
)

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Production-grade audit logger.

    Features:
    - Complete audit trail for all system interactions
    - Async logging for non-blocking operation
    - File-based storage with optional ClickHouse backup
    - In-memory cache for recent entries
    - Comprehensive query capabilities
    - Export to JSON/CSV
    - Automatic data sanitization
    """

    def __init__(
        self,
        storage_path: str = "data/audit",
        cache_size: int = 1000,
        enable_clickhouse: bool = False,
    ):
        """
        Initialize the audit logger.

        Args:
            storage_path: Directory for audit log files
            cache_size: Maximum number of recent entries to keep in memory
            enable_clickhouse: Whether to enable ClickHouse backup
        """
        self.storage_path = storage_path
        self.cache_size = cache_size
        self.enable_clickhouse = enable_clickhouse

        # Create storage directory
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        # In-memory cache for recent entries
        self._cache: List[AuditEntry] = []
        self._cache_lock = asyncio.Lock()

        # ClickHouse client (lazy initialization)
        self._clickhouse_client = None

        logger.info(f"✅ AuditLogger initialized with storage_path={storage_path}")

    async def log(self, entry: AuditEntry) -> bool:
        """
        Log an audit entry.

        Args:
            entry: Audit entry to log

        Returns:
            True if logging succeeded
        """
        try:
            # Validate entry
            if not entry.session_id:
                logger.error("Audit entry missing session_id")
                return False

            # Sanitize sensitive data
            sanitized_entry = self._sanitize_entry(entry)

            # Add to cache
            async with self._cache_lock:
                self._cache.append(sanitized_entry)
                # Trim cache if needed
                if len(self._cache) > self.cache_size:
                    self._cache = self._cache[-self.cache_size:]

            # Write to file
            await self._write_to_file(sanitized_entry)

            # Optionally write to ClickHouse
            if self.enable_clickhouse:
                await self._write_to_clickhouse(sanitized_entry)

            logger.debug(f"✅ Logged audit entry: {entry.audit_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to log audit entry: {e}")
            return False

    async def query(self, filters: AuditFilter) -> List[AuditEntry]:
        """
        Query audit trail with filters.

        Args:
            filters: Filter criteria

        Returns:
            List of matching audit entries
        """
        try:
            # Start with cache
            results = await self._get_from_cache(filters)

            # If we need more results, check files
            if len(results) < filters.limit:
                file_results = await self._get_from_files(filters)
                # Combine and deduplicate
                all_results = results + file_results
                # Remove duplicates (keep first occurrence)
                seen = {e.audit_id for e in results}
                unique_results = [e for e in all_results if e.audit_id not in seen]
                results = unique_results

            # Apply sorting
            results = self._sort_results(results, filters.sort_by, filters.sort_order)

            # Apply pagination
            start = filters.offset
            end = start + filters.limit
            results = results[start:end]

            return results

        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            return []

    async def query_session(self, session_id: str, limit: int = 100) -> List[AuditEntry]:
        """
        Get all audit entries for a session.

        Args:
            session_id: Session ID
            limit: Maximum entries to return

        Returns:
            List of audit entries for the session
        """
        filters = AuditFilter(session_id=session_id, limit=limit, sort_order="asc")
        return await self.query(filters)

    async def get_recent(self, limit: int = 50) -> List[AuditEntry]:
        """
        Get recent audit entries from cache.

        Args:
            limit: Maximum entries to return

        Returns:
            List of recent audit entries
        """
        async with self._cache_lock:
            return list(self._cache[-limit:])

    async def export(
        self,
        export_config: AuditExport
    ) -> Union[str, Dict[str, Any]]:
        """
        Export audit trail for a session.

        Args:
            export_config: Export configuration

        Returns:
            File path or export data
        """
        try:
            # Get entries for session
            filters = AuditFilter(session_id=export_config.session_id, limit=10000)
            entries = await self.query(filters)

            # Sanitize if requested
            if export_config.sanitize_sensitive_data:
                entries = [self._sanitize_entry(e) for e in entries]

            # Filter based on configuration
            filtered_entries = []
            for entry in entries:
                filtered_entry = entry.model_copy()

                if not export_config.include_metadata:
                    filtered_entry.tags = []
                    filtered_entry.metadata = {}

                if not export_config.include_tool_calls:
                    filtered_entry.tool_name = None
                    filtered_entry.tool_arguments = None
                    filtered_entry.tool_result = None

                if not export_config.include_guardrails:
                    filtered_entry.guardrail_result = None
                    filtered_entry.guardrail_triggered_by = []
                    filtered_entry.guardrail_details = {}

                if not export_config.include_data_access:
                    filtered_entry.data_accessed = []

                filtered_entries.append(filtered_entry)

            # Generate export
            if export_config.format == "json":
                return self._export_json(filtered_entries, export_config.session_id)
            else:  # csv
                return self._export_csv(filtered_entries, export_config.session_id)

        except Exception as e:
            logger.error(f"❌ Export failed: {e}")
            raise

    async def get_summary(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> AuditSummary:
        """
        Generate audit summary for a time period.

        Args:
            start_time: Start time (ISO format)
            end_time: End time (ISO format)

        Returns:
            Audit summary
        """
        try:
            # Default to last 24 hours
            if not start_time:
                start_time = (datetime.now() - timedelta(hours=24)).isoformat()
            if not end_time:
                end_time = datetime.now().isoformat()

            # Query all entries in time range
            filters = AuditFilter(
                start_time=start_time,
                end_time=end_time,
                limit=100000,  # Large limit for summary
            )
            entries = await self.query(filters)

            # Calculate summary statistics
            summary = self._calculate_summary(entries, start_time, end_time)

            return summary

        except Exception as e:
            logger.error(f"❌ Summary generation failed: {e}")
            raise

    async def _write_to_file(self, entry: AuditEntry) -> None:
        """Write audit entry to file."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = os.path.join(self.storage_path, f"audit_{date_str}.jsonl")

        try:
            # Append to file
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.model_dump()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to file {file_path}: {e}")
            raise

    async def _write_to_clickhouse(self, entry: AuditEntry) -> None:
        """Write audit entry to ClickHouse (optional)."""
        if not self.enable_clickhouse:
            return

        try:
            # Lazy load ClickHouse client
            if self._clickhouse_client is None:
                from database.clickhouse_client import get_clickhouse_client
                self._clickhouse_client = get_clickhouse_client()

            # Convert to dict and insert
            data = entry.model_dump()

            # Use async execution
            await self._clickhouse_client.execute(
                "INSERT INTO audit_trail (*) VALUES",
                [data]
            )

            logger.debug(f"✅ Wrote audit entry to ClickHouse: {entry.audit_id}")

        except Exception as e:
            logger.warning(f"Failed to write to ClickHouse: {e}")
            # Don't fail the audit log if ClickHouse is unavailable

    async def _get_from_cache(self, filters: AuditFilter) -> List[AuditEntry]:
        """Get entries from in-memory cache."""
        async with self._cache_lock:
            results = []

            for entry in self._cache:
                if self._matches_filter(entry, filters):
                    results.append(entry)

            return results

    async def _get_from_files(self, filters: AuditFilter) -> List[AuditEntry]:
        """Get entries from file storage."""
        results = []

        try:
            # Determine date range to scan
            start_date = datetime.fromisoformat(filters.start_time) if filters.start_time else datetime.now() - timedelta(days=7)
            end_date = datetime.fromisoformat(filters.end_time) if filters.end_time else datetime.now()

            # Scan audit files
            current_date = start_date.date()
            end_date_only = end_date.date()

            while current_date <= end_date_only:
                file_path = os.path.join(
                    self.storage_path,
                    f"audit_{current_date.strftime('%Y-%m-%d')}.jsonl"
                )

                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                entry_data = json.loads(line.strip())
                                entry = AuditEntry(**entry_data)

                                if self._matches_filter(entry, filters):
                                    results.append(entry)

                                # Stop if we've reached the limit
                                if len(results) >= filters.limit + filters.offset:
                                    break

                            except (json.JSONDecodeError, ValueError) as e:
                                logger.debug(f"Skipping invalid audit entry: {e}")
                                continue

                current_date += timedelta(days=1)

            return results

        except Exception as e:
            logger.error(f"Failed to read from files: {e}")
            return []

    def _matches_filter(self, entry: AuditEntry, filters: AuditFilter) -> bool:
        """Check if entry matches filter criteria."""
        # Time range
        if filters.start_time and entry.timestamp < filters.start_time:
            return False
        if filters.end_time and entry.timestamp > filters.end_time:
            return False

        # Session and user filters
        if filters.session_id and entry.session_id != filters.session_id:
            return False
        if filters.user_id and entry.user_id != filters.user_id:
            return False
        if filters.tenant_id and entry.tenant_id != filters.tenant_id:
            return False
        if filters.correlation_id and entry.correlation_id != filters.correlation_id:
            return False

        # Action filters
        if filters.action_types and entry.action_type not in filters.action_types:
            return False
        if filters.action_name and entry.action_name != filters.action_name:
            return False
        if filters.tool_name and entry.tool_name != filters.tool_name:
            return False

        # Result filters
        if filters.tool_success is not None and entry.tool_success != filters.tool_success:
            return False
        if filters.approval_decision and entry.approval_decision != filters.approval_decision:
            return False
        if filters.guardrail_result and entry.guardrail_result != filters.guardrail_result:
            return False

        # Data source filter
        if filters.data_source:
            has_data_source = any(
                da.source == filters.data_source
                for da in entry.data_accessed or []
            )
            if not has_data_source:
                return False

        # Error filter
        if filters.has_errors is not None:
            has_errors = entry.error_type is not None
            if has_errors != filters.has_errors:
                return False

        # Text search
        if filters.search_text:
            search_lower = filters.search_text.lower()
            text_to_search = (
                (entry.input_text or "") +
                " " +
                (entry.output_text or "")
            ).lower()
            if search_lower not in text_to_search:
                return False

        return True

    def _sort_results(
        self,
        results: List[AuditEntry],
        sort_by: str,
        sort_order: str
    ) -> List[AuditEntry]:
        """Sort results by specified field."""
        reverse = sort_order == "desc"

        if sort_by == "timestamp":
            results.sort(key=lambda e: e.timestamp, reverse=reverse)
        elif sort_by == "action_type":
            results.sort(key=lambda e: e.action_type.value, reverse=reverse)
        elif sort_by == "tool_execution_time_ms":
            results.sort(
                key=lambda e: e.tool_execution_time_ms or 0,
                reverse=reverse
            )

        return results

    def _sanitize_entry(self, entry: AuditEntry) -> AuditEntry:
        """Sanitize sensitive data in audit entry."""
        sanitized = entry.model_copy()

        # Sanitize tool arguments
        if sanitized.tool_arguments:
            sanitized.tool_arguments = self._sanitize_dict(sanitized.tool_arguments)

        # Sanitize tool result
        if sanitized.tool_result:
            sanitized.tool_result = self._sanitize_dict(sanitized.tool_result)

        # Truncate long strings
        if sanitized.input_text and len(sanitized.input_text) > 5000:
            sanitized.input_text = sanitized.input_text[:5000] + "... (truncated)"
        if sanitized.output_text and len(sanitized.output_text) > 10000:
            sanitized.output_text = sanitized.output_text[:10000] + "... (truncated)"

        # Redact sensitive fields
        if sanitized.ip_address:
            # Partially redact IP
            parts = sanitized.ip_address.split('.')
            if len(parts) == 4:
                sanitized.ip_address = f"{parts[0]}.{parts[1]}.***.***"

        return sanitized

    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary values."""
        sanitized = {}
        sensitive_keys = [
            "password", "passwd", "pwd",
            "token", "api_key", "apikey", "api-key",
            "secret", "private_key", "private-key",
            "auth", "credential", "session_token"
        ]

        for key, value in data.items():
            key_lower = key.lower()

            # Check if key is sensitive
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_dict(v) if isinstance(v, dict) else v
                    for v in value
                ]
            elif isinstance(value, str) and len(value) > 2000:
                # Truncate long strings
                sanitized[key] = value[:2000] + "... (truncated)"
            else:
                sanitized[key] = value

        return sanitized

    def _export_json(self, entries: List[AuditEntry], session_id: str) -> str:
        """Export entries as JSON file."""
        export_dir = os.path.join(self.storage_path, "exports")
        Path(export_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audit_export_{session_id}_{timestamp}.json"
        file_path = os.path.join(export_dir, filename)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump([e.model_dump() for e in entries], f, indent=2, default=str)

        logger.info(f"✅ Exported {len(entries)} entries to {file_path}")
        return file_path

    def _export_csv(self, entries: List[AuditEntry], session_id: str) -> str:
        """Export entries as CSV file."""
        export_dir = os.path.join(self.storage_path, "exports")
        Path(export_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audit_export_{session_id}_{timestamp}.csv"
        file_path = os.path.join(export_dir, filename)

        # Flatten entries for CSV
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            if not entries:
                return file_path

            # Get all fields from first entry
            writer = csv.DictWriter(f, fieldnames=[
                "audit_id", "timestamp", "session_id", "user_id",
                "action_type", "action_name", "tool_name",
                "input_text", "output_text",
                "tool_success", "approval_decision",
                "guardrail_result", "error_type", "error_message"
            ])

            writer.writeheader()

            for entry in entries:
                writer.writerow({
                    "audit_id": entry.audit_id,
                    "timestamp": entry.timestamp,
                    "session_id": entry.session_id,
                    "user_id": entry.user_id or "",
                    "action_type": entry.action_type.value,
                    "action_name": entry.action_name or "",
                    "tool_name": entry.tool_name or "",
                    "input_text": (entry.input_text or "")[:1000],
                    "output_text": (entry.output_text or "")[:1000],
                    "tool_success": entry.tool_success if entry.tool_success is not None else "",
                    "approval_decision": entry.approval_decision.value if entry.approval_decision else "",
                    "guardrail_result": entry.guardrail_result.value if entry.guardrail_result else "",
                    "error_type": entry.error_type or "",
                    "error_message": (entry.error_message or "")[:500],
                })

        logger.info(f"✅ Exported {len(entries)} entries to {file_path}")
        return file_path

    def _calculate_summary(
        self,
        entries: List[AuditEntry],
        start_time: str,
        end_time: str
    ) -> AuditSummary:
        """Calculate summary statistics from entries."""
        summary = AuditSummary(
            period_start=start_time,
            period_end=end_time,
            total_entries=len(entries),
        )

        # Track unique sessions and users
        sessions = set()
        users = set()

        # Performance metrics
        response_times = []
        tool_times = []

        for entry in entries:
            # Track unique entities
            sessions.add(entry.session_id)
            if entry.user_id:
                users.add(entry.user_id)

            # Count by action type
            action_type = entry.action_type.value
            summary.by_action_type[action_type] = summary.by_action_type.get(action_type, 0) + 1

            # Count by tool
            if entry.tool_name:
                summary.by_tool[entry.tool_name] = summary.by_tool.get(entry.tool_name, 0) + 1

            # Approval statistics
            if entry.approval_decision:
                summary.approvals_requested += 1
                if entry.approval_decision == ApprovalDecision.APPROVED:
                    summary.approvals_granted += 1
                elif entry.approval_decision == ApprovalDecision.REJECTED:
                    summary.approvals_rejected += 1
                elif entry.approval_decision == ApprovalDecision.PENDING:
                    summary.approvals_pending += 1
                elif entry.approval_decision == ApprovalDecision.TIMEOUT:
                    summary.approvals_timeout += 1

            # Guardrail statistics
            if entry.guardrail_result:
                summary.guardrails_triggered += 1
                if entry.guardrail_result == GuardrailResult.BLOCKED:
                    summary.guardrails_blocked += 1
                elif entry.guardrail_result == GuardrailResult.PASSED:
                    summary.guardrails_passed += 1

            # Data access statistics
            if entry.data_accessed:
                summary.data_access_count += len(entry.data_accessed)
                for da in entry.data_accessed:
                    summary.by_data_source[da.source] = summary.by_data_source.get(da.source, 0) + 1

            # Performance metrics
            if entry.total_processing_time_ms:
                response_times.append(entry.total_processing_time_ms)
            if entry.tool_execution_time_ms:
                tool_times.append(entry.tool_execution_time_ms)

            # Error statistics
            if entry.error_type:
                summary.error_count += 1
                summary.by_error_type[entry.error_type] = summary.by_error_type.get(entry.error_type, 0) + 1

        # Calculate derived metrics
        summary.total_sessions = len(sessions)
        summary.total_users = len(users)

        if response_times:
            summary.avg_response_time_ms = sum(response_times) / len(response_times)

        if tool_times:
            summary.avg_tool_execution_time_ms = sum(tool_times) / len(tool_times)

        if summary.total_entries > 0:
            summary.error_rate = summary.error_count / summary.total_entries

        # Top sessions by activity
        session_activity = {}
        for entry in entries:
            session_activity[entry.session_id] = session_activity.get(entry.session_id, 0) + 1

        summary.top_sessions = [
            {"session_id": sid, "entry_count": count}
            for sid, count in sorted(session_activity.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        return summary


# Global singleton
_audit_logger: Optional[AuditLogger] = None
_logger_lock = asyncio.Lock()


async def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger

    if _audit_logger is None:
        async with _logger_lock:
            if _audit_logger is None:
                # Read from environment
                storage_path = os.getenv("AUDIT_LOG_PATH", "data/audit")
                cache_size = int(os.getenv("AUDIT_CACHE_SIZE", "1000"))
                enable_clickhouse = os.getenv("AUDIT_CLICKHOUSE_ENABLED", "false").lower() == "true"

                _audit_logger = AuditLogger(
                    storage_path=storage_path,
                    cache_size=cache_size,
                    enable_clickhouse=enable_clickhouse,
                )

    return _audit_logger


def set_audit_logger(logger_instance: AuditLogger) -> None:
    """Set a custom audit logger instance (useful for testing)."""
    global _audit_logger
    _audit_logger = logger_instance
