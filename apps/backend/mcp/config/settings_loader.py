"""Settings Loader for RAG MCP Server.

All values are sourced from the central :mod:`config.settings` model so this
file remains consistent with the rest of the backend.
"""

from pathlib import Path

from config.settings import get_settings

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"


def get_ollama_url(service: str) -> str:
    """Get Ollama service URL."""
    settings = get_settings()
    if service == "embeddings":
        return settings.resolved_ollama_embed_url
    if service == "chat":
        return settings.resolved_ollama_chat_url
    if service == "generate":
        return settings.resolved_ollama_generate_url
    return settings.ollama_base_url


def get_model(purpose: str) -> str:
    """Get model name for a purpose."""
    settings = get_settings()
    if purpose == "embedding":
        return settings.embed_model
    if purpose == "semantic_chunking":
        return settings.rag_llm_model
    if purpose == "image_captioning":
        return settings.vision_model
    return settings.rag_llm_model


def get_timeout() -> int:
    """Get timeout in seconds."""
    return get_settings().ollama_timeout


def build_settings() -> dict:
    """Build the default RAG settings block."""
    settings = get_settings()
    return {
        "rag": {
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "max_chunk_length": settings.max_chunk_length,
            "top_k": settings.top_k,
        }
    }


# Default settings (module-level, resolved from the central Settings model)
settings = build_settings()
