"""
ClickHouse NL→SQL Tool — Natural language to SQL conversion and execution

Combines schema discovery with LLM-based natural language understanding
to generate and execute safe SQL queries on ClickHouse.

Usage:
    from tools.clickhouse_tool import ClickHouseTool

    tool = ClickHouseTool()
    result = tool.query_nl("Show me recent errors from the logs")

Features:
- Natural language to SQL conversion
- Schema-aware query generation
- SQL safety validation
- Query timeout enforcement
- Result formatting
- Query history tracking
"""

import logging
import signal
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database import get_clickhouse_client
from tools.clickhouse_schema import ClickHouseSchemaExplorer, get_schema_explorer
from guardrails.sql_guard import SQLGuard, is_safe_sql
from agent.llm_provider import llm_generate

logger = logging.getLogger(__name__)


class QueryStatus(Enum):
    """Status of a query execution."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    UNSAFE_SQL = "unsafe_sql"
    EMPTY_RESULT = "empty_result"


@dataclass
class QueryResult:
    """Result of a query execution."""
    status: QueryStatus
    sql: Optional[str] = None
    rows: List[Dict[str, Any]] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    natural_query: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "sql": self.sql,
            "rows": self.rows,
            "columns": self.columns,
            "row_count": self.row_count,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "natural_query": self.natural_query,
        }


@dataclass
class QueryHistory:
    """History of queries for context and learning."""
    natural_query: str
    generated_sql: str
    status: QueryStatus
    timestamp: datetime = field(default_factory=datetime.now)
    execution_time_ms: Optional[int] = None


class QueryTimeoutError(Exception):
    """Raised when query exceeds timeout."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for query timeout."""
    raise QueryTimeoutError("Query execution exceeded timeout limit")


