"""
ClickHouse Client Module

Provides a singleton client for ClickHouse Cloud operations.
"""

import logging
from typing import Any, Optional
import clickhouse_connect
from .config import config

logger = logging.getLogger(__name__)


class ClickHouseClient:
    """Singleton ClickHouse Cloud client."""

    _instance: Optional["ClickHouseClient"] = None
    _client: Optional[clickhouse_connect.driver.client.Client] = None

    def __new__(cls) -> "ClickHouseClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            self._connect()

    def _connect(self):
        """Establish connection to ClickHouse Cloud."""
        try:
            logger.info(f"Connecting to ClickHouse Cloud at {config.host}...")
            self._client = clickhouse_connect.get_client(**config.to_client_kwargs())
            # Test connection
            result = self._client.query("SELECT 1")
            logger.info("[OK] Successfully connected to ClickHouse Cloud!")
        except Exception as e:
            logger.error(f"❌ Failed to connect to ClickHouse Cloud: {e}")
            raise

    def execute_query(self, query: str, parameters: Optional[dict] = None) -> Any:
        """
        Execute a SQL query and return results.

        Args:
            query: SQL query string
            parameters: Optional query parameters

        Returns:
            Query result
        """
        try:
            # Pass parameters as keyword argument (not positional)
            result = self._client.query(query, parameters=parameters)
            return result
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise

    def execute_command(self, command: str) -> None:
        """
        Execute a SQL command without returning results (INSERT, CREATE, etc.).

        Args:
            command: SQL command string
        """
        try:
            self._client.command(command)
            logger.info(f"Command executed successfully: {command[:50]}...")
        except Exception as e:
            logger.error(f"Command failed: {e}")
            raise

    def insert_data(
        self,
        table: str,
        data: list[list[Any]],
        column_names: Optional[list[str]] = None,
    ) -> None:
        """
        Insert data into a table.

        Args:
            table: Table name
            data: List of rows (each row is a list of values)
            column_names: Optional list of column names
        """
        try:
            self._client.insert(table, data, column_names=column_names)
            logger.info(f"Inserted {len(data)} rows into {table}")
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            raise

    def create_database(self, database_name: str) -> None:
        """Create a new database if it doesn't exist."""
        self.execute_command(f"CREATE DATABASE IF NOT EXISTS {database_name}")

    def create_table(
        self,
        table_name: str,
        schema: str,
        engine: str = "MergeTree()",
        order_by: str = "tuple()",
        partition_by: Optional[str] = None,
    ) -> None:
        """
        Create a new table.

        Args:
            table_name: Table name
            schema: Column definitions (e.g., "id UInt64, name String, created_at DateTime")
            engine: ClickHouse engine (default: MergeTree)
            order_by: ORDER BY clause for MergeTree
            partition_by: Optional PARTITION BY clause
        """
        partition_clause = f"PARTITION BY {partition_by}" if partition_by else ""
        query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {schema}
        )
        ENGINE = {engine}
        ORDER BY ({order_by})
        {partition_clause}
        """
        self.execute_command(query)

    def drop_table(self, table_name: str) -> None:
        """Drop a table if it exists."""
        self.execute_command(f"DROP TABLE IF EXISTS {table_name}")

    def get_table_info(self, table_name: str) -> Any:
        """Get table structure information."""
        return self.execute_query(f"DESCRIBE TABLE {table_name}")

    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()
            logger.info("ClickHouse connection closed.")


# Global client instance
def get_clickhouse_client() -> ClickHouseClient:
    """Get or create the singleton ClickHouse client."""
    return ClickHouseClient()


# Example usage functions
def example_setup():
    """Example: Create a sample database and table."""
    client = get_clickhouse_client()

    # Create database
    client.create_database("devrel_data")

    # Create table
    client.create_table(
        table_name="devrel_data.events",
        schema="""
            id UInt64,
            timestamp DateTime,
            event_type String,
            user_id UInt32,
            metadata String,
            created_at DateTime DEFAULT now()
        """,
        order_by="timestamp, event_type",
        partition_by="toYYYYMM(timestamp)",
    )

    print("[OK] Database and table created successfully!")


def example_insert():
    """Example: Insert sample data."""
    client = get_clickhouse_client()

    # Insert data
    client.insert_data(
        table="devrel_data.events",
        data=[
            [1, "2024-03-01 10:00:00", "page_view", 100, '{"page": "/home"}'],
            [2, "2024-03-01 10:01:00", "click", 100, '{"button": "submit"}'],
            [3, "2024-03-01 10:02:00", "purchase", 101, '{"amount": 99.99}'],
        ],
        column_names=["id", "timestamp", "event_type", "user_id", "metadata"],
    )

    print("[OK] Data inserted successfully!")


def example_query():
    """Example: Query data."""
    client = get_clickhouse_client()

    result = client.execute_query("SELECT * FROM devrel_data.events ORDER BY timestamp DESC LIMIT 10")

    print("📊 Query Results:")
    for row in result.result_rows:
        print(row)


if __name__ == "__main__":
    # Run examples
    example_setup()
    example_insert()
    example_query()
