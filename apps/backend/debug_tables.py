"""
Debug script to check table listing
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_clickhouse_client, config

print("=" * 60)
print("Debug: Table Listing")
print("=" * 60)

client = get_clickhouse_client()

# Show configured database
print(f"\n📌 Configured database: '{config.database}'")
print(f"   Client database: '{client._client.database}'")

# Query system.tables directly
print(f"\n🔍 Querying system.tables for all databases...")
result = client.execute_query("SELECT name, database FROM system.tables")

print(f"   Total rows in system.tables: {len(result.result_rows)}")

# Show first few rows with their types
print(f"\n   Sample rows (showing database column):")
seen_databases = set()
for i, row in enumerate(result.result_rows[:20]):
    if len(row) >= 2:
        table_name = row[0]
        db_name = row[1]
        print(f"   Row {i}: table='{table_name}' (type: {type(table_name)}), db='{db_name}' (type: {type(db_name)})")
        seen_databases.add(str(db_name))

print(f"\n   Unique databases found: {sorted(seen_databases)}")

# Try to find devrel_test tables
print(f"\n🔍 Looking for tables in 'devrel_test' database...")
devrel_tables = []
for row in result.result_rows:
    if len(row) >= 2:
        table_name = str(row[0])
        db_name = str(row[1])
        if db_name == "devrel_test":
            devrel_tables.append(f"{db_name}.{table_name}")

print(f"   Found {len(devrel_tables)} tables:")
for table in devrel_tables:
    print(f"   ✅ {table}")

if not devrel_tables:
    print(f"   ⚠️ No tables found in 'devrel_test'")
    print(f"   💡 Your .env has CLICKHOUSE_DATABASE={config.database}")
    print(f"   💡 Try listing ALL tables and check the database names")
