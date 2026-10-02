"""
Audit Trail Module - Production-Grade Audit Logging

Provides comprehensive audit trail functionality:
- Event logging for all user interactions
- Tool execution tracking
- Approval decision logging
- Guardrail violation tracking
- Data access monitoring
- Audit query and export capabilities

Usage:
    from audit.logger import get_audit_logger

    logger = get_audit_logger()
    await logger.log_entry(entry)

    # Query audit trail
    entries = await logger.query_session(session_id="abc123")
"""

from .logger import AuditLogger, get_audit_logger
from .schemas import AuditEntry, AuditExport, AuditFilter, AuditSummary

__all__ = [
    "AuditEntry",
    "AuditFilter",
    "AuditExport",
    "AuditSummary",
    "AuditLogger",
    "get_audit_logger",
]
