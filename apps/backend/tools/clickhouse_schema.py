"""
ClickHouse Schema Explorer — Auto-discover tables, columns, and metadata

Provides schema introspection capabilities for ClickHouse databases.
Caches schema information for performance and includes sample data fetching.

Usage:
    from tools.clickhouse_schema import ClickHouseSchemaExplorer

    explorer = ClickHouseSchemaExplorer()
    tables = explorer.list_tables()
    schema = explorer.get_table_schema("my_table")
    description = explorer.describe_table("my_table")
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database import get_clickhouse_client

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    """Information about a table column."""
    name: str
    type: str
    default_type: Optional[str] = None
    default_expression: Optional[str] = None
    comment: Optional[str] = None
    is_nullable: bool = False
    is_partition_key: bool = False
    is_sorting_key: bool = False
    is_primary_key: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "default_type": self.default_type,
            "default_expression": self.default_expression,
            "comment": self.comment,
            "is_nullable": self.is_nullable,
            "is_partition_key": self.is_partition_key,
            "is_sorting_key": self.is_sorting_key,
            "is_primary_key": self.is_primary_key,
        }


@dataclass
class TableInfo:
    """Information about a table."""
    database: str
    name: str
    engine: str
    total_rows: Optional[int] = None
    total_bytes: Optional[int] = None
    partition_key: Optional[str] = None
    sorting_key: Optional[str] = None
    primary_key: Optional[str] = None
    create_table_query: Optional[str] = None
    columns: List[ColumnInfo] = field(default_factory=list)
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "database": self.database,
            "name": self.name,
            "full_name": f"{self.database}.{self.name}",
            "engine": self.engine,
            "total_rows": self.total_rows,
            "total_bytes": self.total_bytes,
            "partition_key": self.partition_key,
            "sorting_key": self.sorting_key,
            "primary_key": self.primary_key,
            "create_table_query": self.create_table_query,
            "columns": [col.to_dict() for col in self.columns],
            "sample_data": self.sample_data,
            "column_count": len(self.columns),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class ClickHouseSchemaExplorer:
    """
    ClickHouse schema explorer with caching.

    Features:
    - List databases and tables
    - Get detailed table schema
    - Fetch sample data
    - Generate table descriptions for LLM prompts
    - Schema caching with TTL
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 300,  # 5 minutes
        sample_rows: int = 5,
        include_system_tables: bool = False,
    ):
        """
        Initialize schema explorer.

        Args:
            cache_ttl_seconds: How long to cache schema info
            sample_rows: Number of sample rows to fetch
            include_system_tables: Include system tables in listings
        """
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.sample_rows = sample_rows
        self.include_system_tables = include_system_tables

        self._schema_cache: Dict[str, tuple[datetime, TableInfo]] = {}
        self._tables_cache: tuple[datetime, List[str]] = None
        self._databases_cache: tuple[datetime, List[str]] = None

        self.client = get_clickhouse_client()

    def _is_cache_valid(self, cache_entry: Optional[tuple[datetime, Any]]) -> bool:
        """Check if a cache entry is still valid."""
        if cache_entry is None:
            return False
        cached_at, _ = cache_entry
        return datetime.now() - cached_at < self.cache_ttl

    def clear_cache(self):
        """Clear all cached schema information."""
        self._schema_cache.clear()
        self._tables_cache = None
        self._databases_cache = None
        logger.info("Schema cache cleared")

    def list_databases(self, force_refresh: bool = False) -> List[str]:
        """
        List all databases in ClickHouse.

        Args:
            force_refresh: Ignore cache and fetch from database

        Returns:
            List of database names
        """
        if not force_refresh and self._is_cache_valid(self._databases_cache):
            return self._databases_cache[1]

        try:
            result = self.client.execute_query("SHOW DATABASES")
            databases = [row[0] for row in result.result_rows]

            # Filter out system databases if needed
            if not self.include_system_tables:
                databases = [
                    db for db in databases
                    if db not in ("system", "information_schema", "INFORMATION_SCHEMA")
                ]

            self._databases_cache = (datetime.now(), databases)
            return databases

        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            return []

    def list_tables(
        self,
        database: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[str]:
        """
        List all tables in a database.

        Args:
            database: Database name (default: configured database)
            force_refresh: Ignore cache and fetch from database

        Returns:
            List of fully-qualified table names (database.table)
        """
        if not force_refresh and self._is_cache_valid(self._tables_cache):
            return self._tables_cache[1]

        try:
            # Use configured database as default
            if database is None:
                database = self.client._client.database

            # Fetch all tables from system.tables
            # Explicitly select columns to avoid ordinal position issues
            query = "SELECT name, database FROM system.tables"

            result = self.client.execute_query(query)

            # Process results and filter in Python
            tables = []
            excluded_databases = {'system', 'information_schema', 'INFORMATION_SCHEMA'}

            for row in result.result_rows:
                # Query returns: name (index 0), database (index 1)
                if len(row) >= 2:
                    table_name = str(row[0]).strip()  # name column
                    db_name = str(row[1]).strip()     # database column

                    # Filter by database
                    if db_name != database:
                        continue

                    # Filter out system databases if needed
                    if not self.include_system_tables and db_name.upper() in excluded_databases:
                        continue

                    tables.append(f"{db_name}.{table_name}")

            self._tables_cache = (datetime.now(), tables)
            return tables

        except Exception as e:
            logger.error(f"Failed to list tables: {e}")
            return []

    def get_table_schema(
        self,
        table_name: str,
        force_refresh: bool = False,
        include_sample: bool = True,
    ) -> Optional[TableInfo]:
        """
        Get detailed schema information for a table.

        Args:
            table_name: Fully-qualified table name (database.table) or just table name
            force_refresh: Ignore cache
            include_sample: Include sample data in result

        Returns:
            TableInfo object or None if table not found
        """
        # Parse table name
        if "." in table_name:
            database, table = table_name.split(".", 1)
        else:
            database = self.client._client.database
            table = table_name
            table_name = f"{database}.{table}"

        # Check cache
        cache_key = table_name
        if not force_refresh and cache_key in self._schema_cache:
            cached_at, table_info = self._schema_cache[cache_key]
            if self._is_cache_valid((cached_at, table_info)):
                return table_info

        try:
            # Get table metadata
            table_info = self._fetch_table_info(database, table, include_sample)
            if table_info:
                self._schema_cache[cache_key] = (datetime.now(), table_info)

            return table_info

        except Exception as e:
            logger.error(f"Failed to get schema for {table_name}: {e}")
            return None

    def _fetch_table_info(
        self,
        database: str,
        table: str,
        include_sample: bool,
    ) -> Optional[TableInfo]:
        """Fetch table information from ClickHouse."""
        # Get basic table info - explicitly select columns we need
        result = self.client.execute_query(
            "SELECT name, database, engine, partition_key, sorting_key, primary_key, total_rows, total_bytes "
            "FROM system.tables"
        )

        # Find the matching table
        table_row = None
        for row in result.result_rows:
            if len(row) >= 2:
                row_name = str(row[0]).strip()   # name column
                row_db = str(row[1]).strip()     # database column
                if row_name == table and row_db == database:
                    table_row = row
                    break

        if not table_row:
            return None

        # Helper function to safely convert to int
        def safe_to_int(value, default=None):
            """Safely convert value to int, handling None and datetime objects."""
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, datetime):
                return default  # Skip datetime fields
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        # Extract fields from the row using explicit indices
        # 0:name, 1:database, 2:engine, 3:partition_key, 4:sorting_key, 5:primary_key, 6:total_rows, 7:total_bytes
        table_info = TableInfo(
            database=database,
            name=table,
            engine=str(table_row[2]) if len(table_row) > 2 else "",
            partition_key=str(table_row[3]) if len(table_row) > 3 and table_row[3] else None,
            sorting_key=str(table_row[4]) if len(table_row) > 4 and table_row[4] else None,
            primary_key=str(table_row[5]) if len(table_row) > 5 and table_row[5] else None,
            total_rows=safe_to_int(table_row[6] if len(table_row) > 6 else None),
            total_bytes=safe_to_int(table_row[7] if len(table_row) > 7 else None),
            last_updated=datetime.now(),
        )

        # Get column information - explicitly select columns we need
        columns_result = self.client.execute_query(
            "SELECT database, table, name, type, default_kind, default_expression, comment "
            "FROM system.columns"
        )

        for col_row in columns_result.result_rows:
            if len(col_row) >= 3:
                col_db = str(col_row[0]).strip()    # database column
                col_table = str(col_row[1]).strip()  # table column
                col_name = str(col_row[2]).strip()   # name column

                if col_db == database and col_table == table:
                    # Extract column fields
                    # 3:type, 4:default_kind, 5:default_expression, 6:comment
                    col_type = str(col_row[3]) if len(col_row) > 3 else ""
                    col_default_type = str(col_row[4]) if len(col_row) > 4 else None
                    col_default_expr = str(col_row[5]) if len(col_row) > 5 else None
                    col_comment = str(col_row[6]) if len(col_row) > 6 else None

                    col_info = ColumnInfo(
                        name=col_name,
                        type=col_type,
                        default_type=col_default_type,
                        default_expression=col_default_expr,
                        comment=col_comment,
                        is_partition_key=col_name in (table_info.partition_key or ""),
                        is_sorting_key=col_name in (table_info.sorting_key or ""),
                        is_primary_key=col_name in (table_info.primary_key or ""),
                    )
                    table_info.columns.append(col_info)

        # Get CREATE TABLE query
        try:
            create_result = self.client.execute_query(f"SHOW CREATE TABLE {database}.{table}")
            if create_result.result_rows:
                table_info.create_table_query = create_result.result_rows[0][0]
        except Exception as e:
            logger.warning(f"Failed to get CREATE TABLE query: {e}")

        # Get sample data
        if include_sample and table_info.total_rows and table_info.total_rows > 0:
            try:
                sample_result = self.client.execute_query(
                    f"SELECT * FROM {database}.{table} LIMIT {self.sample_rows}"
                )
                columns = [col.name for col in table_info.columns]
                for row in sample_result.result_rows:
                    row_dict = dict(zip(columns, row))
                    table_info.sample_data.append(row_dict)
            except Exception as e:
                logger.warning(f"Failed to get sample data: {e}")

        return table_info

    def describe_table(self, table_name: str) -> str:
        """
        Generate a human-readable description of a table.

        Useful for LLM prompts.

        Args:
            table_name: Table name

        Returns:
            Human-readable table description
        """
        table_info = self.get_table_schema(table_name)
        if not table_info:
            return f"Table {table_name} not found."

        lines = [
            f"Table: {table_info.database}.{table_info.name}",
            f"Engine: {table_info.engine}",
        ]

        if table_info.total_rows is not None:
            lines.append(f"Total Rows: {table_info.total_rows:,}")

        if table_info.partition_key:
            lines.append(f"Partition Key: {table_info.partition_key}")

        if table_info.sorting_key:
            lines.append(f"Sorting Key: {table_info.sorting_key}")

        lines.append("\nColumns:")

        for col in table_info.columns:
            col_desc = f"  - {col.name}: {col.type}"
            if col.comment:
                col_desc += f" ({col.comment})"
            if col.is_partition_key:
                col_desc += " [PARTITION]"
            if col.is_sorting_key:
                col_desc += " [SORT]"
            lines.append(col_desc)

        if table_info.sample_data:
            lines.append(f"\nSample Data (first {len(table_info.sample_data)} rows):")
            for i, row in enumerate(table_info.sample_data, 1):
                lines.append(f"  Row {i}: {row}")

        return "\n".join(lines)

    def get_schema_for_llm(
        self,
        tables: Optional[List[str]] = None,
        include_samples: bool = False,
    ) -> str:
        """
        Generate schema description suitable for LLM prompts.

        Args:
            tables: List of tables to include (all if None)
            include_samples: Include sample data

        Returns:
            Formatted schema string
        """
        if tables is None:
            tables = self.list_tables()

        sections = []

        for table_name in tables:
            table_info = self.get_table_schema(
                table_name,
                include_sample=include_samples,
            )

            if not table_info:
                continue

            # Table header
            sections.append(f"## {table_info.database}.{table_info.name}")
            sections.append(f"Engine: {table_info.engine}")

            # Columns
            sections.append("\nColumns:")
            for col in table_info.columns:
                col_line = f"  - {col.name}: {col.type}"
                if col.comment:
                    col_line += f" -- {col.comment}"
                sections.append(col_line)

            # Sample data
            if include_samples and table_info.sample_data:
                sections.append("\nSample Data:")
                for row in table_info.sample_data[:3]:
                    sections.append(f"  {row}")

            sections.append("")  # Blank line between tables

        return "\n".join(sections)

    def search_tables_by_column(
        self,
        column_name: str,
        exact_match: bool = False,
    ) -> List[str]:
        """
        Find tables that have a specific column.

        Args:
            column_name: Column name to search for
            exact_match: If True, exact match; if False, partial match

        Returns:
            List of table names
        """
        try:
            # Fetch columns and filter in Python to avoid SQL syntax issues
            # Explicitly select columns we need
            query = "SELECT database, table, name FROM system.columns"

            if exact_match:
                query += f" WHERE name = '{column_name}'"
            else:
                query += f" WHERE name LIKE '%{column_name}%'"

            result = self.client.execute_query(query)
            tables = set()

            for row in result.result_rows:
                # Query returns: database (index 0), table (index 1), name (index 2)
                if len(row) >= 2:
                    db_name = str(row[0]).strip()   # database column
                    tbl_name = str(row[1]).strip()  # table column
                    tables.add(f"{db_name}.{tbl_name}")

            return sorted(list(tables))

        except Exception as e:
            logger.error(f"Failed to search tables by column: {e}")
            return []

    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """
        Get statistics for a table.

        Args:
            table_name: Table name

        Returns:
            Dictionary with table statistics
        """
        table_info = self.get_table_schema(table_name)
        if not table_info:
            return {}

        return {
            "database": table_info.database,
            "name": table_info.name,
            "full_name": f"{table_info.database}.{table_info.name}",
            "engine": table_info.engine,
            "total_rows": table_info.total_rows,
            "total_bytes": table_info.total_bytes,
            "total_bytes_mb": round(table_info.total_bytes / 1024 / 1024, 2) if table_info.total_bytes else None,
            "total_bytes_gb": round(table_info.total_bytes / 1024 / 1024 / 1024, 2) if table_info.total_bytes else None,
            "column_count": len(table_info.columns),
            "partition_key": table_info.partition_key,
            "sorting_key": table_info.sorting_key,
            "primary_key": table_info.primary_key,
            "has_sample_data": len(table_info.sample_data) > 0,
            "last_updated": table_info.last_updated.isoformat() if table_info.last_updated else None,
        }


# Singleton instance
_default_explorer: Optional[ClickHouseSchemaExplorer] = None


def get_schema_explorer() -> ClickHouseSchemaExplorer:
    """Get the default schema explorer instance."""
    global _default_explorer
    if _default_explorer is None:
        _default_explorer = ClickHouseSchemaExplorer()
    return _default_explorer


# CLI for testing
if __name__ == "__main__":
    explorer = ClickHouseSchemaExplorer()

    print("\n=== Databases ===")
    databases = explorer.list_databases()
    print(f"Databases: {databases}")

    print("\n=== Tables ===")
    tables = explorer.list_tables()
    print(f"Found {len(tables)} tables")
    for table in tables[:5]:
        print(f"  - {table}")

    if tables:
        print(f"\n=== Table Schema: {tables[0]} ===")
        description = explorer.describe_table(tables[0])
        print(description)
