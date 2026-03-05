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
from tools.registry import get_registry
from tools.clickhouse_tool import get_clickhouse_tool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("🚀 DevRelAgent API starting...")

    # Initialize tool registry
    registry = get_registry()

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

    logger.info(f"📦 Tool registry initialized with {len(registry.tool_names)} tools")

    # Start background tasks
    cleanup_task = asyncio.create_task(start_cleanup_task(interval_minutes=10))

    yield

    # Cleanup
    cleanup_task.cancel()
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
