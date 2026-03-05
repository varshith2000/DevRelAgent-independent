"""
Debug: Check what database the explorer is connected to
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_clickhouse_client, config
from tools.clickhouse_schema import ClickHouseSchemaExplorer

print("=" * 60)
print("Debug: Explorer Database")
print("=" * 60)

# Direct client
direct_client = get_clickhouse_client()
print(f"\n📌 Direct client database: '{direct_client._client.database}'")
print(f"📌 Config database: '{config.database}'")

# Explorer's client
explorer = ClickHouseSchemaExplorer()
print(f"\n📌 Explorer's client database: '{explorer.client._client.database}'")
print(f"📌 Are they the same? {direct_client._client.database == explorer.client._client.database}")

# Check if the singleton is being reused
print(f"\n📌 Are they the same object? {direct_client is explorer.client}")
print(f"📌 Are their clients the same? {direct_client._client is explorer.client._client}")
