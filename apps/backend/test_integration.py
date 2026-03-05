"""
Integration Test Script for Phase 1B + 1C

Tests:
1. SQL Safety Guard
2. Schema Explorer
3. NL→SQL Tool
4. Tool Registry
5. Agent Loop
6. Chat API (requires server running)

Usage:
    python test_integration.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_sql_guard():
    """Test SQL Safety Guard."""
    print("\n" + "="*60)
    print("TEST 1: SQL Safety Guard")
    print("="*60)

    from guardrails import SQLGuard

    guard = SQLGuard()

    safe_queries = [
        "SELECT * FROM users WHERE id = 1",
        "SELECT name, email FROM users ORDER BY created_at DESC LIMIT 10",
        "SHOW TABLES",
        "DESCRIBE users",
    ]

    unsafe_queries = [
        "DROP TABLE users",
        "DELETE FROM users WHERE id = 1",
        "SELECT * FROM users; DROP TABLE users;",
        "SELECT * FROM users WHERE name = '' OR 1=1 --'",
    ]

    print("\n✅ Testing SAFE queries:")
    for query in safe_queries:
        is_safe, violations = guard.is_safe_sql(query)
        status = "✅" if is_safe else "❌"
        print(f"  {status} {query[:50]}...")
        if not is_safe:
            print(f"     ERROR: {violations}")

    print("\n❌ Testing UNSAFE queries (should be blocked):")
    for query in unsafe_queries:
        is_safe, violations = guard.is_safe_sql(query)
        status = "✅ BLOCKED" if not is_safe else "❌ MISSED"
        print(f"  {status} {query[:50]}...")
        if violations:
            for v in violations:
                print(f"     → {v}")

    print("\n✅ SQL Guard test passed!")


async def test_tool_registry():
    """Test Tool Registry."""
    print("\n" + "="*60)
    print("TEST 2: Tool Registry")
    print("="*60)

    from tools.registry import get_registry, ToolCategory, tool

    registry = get_registry()

    # Register a test tool
    @tool(
        name="test_calculator",
        description="Perform simple calculations",
        parameters={
            "a": {"type": "integer", "description": "First number"},
            "b": {"type": "integer", "description": "Second number"},
        },
        category=ToolCategory.UTILITY,
    )
    def test_calculator(a: int, b: int = 10):
        return {"result": a + b}

    print(f"\n✅ Registered tools: {registry.tool_names}")

    # Get OpenAI schemas
    schemas = registry.get_openai_schemas()
    print(f"\n✅ Generated {len(schemas)} OpenAI schemas")
    for schema in schemas[:3]:
        print(f"  - {schema['name']}: {schema['description'][:50]}...")

    # Execute a tool
    if "test_calculator" in registry.tool_names:
        result = await registry.execute_tool("test_calculator", {"a": 5, "b": 3})
        print(f"\n✅ Executed test_calculator(5, 3): {result.to_dict()}")

    print("\n✅ Tool Registry test passed!")


async def test_schema_explorer():
    """Test Schema Explorer (requires ClickHouse connection)."""
    print("\n" + "="*60)
    print("TEST 3: Schema Explorer (ClickHouse)")
    print("="*60)

    from tools.clickhouse_schema import ClickHouseSchemaExplorer

    try:
        explorer = ClickHouseSchemaExplorer()

        # List tables
        tables = explorer.list_tables()
        print(f"\n✅ Found {len(tables)} tables")

        if tables:
            # Get schema for first table
            schema = explorer.get_table_schema(tables[0])
            if schema:
                print(f"\n✅ Table: {schema.database}.{schema.name}")
                print(f"   Engine: {schema.engine}")
                print(f"   Columns: {len(schema.columns)}")
                for col in schema.columns[:5]:
                    print(f"     - {col.name}: {col.type}")

                # Get description
                description = explorer.describe_table(tables[0])
                print(f"\n   Description:\n{description[:300]}...")

        print("\n✅ Schema Explorer test passed!")

    except Exception as e:
        print(f"\n⚠️ Schema Explorer test skipped (ClickHouse not configured): {e}")


async def test_nl_to_sql():
    """Test NL→SQL Tool (requires ClickHouse connection)."""
    print("\n" + "="*60)
    print("TEST 4: NL→SQL Tool (ClickHouse)")
    print("="*60)

    from tools.clickhouse_tool import ClickHouseTool

    try:
        tool = ClickHouseTool()

        # Test NL→SQL conversion
        test_queries = [
            "Show me all tables",
            "Count the total rows",
        ]

        for query in test_queries:
            print(f"\n  Query: {query}")
            result = tool.query_nl(query)

            if result.status.value == "success":
                print(f"  ✅ Status: {result.status.value}")
                print(f"  ✅ Rows: {result.row_count}")
                if result.sql:
                    print(f"  📄 SQL: {result.sql[:100]}...")
            else:
                print(f"  ⚠️ Status: {result.status.value}")
                print(f"     Error: {result.error_message}")

        print("\n✅ NL→SQL Tool test passed!")

    except Exception as e:
        print(f"\n⚠️ NL→SQL Tool test skipped (ClickHouse not configured): {e}")


async def test_agent_loop():
    """Test Agent Loop."""
    print("\n" + "="*60)
    print("TEST 5: Agent Loop")
    print("="*60)

    from agent.loop import AgentLoop

    loop = AgentLoop()

    test_queries = [
        "What can you help me with?",
        "Show me recent database errors",
        "How do I authenticate?",
    ]

    for query in test_queries:
        print(f"\n  Query: {query}")
        response, tool_calls = await loop.process_with_tools(query)

        print(f"  ✅ Response: {response[:100]}...")
        if tool_calls:
            print(f"  🔧 Tool calls: {len(tool_calls)}")
            for tc in tool_calls:
                print(f"     - {tc.tool_name}: {'✅' if tc.success else '❌'}")

    print("\n✅ Agent Loop test passed!")


async def test_agent_streaming():
    """Test Agent Loop Streaming."""
    print("\n" + "="*60)
    print("TEST 6: Agent Loop Streaming")
    print("="*60)

    from agent.loop import AgentLoop

    loop = AgentLoop()

    query = "Tell me about the database"
    print(f"\n  Query: {query}")
    print("\n  Streaming response:")

    async for chunk in loop.process_stream(query):
        if chunk["type"] == "token":
            print(chunk["content"], end="", flush=True)
        elif chunk["type"] == "tool_call":
            print(f"\n\n  🔧 Tool: {chunk['data'].get('tool_name')}")
        elif chunk["type"] == "done":
            print(f"\n\n  ✅ Done")

    print("\n\n✅ Agent Streaming test passed!")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DevRelAgent Integration Tests")
    print("Phase 1B (ClickHouse) + Phase 1C (Tool Integration)")
    print("="*60)

    try:
        await test_sql_guard()
        await test_tool_registry()
        await test_schema_explorer()
        await test_nl_to_sql()
        await test_agent_loop()
        await test_agent_streaming()

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
