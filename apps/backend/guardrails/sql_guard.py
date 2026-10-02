"""
SQL Safety Guard — AST-based SQL injection prevention

Protects against:
- Destructive operations (DROP, DELETE, TRUNCATE, ALTER)
- Data modification operations (INSERT, UPDATE, CREATE, REPLACE)
- SQL injection via comments
- Multi-statement attacks
- System function abuse
- Information disclosure

Usage:
    from guardrails.sql_guard import SQLGuard, is_safe_sql

    guard = SQLGuard()
    is_safe, reason = guard.is_safe_sql("SELECT * FROM users")
    if not is_safe:
        raise ValueError(f"Unsafe SQL: {reason}")
"""

import logging
import re
from enum import Enum
from typing import List, Optional, Set, Tuple

import sqlparse
from sqlparse.sql import Statement, Token, TokenList
from sqlparse.tokens import DDL, DML, Keyword, Name

logger = logging.getLogger(__name__)


class SQLViolationType(Enum):
    """Types of SQL violations."""
    DESTRUCTIVE_OPERATION = "destructive_operation"
    DATA_MODIFICATION = "data_modification"
    SQL_INJECTION = "sql_injection"
    MULTI_STATEMENT = "multi_statement"
    SYSTEM_FUNCTION = "system_function"
    COMMENT_ABUSE = "comment_abuse"
    UNALLOWED_KEYWORD = "unallowed_keyword"


class SQLViolation:
    """Represents a SQL safety violation."""

    def __init__(
        self,
        violation_type: SQLViolationType,
        reason: str,
        keyword: Optional[str] = None,
        position: Optional[int] = None,
    ):
        self.violation_type = violation_type
        self.reason = reason
        self.keyword = keyword
        self.position = position

    def __str__(self) -> str:
        if self.keyword:
            return f"{self.reason} (found: {self.keyword})"
        return self.reason

    def to_dict(self) -> dict:
        return {
            "type": self.violation_type.value,
            "reason": self.reason,
            "keyword": self.keyword,
            "position": self.position,
        }


