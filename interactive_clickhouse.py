"""
Interactive ClickHouse query tool - ask questions in natural language
"""
import sys
import os
from pathlib import Path

# Set UTF-8 encoding for Windows console
if os.name == 'nt':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent / "apps" / "backend"))

from database import get_clickhouse_client

def show_all_tables():
    """Show all tables in the database."""
    print("\n=== All Tables in Database ===")
    try:
        client = get_clickhouse_client()
        result = client.execute_query("SHOW TABLES")
        tables = [row[0] for row in result.result_rows]
        print(f"Found {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")
        return tables
    except Exception as e:
        print(f"Error: {e}")
        return []

def describe_table(table_name):
    """Show columns in a table."""
    print(f"\n=== Columns in '{table_name}' Table ===")
    try:
        client = get_clickhouse_client()
        result = client.execute_query(f"DESCRIBE TABLE {table_name}")
        columns = result.result_rows
        print(f"Found {len(columns)} columns:")
        for col in columns:
            # Each row is: (name, type, ...)
            col_name = col[0] if len(col) > 0 else "unknown"
            col_type = col[1] if len(col) > 1 else "unknown"
            print(f"  - {col_name}: {col_type}")
        return columns
    except Exception as e:
        print(f"Error: {e}")
        return []

def count_rows(table_name):
    """Count total rows in a table."""
    print(f"\n=== Total Rows in '{table_name}' Table ===")
    try:
        client = get_clickhouse_client()
        result = client.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result.result_rows[0][0] if result.result_rows else 0
        print(f"Total rows: {count:,}")
        return count
    except Exception as e:
        print(f"Error: {e}")
        return 0

if __name__ == "__main__":
    print("=== ClickHouse Interactive Query Tool ===")

    # Test the queries you mentioned
    show_all_tables()

    # If you have a 'users' table
    print("\n" + "=" * 50)
    describe_table("users")

    # If you have a 'logs' table
    print("\n" + "=" * 50)
    count_rows("logs")

    print("\n" + "=" * 50)
    print("All queries completed successfully!")
