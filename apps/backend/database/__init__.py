"""
Database Package

Provides ClickHouse Cloud connection and utilities.
"""

from .clickhouse_client import (
    ClickHouseClient,
    get_clickhouse_client,
    example_setup,
    example_insert,
    example_query,
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
