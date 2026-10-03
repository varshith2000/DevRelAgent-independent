"""Single, typed source of truth for all backend configuration.

Every environment variable the backend consumes is declared here as a typed
field. ``grep -rn "os.getenv" apps/backend`` should only ever match this file.

Usage
-----
    from config.settings import get_settings

    settings = get_settings()
    settings.llm_provider
    settings.grafana_url

Startup validation
------------------
``validate_startup()`` raises a ``ConfigurationError`` listing every missing
required variable, so a misconfigured deployment fails fast and loudly instead
of failing later at request time. ``main.py`` calls it during lifespan startup.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]

# Load .env values (backend-local first, then repo root) into the process
# environment before pydantic-settings reads them. This mirrors the historical
# ``load_dotenv()`` behaviour while keeping a single reader in this module.
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(REPO_ROOT / ".env")

# Which API key each LLM provider requires, as (attribute, env var name).
PROVIDER_KEY_FIELDS: dict[str, Tuple[str, str]] = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "gemini": ("google_api_key", "GOOGLE_API_KEY"),
    "zai": ("z_ai_api_key", "Z_AI_API_KEY"),
    "glm": ("z_ai_api_key", "Z_AI_API_KEY"),
}


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing at startup."""


class Settings(BaseSettings):
    """Typed view of every environment variable used by the backend.

    Field names map to environment variables case-insensitively
    (``llm_provider`` <- ``LLM_PROVIDER``, ``z_ai_api_key`` <- ``Z_AI_API_KEY``).
    Unknown variables are ignored so unrelated shell state cannot break startup.
    """

    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # ── LLM providers ─────────────────────────────────────────────────────
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    z_ai_api_key: Optional[str] = None

    # ── System of record (Phase 1) ────────────────────────────────────────
    # SQLite by default so a fresh clone runs with no infrastructure; point
    # at Postgres (e.g. Supabase) with DATABASE_URL for anything real.
    database_url: str = "sqlite:///./data/devrelagent.db"
    database_echo: bool = False
    # Create missing tables at startup (dev/CI convenience). Turn this off in
    # production and run `alembic upgrade head` instead.
    database_auto_create: bool = True

    # ── Identity ──────────────────────────────────────────────────────────
    # "dev" trusts X-Dev-* headers (local development and tests).
    # "clerk" verifies a real Clerk/OIDC JWT against the JWKS endpoint.
    auth_provider: str = "dev"
    clerk_jwks_url: Optional[str] = None
    clerk_issuer: Optional[str] = None
    clerk_audience: Optional[str] = None
    dev_user_email: str = "dev@localhost"
    dev_user_name: str = "Dev User"
    dev_workspace_slug: str = "dev-workspace"
    # Salt for hashing API keys at rest. Set this in any real deployment.
    api_key_pepper: Optional[str] = None

    # ── Shared session store ──────────────────────────────────────────────
    # "memory" keeps sessions process-local (single worker only).
    # "redis" shares them across replicas.
    session_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_minutes: int = 60

    # ── Human-in-the-loop ─────────────────────────────────────────────────
    # How long an approval request waits for a decision before auto-rejecting.
    approval_timeout_seconds: int = 300

    # ── Health check scheduler ────────────────────────────────────────────
    health_check_enabled: bool = False
    health_check_interval_minutes: int = 5
    error_spike_threshold: float = 5.0

    # ── ClickHouse (primary datasource) ───────────────────────────────────
    clickhouse_host: str = ""
    clickhouse_port: int = 8443
    clickhouse_username: str = "default"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "default"
    clickhouse_secure: bool = False

    # ── Grafana ───────────────────────────────────────────────────────────
    grafana_url: str = "http://localhost:3000"
    grafana_api_token: str = ""
    grafana_default_datasource: str = "ClickHouse"

    # ── GitHub ────────────────────────────────────────────────────────────
    github_token: Optional[str] = None

    # ── Browser automation ────────────────────────────────────────────────
    allowed_urls: str = "localhost,127.0.0.1"

    # ── Ollama / embeddings / RAG ─────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_url: Optional[str] = None
    ollama_chat_url: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_timeout: int = 30
    embed_model: str = "nomic-embed-text"
    rag_llm_model: str = "llama3.2"
    vision_model: str = "llava"

    # ── Chunking / retrieval ──────────────────────────────────────────────
    chunk_size: int = 256
    chunk_overlap: int = 40
    max_chunk_length: int = 1200
    top_k: int = 5

    # ── Audit ─────────────────────────────────────────────────────────────
    audit_log_path: str = "data/audit"
    audit_cache_size: int = 1000
    audit_clickhouse_enabled: bool = False
    tenant_config_path: str = "data/tenants"

    # ── Storage paths ─────────────────────────────────────────────────────
    investigation_storage_path: str = "data/investigations"
    learning_memory_path: str = "data/learning_memory.json"
    dashboard_storage_path: str = "data/dashboards"

    # ── Deployment defaults for generated env config ──────────────────────
    database_host: str = "localhost"
    database_port: str = "5432"
    database_name: Optional[str] = None
    database_user: str = "user"
    database_ssl_mode: Optional[str] = None
    cache_host: str = "localhost"
    cache_port: str = "6379"
    cache_db: str = "0"

    # ── Derived helpers ───────────────────────────────────────────────────
    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def allowed_urls_list(self) -> List[str]:
        """Allowed browser URLs as a cleaned list."""
        return [url.strip() for url in self.allowed_urls.split(",") if url.strip()]

    @property
    def resolved_ollama_embed_url(self) -> str:
        return self.ollama_embed_url or f"{self.ollama_base_url}/api/embeddings"

    @property
    def resolved_ollama_chat_url(self) -> str:
        return self.ollama_chat_url or f"{self.ollama_base_url}/v1/chat/completions"

    @property
    def resolved_ollama_generate_url(self) -> str:
        return self.ollama_url or f"{self.ollama_base_url}/api/generate"

    # ── Validation ────────────────────────────────────────────────────────
    def missing_required(self) -> List[str]:
        """Return env var names that are required but unset."""
        missing: List[str] = []

        provider = (self.llm_provider or "anthropic").lower()
        key_field = PROVIDER_KEY_FIELDS.get(provider)
        if key_field is not None:
            attr, env_name = key_field
            if not getattr(self, attr, None):
                missing.append(env_name)

        if self.health_check_enabled and not self.clickhouse_host:
            missing.append("CLICKHOUSE_HOST")

        if (self.auth_provider or "dev").lower() == "clerk":
            if not (self.clerk_jwks_url or self.clerk_issuer):
                missing.append("CLERK_JWKS_URL")
            if not self.clerk_issuer:
                missing.append("CLERK_ISSUER")

        return missing

    def validate_startup(self) -> None:
        """Fail fast with a clear, actionable list of missing variables."""
        missing = self.missing_required()
        if missing:
            raise ConfigurationError(
                "Missing required configuration: "
                + ", ".join(missing)
                + ". Set them in apps/backend/.env (see .env.example) or the "
                "process environment before starting the backend."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests after changing the env)."""
    get_settings.cache_clear()


__all__ = [
    "Settings",
    "ConfigurationError",
    "get_settings",
    "reset_settings_cache",
    "PROVIDER_KEY_FIELDS",
    "BACKEND_ROOT",
    "REPO_ROOT",
]
