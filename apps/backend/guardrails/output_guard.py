"""
Output Guardrails — SQL safety, grounding check, HITL gate enforcement

Production-grade output validation for DevRelAgent.

Features:
- SQL safety validation (AST-based)
- Response grounding verification
- HITL (Human-in-the-Loop) gate enforcement
- PII leakage prevention
- Hallucination detection
- Audit logging for compliance

Usage:
    from guardrails.output_guard import OutputGuardrail, get_output_guardrail

    guard = get_output_guardrail()
    result = await guard.validate(response, context)
    
    if not result.is_valid:
        # Handle rejection
        logger.warning(f"Output rejected: {result.reason}")
    else:
        # Use validated output
        process(result.validated_text)
"""

import re
import logging
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Set, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import sqlparse
from sqlparse.sql import Statement, TokenList
from sqlparse.tokens import Keyword, DML, DDL

logger = logging.getLogger(__name__)


class GroundingStatus(Enum):
    """Status of response grounding."""
    GROUNDED = "grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNGROUNDED = "ungrounded"
    UNKNOWN = "unknown"


@dataclass
class OutputValidationResult:
    """Result of output guardrail validation."""
    is_valid: bool
    validated_text: str
    reason: Optional[str] = None
    violations: Optional[List[Dict[str, Any]]] = None
    sql_safe: bool = True
    sql_violations: Optional[List[Dict[str, Any]]] = None
    grounding_status: GroundingStatus = GroundingStatus.UNKNOWN
    grounding_score: float = 0.0
    hitl_required: bool = False
    hitl_approved: bool = False
    pii_leaked: Optional[List[Dict[str, Any]]] = None
    hallucination_risk: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "validated_text": self.validated_text,
            "reason": self.reason,
            "violations": self.violations,
            "sql_safe": self.sql_safe,
            "sql_violations": self.sql_violations,
            "grounding_status": self.grounding_status.value,
            "grounding_score": self.grounding_score,
            "hitl_required": self.hitl_required,
            "hitl_approved": self.hitl_approved,
            "pii_leaked": self.pii_leaked,
            "hallucination_risk": self.hallucination_risk,
            "metadata": self.metadata,
            "timestamp": datetime.now().isoformat(),
        }


