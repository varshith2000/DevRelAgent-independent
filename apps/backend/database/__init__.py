"""
Database Package

Provides ClickHouse Cloud connection and utilities.
"""

from .clickhouse_client import (
    ClickHouseClient,
    example_insert,
    example_query,
    example_setup,
    get_clickhouse_client,
)
from .config import ClickHouseConfig, config

__all__ = [
    "ClickHouseClient",
    "get_clickhouse_client",
    "example_setup",
    "example_insert",
    "example_query",
    "config",
    "ClickHouseConfig",
]
