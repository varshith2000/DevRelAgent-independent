"""
Settings Loader for RAG MCP Server

Minimal configuration - loads from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"


def get_ollama_url(service: str) -> str:
    """Get Ollama service URL."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    if service == "embeddings":
        return os.getenv("OLLAMA_EMBED_URL", f"{base_url}/api/embeddings")
    elif service == "chat":
        return os.getenv("OLLAMA_CHAT_URL", f"{base_url}/v1/chat/completions")
    elif service == "generate":
        return os.getenv("OLLAMA_URL", f"{base_url}/api/generate")
    return base_url


def get_model(purpose: str) -> str:
    """Get model name for a purpose."""
    if purpose == "embedding":
        return os.getenv("EMBED_MODEL", "nomic-embed-text")
    elif purpose == "semantic_chunking":
        return os.getenv("RAG_LLM_MODEL", "llama3.2")
    elif purpose == "image_captioning":
        return os.getenv("VISION_MODEL", "llava")
    return os.getenv("LLM_MODEL", "llama3.2")


def get_timeout() -> int:
    """Get timeout in seconds."""
    return int(os.getenv("OLLAMA_TIMEOUT", "30"))


# Default settings
settings = {
    "rag": {
        "chunk_size": int(os.getenv("CHUNK_SIZE", "256")),
        "chunk_overlap": int(os.getenv("CHUNK_OVERLAP", "40")),
        "max_chunk_length": int(os.getenv("MAX_CHUNK_LENGTH", "1200")),
        "top_k": int(os.getenv("TOP_K", "5")),
    }
}