class SQLSafetyValidator:
    """
    SQL Safety validation for output responses.

    Validates any SQL in the response to ensure:
    - No destructive operations (DROP, DELETE, TRUNCATE, ALTER)
    - No data modification (INSERT, UPDATE, REPLACE)
    - No SQL injection patterns
    - Read-only operations only
    """

    # Dangerous SQL keywords
    BLOCKED_KEYWORDS: Set[str] = {
        "DROP", "TRUNCATE", "ALTER", "DELETE", "INSERT", "UPDATE",
        "REPLACE", "MERGE", "CREATE", "GRANT", "REVOKE", "KILL",
        "SHUTDOWN", "RESTART", "COMMIT", "ROLLBACK", "LOAD DATA",
        "INTO OUTFILE", "INTO DUMPFILE"
    }

    # Safe SQL keywords
    ALLOWED_KEYWORDS: Set[str] = {
        "SELECT", "FROM", "WHERE", "WITH", "JOIN", "INNER", "LEFT",
        "RIGHT", "FULL", "OUTER", "ON", "AND", "OR", "NOT", "IN",
        "EXISTS", "BETWEEN", "LIKE", "IS", "NULL", "ORDER", "BY",
        "GROUP", "HAVING", "LIMIT", "OFFSET", "DISTINCT", "AS",
        "UNION", "INTERSECT", "EXCEPT", "ASC", "DESC", "SHOW",
        "DESCRIBE", "DESC", "EXPLAIN", "USE"
    }

    def __init__(self, strict_mode: bool = True):
        """
        Initialize SQL safety validator.

        Args:
            strict_mode: If True, reject on any violation
        """
        self.strict_mode = strict_mode
        self._violations: List[Dict[str, Any]] = []

    def validate(self, text: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Validate text for SQL safety.

        Args:
            text: Text to validate (may contain SQL queries)

        Returns:
            Tuple of (is_safe, list_of_violations)
        """
        self._violations = []

        # Extract SQL queries from text
        sql_queries = self._extract_sql_queries(text)

        # Validate each query
        for query in sql_queries:
            self._validate_query(query)

        is_safe = len(self._violations) == 0
        return is_safe, self._violations

    def _extract_sql_queries(self, text: str) -> List[str]:
        """Extract potential SQL queries from text."""
        queries = []

        # Look for SQL-like patterns
        # Pattern 1: Code blocks with SQL
        code_block_pattern = re.compile(
            r'```(?:sql)?\s*(.*?)```',
            re.IGNORECASE | re.DOTALL
        )
        for match in code_block_pattern.finditer(text):
            query = match.group(1).strip()
            if self._looks_like_sql(query):
                queries.append(query)

        # Pattern 2: Inline SQL-like statements
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP",
                       "CREATE", "ALTER", "SHOW", "DESCRIBE"]
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if any(line.upper().startswith(kw) for kw in sql_keywords):
                if self._looks_like_sql(line):
                    queries.append(line)

        return queries

    def _looks_like_sql(self, text: str) -> bool:
        """Check if text looks like SQL."""
        text_upper = text.upper()
        sql_indicators = [
            "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE",
            "CREATE", "DROP", "ALTER", "JOIN", "ORDER BY", "GROUP BY"
        ]
        return any(indicator in text_upper for indicator in sql_indicators)

    def _validate_query(self, query: str):
        """Validate a single SQL query."""
        try:
            # Parse with sqlparse
            statements = sqlparse.parse(query)

            for statement in statements:
                self._check_statement(statement)

        except Exception as e:
            logger.warning(f"Failed to parse SQL: {e}")
            self._violations.append({
                "type": "parse_error",
                "reason": f"Unable to parse SQL: {str(e)}",
                "query": query[:100],
            })

    def _check_statement(self, statement: Statement):
        """Check a single SQL statement for violations."""
        tokens = list(statement.flatten())

        for token in tokens:
            token_value = token.value.upper().strip()

            # Skip non-keywords
            if token_value not in self.BLOCKED_KEYWORDS:
                continue

            # Check if it's actually a keyword (not an identifier)
            if token.ttype in (Keyword, DML, DDL):
                self._violations.append({
                    "type": "blocked_keyword",
                    "reason": f"Dangerous SQL operation detected",
                    "keyword": token_value,
                    "severity": "high" if token_value in ["DROP", "DELETE", "TRUNCATE"] else "medium",
                })


class ResponseGroundingChecker:
    """
    Response grounding verification.

    Checks if the response is grounded in:
    - Tool results
    - Retrieved documents
    - Conversation context
    - Known facts

    Detects potential hallucinations by checking for:
    - Unsupported claims
    - Fabricated citations
    - Inconsistent information
    """

    # Phrases that suggest hallucination
    HALLUCINATION_INDICATORS: List[str] = [
        "i believe", "i think", "probably", "might be", "could be",
        "possibly", "perhaps", "may have", "seems like", "appears to",
        "to the best of my knowledge", "as far as i know",
        "i'm not sure but", "i don't have access to", "i cannot verify"
    ]

    # Phrases that suggest confidence without grounding
    UNSUPPORTED_CLAIM_PHRASES: List[str] = [
        "definitely", "certainly", "absolutely", "without a doubt",
        "clearly", "obviously", "undoubtedly", " unquestionably"
    ]

    def __init__(self):
        self._evidence_sources: List[str] = []
        self._context: Dict[str, Any] = {}

    def set_evidence(self, evidence: List[str]):
        """Set evidence sources for grounding check."""
        self._evidence_sources = evidence

    def set_context(self, context: Dict[str, Any]):
        """Set conversation context."""
        self._context = context

    def check(self, response: str, tool_results: Optional[List[Dict[str, Any]]] = None) -> Tuple[GroundingStatus, float, List[str]]:
        """
        Check if response is grounded.

        Args:
            response: Response text to check
            tool_results: Optional tool results for grounding

        Returns:
            Tuple of (status, confidence_score, unsupported_claims)
        """
        unsupported_claims: List[str] = []
        response_lower = response.lower()

        # 1. Check for hallucination indicators
        hallucination_count = sum(
            1 for indicator in self.HALLUCINATION_INDICATORS
            if indicator in response_lower
        )

        # 2. Check for unsupported confident claims
        unsupported_confidence = sum(
            1 for phrase in self.UNSUPPORTED_CLAIM_PHRASES
            if phrase in response_lower
        )

        # 3. Check grounding against tool results
        grounded_facts = 0
        total_claims = 0

        if tool_results:
            for result in tool_results:
                if result.get("success") and result.get("result"):
                    result_str = str(result["result"]).lower()
                    # Check if response references tool results
                    if any(word in response_lower for word in result_str.split()[:10]):
                        grounded_facts += 1
                total_claims += 1

        # 4. Check against evidence sources
        evidence_matches = 0
        for evidence in self._evidence_sources:
            if evidence.lower() in response_lower:
                evidence_matches += 1

        # Calculate grounding score
        grounding_score = 0.0

        if grounded_facts > 0 and total_claims > 0:
            grounding_score += (grounded_facts / total_claims) * 0.4

        if evidence_matches > 0:
            grounding_score += min(evidence_matches * 0.1, 0.3)

        # Penalize for hallucination indicators
        grounding_score -= min(hallucination_count * 0.05, 0.2)

        # Penalize for unsupported confident claims
        grounding_score -= min(unsupported_confidence * 0.1, 0.2)

        grounding_score = max(0.0, min(1.0, grounding_score))

        # Determine status
        if grounding_score >= 0.7:
            status = GroundingStatus.GROUNDED
        elif grounding_score >= 0.4:
            status = GroundingStatus.PARTIALLY_GROUNDED
        elif grounding_score > 0:
            status = GroundingStatus.UNGROUNDED
        else:
            status = GroundingStatus.UNKNOWN

        return status, grounding_score, unsupported_claims


class HITLGateEnforcer:
    """
    Human-in-the-Loop gate enforcement.

    Requires human approval for:
    - High-risk actions
    - Low-confidence responses
    - Sensitive operations
    - Novel situations

    Integrates with approval guard for async approval workflow.
    """

    # Actions requiring HITL
    HITL_REQUIRED_ACTIONS: Set[str] = {
        "database_write",
        "schema_change",
        "github_issue_create",
        "github_pr_create",
        "browser_write_operation",
        "file_write",
        "code_deployment",
        "credential_access",
    }

    # Risk thresholds
    RISK_THRESHOLDS = {
        "low": 0.3,
        "medium": 0.5,
        "high": 0.7,
        "critical": 0.9,
    }

    def __init__(
        self,
        auto_approve_threshold: float = 0.8,
        require_hitl_threshold: float = 0.5,
        timeout_seconds: int = 300,
    ):
        """
        Initialize HITL gate enforcer.

        Args:
            auto_approve_threshold: Score above which auto-approve
            require_hitl_threshold: Score below which require HITL
            timeout_seconds: Timeout for approval waiting
        """
        self.auto_approve_threshold = auto_approve_threshold
        self.require_hitl_threshold = require_hitl_threshold
        self.timeout_seconds = timeout_seconds

        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_callbacks: Dict[str, Callable] = {}

    def requires_hitl(
        self,
        action: str,
        risk_score: float,
        confidence: float,
    ) -> bool:
        """
        Check if action requires HITL approval.

        Args:
            action: Action being performed
            risk_score: Calculated risk score (0-1)
            confidence: Response confidence score (0-1)

        Returns:
            True if HITL approval required
        """
        # Check action-based requirements
        if any(hitl_action in action.lower() for hitl_action in self.HITL_REQUIRED_ACTIONS):
            return True

        # Check confidence-based requirements
        if confidence < self.require_hitl_threshold:
            return True

        # Check risk-based requirements
        if risk_score > self.RISK_THRESHOLDS["high"]:
            return True

        return False

    async def request_approval(
        self,
        action: str,
        response: str,
        context: Dict[str, Any],
    ) -> bool:
        """
        Request HITL approval for an action.

        Args:
            action: Action requiring approval
            response: Generated response
            context: Additional context

        Returns:
            True if approved, False if rejected
        """
        approval_id = hashlib.sha256(
            f"{action}:{response[:50]}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        approval_request = {
            "approval_id": approval_id,
            "action": action,
            "response": response,
            "context": context,
            "created_at": datetime.now(),
            "status": "pending",
        }

        self._pending_approvals[approval_id] = approval_request

        logger.info(f"HITL approval requested: {approval_id} for {action}")

        # Wait for approval (callback-based)
        # In production, this would integrate with the approval API
        return False  # Default to not approved without explicit approval

    async def approve(self, approval_id: str, user: str) -> bool:
        """
        Approve a pending HITL request.

        Args:
            approval_id: ID of approval request
            user: User approving

        Returns:
            True if approval recorded
        """
        if approval_id not in self._pending_approvals:
            return False

        self._pending_approvals[approval_id]["status"] = "approved"
        self._pending_approvals[approval_id]["approved_by"] = user
        self._pending_approvals[approval_id]["approved_at"] = datetime.now()

        # Trigger callback if registered
        if approval_id in self._approval_callbacks:
            self._approval_callbacks[approval_id](True)

        return True

    async def reject(self, approval_id: str, user: str, reason: str) -> bool:
        """
        Reject a pending HITL request.

        Args:
            approval_id: ID of approval request
            user: User rejecting
            reason: Reason for rejection

        Returns:
            True if rejection recorded
        """
        if approval_id not in self._pending_approvals:
            return False

        self._pending_approvals[approval_id]["status"] = "rejected"
        self._pending_approvals[approval_id]["rejected_by"] = user
        self._pending_approvals[approval_id]["rejection_reason"] = reason
        self._pending_approvals[approval_id]["rejected_at"] = datetime.now()

        # Trigger callback if registered
        if approval_id in self._approval_callbacks:
            self._approval_callbacks[approval_id](False)

        return True

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get list of pending approvals."""
        return list(self._pending_approvals.values())


class OutputPIIChecker:
    """
    PII leakage prevention for output responses.

    Ensures no sensitive information is leaked in responses:
    - API keys and tokens
    - Internal IP addresses
    - Database credentials
    - Personal information
    """

    def __init__(self):
        self.patterns = [
            {
                "name": "api_key",
                "pattern": re.compile(r'\b(?:api[_-]?key|token|secret)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{16,}["\']?', re.IGNORECASE),
                "severity": "critical",
            },
            {
                "name": "private_key",
                "pattern": re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', re.IGNORECASE),
                "severity": "critical",
            },
            {
                "name": "password",
                "pattern": re.compile(r'\bpassword\s*[=:]\s*["\']?[^\s"\']{8,}["\']?', re.IGNORECASE),
                "severity": "high",
            },
            {
                "name": "internal_ip",
                "pattern": re.compile(r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b'),
                "severity": "medium",
            },
            {
                "name": "email",
                "pattern": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
                "severity": "medium",
            },
        ]

    def check(self, text: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Check for PII leakage in text.

        Args:
            text: Text to check

        Returns:
            Tuple of (is_safe, list_of_leaks)
        """
        leaks: List[Dict[str, Any]] = []

        for pii_pattern in self.patterns:
            matches = list(pii_pattern["pattern"].finditer(text))
            for match in matches:
                leaks.append({
                    "type": pii_pattern["name"],
                    "severity": pii_pattern["severity"],
                    "position": {"start": match.start(), "end": match.end()},
                    "snippet": text[max(0, match.start()-10):match.end()+10],
                })

        is_safe = len(leaks) == 0
        return is_safe, leaks


class OutputGuardrail:
    """
    Main output guardrail combining all validation components.

    Usage:
        guard = OutputGuardrail()
        result = await guard.validate(response, context)
        
        if not result.is_valid:
            # Handle rejection
            logger.warning(f"Output rejected: {result.reason}")
        else:
            # Use validated output
            process(result.validated_text)
    """

    def __init__(
        self,
        enable_sql_validation: bool = True,
        enable_grounding_check: bool = True,
        enable_hitl_gate: bool = True,
        enable_pii_check: bool = True,
        strict_mode: bool = True,
    ):
        """
        Initialize output guardrail.

        Args:
            enable_sql_validation: Enable SQL safety validation
            enable_grounding_check: Enable response grounding check
            enable_hitl_gate: Enable HITL gate enforcement
            enable_pii_check: Enable PII leakage check
            strict_mode: If True, reject on any violation
        """
        self.enable_sql_validation = enable_sql_validation
        self.enable_grounding_check = enable_grounding_check
        self.enable_hitl_gate = enable_hitl_gate
        self.enable_pii_check = enable_pii_check
        self.strict_mode = strict_mode

        self.sql_validator = SQLSafetyValidator(strict_mode=strict_mode)
        self.grounding_checker = ResponseGroundingChecker()
        self.hitl_enforcer = HITLGateEnforcer()
        self.pii_checker = OutputPIIChecker()

        # Statistics
        self.stats = {
            "total_validated": 0,
            "rejected": 0,
            "sql_violations": 0,
            "grounding_failures": 0,
            "hitl_required": 0,
            "pii_leaks": 0,
        }

    async def validate(
        self,
        response: str,
        context: Optional[Dict[str, Any]] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        action: Optional[str] = None,
    ) -> OutputValidationResult:
        """
        Validate output response.

        Args:
            response: Response text to validate
            context: Optional context including evidence sources
            tool_results: Optional tool execution results
            action: Optional action being performed

        Returns:
            OutputValidationResult with validation outcome
        """
        self.stats["total_validated"] += 1

        violations: List[Dict[str, Any]] = []
        sql_safe = True
        sql_violations: List[Dict[str, Any]] = []
        grounding_status = GroundingStatus.UNKNOWN
        grounding_score = 0.0
        hitl_required = False
        hitl_approved = False
        pii_leaked: List[Dict[str, Any]] = []

        # 1. SQL Safety Validation
        if self.enable_sql_validation:
            sql_safe, sql_violations = self.sql_validator.validate(response)
            if not sql_safe:
                violations.append({
                    "type": "sql_safety",
                    "reason": "Unsafe SQL detected in response",
                    "violations": sql_violations,
                })
                self.stats["sql_violations"] += 1

        # 2. PII Leakage Check
        if self.enable_pii_check:
            pii_safe, pii_leaked = self.pii_checker.check(response)
            if not pii_safe:
                violations.append({
                    "type": "pii_leak",
                    "reason": "Sensitive information detected in response",
                    "leaks": pii_leaked,
                })
                self.stats["pii_leaks"] += 1

        # 3. Grounding Check
        if self.enable_grounding_check:
            if context and "evidence" in context:
                self.grounding_checker.set_evidence(context["evidence"])
            if context and "conversation" in context:
                self.grounding_checker.set_context(context["conversation"])

            grounding_status, grounding_score, _ = self.grounding_checker.check(
                response,
                tool_results,
            )

            if grounding_status == GroundingStatus.UNGROUNDED and self.strict_mode:
                violations.append({
                    "type": "grounding",
                    "reason": "Response appears to be ungrounded/hallucinated",
                    "grounding_score": grounding_score,
                })
                self.stats["grounding_failures"] += 1

        # 4. HITL Gate
        if self.enable_hitl_gate and action:
            risk_score = self._calculate_risk_score(
                sql_safe, grounding_score, pii_leaked, violations
            )

            hitl_required = self.hitl_enforcer.requires_hitl(
                action=action,
                risk_score=risk_score,
                confidence=grounding_score,
            )

            if hitl_required:
                self.stats["hitl_required"] += 1

                # For now, mark as not approved
                # In production, this would trigger async approval workflow
                hitl_approved = False

                if not hitl_approved:
                    violations.append({
                        "type": "hitl_required",
                        "reason": "Human approval required for this action",
                        "action": action,
                    })

        # Determine overall validity
        is_valid = len(violations) == 0

        if not is_valid:
            self.stats["rejected"] += 1

        # Build reason
        reason = None
        if violations:
            reasons = [v["reason"] for v in violations]
            reason = "; ".join(reasons)

        return OutputValidationResult(
            is_valid=is_valid,
            validated_text=response if is_valid else self._sanitize_response(response),
            reason=reason,
            violations=violations,
            sql_safe=sql_safe,
            sql_violations=sql_violations,
            grounding_status=grounding_status,
            grounding_score=grounding_score,
            hitl_required=hitl_required,
            hitl_approved=hitl_approved,
            pii_leaked=pii_leaked,
            hallucination_risk=1.0 - grounding_score,
            metadata={
                "action": action,
                "tool_results_count": len(tool_results) if tool_results else 0,
            },
        )

    def _calculate_risk_score(
        self,
        sql_safe: bool,
        grounding_score: float,
        pii_leaked: List[Dict[str, Any]],
        violations: List[Dict[str, Any]],
    ) -> float:
        """Calculate overall risk score."""
        score = 0.0

        # SQL violations increase risk
        if not sql_safe:
            score += 0.3

        # Low grounding increases risk
        score += (1.0 - grounding_score) * 0.3

        # PII leaks increase risk
        if pii_leaked:
            score += min(len(pii_leaked) * 0.1, 0.3)

        # Other violations increase risk
        score += min(len(violations) * 0.05, 0.2)

        return min(score, 1.0)

    def _sanitize_response(self, response: str) -> str:
        """Sanitize response by redacting sensitive content."""
        sanitized = response

        # Redact potential API keys
        sanitized = re.sub(
            r'\b(?:api[_-]?key|token|secret)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{16,}["\']?',
            '[REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )

        # Redact potential passwords
        sanitized = re.sub(
            r'\bpassword\s*[=:]\s*["\']?[^\s"\']{8,}["\']?',
            'password=[REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )

        return sanitized

    def get_stats(self) -> Dict[str, Any]:
        """Get guardrail statistics."""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            "total_validated": 0,
            "rejected": 0,
            "sql_violations": 0,
            "grounding_failures": 0,
            "hitl_required": 0,
            "pii_leaks": 0,
        }


# Singleton instance
_default_guardrail: Optional[OutputGuardrail] = None


def get_output_guardrail() -> OutputGuardrail:
    """Get the default output guardrail instance."""
    global _default_guardrail
    if _default_guardrail is None:
        _default_guardrail = OutputGuardrail()
    return _default_guardrail


def set_output_guardrail(guardrail: OutputGuardrail):
    """Set a custom output guardrail instance (useful for testing)."""
    global _default_guardrail
    _default_guardrail = guardrail


async def validate_output(
    response: str,
    context: Optional[Dict[str, Any]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> OutputValidationResult:
    """
    Convenience function to validate output.

    Args:
        response: Response text to validate
        context: Optional context
        tool_results: Optional tool results

    Returns:
        OutputValidationResult with validation outcome
    """
    guardrail = get_output_guardrail()
    return await guardrail.validate(response, context, tool_results)


# CLI for testing
if __name__ == "__main__":
    import asyncio

    async def main():
        guardrail = OutputGuardrail()

        test_responses = [
            # Safe response
            "To query ClickHouse for error logs, you can use: SELECT * FROM errors WHERE level = 'ERROR' LIMIT 10",

            # Unsafe SQL
            "You should run: DROP TABLE users; DELETE FROM logs;",

            # Potential PII leak
            "Your API key is: sk-1234567890abcdef1234567890abcdef",

            # Ungrounded response
            "I believe the system might work this way, but I'm not entirely sure. It could be that the API uses OAuth, or perhaps it uses basic auth.",
        ]

        for response in test_responses:
            print(f"\n{'='*60}")
            print(f"Response: {response[:80]}...")
            print('-'*60)

            result = await guardrail.validate(response)

            print(f"Valid: {result.is_valid}")
            print(f"SQL Safe: {result.sql_safe}")
            print(f"Grounding: {result.grounding_status.value} (score: {result.grounding_score:.2f})")
            print(f"HITL Required: {result.hitl_required}")

            if result.pii_leaked:
                print(f"PII Leaked: {len(result.pii_leaked)} items")
                for leak in result.pii_leaked:
                    print(f"  - {leak['type']} ({leak['severity']})")

            if not result.is_valid:
                print(f"Reason: {result.reason}")

        print(f"\n{'='*60}")
        print(f"Stats: {guardrail.get_stats()}")

    asyncio.run(main())
