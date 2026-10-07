"""ClickHouse configuration.

Values are sourced from the central :mod:`config.settings` model. Validation is
performed lazily (via :meth:`ClickHouseConfig.validate`) rather than at import
time so that importing modules does not require a live datasource.
"""

from dataclasses import dataclass, field
from typing import Optional

from config.settings import get_settings


def _default_clickhouse_secure() -> bool:
    """Use TLS by default on common ClickHouse secure HTTP ports."""
    settings = get_settings()
    if settings.clickhouse_secure is not None:
        return settings.clickhouse_secure
    return settings.clickhouse_port in {443, 8443}


@dataclass
class ClickHouseConfig:
    """ClickHouse connection configuration."""

    host: str = field(default_factory=lambda: get_settings().clickhouse_host)
    port: int = field(default_factory=lambda: get_settings().clickhouse_port)
    username: str = field(default_factory=lambda: get_settings().clickhouse_username)
    password: str = field(default_factory=lambda: get_settings().clickhouse_password)
    database: str = field(default_factory=lambda: get_settings().clickhouse_database)

    # Connection settings
    secure: bool = field(
        default_factory=lambda: _default_clickhouse_secure()
    )
    # Local ClickHouse defaults to HTTP; cloud TLS ports are secure by default.
    verify: bool = True  # Verify SSL certificate
    connect_timeout: int = 10
    send_receive_timeout: int = 300

    def validate(self) -> None:
        """Validate required fields, raising a clear error when unset."""
        missing = []
        if not self.host:
            missing.append("CLICKHOUSE_HOST")
        if self.secure and not self.password:
            missing.append("CLICKHOUSE_PASSWORD")
        if missing:
            raise ValueError(
                "ClickHouse is not configured. Missing: "
                + ", ".join(missing)
                + ". Set them in your .env file or environment variables."
            )

    @property
    def connection_url(self) -> str:
        """Generate connection URL string."""
        return f"{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    def to_client_kwargs(self) -> dict:
        """Convert to keyword arguments for clickhouse_connect.get_client()."""
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "database": self.database,
            "secure": self.secure,
            "verify": self.verify,
            "connect_timeout": self.connect_timeout,
            "send_receive_timeout": self.send_receive_timeout,
        }


_config: Optional[ClickHouseConfig] = None


def get_clickhouse_config() -> ClickHouseConfig:
    """Return the process-wide ClickHouse config, built lazily."""
    global _config
    if _config is None:
        _config = ClickHouseConfig()
    return _config


# Backwards-compatible attribute: historically ``from .config import config``.
class _LazyConfig:
    """Lazy proxy so ``config.host`` works without importing eager env values."""

    def __getattr__(self, item: str):
        return getattr(get_clickhouse_config(), item)


config = _LazyConfig()