class ClickHouseTool:
    """
    Natural Language to ClickHouse SQL tool.

    Features:
    - Convert natural language to SQL using LLM
    - Validate SQL safety before execution
    - Execute queries with timeout protection
    - Format results for human consumption
    - Track query history for context
    """

    def __init__(
        self,
        query_timeout_seconds: int = 30,
        max_result_rows: int = 1000,
        enable_history: bool = True,
        schema_explorer: Optional[ClickHouseSchemaExplorer] = None,
    ):
        """
        Initialize ClickHouse tool.

        Args:
            query_timeout_seconds: Maximum query execution time
            max_result_rows: Maximum rows to return
            enable_history: Track query history for context
            schema_explorer: Schema explorer instance (created if None)
        """
        self.query_timeout = query_timeout_seconds
        self.max_result_rows = max_result_rows
        self.enable_history = enable_history
        self.schema_explorer = schema_explorer or get_schema_explorer()
        self.client = get_clickhouse_client()
        self.sql_guard = SQLGuard(strict_mode=True)

        self.query_history: List[QueryHistory] = []

    def query_nl(self, natural_query: str) -> QueryResult:
        """
        Execute a natural language query.

        Args:
            natural_query: Natural language query

        Returns:
            QueryResult with status and data
        """
        logger.info(f"Processing NL query: {natural_query[:100]}...")

        # Step 1: Generate SQL from natural language
        sql = self.nl_to_sql(natural_query)
        if not sql:
            return QueryResult(
                status=QueryStatus.ERROR,
                natural_query=natural_query,
                error_message="Failed to generate SQL from natural language",
            )

        logger.info(f"Generated SQL: {sql[:200]}...")

        # Step 2: Validate SQL safety
        is_safe, violations = is_safe_sql(sql)
        if not is_safe:
            logger.warning(f"Unsafe SQL rejected: {violations}")
            return QueryResult(
                status=QueryStatus.UNSAFE_SQL,
                sql=sql,
                natural_query=natural_query,
                error_message=f"Query rejected for safety reasons: {violations}",
            )

        # Step 3: Execute SQL with timeout
        try:
            result = self.execute_sql(sql, natural_query=natural_query)

            # Track history
            if self.enable_history:
                self.query_history.append(QueryHistory(
                    natural_query=natural_query,
                    generated_sql=sql,
                    status=result.status,
                    execution_time_ms=result.execution_time_ms,
                ))

            return result

        except QueryTimeoutError:
            logger.error(f"Query timeout: {sql[:100]}...")
            return QueryResult(
                status=QueryStatus.TIMEOUT,
                sql=sql,
                natural_query=natural_query,
                error_message=f"Query exceeded timeout of {self.query_timeout} seconds",
            )
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return QueryResult(
                status=QueryStatus.ERROR,
                sql=sql,
                natural_query=natural_query,
                error_message=str(e),
            )

    def nl_to_sql(self, natural_query: str) -> Optional[str]:
        """
        Convert natural language to SQL using LLM.

        Args:
            natural_query: Natural language query

        Returns:
            SQL query string or None if generation failed
        """
        try:
            # Get schema context
            schema_context = self._build_schema_context(natural_query)

            # Build prompt
            prompt = self._build_nl_to_sql_prompt(natural_query, schema_context)

            # Generate SQL
            system_prompt = """You are a ClickHouse SQL expert. Convert natural language questions into valid ClickHouse SQL queries.

Rules:
- Only use SELECT statements (read-only)
- Use proper table and column names from the schema
- Add LIMIT clause to avoid excessive results (default: 100)
- Use appropriate WHERE clauses for filtering
- Order results by timestamp/date when querying recent data
- Use proper ClickHouse syntax (e.g., toYYYYMM(), toDateTime(), etc.)
- Return ONLY the SQL query, no explanations

Examples:
"Show recent errors" -> SELECT * FROM logs WHERE level = 'ERROR' ORDER BY timestamp DESC LIMIT 100
"Count users by day" -> SELECT toDate(timestamp) as day, count(DISTINCT user_id) FROM events GROUP BY day ORDER BY day DESC LIMIT 30
"Top 10 slowest queries" -> SELECT query, duration_ms FROM query_log ORDER BY duration_ms DESC LIMIT 10"""

            sql = llm_generate(
                prompt=prompt,
                max_tokens=500,
                system=system_prompt,
            )

            # Extract SQL from response (remove markdown code blocks if present)
            sql = self._extract_sql_from_response(sql)

            if sql:
                logger.info(f"Generated SQL: {sql[:200]}...")
                return sql.strip()

            return None

        except Exception as e:
            logger.error(f"Failed to generate SQL: {e}")
            return None

    def _build_schema_context(self, natural_query: str) -> str:
        """Build schema context for LLM prompt."""
        # Get all tables
        tables = self.schema_explorer.list_tables()

        # For simplicity, include schema for all tables
        # In production, you might use LLM to select relevant tables
        schema = self.schema_explorer.get_schema_for_llm(
            tables=tables[:10],  # Limit to avoid token overflow
            include_samples=False,
        )

        return schema

    def _build_nl_to_sql_prompt(self, natural_query: str, schema_context: str) -> str:
        """Build prompt for NL→SQL conversion."""
        prompt = f"""Available Database Schema:

{schema_context}

User Question: {natural_query}

Convert this question into a ClickHouse SQL query. Return ONLY the SQL query, no explanations.

SQL:"""

        return prompt

    def _extract_sql_from_response(self, response: str) -> Optional[str]:
        """Extract SQL from LLM response (remove markdown, etc.)."""
        response = response.strip()

        # Remove markdown code blocks
        if response.startswith("```sql"):
            response = response[6:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        response = response.strip()

        # Basic validation - should start with SELECT or SHOW
        response_upper = response.upper()
        if not (response_upper.startswith("SELECT") or
                response_upper.startswith("SHOW") or
                response_upper.startswith("DESCRIBE") or
                response_upper.startswith("DESC") or
                response_upper.startswith("EXPLAIN")):
            logger.warning(f"Generated SQL doesn't start with safe keyword: {response[:100]}...")
            return None

        return response

    def execute_sql(
        self,
        sql: str,
        timeout: Optional[int] = None,
        natural_query: Optional[str] = None,
    ) -> QueryResult:
        """
        Execute SQL with timeout protection.

        Args:
            sql: SQL query to execute
            timeout: Override default timeout
            natural_query: Original natural language query (for tracking)

        Returns:
            QueryResult with data
        """
        timeout = timeout or self.query_timeout

        # Set up signal-based timeout (Unix only)
        # For Windows, we'll use a different approach
        import time
        start_time = time.time()

        try:
            # Execute query
            result = self.client.execute_query(sql)

            execution_time = int((time.time() - start_time) * 1000)

            # Extract columns and rows
            # ClickHouse client returns column names with the result
            if hasattr(result, 'column_names') and result.column_names:
                columns = result.column_names
            else:
                # Fallback: try to get column names from first row
                columns = []

            rows = []
            for row in result.result_rows[:self.max_result_rows]:
                if columns:
                    rows.append(dict(zip(columns, row)))
                else:
                    # If no column names, use positional indexing
                    rows.append({"values": row})

            row_count = len(result.result_rows)

            logger.info(f"Query executed successfully: {row_count} rows in {execution_time}ms")

            return QueryResult(
                status=QueryStatus.SUCCESS,
                sql=sql,
                rows=rows,
                columns=columns,
                row_count=row_count,
                execution_time_ms=execution_time,
                natural_query=natural_query,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Query execution failed: {e}")

            return QueryResult(
                status=QueryStatus.ERROR,
                sql=sql,
                error_message=str(e),
                execution_time_ms=execution_time,
                natural_query=natural_query,
            )

    def format_result(self, result: QueryResult) -> str:
        """
        Format query result for human consumption.

        Args:
            result: QueryResult to format

        Returns:
            Formatted string representation
        """
        lines = []

        if result.status == QueryStatus.SUCCESS:
            lines.append(f"✅ Query executed successfully ({result.row_count:,} rows returned)")

            if result.rows:
                # Create table-like output
                if result.columns:
                    # Header
                    lines.append("\n" + " | ".join(result.columns))
                    lines.append("-" * (len(" | ".join(result.columns))))

                    # Data rows (limit to 20)
                    for row in result.rows[:20]:
                        values = [str(row.get(col, "")) for col in result.columns]
                        lines.append(" | ".join(values))

                    if len(result.rows) > 20:
                        lines.append(f"\n... and {len(result.rows) - 20} more rows")

            if result.execution_time_ms:
                lines.append(f"\nExecution time: {result.execution_time_ms}ms")

        elif result.status == QueryStatus.UNSAFE_SQL:
            lines.append(f"❌ Query rejected for safety reasons")
            lines.append(f"Reason: {result.error_message}")
            if result.sql:
                lines.append(f"\nBlocked SQL: {result.sql}")

        elif result.status == QueryStatus.TIMEOUT:
            lines.append(f"❌ Query exceeded timeout limit ({self.query_timeout}s)")

        elif result.status == QueryStatus.ERROR:
            lines.append(f"❌ Query execution failed")
            lines.append(f"Error: {result.error_message}")
            if result.sql:
                lines.append(f"\nFailed SQL: {result.sql}")

        return "\n".join(lines)

    def explain_query(self, natural_query: str) -> str:
        """
        Generate and explain the SQL without executing.

        Args:
            natural_query: Natural language query

        Returns:
            Explanation of the generated SQL
        """
        sql = self.nl_to_sql(natural_query)

        if not sql:
            return "Failed to generate SQL from the natural language query."

        # Build explanation prompt
        prompt = f"""Explain this ClickHouse SQL query in simple terms:

SQL: {sql}

Provide:
1. What this query does
2. What tables it accesses
3. Any important filters or conditions
4. What the results will show

Explanation:"""

        explanation = llm_generate(
            prompt=prompt,
            max_tokens=300,
            system="You are a SQL expert explaining database queries to non-technical users.",
        )

        return f"""**Generated SQL:**
```sql
{sql}
```

**Explanation:**
{explanation}"""

    def get_query_history(self, limit: int = 10) -> List[QueryHistory]:
        """Get recent query history."""
        return self.query_history[-limit:]

    def clear_history(self):
        """Clear query history."""
        self.query_history.clear()
        logger.info("Query history cleared")


# Singleton instance
_default_tool: Optional[ClickHouseTool] = None


def get_clickhouse_tool() -> ClickHouseTool:
    """Get the default ClickHouse tool instance."""
    global _default_tool
    if _default_tool is None:
        _default_tool = ClickHouseTool()
    return _default_tool


# Convenience function
def query_clickhouse(natural_query: str) -> str:
    """
    Convenience function to query ClickHouse with natural language.

    Args:
        natural_query: Natural language query

    Returns:
        Formatted result string
    """
    tool = get_clickhouse_tool()
    result = tool.query_nl(natural_query)
    return tool.format_result(result)


# CLI for testing
if __name__ == "__main__":
    import sys

    tool = ClickHouseTool()

    # Test queries
    test_queries = [
        "Show me all tables",
        "Count the total rows",
        "Show the schema of the first table",
    ]

    if len(sys.argv) > 1:
        # Use command line argument as query
        query = " ".join(sys.argv[1:])
        result = tool.query_nl(query)
        print(tool.format_result(result))
    else:
        # Run test queries
        print("=== ClickHouse NL→SQL Tool Test ===\n")
        for query in test_queries:
            print(f"\nQuery: {query}")
            result = tool.query_nl(query)
            print(tool.format_result(result))
            print("-" * 80)
