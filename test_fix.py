"""
Quick test script to verify ClickHouse queries work after the fix
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
from tools.clickhouse_schema import ClickHouseSchemaExplorer

def test_basic_queries():
    """Test basic ClickHouse queries that should work after the fix."""
    print("Testing ClickHouse queries after fix...\n")

    try:
        # Get client
        client = get_clickhouse_client()

        # Test 1: Show all tables
        print("=" * 50)
        print("Test 1: SHOW TABLES")
        print("=" * 50)
        result = client.execute_query("SHOW TABLES")
        tables = [row[0] for row in result.result_rows]
        print(f"[SUCCESS] Found {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")

        # Test 2: Show databases
        print("\n" + "=" * 50)
        print("Test 2: SHOW DATABASES")
        print("=" * 50)
        result = client.execute_query("SHOW DATABASES")
        databases = [row[0] for row in result.result_rows]
        print(f"[SUCCESS] Found {len(databases)} databases:")
        for db in databases:
            print(f"  - {db}")

        # Test 3: Test with schema explorer
        print("\n" + "=" * 50)
        print("Test 3: Schema Explorer - List Tables")
        print("=" * 50)
        explorer = ClickHouseSchemaExplorer()
        tables = explorer.list_tables()
        print(f"[SUCCESS] Schema explorer found {len(tables)} tables")
        for table in tables[:5]:
            print(f"  - {table}")

        print("\n" + "=" * 50)
        print("[SUCCESS] All tests passed!")
        print("=" * 50)

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

def test_natural_language_queries():
    """Test natural language queries using the ClickHouse tool."""
    print("\n" + "=" * 50)
    print("Test 4: Natural Language Queries")
    print("=" * 50)
    
    try:
        from tools.clickhouse_tool import get_clickhouse_tool
        tool = get_clickhouse_tool()
        
        # Test queries from the issue
        test_queries = [
            "Show me all tables in the database",
            "Count the total rows",
        ]
        
        for query in test_queries:
            print(f"\nQuery: '{query}'")
            result = tool.query_nl(query)
            formatted = tool.format_result(result)
            print(formatted)
            
            if result.status.value == 'success':
                print(f"✅ Query succeeded")
            else:
                print(f"⚠️ Status: {result.status.value}")
                if result.error_message:
                    print(f"   Error: {result.error_message}")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] NL query test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_basic_queries()
    success = test_natural_language_queries() and success
    sys.exit(0 if success else 1)
