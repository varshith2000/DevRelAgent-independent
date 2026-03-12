"""
Debug filtering logic
"""

import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

from database import get_clickhouse_client, config
from tools.clickhouse_schema import get_schema_explorer

print("=" * 60)
print("Debug: Filtering Logic")
print("=" * 60)

client = get_clickhouse_client()
explorer = get_schema_explorer()

# Show what database the client is connected to
print(f"\n📌 Client database: '{client._client.database}'")
print(f"📌 Config database: '{config.database}'")

# Query and manually filter
print(f"\n🔍 Manual filtering test...")
result = client.execute_query("SELECT name, database FROM system.tables")

database = client._client.database
excluded_databases = {'system', 'information_schema', 'INFORMATION_SCHEMA'}
include_system_tables = explorer.include_system_tables

print(f"   Filtering for database: '{database}'")
print(f"   include_system_tables: {include_system_tables}")
print(f"   excluded_databases: {excluded_databases}")

matched_count = 0
filtered_count = 0

for i, row in enumerate(result.result_rows):
    if len(row) >= 2:
        table_name = str(row[0]).strip()
        db_name = str(row[1]).strip()

        # First filter
        if db_name != database:
            filtered_count += 1
            if filtered_count <= 3:  # Show first 3 filtered
                print(f"   Filtered out (wrong DB): db='{db_name}' != '{database}'")
            continue

        # Second filter
        if not include_system_tables and db_name.upper() in excluded_databases:
            filtered_count += 1
            print(f"   Filtered out (system DB): db='{db_name}'")
            continue

        matched_count += 1
        print(f"   [OK] MATCHED: {db_name}.{table_name}")

print(f"\n   Total matched: {matched_count}")
print(f"   Total filtered: {filtered_count}")

# Now try using the list_tables method with cache cleared
print(f"\n🔍 Using list_tables() with cleared cache...")
explorer.clear_cache()
tables = explorer.list_tables()
print(f"   Found {len(tables)} tables")
