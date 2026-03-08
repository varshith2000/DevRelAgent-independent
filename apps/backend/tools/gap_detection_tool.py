"""
Gap Detection Tool — Automatic Documentation Gap Detection

Detects gaps in documentation and knowledge base.
Optionally creates tickets for missing content.
"""

import logging
from typing import Dict, Any, List, Optional, Literal, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from tools.registry import tool, ToolCategory

logger = logging.getLogger(__name__)


# ============== Data Structures ==============

class GapType(str, Enum):
    """Types of documentation gaps."""
    MISSING_API_ENDPOINT = "missing_api_endpoint"
    MISSING_CONFIG_EXAMPLE = "missing_config_example"
    MISSING_ERROR_EXPLANATION = "missing_error_explanation"
    MISSING_AUTH_GUIDE = "missing_auth_guide"
    OUTDATED_CONTENT = "outdated_content"
    INCOMPLETE_TUTORIAL = "incomplete_tutorial"
    MISSING_CODE_EXAMPLE = "missing_code_example"
    MISSING_DEPLOYMENT_GUIDE = "missing_deployment_guide"


class GapSeverity(str, Enum):
    """Severity levels for gaps."""
    CRITICAL = "critical"  # Blocks users completely
    HIGH = "high"  # Major impact on user experience
    MEDIUM = "medium"  # Moderate impact
    LOW = "low"  # Minor improvement opportunity


@dataclass
class DocumentationGap:
    """Represents a documentation gap."""
    gap_type: GapType
    severity: GapSeverity
    title: str
    description: str
    location: Optional[str]  # Where this gap was detected
    suggested_content: Optional[str]
    related_services: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gap_type": self.gap_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "suggested_content": self.suggested_content,
            "related_services": self.related_services,
            "evidence": self.evidence,
            "detected_at": self.detected_at.isoformat()
        }


# ============== Gap Detection Logic ==============

