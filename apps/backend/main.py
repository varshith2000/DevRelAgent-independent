"""
DevRelAgent Backend — FastAPI Entry Point

Health endpoint, CORS, lifespan hooks, and route integration.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import get_settings
from db.session import init_db
from guardrails.approval_guard import get_approval_guard
from observability.logging import configure_logging
from routes.approvals import router as approvals_router
from routes.audit import router as audit_router
from routes.chat import router as chat_router
from routes.chat import start_cleanup_task
from routes.dashboard import router as dashboard_router
from routes.identity import router as identity_router
from routes.workspaces import router as workspaces_router
from scheduler import HealthCheckScheduler
from tools.clickhouse_tool import get_clickhouse_tool
from tools.registry import ToolCategory, get_registry

settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("🚀 DevRelAgent API starting...")

    # Fail fast with a clear list of any missing required configuration.
    settings.validate_startup()

    # Ensure the system-of-record schema exists (dev/CI). Production should run
    # `alembic upgrade head` with DATABASE_AUTO_CREATE=false.
    if settings.database_auto_create:
        try:
            init_db()
            logger.info("[OK] System-of-record schema ready")
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed: {e}")

    # Initialize tool registry
    registry = get_registry()

    # Initialize SSE queue for dashboard and approvals
    sse_queue = asyncio.Queue()

    # Register KeDB tools
    try:
        from tools.kedb_tool import get_kedb_tool
        kedb_tool = get_kedb_tool()
        logger.info("[OK] KeDB tools registered")
    except Exception as e:
        logger.warning(f"⚠️ KeDB tools not available: {e}")

    # Register ClickHouse tool
    try:
        ch_tool = get_clickhouse_tool()
        from tools.clickhouse_tool import ClickHouseTool

        # Manual registration for ClickHouse tool
        registry.register_manual(
            name="clickhouse_query",
            handler=lambda natural_query: ch_tool.format_result(
                ch_tool.query_nl(natural_query)
            ),
            description="Query ClickHouse database with natural language",
            parameters={
                "natural_query": {
                    "type": "string",
                    "description": "Natural language query for the database",
                }
            },
            category=ToolCategory.DATABASE_QUERY,
        )
        logger.info("[OK] ClickHouse tool registered")

    except Exception as e:
        logger.warning(f"⚠️ ClickHouse tool not available: {e}")

    # Register browser tool
    try:
        from tools.browser_tool import browser_action
        registry.register_manual(
            name="browser_action",
            handler=browser_action,
            description="Perform browser actions with Playwright (requires approval)",
            category=ToolCategory.API,
        )
        logger.info("[OK] Browser tool registered")
    except Exception as e:
        logger.warning(f"⚠️ Browser tool not available: {e}")

    # Import Grafana tools (auto-registered via @tool decorator)
    try:
        from tools import grafana_tool
        logger.info("[OK] Grafana tools registered")
    except Exception as e:
        logger.warning(f"⚠️ Grafana tools not available: {e}")

    # Import observability tools (auto-registered via @tool decorator)
    try:
        from tools import observability_tool
        logger.info("[OK] Observability tools registered")
    except Exception as e:
        logger.warning(f"⚠️ Observability tools not available: {e}")

    # Import gap detection tools (auto-registered via @tool decorator)
    try:
        from tools import gap_detection_tool
        logger.info("[OK] Gap detection tools registered")
    except Exception as e:
        logger.warning(f"⚠️ Gap detection tools not available: {e}")

    # Import automation tools (auto-registered via @tool decorator)
    try:
        from tools import automation_tool
        logger.info("[OK] Automation tools registered")
    except Exception as e:
        logger.warning(f"⚠️ Automation tools not available: {e}")

    # Import dashboard tools (auto-registered via @tool decorator)
    try:
        from tools import dashboard_tool
        logger.info("[OK] Dashboard tools registered")
    except Exception as e:
        logger.warning(f"⚠️ Dashboard tools not available: {e}")

    # Register GitHub tools
    try:
        from tools.github_tool import draft_github_issue, draft_github_pr, search_github_issues

        registry.register_manual(
            name="draft_github_issue",
            handler=draft_github_issue,
            description="Draft a GitHub issue (requires approval)",
            category=ToolCategory.API,
        )

        registry.register_manual(
            name="draft_github_pr",
            handler=draft_github_pr,
            description="Create a GitHub PR (requires approval)",
            category=ToolCategory.API,
        )

        registry.register_manual(
            name="search_github_issues",
            handler=search_github_issues,
            description="Search GitHub issues (read-only)",
            category=ToolCategory.API,
        )

        logger.info("[OK] GitHub tools registered")
    except Exception as e:
        logger.warning(f"⚠️ GitHub tools not available: {e}")

    logger.info(f"📦 Tool registry initialized with {len(registry.tool_names)} tools")

    # Initialize ApprovalGuard and connect SSE queue
    try:
        approval_guard = get_approval_guard()
        approval_guard.set_sse_queue(sse_queue)
        logger.info("[OK] ApprovalGuard initialized")
    except Exception as e:
        logger.warning(f"⚠️ ApprovalGuard initialization failed: {e}")

    # Initialize Health Check Scheduler
    health_scheduler = None
    try:
        health_check_enabled = settings.health_check_enabled

        if health_check_enabled:
            from database.clickhouse_client import get_clickhouse_client

            ch_client = get_clickhouse_client()
            health_scheduler = HealthCheckScheduler(
                clickhouse_client=ch_client,
                tool_registry=registry,
                interval_minutes=settings.health_check_interval_minutes,
                error_threshold=settings.error_spike_threshold
            )

            # Connect SSE queue for alerts
            health_scheduler.set_alert_queue(sse_queue)

            # Start scheduler
            health_scheduler.start()
            logger.info("[OK] Health check scheduler started")
        else:
            logger.info("ℹ️ Health check scheduler disabled (HEALTH_CHECK_ENABLED=false)")

    except Exception as e:
        logger.warning(f"⚠️ Health check scheduler failed: {e}")

    # Start background tasks
    cleanup_task = asyncio.create_task(start_cleanup_task(interval_minutes=10))

    yield

    # Cleanup
    cleanup_task.cancel()

    if health_scheduler:
        health_scheduler.stop()

    logger.info("🛑 DevRelAgent API shutting down...")


app = FastAPI(
    title="DevRelAgent",
    description="24/7 AI-Powered Developer Relations Agent with ClickHouse integration",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # Next.js
        "http://localhost:5173",    # Vite
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ──────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    registry = get_registry()
    return {
        "status": "ok",
        "version": "0.1.0",
        "tools": {
            "total": len(registry.tool_names),
            "enabled": len([t for t in registry.list_tools() if t.metadata.enabled]),
            "names": registry.list_tool_names(),
        },
    }


# ─── Route Registration ────────────────────────────────
app.include_router(identity_router)
app.include_router(workspaces_router)
app.include_router(chat_router, tags=["chat"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(approvals_router, tags=["approvals"])
app.include_router(audit_router, tags=["audit"])


# ─── Root ──────────────────────────────────────────────
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "DevRelAgent API",
        "version": "0.1.0",
        "description": "24/7 AI-Powered Developer Relations Agent",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "chat_stream": "/chat/stream",
            "dashboard": "/dashboard",
            "dashboard_stream": "/dashboard/stream",
            "approvals": "/approvals",
            "audit": "/audit",
            "audit_recent": "/audit/recent",
            "audit_session": "/audit/session/{session_id}",
            "audit_query": "/audit/query",
            "audit_summary": "/audit/summary",
            "audit_export": "/audit/export",
            "docs": "/docs",
        },
        "tools": get_registry().list_tool_names(),
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
