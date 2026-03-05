"""
Quick test with cache cleared
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.clickhouse_schema import get_schema_explorer

print("Clearing cache and listing tables...")

explorer = get_schema_explorer()
explorer.clear_cache()

tables = explorer.list_tables()

print(f"\n✅ Found {len(tables)} tables:")
for table in tables:
    print(f"   • {table}")
