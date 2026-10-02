"""
Correlation Engine — Cross-Domain Analysis

Correlates data across metrics, logs, and traces to find patterns and relationships.
Used by multi-step reasoning to provide comprehensive analysis.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """
    Cross-reference metrics, logs, and traces.

    Finds correlations and patterns across different data sources.
    """

    def __init__(self):
        """Initialize the correlation engine."""
        logger.info("CorrelationEngine initialized")

    async def correlate(
        self,
        metrics: Optional[Dict[str, Any]] = None,
        logs: Optional[List[Dict[str, Any]]] = None,
        traces: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Find correlations across different data sources.

        Args:
            metrics: Metric data points
            logs: Log entries
            traces: Distributed trace data

        Returns:
            Dictionary with correlations, anomalies, and relationships
        """
        correlations = {
            "patterns": [],
            "anomalies": [],
            "relationships": [],
            "summary": ""
        }

        # Find time-based correlations
        if metrics and logs:
            time_correlations = self._find_time_correlations(metrics, logs)
            correlations["patterns"].extend(time_correlations)

        # Find error patterns
        if logs:
            error_patterns = self._find_error_patterns(logs, traces or [])
            correlations["anomalies"].extend(error_patterns)

        # Find service dependencies
        if traces:
            dependencies = self._find_dependencies(traces)
            correlations["relationships"].extend(dependencies)

        # Generate summary
        correlations["summary"] = self._generate_summary(correlations)

        return correlations

    def _find_time_correlations(
        self,
        metrics: Dict[str, Any],
        logs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find time-based correlations between metrics and logs.

        Args:
            metrics: Metric data
            logs: Log entries

        Returns:
            List of time-based correlations
        """
        correlations = []

        # Look for metric spikes that correlate with error logs
        for service, metric_data in metrics.items():
            if isinstance(metric_data, dict) and "value" in metric_data:
                value = metric_data["value"]
                threshold = metric_data.get("threshold", 100)

                if value > threshold:
                    # Find related error logs
                    related_errors = [
                        log for log in logs
                        if log.get("service") == service and log.get("level") == "ERROR"
                    ]

                    if related_errors:
                        correlations.append({
                            "type": "time_correlation",
                            "service": service,
                            "metric": f"{value} (threshold: {threshold})",
                            "related_errors": len(related_errors),
                            "description": f"{service} metric spike correlates with {len(related_errors)} errors"
                        })

        return correlations

    def _find_error_patterns(
        self,
        logs: List[Dict[str, Any]],
        traces: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find error patterns across logs and traces.

        Args:
            logs: Log entries
            traces: Distributed trace data

        Returns:
            List of error patterns
        """
        patterns = []

        # Group errors by service
        service_errors = {}
        for log in logs:
            if log.get("level") == "ERROR":
                service = log.get("service", "unknown")
                if service not in service_errors:
                    service_errors[service] = []
                service_errors[service].append(log)

        # Find services with high error rates
        for service, errors in service_errors.items():
            if len(errors) >= 5:  # Threshold for pattern detection
                # Extract common error patterns
                error_messages = [e.get("message", "") for e in errors]

                # Find common substrings
                common = self._find_common_substrings(error_messages)

                patterns.append({
                    "type": "error_pattern",
                    "service": service,
                    "error_count": len(errors),
                    "common_patterns": common[:3],  # Top 3 patterns
                    "description": f"{service} has {len(errors)} errors with common patterns"
                })

        return patterns

    def _find_dependencies(
        self,
        traces: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find service dependencies from traces.

        Args:
            traces: Distributed trace data

        Returns:
            List of service dependencies
        """
        dependencies = []

        # Extract service relationships from traces
        for trace in traces:
            if "spans" in trace:
                for i in range(len(trace["spans"]) - 1):
                    current = trace["spans"][i]
                    next_span = trace["spans"][i + 1]

                    if "service" in current and "service" in next_span:
                        dependencies.append({
                            "type": "dependency",
                            "from": current["service"],
                            "to": next_span["service"],
                            "trace_id": trace.get("trace_id", "unknown")
                        })

        return dependencies

    def _find_common_substrings(self, strings: List[str], min_length: int = 10) -> List[str]:
        """
        Find common substrings in a list of strings.

        Args:
            strings: List of strings
            min_length: Minimum substring length

        Returns:
            List of common substrings
        """
        if not strings:
            return []

        # Simple implementation - find common prefixes
        common = []

        for i, s1 in enumerate(strings):
            for s2 in strings[i + 1:]:
                # Find common prefix
                common_len = 0
                min_len = min(len(s1), len(s2))

                while common_len < min_len and s1[common_len] == s2[common_len]:
                    common_len += 1

                if common_len >= min_length:
                    common_str = s1[:common_len]
                    if common_str not in common:
                        common.append(common_str)

        return sorted(common, key=len, reverse=True)

    def _generate_summary(self, correlations: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of correlations.

        Args:
            correlations: Correlation data

        Returns:
            Summary string
        """
        parts = []

        if correlations["patterns"]:
            parts.append(f"Found {len(correlations['patterns'])} patterns")

        if correlations["anomalies"]:
            parts.append(f"Detected {len(correlations['anomalies'])} anomalies")

        if correlations["relationships"]:
            parts.append(f"Identified {len(correlations['relationships'])} relationships")

        if not parts:
            return "No significant correlations found"

        return ". ".join(parts) + "."
