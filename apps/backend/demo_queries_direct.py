"""
Direct SQL queries for demo purposes.
These bypass the LLM and directly query ClickHouse for reliable results.
"""

from database.clickhouse_client import ClickHouseClient
import json
from datetime import datetime

def run_demo_queries():
    """Run a series of demo queries against ClickHouse."""
    client = ClickHouseClient()

    print("=" * 80)
    print("DEVREL AGENT - DIRECT DATABASE QUERIES")
    print("=" * 80)
    print(f"\nConnected to ClickHouse Cloud")
    print(f"Database: devrel_test")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Query 1: Recent critical errors
    print("=" * 80)
    print("QUERY 1: Recent Critical Errors")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            timestamp,
            service,
            level,
            message,
            status_code
        FROM logs
        WHERE level = 'CRITICAL'
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    print(f"\nFound {len(result.result_rows)} critical errors:\n")
    for i, row in enumerate(result.result_rows, 1):
        row_dict = dict(zip(result.column_names, row))
        print(f"{i}. [{row_dict['timestamp']}] {row_dict['service']}")
        print(f"   Level: {row_dict['level']}")
        print(f"   Message: {row_dict['message']}")
        print(f"   Status Code: {row_dict['status_code']}")
        print()

    # Query 2: Error counts by service
    print("=" * 80)
    print("QUERY 2: Error Counts by Service")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            service,
            level,
            count(*) as error_count
        FROM logs
        WHERE level IN ('ERROR', 'CRITICAL')
        GROUP BY service, level
        ORDER BY service, level
    """)

    print(f"\nError distribution by service:\n")
    current_service = None
    for row in result.result_rows:
        service, level, count = row
        if service != current_service:
            if current_service is not None:
                print()
            print(f"{service.upper()}:")
            current_service = service
        print(f"  {level}: {count}")

    # Query 3: Recent authentication failures
    print("\n" + "=" * 80)
    print("QUERY 3: Authentication Failures")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            timestamp,
            service,
            message,
            user_id
        FROM logs
        WHERE message LIKE '%Authentication%'
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    print(f"\nFound {len(result.result_rows)} authentication-related issues:\n")
    for i, row in enumerate(result.result_rows, 1):
        row_dict = dict(zip(result.column_names, row))
        print(f"{i}. [{row_dict['timestamp']}] {row_dict['service']}")
        print(f"   Message: {row_dict['message']}")
        print(f"   User ID: {row_dict['user_id']}")
        print()

    # Query 4: High memory warnings
    print("=" * 80)
    print("QUERY 4: High Memory Warnings")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            timestamp,
            service,
            message,
            level
        FROM logs
        WHERE message LIKE '%memory%'
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    print(f"\nFound {len(result.result_rows)} memory-related logs:\n")
    for i, row in enumerate(result.result_rows, 1):
        row_dict = dict(zip(result.column_names, row))
        print(f"{i}. [{row_dict['timestamp']}] {row_dict['service']} - {row_dict['level']}")
        print(f"   Message: {row_dict['message']}")
        print()

    # Query 5: Service crashes
    print("=" * 80)
    print("QUERY 5: Service Crashes")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            timestamp,
            service,
            message,
            level
        FROM logs
        WHERE message LIKE '%crash%'
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    print(f"\nFound {len(result.result_rows)} crash-related logs:\n")
    for i, row in enumerate(result.result_rows, 1):
        row_dict = dict(zip(result.column_names, row))
        print(f"{i}. [{row_dict['timestamp']}] {row_dict['service']} - {row_dict['level']}")
        print(f"   Message: {row_dict['message']}")
        print()

    # Query 6: Slow requests (>4000ms)
    print("=" * 80)
    print("QUERY 6: Slow Requests (>4000ms)")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            timestamp,
            service,
            message,
            duration_ms,
            level
        FROM logs
        WHERE duration_ms > 4000
        ORDER BY duration_ms DESC
        LIMIT 10
    """)

    print(f"\nFound {len(result.result_rows)} slow requests:\n")
    for i, row in enumerate(result.result_rows, 1):
        row_dict = dict(zip(result.column_names, row))
        print(f"{i}. [{row_dict['timestamp']}] {row_dict['service']}")
        print(f"   Duration: {row_dict['duration_ms']}ms")
        print(f"   Level: {row_dict['level']}")
        print(f"   Message: {row_dict['message']}")
        print()

    # Query 7: Database connection pool issues
    print("=" * 80)
    print("QUERY 7: Database Connection Issues")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            timestamp,
            service,
            message,
            level
        FROM logs
        WHERE service = 'database' AND level IN ('ERROR', 'CRITICAL')
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    print(f"\nFound {len(result.result_rows)} database errors:\n")
    for i, row in enumerate(result.result_rows, 1):
        row_dict = dict(zip(result.column_names, row))
        print(f"{i}. [{row_dict['timestamp']}]")
        print(f"   Level: {row_dict['level']}")
        print(f"   Message: {row_dict['message']}")
        print()

    # Query 8: Error trends by hour
    print("=" * 80)
    print("QUERY 8: Error Trends by Hour")
    print("=" * 80)
    result = client.execute_query("""
        SELECT
            toStartOfHour(timestamp) as hour,
            level,
            count(*) as count
        FROM logs
        WHERE level IN ('ERROR', 'CRITICAL')
        GROUP BY hour, level
        ORDER BY hour DESC, level
        LIMIT 20
    """)

    print(f"\nError counts by hour (most recent 20):\n")
    current_hour = None
    for row in result.result_rows:
        hour, level, count = row
        if hour != current_hour:
            if current_hour is not None:
                print()
            print(f"{hour}:")
            current_hour = hour
        print(f"  {level}: {count}")

    print("\n" + "=" * 80)
    print("END OF DEMO QUERIES")
    print("=" * 80)


if __name__ == "__main__":
    try:
        run_demo_queries()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