class GapDetector:
    """Detects documentation gaps using deterministic rules."""

    # Known services and their expected documentation
    EXPECTED_API_ENDPOINTS = {
        "api": ["/health", "/metrics", "/api/users", "/api/auth"],
        "database": ["/query", "/schema", "/health"],
        "cache": ["/get", "/set", "/delete", "/health"]
    }

    EXPECTED_CONFIG_PARAMS = {
        "database": ["host", "port", "username", "password", "database"],
        "api": ["port", "cors_origins", "auth_secret"],
        "cache": ["host", "port", "ttl"]
    }

    COMMON_ERROR_CODES = [400, 401, 403, 404, 500, 502, 503]

    def __init__(self, indexed_docs: Dict[str, Any], service_list: List[str]):
        """
        Initialize gap detector.

        Args:
            indexed_docs: Dictionary of indexed documentation
            service_list: List of known services
        """
        self.indexed_docs = indexed_docs
        self.service_list = service_list
        self.detected_gaps: List[DocumentationGap] = []

    def detect_all_gaps(self) -> List[DocumentationGap]:
        """Detect all types of documentation gaps."""
        self.detected_gaps = []

        self._detect_missing_api_endpoints()
        self._detect_missing_config_examples()
        self._detect_missing_error_explanations()
        self._detect_missing_auth_guides()
        self._detect_outdated_content()
        self._detect_incomplete_tutorials()
        self._detect_missing_code_examples()
        self._detect_missing_deployment_guides()

        return self.detected_gaps

    def _detect_missing_api_endpoints(self):
        """Detect missing API endpoint documentation."""
        for service, expected_endpoints in self.EXPECTED_API_ENDPOINTS.items():
            if service not in self.service_list:
                continue

            service_docs = self.indexed_docs.get(service, {})
            documented_endpoints = set()

            # Extract documented endpoints from docs
            for doc in service_docs.values():
                content = str(doc).lower()
                for endpoint in expected_endpoints:
                    if endpoint.lower() in content:
                        documented_endpoints.add(endpoint)

            # Find missing endpoints
            missing = set(expected_endpoints) - documented_endpoints
            if missing:
                self.detected_gaps.append(
                    DocumentationGap(
                        gap_type=GapType.MISSING_API_ENDPOINT,
                        severity=GapSeverity.HIGH,
                        title=f"Missing API endpoint documentation for {service}",
                        description=f"The following API endpoints are not documented: {', '.join(missing)}",
                        location=f"Service: {service}",
                        suggested_content=f"Add documentation for endpoints: {', '.join(missing)}",
                        related_services=[service],
                        evidence=[f"Expected endpoints: {expected_endpoints}", f"Documented: {documented_endpoints}"]
                    )
                )

    def _detect_missing_config_examples(self):
        """Detect missing configuration examples."""
        for service, expected_params in self.EXPECTED_CONFIG_PARAMS.items():
            service_docs = self.indexed_docs.get(service, {})

            # Check for config examples
            has_config_example = False
            for doc in service_docs.values():
                content = str(doc).lower()
                if any(param in content for param in expected_params):
                    has_config_example = True
                    break

            if not has_config_example:
                self.detected_gaps.append(
                    DocumentationGap(
                        gap_type=GapType.MISSING_CONFIG_EXAMPLE,
                        severity=GapSeverity.MEDIUM,
                        title=f"Missing configuration example for {service}",
                        description=f"No configuration example found for {service}. Expected parameters: {', '.join(expected_params)}",
                        location=f"Service: {service}",
                        suggested_content=f"Add configuration example with parameters: {', '.join(expected_params)}",
                        related_services=[service],
                        evidence=[f"Expected parameters: {expected_params}"]
                    )
                )

    def _detect_missing_error_explanations(self):
        """Detect missing error code explanations."""
        error_codes_mentioned: Set[int] = set()

        # Find mentioned error codes
        for service_docs in self.indexed_docs.values():
            for doc in service_docs.values():
                content = str(doc)
                for code in self.COMMON_ERROR_CODES:
                    if str(code) in content:
                        error_codes_mentioned.add(code)

        # Check if all common errors are explained
        for code in self.COMMON_ERROR_CODES:
            if code not in error_codes_mentioned:
                self.detected_gaps.append(
                    DocumentationGap(
                        gap_type=GapType.MISSING_ERROR_EXPLANATION,
                        severity=GapSeverity.MEDIUM,
                        title=f"Missing explanation for HTTP {code}",
                        description=f"No explanation or troubleshooting guide found for HTTP {code} status code",
                        location="General documentation",
                        suggested_content=f"Add explanation for HTTP {code} including causes and solutions",
                        evidence=[f"Common error codes: {self.COMMON_ERROR_CODES}"]
                    )
                )

    def _detect_missing_auth_guides(self):
        """Detect missing authentication/authorization guides."""
        has_auth_guide = False

        for service_docs in self.indexed_docs.values():
            for doc in service_docs.values():
                content = str(doc).lower()
                if any(keyword in content for keyword in ["authentication", "authorization", "auth", "login", "token"]):
                    has_auth_guide = True
                    break

            if has_auth_guide:
                break

        if not has_auth_guide:
            self.detected_gaps.append(
                DocumentationGap(
                    gap_type=GapType.MISSING_AUTH_GUIDE,
                    severity=GapSeverity.CRITICAL,
                    title="Missing authentication/authorization guide",
                    description="No documentation found for authentication or authorization procedures",
                    location="General documentation",
                    suggested_content="Add comprehensive authentication guide including token generation, usage, and troubleshooting",
                    related_services=[],
                    evidence=["Searched for: authentication, authorization, auth, login, token"]
                )
            )

    def _detect_outdated_content(self):
        """Detect potentially outdated content."""
        # Check for version mentions
        for service, service_docs in self.indexed_docs.items():
            for doc_name, doc in service_docs.items():
                content = str(doc)

                # Look for old version patterns
                outdated_patterns = ["v1.0", "version 1.0", "legacy", "deprecated"]

                for pattern in outdated_patterns:
                    if pattern.lower() in content.lower():
                        self.detected_gaps.append(
                            DocumentationGap(
                                gap_type=GapType.OUTDATED_CONTENT,
                                severity=GapSeverity.LOW,
                                title=f"Potentially outdated content in {doc_name}",
                                description=f"Document contains '{pattern}' which may indicate outdated content",
                                location=f"Document: {doc_name}",
                                suggested_content="Review and update content, or add version notice",
                                related_services=[service],
                                evidence=[f"Found pattern: {pattern}"]
                            )
                        )
                        break

    def _detect_incomplete_tutorials(self):
        """Detect incomplete tutorials."""
        tutorial_keywords = ["tutorial", "getting started", "quick start", "guide"]

        for service, service_docs in self.indexed_docs.items():
            for doc_name, doc in service_docs.items():
                content = str(doc).lower()

                # Check if this is a tutorial
                if any(keyword in content for keyword in tutorial_keywords):
                    # Check for completeness indicators
                    has_steps = "step" in content or "follow" in content
                    has_code = "```" in content or "code" in content
                    has_example = "example" in content

                    if not (has_steps and has_code and has_example):
                        self.detected_gaps.append(
                            DocumentationGap(
                                gap_type=GapType.INCOMPLETE_TUTORIAL,
                                severity=GapSeverity.MEDIUM,
                                title=f"Incomplete tutorial: {doc_name}",
                                description="Tutorial appears to be incomplete (missing steps, code, or examples)",
                                location=f"Document: {doc_name}",
                                suggested_content="Add missing steps, code examples, and usage examples to complete the tutorial",
                                related_services=[service],
                                evidence=[
                                    f"Has steps: {has_steps}",
                                    f"Has code: {has_code}",
                                    f"Has examples: {has_example}"
                                ]
                            )
                        )

    def _detect_missing_code_examples(self):
        """Detect missing code examples."""
        for service, service_docs in self.indexed_docs.items():
            has_code_example = False

            for doc in service_docs.values():
                content = str(doc)
                if "```" in content or "code example" in content.lower():
                    has_code_example = True
                    break

            if not has_code_example:
                self.detected_gaps.append(
                    DocumentationGap(
                        gap_type=GapType.MISSING_CODE_EXAMPLE,
                        severity=GapSeverity.MEDIUM,
                        title=f"Missing code examples for {service}",
                        description="No code examples found in documentation",
                        location=f"Service: {service}",
                        suggested_content="Add code examples showing common usage patterns",
                        related_services=[service]
                    )
                )

    def _detect_missing_deployment_guides(self):
        """Detect missing deployment guides."""
        deployment_keywords = ["deploy", "deployment", "install", "installation", "setup"]

        has_deployment_guide = False
        for service_docs in self.indexed_docs.values():
            for doc in service_docs.values():
                content = str(doc).lower()
                if any(keyword in content for keyword in deployment_keywords):
                    has_deployment_guide = True
                    break

            if has_deployment_guide:
                break

        if not has_deployment_guide:
            self.detected_gaps.append(
                DocumentationGap(
                    gap_type=GapType.MISSING_DEPLOYMENT_GUIDE,
                    severity=GapSeverity.HIGH,
                    title="Missing deployment/installation guide",
                    description="No deployment or installation guide found",
                    location="General documentation",
                    suggested_content="Add comprehensive deployment guide including requirements, installation steps, and configuration",
                    evidence=["Searched for: deploy, deployment, install, installation, setup"]
                )
            )


