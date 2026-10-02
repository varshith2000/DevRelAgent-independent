"""
Quick ClickHouse Connection Verification

Verifies your ClickHouse Cloud connection and lists available tables.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import config, get_clickhouse_client
from tools.clickhouse_schema import get_schema_explorer

print("=" * 60)
print("ClickHouse Cloud Connection Verification")
print("=" * 60)

try:
    # Test connection
    print("\n🔌 Testing connection...")
    client = get_clickhouse_client()

    # Get current database
    print("✅ Connected successfully!")
    print(f"   Database: {config.database}")
    print(f"   Host: {config.host}")
    print(f"   Port: {config.port}")

    # List tables
    print("\n📋 Listing tables...")
    explorer = get_schema_explorer()

    tables = explorer.list_tables()
    print(f"✅ Found {len(tables)} tables:")

    if tables:
        for table in tables:
            print(f"   • {table}")
    else:
        print("   ⚠️ No tables found. Run 'python setup_test_data.py' first.")

    # Try to query specific tables
    test_tables = ["devrel_test.logs", "devrel_test.metrics", "devrel_test.users"]

    print("\n🔍 Checking test tables...")
    for table in test_tables:
        result = client.execute_query(f"SELECT count(*) FROM {table}")
        if result.result_rows:
            count = result.result_rows[0][0]
            print(f"   ✅ {table}: {count:,} rows")
        else:
            print(f"   ❌ {table}: Not found")

    print("\n" + "=" * 60)
    print("✅ Verification complete!")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    import traceback
    traceback.print_exc()

    print("\n💡 Troubleshooting:")
    print("   1. Check your .env file has correct credentials")
    print("   2. Verify CLICKHOUSE_DATABASE is set to 'devrel_test'")
    print("   3. Make sure you ran setup_test_data.py first")
    print("   4. Check ClickHouse Cloud is accessible")