class SQLGuard:
    """
    SQL Safety Guard using AST parsing.

    Enforces read-only operations and blocks dangerous SQL patterns.
    """

    # Keywords that are NEVER allowed
    BLOCKED_KEYWORDS: Set[str] = {
        # Destructive DDL
        "DROP", "TRUNCATE", "ALTER",
        # Data modification DML
        "DELETE", "INSERT", "UPDATE", "REPLACE", "MERGE",
        # Database modification
        "CREATE", "TABLE", "VIEW", "INDEX",
        "GRANT", "REVOKE",
        # System operations
        "KILL", "SHUTDOWN", "RESTART",
        # Transaction control (we auto-commit)
        "COMMIT", "ROLLBACK", "BEGIN", "START",
        # File operations
        "LOAD", "LOAD DATA", "LOAD XML",
        "INTO OUTFILE", "INTO DUMPFILE",
    }

    # Keywords that are ALWAYS allowed
    ALLOWED_KEYWORDS: Set[str] = {
        "SELECT", "FROM", "WHERE", "WITH",
        "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS",
        "ON", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN",
        "LIKE", "RLIKE", "REGEXP", "SIMILAR",
        "IS", "NULL", "TRUE", "FALSE",
        "ORDER", "BY", "GROUP", "HAVING",
        "LIMIT", "OFFSET", "TOP", "FETCH",
        "DISTINCT", "ALL", "ANY", "SOME",
        "AS", "CASE", "WHEN", "THEN", "ELSE", "END",
        "UNION", "INTERSECT", "EXCEPT", "MINUS",
        "ASC", "DESC", "NULLS", "FIRST", "LAST",
        # ClickHouse specific (read-only)
        "ARRAY", "ARRAY JOIN", "LEFT ARRAY JOIN",
        "PREWHERE", "SAMPLE", "FINAL",
        # Functions (safe)
        "COUNT", "SUM", "AVG", "MIN", "MAX",
        "STDDEV", "VARIANCE", "MEDIAN",
        # Window functions
        "OVER", "PARTITION", "ROWS", "RANGE",
        # Subqueries
        "SUBSTRING", "TRIM", "UPPER", "LOWER",
        "COALESCE", "NULLIF", "CAST", "CONVERT",
        # Date/Time
        "EXTRACT", "DATE_TRUNC", "NOW", "TODAY",
        # Show/Describe commands
        "SHOW", "DESCRIBE", "DESC", "EXPLAIN",
    }

    # System functions that may leak information
    # These are only blocked when called as functions, not as keywords
    RESTRICTED_FUNCTIONS: Set[str] = {
        "CURRENT_USER", "USER", "SESSION_USER",
        "SYSTEM_USER", "VERSION",
        "SCHEMA", "LOAD_FILE", "BENCHMARK",
    }

    # Patterns that suggest SQL injection
    INJECTION_PATTERNS: List[re.Pattern] = [
        re.compile(r"--", re.IGNORECASE),  # SQL comment
        re.compile(r"/\*.*?\*/", re.DOTALL),  # C-style comment
        re.compile(r";\s*\w", re.IGNORECASE),  # Statement separator
        # NOTE: Removed multiple string literal patterns as they cause false positives
        # with legitimate SQL queries. AST-based checks are more reliable.
        re.compile(r"\\x[0-9a-f]{2}", re.IGNORECASE),  # Hex encoding
        re.compile(r"\\[0-7]{3}", re.IGNORECASE),  # Octal encoding
        re.compile(r"\bor\s+1\s*=\s*1\b", re.IGNORECASE),  # Tautology
        re.compile(r"\bor\s+true\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        allow_multi_statement: bool = False,
        allow_comments: bool = False,
        strict_mode: bool = True,
    ):
        """
        Initialize SQL Guard.

        Args:
            allow_multi_statement: Allow multiple SQL statements in one query
            allow_comments: Allow SQL comments in queries
            strict_mode: If True, reject on any violation. If False, warn only.
        """
        self.allow_multi_statement = allow_multi_statement
        self.allow_comments = allow_comments
        self.strict_mode = strict_mode
        self._violations: List[SQLViolation] = []

    def is_safe_sql(self, sql: str) -> Tuple[bool, List[SQLViolation]]:
        """
        Check if SQL is safe to execute.

        Args:
            sql: SQL query to validate

        Returns:
            Tuple of (is_safe, list_of_violations)
        """
        self._violations = []

        if not sql or not sql.strip():
            self._violations.append(SQLViolation(
                SQLViolationType.SQL_INJECTION,
                "Empty SQL query"
            ))
            return self._get_result()

        # Normalize whitespace
        sql = sql.strip()

        # Check for injection patterns
        self._check_injection_patterns(sql)

        # Check for multiple statements
        self._check_multi_statement(sql)

        # Parse and check AST
        self._check_ast(sql)

        # Check for restricted functions
        self._check_restricted_functions(sql)

        return self._get_result()

    def _get_result(self) -> Tuple[bool, List[SQLViolation]]:
        """Return the result of validation."""
        is_safe = len(self._violations) == 0
        return is_safe, self._violations

    def _add_violation(self, violation_type: SQLViolationType, reason: str, **kwargs):
        """Add a violation to the list."""
        self._violations.append(SQLViolation(violation_type, reason, **kwargs))
        if self.strict_mode:
            logger.warning(f"SQL Guard violation: {reason}")

    def _check_injection_patterns(self, sql: str):
        """Check for SQL injection patterns."""
        # Check for comments
        if not self.allow_comments:
            if "--" in sql or "/*" in sql:
                self._add_violation(
                    SQLViolationType.COMMENT_ABUSE,
                    "SQL comments are not allowed",
                )

        # Check injection patterns
        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(sql):
                self._add_violation(
                    SQLViolationType.SQL_INJECTION,
                    f"Potential SQL injection detected: {pattern.pattern}",
                )

    def _check_multi_statement(self, sql: str):
        """Check for multiple statements."""
        if self.allow_multi_statement:
            return

        # Simple check for semicolon outside of string literals
        # A more robust check would require parsing
        statements = sqlparse.parse(sql)
        if len(statements) > 1:
            self._add_violation(
                SQLViolationType.MULTI_STATEMENT,
                f"Multiple SQL statements detected ({len(statements)}). Only single-statement queries are allowed.",
            )

    def _check_ast(self, sql: str):
        """Check SQL AST for dangerous operations."""
        try:
            statements = sqlparse.parse(sql)

            for statement in statements:
                self._check_statement(statement)

        except Exception as e:
            logger.warning(f"Failed to parse SQL AST: {e}")
            # If we can't parse it, be conservative and reject
            self._add_violation(
                SQLViolationType.SQL_INJECTION,
                f"Unable to parse SQL: {str(e)}",
            )

    def _check_statement(self, statement: Statement):
        """Check a single SQL statement."""
        tokens = list(statement.flatten())

        for i, token in enumerate(tokens):
            token_value = token.value.upper().strip()

            # Skip whitespace and non-keywords
            if not token_value or token.ttype is None:
                continue

            # Check for blocked keywords
            if token_value in self.BLOCKED_KEYWORDS:
                # Check if it's actually being used as a keyword (not a column/table name)
                if self._is_keyword_context(token, tokens, i):
                    self._add_violation(
                        SQLViolationType.DESTRUCTIVE_OPERATION
                        if token_value in ("DROP", "TRUNCATE", "ALTER")
                        else SQLViolationType.DATA_MODIFICATION,
                        "Dangerous SQL operation detected",
                        keyword=token_value,
                    )

    def _is_keyword_context(self, token: Token, tokens: List[Token], index: int) -> bool:
        """
        Check if a token is being used as a keyword vs. an identifier.

        This is a simplified check. A production implementation would need
        more sophisticated context analysis.
        """
        # If it's explicitly a keyword/DML/DDL type, it's definitely a keyword
        if token.ttype in (Keyword, DML, DDL):
            return True

        # Check if it's at the beginning of the statement (likely a keyword)
        # or preceded by certain keywords
        if index == 0:
            return True

        # Check preceding tokens
        if index > 0:
            prev_token = tokens[index - 1]
            if prev_token.ttype in (Keyword, DML, DDL):
                # Previous was a keyword, this is likely also a keyword
                return True

        return False

    def _check_restricted_functions(self, sql: str):
        """Check for restricted system functions."""
        sql_upper = sql.upper()

        for func in self.RESTRICTED_FUNCTIONS:
            # Look for function call pattern: FUNCTION_NAME(
            pattern = f"{func}\\s*\\("
            if re.search(pattern, sql_upper):
                self._add_violation(
                    SQLViolationType.SYSTEM_FUNCTION,
                    f"Restricted function not allowed: {func}",
                    keyword=func,
                )


# Singleton instance
_default_guard: Optional[SQLGuard] = None


def get_sql_guard() -> SQLGuard:
    """Get the default SQL guard instance."""
    global _default_guard
    if _default_guard is None:
        _default_guard = SQLGuard()
    return _default_guard


def is_safe_sql(sql: str, strict: bool = True) -> Tuple[bool, str]:
    """
    Convenience function to check if SQL is safe.

    Args:
        sql: SQL query to validate
        strict: If True, reject on any violation

    Returns:
        Tuple of (is_safe, reason_message)
    """
    guard = SQLGuard(strict_mode=strict)
    is_safe, violations = guard.is_safe_sql(sql)

    if not is_safe:
        reasons = "; ".join(str(v) for v in violations)
        return False, reasons

    return True, ""


def validate_and_sanitize_sql(
    sql: str,
    allowed_keywords: Optional[Set[str]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate SQL and return a sanitized version.

    Args:
        sql: SQL query to validate
        allowed_keywords: Additional keywords to allow beyond defaults

    Returns:
        Tuple of (is_safe, error_message, sanitized_sql)
    """
    # Remove comments if not allowed
    sanitized = sql.strip()

    # Remove SQL comments
    sanitized = re.sub(r"--.*?\n", "\n", sanitized)
    sanitized = re.sub(r"/\*.*?\*/", "", sanitized, flags=re.DOTALL)
    sanitized = re.sub(r"#.*?\n", "\n", sanitized)

    # Check safety
    is_safe, violations = is_safe_sql(sanitized)

    if not is_safe:
        return False, "; ".join(str(v) for v in violations), None

    return True, "", sanitized


# CLI for testing
if __name__ == "__main__":
    import sys

    test_queries = [
        "SELECT * FROM users WHERE id = 1",  # Safe
        "SELECT name FROM users ORDER BY created_at DESC LIMIT 10",  # Safe
        "DROP TABLE users",  # Unsafe - destructive
        "DELETE FROM users WHERE id = 1",  # Unsafe - data modification
        "SELECT * FROM users WHERE name = '' OR 1=1 --",  # Unsafe - injection
        "SELECT * FROM users; DROP TABLE users;",  # Unsafe - multi-statement
        "SHOW TABLES",  # Safe
        "DESCRIBE users",  # Safe
        "INSERT INTO users VALUES (1, 'test')",  # Unsafe - data modification
    ]

    guard = SQLGuard()

    for query in test_queries:
        is_safe, violations = guard.is_safe_sql(query)
        status = "[OK] SAFE" if is_safe else "[ERROR] UNSAFE"
        print(f"\n{status}: {query[:60]}")
        if violations:
            for v in violations:
                print(f"   → {v}")