# ============== Tool Implementations ==============

@tool(
    name="detect_documentation_gaps",
    description="Detect gaps in documentation using deterministic rules (read-only)",
    category=ToolCategory.DOCUMENT_SEARCH,
    read_only=True,
    parameters={
        "services": {
            "type": "array",
            "description": "Services to check (empty for all)",
            "items": {"type": "string"}
        },
        "gap_types": {
            "type": "array",
            "description": "Types of gaps to detect (empty for all)",
            "items": {
                "type": "string",
                "enum": ["missing_api_endpoint", "missing_config_example", "missing_error_explanation",
                        "missing_auth_guide", "outdated_content", "incomplete_tutorial",
                        "missing_code_example", "missing_deployment_guide"]
            }
        },
        "min_severity": {
            "type": "string",
            "description": "Minimum severity level",
            "enum": ["low", "medium", "high", "critical"]
        }
    }
)
async def detect_documentation_gaps(
    services: List[str] = [],
    gap_types: List[str] = [],
    min_severity: str = "low"
) -> Dict[str, Any]:
    """
    Detect documentation gaps.

    Uses deterministic rules to find missing or incomplete documentation.
    Optionally filters by gap type and severity.

    Args:
        services: Services to check (empty for all)
        gap_types: Types of gaps to detect (empty for all)
        min_severity: Minimum severity level

    Returns:
        Detected documentation gaps
    """
    try:
        from doc_search.rag_tool import get_rag_tool

        # Get indexed documents
        rag_tool = get_rag_tool()
        indexed_docs = {}

        # Get service list
        if not services:
            services = ["api", "database", "cache", "worker"]  # Default services

        # Get documents for each service
        for service in services:
            try:
                result = rag_tool.search(
                    query=service,
                    top_k=20,
                    filters={"service": service}
                )
                indexed_docs[service] = {f"doc_{i}": doc for i, doc in enumerate(result.get("results", []))}
            except Exception as e:
                logger.warning(f"Failed to get docs for {service}: {e}")
                indexed_docs[service] = {}

        # Detect gaps
        detector = GapDetector(indexed_docs, services)
        all_gaps = detector.detect_all_gaps()

        # Filter by gap type
        if gap_types:
            all_gaps = [g for g in all_gaps if g.gap_type.value in gap_types]

        # Filter by severity
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_severity_level = severity_order.get(min_severity, 0)
        filtered_gaps = [
            g for g in all_gaps
            if severity_order.get(g.severity.value, 0) >= min_severity_level
        ]

        # Group by severity
        gaps_by_severity = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": []
        }

        for gap in filtered_gaps:
            gaps_by_severity[gap.severity.value].append(gap.to_dict())

        return {
            "success": True,
            "gaps": [g.to_dict() for g in filtered_gaps],
            "summary": {
                "total": len(filtered_gaps),
                "by_severity": {
                    sev: len(gaps) for sev, gaps in gaps_by_severity.items()
                },
                "by_type": {
                    gap_type: len([g for g in filtered_gaps if g.gap_type.value == gap_type])
                    for gap_type in set(g.gap_type.value for g in filtered_gaps)
                }
            },
            "metadata": {
                "services_checked": services,
                "gap_types_checked": gap_types or "all",
                "min_severity": min_severity
            }
        }

    except Exception as e:
        logger.error(f"detect_documentation_gaps failed: {e}")
        return {
            "success": False,
            "error": f"Failed to detect gaps: {str(e)}"
        }


