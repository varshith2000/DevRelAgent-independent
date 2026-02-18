"""
DevRelAgent Backend — FastAPI Entry Point

Health endpoint, CORS, and lifespan hooks.
"""

import os
import sys
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    print("🚀 DevRelAgent API starting...")
    yield
    print("🛑 DevRelAgent API shutting down...")


app = FastAPI(
    title="DevRelAgent",
    description="24/7 AI-Powered Developer Relations Agent",
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ──────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


# ─── Future route imports will go here ───────────────
# from agent.loop import router as agent_router
# app.include_router(agent_router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
