"""
DevRelAgent Backend — FastAPI Entry Point

Health endpoint, CORS, lifespan hooks, and route integration.
"""

import asyncio
import os
import sys
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routes.chat import router as chat_router, start_cleanup_task
from routes.dashboard import router as dashboard_router
from routes.approvals import router as approvals_router
from tools.registry import get_registry
from tools.clickhouse_tool import get_clickhouse_tool
from guardrails.approval_guard import get_approval_guard
from scheduler import HealthCheckScheduler
import os

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("🚀 DevRelAgent API starting...")

    # Initialize tool registry
    registry = get_registry()

    # Initialize SSE queue for dashboard and approvals
    sse_queue = asyncio.Queue()

    # Register KeDB tools
    try:
        from tools.kedb_tool import get_kedb_tool
        kedb_tool = get_kedb_tool()
        logger.info("✅ KeDB tools registered")
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
            category="database_query",
        )
        logger.info("✅ ClickHouse tool registered")

    except Exception as e:
        logger.warning(f"⚠️ ClickHouse tool not available: {e}")

    # Register browser tool
    try:
        from tools.browser_tool import browser_action
        registry.register_manual(
            name="browser_action",
            handler=browser_action,
            description="Perform browser actions with Playwright (requires approval)",
            category="api",
        )
        logger.info("✅ Browser tool registered")
    except Exception as e:
        logger.warning(f"⚠️ Browser tool not available: {e}")

    # Register GitHub tools
    try:
        from tools.github_tool import draft_github_issue, draft_github_pr, search_github_issues

        registry.register_manual(
            name="draft_github_issue",
            handler=draft_github_issue,
            description="Draft a GitHub issue (requires approval)",
            category="api",
        )

        registry.register_manual(
            name="draft_github_pr",
            handler=draft_github_pr,
            description="Create a GitHub PR (requires approval)",
            category="api",
        )

        registry.register_manual(
            name="search_github_issues",
            handler=search_github_issues,
            description="Search GitHub issues (read-only)",
            category="api",
        )

        logger.info("✅ GitHub tools registered")
    except Exception as e:
        logger.warning(f"⚠️ GitHub tools not available: {e}")

    logger.info(f"📦 Tool registry initialized with {len(registry.tool_names)} tools")

    # Initialize ApprovalGuard and connect SSE queue
    try:
        approval_guard = get_approval_guard()
        approval_guard.set_sse_queue(sse_queue)
        logger.info("✅ ApprovalGuard initialized")
    except Exception as e:
        logger.warning(f"⚠️ ApprovalGuard initialization failed: {e}")

    # Initialize Health Check Scheduler
    health_scheduler = None
    try:
        health_check_enabled = os.getenv("HEALTH_CHECK_ENABLED", "false").lower() == "true"

        if health_check_enabled:
            from database.clickhouse_client import get_clickhouse_client

            ch_client = get_clickhouse_client()
            health_scheduler = HealthCheckScheduler(
                clickhouse_client=ch_client,
                tool_registry=registry,
                interval_minutes=int(os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", "5")),
                error_threshold=float(os.getenv("ERROR_SPIKE_THRESHOLD", "5.0"))
            )

            # Connect SSE queue for alerts
            health_scheduler.set_alert_queue(sse_queue)

            # Start scheduler
            health_scheduler.start()
            logger.info("✅ Health check scheduler started")
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
app.include_router(chat_router, tags=["chat"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(approvals_router, tags=["approvals"])


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
            "docs": "/docs",
        },
        "tools": get_registry().list_tool_names(),
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="info",
    )
