"""
ClickHouse Configuration Module

Load settings from environment variables for ClickHouse Cloud connection.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ClickHouseConfig:
    """ClickHouse Cloud connection configuration."""

    # Get these from ClickHouse Cloud dashboard
    host: str = os.getenv("CLICKHOUSE_HOST", "")
    port: int = int(os.getenv("CLICKHOUSE_PORT", "8443"))
    username: str = os.getenv("CLICKHOUSE_USERNAME", "default")
    password: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    database: str = os.getenv("CLICKHOUSE_DATABASE", "default")

    # Connection settings
    secure: bool = True  # Use HTTPS for ClickHouse Cloud
    verify: bool = True  # Verify SSL certificate
    connect_timeout: int = 10
    send_receive_timeout: int = 300

    def __post_init__(self):
        """Validate required fields."""
        if not self.host:
            raise ValueError(
                "CLICKHOUSE_HOST is required! "
                "Set it in your .env file or environment variables."
            )
        if not self.password:
            raise ValueError(
                "CLICKHOUSE_PASSWORD is required! "
                "Set it in your .env file or environment variables."
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


# Global config instance
config = ClickHouseConfig()
