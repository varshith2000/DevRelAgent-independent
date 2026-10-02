"""
Quick Test Data Setup for ClickHouse

Generates sample log data for testing the DevRelAgent NL→SQL capabilities.
Creates a realistic log dataset with various log levels, services, and patterns.

Usage:
    python setup_test_data.py
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_clickhouse_client


def generate_sample_logs(count: int = 5000) -> list:
    """
    Generate sample log entries.

    Args:
        count: Number of log entries to generate

    Returns:
        List of log tuples
    """
    levels = ["INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL"]
    services = ["api", "auth", "database", "worker", "frontend", "cache"]

    # Sample messages with realistic patterns
    messages = {
        "INFO": [
            "Request processed successfully",
            "User logged in",
            "Cache hit for key",
            "Health check passed",
            "Job completed successfully",
            "Configuration loaded",
            "Connection established",
            "Data synchronized",
        ],
        "WARNING": [
            "High memory usage detected",
            "Slow query performance",
            "Rate limit approaching",
            "Deprecated API endpoint called",
            "Cache miss for key",
            "Retry attempt {n}",
            "Large payload size",
        ],
        "ERROR": [
            "Failed to connect to database",
            "Authentication failed for user",
            "Null pointer exception",
            "Timeout waiting for response",
            "Invalid request parameters",
            "Resource not found",
            "Permission denied",
            "Service unavailable",
        ],
        "DEBUG": [
            "Processing request step {n}",
            "Variable state: {value}",
            "Entering function {name}",
            "Cache lookup for key",
            "SQL query: {query}",
        ],
        "CRITICAL": [
            "System out of memory",
            "Database connection pool exhausted",
            "Service crash detected",
            "Security breach attempt blocked",
            "Data corruption detected",
        ],
    }

    logs = []
    base_time = datetime.now() - timedelta(days=7)

    # Distribution: more INFO, fewer CRITICAL
    level_weights = [50, 20, 15, 10, 5]  # INFO, WARNING, ERROR, DEBUG, CRITICAL

    for i in range(count):
        # Weighted random level selection
        level = random.choices(levels, weights=level_weights)[0]

        # Select message template
        message = random.choice(messages.get(level, messages["INFO"]))

        # Format message with variables
        message = message.format(
            n=random.randint(1, 5),
            value=random.randint(100, 9999),
            name=f"function_{random.choice(['process', 'handle', 'execute', 'validate'])}",
            query=f"SELECT * FROM table_{random.randint(1, 10)}",
        )

        # Generate timestamp (more recent = more likely)
        days_ago = random.expovariate(1/2)  # Exponential distribution favoring recent
        if days_ago > 7:
            days_ago = 7
        timestamp = base_time + timedelta(days=days_ago, hours=random.randint(0, 23))

        logs.append([
            timestamp,
            level,
            message,
            random.choice(services),
            random.randint(100, 9999),  # user_id
            random.randint(1, 5000),    # duration_ms
            random.randint(200, 599),   # status_code
        ])

    # Sort by timestamp
    logs.sort(key=lambda x: x[0])

    return logs


def generate_sample_metrics(count: int = 1000) -> list:
    """
    Generate sample metrics data.

    Args:
        count: Number of metric entries

    Returns:
        List of metric tuples
    """
    metrics = []
    base_time = datetime.now() - timedelta(days=1)

    metric_names = [
        "cpu_usage_percent",
        "memory_usage_mb",
        "request_count",
        "response_time_ms",
        "error_rate",
        "active_connections",
    ]

    for i in range(count):
        timestamp = base_time + timedelta(minutes=i)

        metric_name = random.choice(metric_names)

        # Generate realistic metric values
        if "cpu" in metric_name:
            value = random.uniform(10, 95)
        elif "memory" in metric_name:
            value = random.uniform(100, 8000)
        elif "request_count" in metric_name:
            value = random.randint(50, 500)
        elif "response_time" in metric_name:
            value = random.uniform(10, 1000)
        elif "error_rate" in metric_name:
            value = random.uniform(0, 10)
        elif "connections" in metric_name:
            value = random.randint(10, 200)
        else:
            value = random.uniform(0, 100)

        metrics.append([
            timestamp,
            metric_name,
            round(value, 2),
            random.choice(["api", "worker", "database"]),
            random.choice(["production", "staging", "dev"]),
        ])

    return metrics


def generate_sample_users(count: int = 100) -> list:
    """
    Generate sample user data.

    Args:
        count: Number of users

    Returns:
        List of user tuples
    """
    users = []
    first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]

    for i in range(1, count + 1):
        users.append([
            i,
            random.choice(first_names),
            random.choice(last_names),
            random.choice(["user", "admin", "moderator"]),
            random.choice([True, False]),
            datetime.now() - timedelta(days=random.randint(1, 365)),
        ])

    return users


def setup_clickhouse_test_data():
    """Set up all test data in ClickHouse."""
    print("=" * 60)
    print("ClickHouse Test Data Setup")
    print("=" * 60)

    try:
        client = get_clickhouse_client()

        # Create test database
        print("\n📦 Creating test database...")
        client.create_database("devrel_test")
        print("[OK] Database 'devrel_test' created")

        # Create logs table
        print("\n📋 Creating logs table...")
        client.execute_command("""
            CREATE TABLE IF NOT EXISTS devrel_test.logs (
                timestamp DateTime,
                level String,
                message String,
                service String,
                user_id UInt32,
                duration_ms UInt32,
                status_code UInt16
            )
            ENGINE = MergeTree()
            ORDER BY (timestamp, level)
            PARTITION BY toYYYYMM(timestamp)
            SETTINGS index_granularity = 8192
        """)
        print("[OK] Table 'logs' created")

        # Create metrics table
        print("\n📊 Creating metrics table...")
        client.execute_command("""
            CREATE TABLE IF NOT EXISTS devrel_test.metrics (
                timestamp DateTime,
                metric_name String,
                value Float64,
                service String,
                environment String
            )
            ENGINE = MergeTree()
            ORDER BY (timestamp, metric_name)
            PARTITION BY toYYYYMM(timestamp)
        """)
        print("[OK] Table 'metrics' created")

        # Create users table
        print("\n👥 Creating users table...")
        client.execute_command("""
            CREATE TABLE IF NOT EXISTS devrel_test.users (
                id UInt32,
                first_name String,
                last_name String,
                role String,
                is_active Bool,
                created_at DateTime
            )
            ENGINE = MergeTree()
            ORDER BY id
            PRIMARY KEY id
        """)
        print("[OK] Table 'users' created")

        # Insert logs
        print("\n📝 Generating and inserting log data...")
        logs = generate_sample_logs(5000)
        client.insert_data(
            "devrel_test.logs",
            logs,
            column_names=["timestamp", "level", "message", "service", "user_id", "duration_ms", "status_code"]
        )
        print(f"[OK] Inserted {len(logs)} log records")

        # Insert metrics
        print("\n📈 Generating and inserting metrics...")
        metrics = generate_sample_metrics(1000)
        client.insert_data(
            "devrel_test.metrics",
            metrics,
            column_names=["timestamp", "metric_name", "value", "service", "environment"]
        )
        print(f"[OK] Inserted {len(metrics)} metric records")

        # Insert users
        print("\n👤 Generating and inserting users...")
        users = generate_sample_users(100)
        client.insert_data(
            "devrel_test.users",
            users,
            column_names=["id", "first_name", "last_name", "role", "is_active", "created_at"]
        )
        print(f"[OK] Inserted {len(users)} user records")

        # Verify data
        print("\n🔍 Verifying data...")
        result = client.execute_query("SELECT count() FROM devrel_test.logs")
        log_count = result.result_rows[0][0]
        print(f"   Logs: {log_count:,} records")

        result = client.execute_query("SELECT count() FROM devrel_test.metrics")
        metric_count = result.result_rows[0][0]
        print(f"   Metrics: {metric_count:,} records")

        result = client.execute_query("SELECT count() FROM devrel_test.users")
        user_count = result.result_rows[0][0]
        print(f"   Users: {user_count:,} records")

        # Sample queries
        print("\n📊 Sample queries to try:")
        print("   • 'Show recent errors'")
        print("   • 'Count logs by level'")
        print("   • 'Show average response time by service'")
        print("   • 'Find slow requests (over 1000ms)'")
        print("   • 'Show metrics from the last hour'")
        print("   • 'List all active users'")

        print("\n" + "=" * 60)
        print("[OK] Test data setup complete!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sample_queries():
    """Run some sample queries to verify the data."""
    print("\n" + "=" * 60)
    print("Running Sample Queries")
    print("=" * 60)

    try:
        from tools.clickhouse_tool import ClickHouseTool

        tool = ClickHouseTool()

        queries = [
            "Show me recent errors from the logs",
            "Count all logs by level",
            "What are the top 5 slowest requests?",
            "Show metrics from the last hour",
            "How many users do we have?",
        ]

        for query in queries:
            print(f"\n❓ Query: {query}")
            result = tool.query_nl(query)

            if result.status.value == "success":
                print(f"[OK] Rows: {result.row_count}")
                if result.rows:
                    for row in result.rows[:3]:
                        print(f"   {row}")
                    if len(result.rows) > 3:
                        print(f"   ... and {len(result.rows) - 3} more")
            else:
                print(f"❌ Error: {result.error_message}")

        print("\n[OK] Sample queries complete!")

    except Exception as e:
        print(f"\n❌ Query test failed: {e}")


if __name__ == "__main__":
    import sys

    # Setup data
    success = setup_clickhouse_test_data()

    if success and "--test" in sys.argv:
        # Run sample queries if requested
        test_sample_queries()

    print("\n💡 Next steps:")
    print("   1. Run integration tests: python test_integration.py")
    print("   2. Start the server: python main.py")
    print("   3. Test the API:")
    print("      curl -X POST http://localhost:8000/chat \\")
    print("        -H 'Content-Type: application/json' \\")
    print("        -d '{\"message\": \"Show recent errors\"}'")
