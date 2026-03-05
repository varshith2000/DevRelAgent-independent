"""
ClickHouse Connection Test Script

Run this script to verify your ClickHouse Cloud connection works.
Usage: python test_clickhouse.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_clickhouse_client


def test_connection():
    """Test ClickHouse Cloud connection."""
    print("🔌 Testing ClickHouse Cloud connection...\n")

    try:
        # Get client
        client = get_clickhouse_client()
        print("✅ Connected to ClickHouse Cloud!\n")

        # Test query
        result = client.execute_query("SELECT version() AS version, now() AS current_time")
        print("📊 Server Info:")
        for row in result.result_rows:
            print(f"   Version: {row[0]}")
            print(f"   Server Time: {row[1]}")

        print("\n✅ All tests passed! Your ClickHouse Cloud is working!\n")
        return True

    except Exception as e:
        print(f"\n❌ Connection failed: {e}\n")
        print("Please check your .env file settings:\n")
        print("   CLICKHOUSE_HOST=your-host.clickhouse.cloud")
        print("   CLICKHOUSE_PORT=8443")
        print("   CLICKHOUSE_USERNAME=default")
        print("   CLICKHOUSE_PASSWORD=your-password")
        print("   CLICKHOUSE_DATABASE=default\n")
        return False


def test_create_table():
    """Test creating a table and inserting data."""
    print("\n🧪 Testing table creation and data operations...\n")

    try:
        client = get_clickhouse_client()

        # Drop if exists
        client.drop_table("test_table")

        # Create table
        client.create_table(
            table_name="test_table",
            schema="""
                id UInt64,
                name String,
                value Float32,
                created_at DateTime DEFAULT now()
            """,
            order_by="id",
        )
        print("✅ Table 'test_table' created!")

        # Insert data
        client.insert_data(
            table="test_table",
            data=[
                [1, "First", 10.5],
                [2, "Second", 20.3],
                [3, "Third", 30.7],
            ],
            column_names=["id", "name", "value"],
        )
        print("✅ Test data inserted!")

        # Query data
        result = client.execute_query("SELECT * FROM test_table ORDER BY id")
        print("\n📊 Query Results:")
        for row in result.result_rows:
            print(f"   {row}")

        # Clean up
        client.drop_table("test_table")
        print("\n✅ Test table cleaned up!")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}\n")
        return False


if __name__ == "__main__":
    success = test_connection()
    if success:
        test_create_table()