@tool(
    name="create_gap_tickets",
    description="Create GitHub issues for detected documentation gaps (requires approval)",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="github_issue",
    read_only=False,
    risk_level="medium",
    parameters={
        "gaps": {
            "type": "array",
            "description": "List of detected gaps",
            "items": {"type": "object"}
        },
        "repo": {
            "type": "string",
            "description": "Repository to create issues in (format: owner/repo)"
        },
        "auto_label": {
            "type": "boolean",
            "description": "Automatically assign labels based on severity"
        },
        "dry_run": {
            "type": "boolean",
            "description": "Preview issues without creating them"
        }
    }
)
async def create_gap_tickets(
    gaps: List[Dict[str, Any]],
    repo: str,
    auto_label: bool = True,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Create GitHub issues for detected documentation gaps.

    Args:
        gaps: List of detected gaps from detect_documentation_gaps
        repo: Repository (format: owner/repo)
        auto_label: Auto-assign labels based on severity
        dry_run: Preview without creating

    Returns:
        Created issue URLs
    """
    try:
        if not gaps:
            return {
                "success": False,
                "error": "No gaps provided"
            }

        # Severity to label mapping
        severity_labels = {
            "critical": ["documentation", "critical", "priority: P0"],
            "high": ["documentation", "high-priority", "priority: P1"],
            "medium": ["documentation", "priority: P2"],
            "low": ["documentation", "enhancement", "priority: P3"]
        }

        # Gap type to label mapping
        type_labels = {
            "missing_api_endpoint": "api-docs",
            "missing_config_example": "config-docs",
            "missing_error_explanation": "error-docs",
            "missing_auth_guide": "auth-docs",
            "outdated_content": "update-needed",
            "incomplete_tutorial": "tutorial",
            "missing_code_example": "code-example",
            "missing_deployment_guide": "deployment-docs"
        }

        created_issues = []

        for gap in gaps:
            # Build issue title
            title = f"Doc Gap: {gap.get('title', 'Documentation Gap')}"

            # Build issue body
            body = f"""## Documentation Gap Detected

**Type:** {gap.get('gap_type', 'unknown')}
**Severity:** {gap.get('severity', 'unknown')}
**Service(s):** {', '.join(gap.get('related_services', [])) or 'N/A'}

### Description
{gap.get('description', 'No description')}

### Location
{gap.get('location', 'Not specified')}

### Suggested Content
{gap.get('suggested_content', 'No suggestion')}

### Evidence
{chr(10).join(f"- {e}" for e in gap.get('evidence', []))}

### Metadata
- **Detected At:** {gap.get('detected_at', 'Unknown')}
- **Gap Type:** {gap.get('gap_type', 'unknown')}

---

*This issue was auto-generated by DevRelAgent gap detection tool.*
"""

            # Build labels
            labels = ["documentation"]
            if auto_label:
                severity = gap.get('severity', 'low')
                gap_type = gap.get('gap_type', '')

                labels.extend(severity_labels.get(severity, []))
                if gap_type in type_labels:
                    labels.append(type_labels[gap_type])

            if dry_run:
                created_issues.append({
                    "dry_run": True,
                    "title": title,
                    "labels": labels,
                    "body_preview": body[:200] + "..."
                })
            else:
                # Create actual issue
                from tools.github_tool import draft_github_issue

                result = await draft_github_issue(
                    repo=repo,
                    title=title,
                    body=body,
                    labels=labels
                )

                if result.get("success"):
                    created_issues.append({
                        "dry_run": False,
                        "title": title,
                        "labels": labels,
                        "issue_url": result.get("issue_url")
                    })
                else:
                    created_issues.append({
                        "dry_run": False,
                        "title": title,
                        "labels": labels,
                        "error": result.get("error")
                    })

        return {
            "success": True,
            "issues": created_issues,
            "summary": {
                "total": len(gaps),
                "created": len([i for i in created_issues if not i.get("dry_run") and "error" not in i]),
                "failed": len([i for i in created_issues if "error" in i]),
                "dry_run": dry_run
            },
            "metadata": {
                "repo": repo,
                "auto_label": auto_label
            }
        }

    except Exception as e:
        logger.error(f"create_gap_tickets failed: {e}")
        return {
            "success": False,
            "error": f"Failed to create tickets: {str(e)}"
        }


@tool(
    name="check_not_supported",
    description="Check if query is supported or if 'not supported' is valid answer",
    category=ToolCategory.UTILITY,
    read_only=True,
    parameters={
        "query": {
            "type": "string",
            "description": "User query to check"
        },
        "indexed_services": {
            "type": "array",
            "description": "List of indexed services to check against",
            "items": {"type": "string"}
        }
    }
)
async def check_not_supported(
    query: str,
    indexed_services: List[str] = []
) -> Dict[str, Any]:
    """
    Check if a query is supported or if 'not supported' is valid.

    Determines if the query asks about something that's documented
    or if it's a legitimate 'not supported' case.

    Args:
        query: User query to check
        indexed_services: List of indexed services

    Returns:
        Support status and reasoning
    """
    try:
        query_lower = query.lower()

        # Keywords that indicate the user is asking about features
        feature_keywords = [
            "how do i", "how to", "how can",
            "what is", "what does", "explain",
            "where is", "find", "search",
            "configure", "setup", "install", "deploy"
        ]

        # Keywords that indicate the user is asking about specific services
        service_keywords = {
            "api": ["api", "endpoint", "rest", "graphql"],
            "database": ["database", "db", "sql", "clickhouse"],
            "cache": ["cache", "redis", "memcached"],
            "auth": ["auth", "authentication", "login", "token"],
            "metrics": ["metric", "monitoring", "observability"]
        }

        # Determine if this is a feature request or documentation query
        is_feature_query = any(kw in query_lower for kw in feature_keywords)

        # Detect mentioned services
        mentioned_services = []
        for service, keywords in service_keywords.items():
            if any(kw in query_lower for kw in keywords):
                mentioned_services.append(service)

        # Check if services are indexed
        if indexed_services:
            missing_services = set(mentioned_services) - set(indexed_services)
            if missing_services:
                return {
                    "success": True,
                    "is_supported": False,
                    "reason": "not_indexed",
                    "message": f"The following services are not indexed: {', '.join(missing_services)}",
                    "suggested_services": list(missing_services),
                    "action": "not_supported_answer"
                }

        # Check if query is about external/third-party services
        external_indicators = ["aws", "azure", "gcp", "kubernetes", "docker", "jenkins"]
        is_external_query = any(ind in query_lower for ind in external_indicators)

        if is_external_query:
            return {
                "success": True,
                "is_supported": False,
                "reason": "external_service",
                "message": "Query is about external/third-party services not covered in our documentation",
                "action": "not_supported_answer",
                "suggestion": "I can help with general guidance, but specific external service documentation is outside our scope"
            }

        # Check if query is about unsupported features
        unsupported_patterns = [
            ("beta", "beta features are not documented"),
            ("experimental", "experimental features are not documented"),
            ("deprecated", "deprecated features are not supported"),
            ("removed", "removed features are not available")
        ]

        for pattern, message in unsupported_patterns:
            if pattern in query_lower:
                return {
                    "success": True,
                    "is_supported": False,
                    "reason": f"unsupported_{pattern}",
                    "message": message,
                    "action": "not_supported_answer"
                }

        # Default: query is potentially supported
        return {
            "success": True,
            "is_supported": True,
            "reason": "documented_topic",
            "message": "Query appears to be about documented topics",
            "mentioned_services": mentioned_services,
            "action": "search_docs"
        }

    except Exception as e:
        logger.error(f"check_not_supported failed: {e}")
        return {
            "success": False,
            "error": f"Failed to check support: {str(e)}"
        }
