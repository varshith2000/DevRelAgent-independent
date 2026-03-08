"""
Observability Tool — Deterministic Observability Operations

Provides structured, deterministic tools for observability queries.
Replaces raw SQL with well-defined operations with enforced limits and scoping.
"""

import logging
from typing import Dict, Any, List, Optional, Literal, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from tools.registry import tool, ToolCategory

logger = logging.getLogger(__name__)


# ============== Data Contracts ==============

@dataclass
class TimeRange:
    """Time range for observability queries."""
    start: datetime
    end: datetime
    duration_minutes: int = field(init=False)

    def __post_init__(self):
        self.duration_minutes = int((self.end - self.start).total_seconds() / 60)

    @classmethod
    def from_minutes(cls, minutes: int, end: Optional[datetime] = None) -> 'TimeRange':
        """Create time range from duration in minutes."""
        end = end or datetime.now()
        start = end - timedelta(minutes=minutes)
        return cls(start=start, end=end)

    def validate(self, max_minutes: int = 1440) -> bool:
        """Validate time range doesn't exceed maximum."""
        return self.duration_minutes <= max_minutes


@dataclass
class ServiceScope:
    """Service scope for queries."""
    services: List[str]
    include_all: bool = False

    def validate(self, available_services: List[str]) -> bool:
        """Validate services exist."""
        if self.include_all:
            return True
        return all(s in available_services for s in self.services)


@dataclass
class ErrorRateMetric:
    """Error rate metric data structure."""
    service: str
    time_range: TimeRange
    total_requests: int
    error_count: int
    error_rate: float
    error_rate_trend: Literal["increasing", "decreasing", "stable"]
    critical_threshold_exceeded: bool


@dataclass
class TopError:
    """Top error data structure."""
    error_message: str
    error_type: str
    service: str
    count: int
    first_seen: datetime
    last_seen: datetime
    affected_traces: int
    example_trace_id: Optional[str] = None


@dataclass
class LatencyMetric:
    """Latency metric data structure."""
    service: str
    time_range: TimeRange
    p50: float
    p95: float
    p99: float
    max: float
    avg: float
    request_count: int
    span_breakdown: Dict[str, float]


@dataclass
class CorrelatedTrace:
    """Correlated trace data structure."""
    trace_id: str
    service: str
    error_message: str
    timestamp: datetime
    duration_ms: float
    span_count: int
    status_code: int
    endpoint: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============== Deterministic Tools ==============

@tool(
    name="get_error_rate",
    description="Get error rate metrics for specified services and time range (deterministic, time-limited)",
    category=ToolCategory.DATABASE_QUERY,
    read_only=True,
    parameters={
        "services": {
            "type": "array",
            "description": "List of service names (empty for all services)",
            "items": {"type": "string"}
        },
        "time_range_minutes": {
            "type": "integer",
            "description": "Time range in minutes (max: 1440 = 24 hours)",
            "minimum": 1,
            "maximum": 1440
        },
        "granularity_minutes": {
            "type": "integer",
            "description": "Granularity in minutes (1, 5, 15, 60)",
            "enum": [1, 5, 15, 60]
        }
    }
)
async def get_error_rate(
    services: List[str] = [],
    time_range_minutes: int = 60,
    granularity_minutes: int = 5
) -> Dict[str, Any]:
    """
    Get error rate metrics for services.

    Deterministic tool that returns structured error rate data.
    Enforces time limits and service scoping.

    Args:
        services: List of service names (empty for all services)
        time_range_minutes: Time range in minutes (max: 1440)
        granularity_minutes: Granularity for time series data

    Returns:
        Structured error rate metrics
    """
    try:
        from database.clickhouse_client import get_clickhouse_client

        # Validate time range
        time_range = TimeRange.from_minutes(time_range_minutes)
        if not time_range.validate(max_minutes=1440):
            return {
                "success": False,
                "error": f"Time range exceeds maximum of 1440 minutes (24 hours)"
            }

        client = get_clickhouse_client()

        # Build query with enforced limits
        service_filter = ""
        if services:
            service_list = "', '".join(services)
            service_filter = f"AND service IN ('{service_list}')"

        query = f"""
        SELECT
            service,
            toStartOfInterval(timestamp, INTERVAL {granularity_minutes} MINUTE) as interval,
            count() as total_requests,
            countIf(status_code >= 400) as error_count,
            (error_count / total_requests) * 100 as error_rate
        FROM logs
        WHERE timestamp >= now() - INTERVAL {time_range_minutes} MINUTE
            {service_filter}
        GROUP BY service, interval
        ORDER BY interval DESC, service
        """

        result = await client.execute_query(query)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message
            }

        # Process results into structured format
        metrics = {}
        for row in result.data:
            service = row.get('service', 'unknown')
            if service not in metrics:
                metrics[service] = {
                    "service": service,
                    "time_range_minutes": time_range_minutes,
                    "granularity_minutes": granularity_minutes,
                    "data_points": [],
                    "summary": {}
                }

            metrics[service]["data_points"].append({
                "interval": row.get('interval'),
                "total_requests": row.get('total_requests'),
                "error_count": row.get('error_count'),
                "error_rate": round(row.get('error_rate', 0), 2)
            })

        # Calculate summary for each service
        for service, data in metrics.items():
            points = data["data_points"]
            if points:
                total_requests = sum(p["total_requests"] for p in points)
                total_errors = sum(p["error_count"] for p in points)
                avg_error_rate = total_errors / total_requests * 100 if total_requests > 0 else 0

                # Determine trend
                recent_rate = points[0]["error_rate"]
                older_rate = points[-1]["error_rate"]
                if recent_rate > older_rate * 1.1:
                    trend = "increasing"
                elif recent_rate < older_rate * 0.9:
                    trend = "decreasing"
                else:
                    trend = "stable"

                data["summary"] = {
                    "total_requests": total_requests,
                    "total_errors": total_errors,
                    "average_error_rate": round(avg_error_rate, 2),
                    "trend": trend,
                    "critical_threshold_exceeded": avg_error_rate > 5.0
                }

        return {
            "success": True,
            "time_range": {
                "start": time_range.start.isoformat(),
                "end": time_range.end.isoformat(),
                "duration_minutes": time_range.duration_minutes
            },
            "services": metrics,
            "metadata": {
                "query_count": len(metrics),
                "enforced_limits": {
                    "max_time_range_minutes": 1440,
                    "actual_time_range_minutes": time_range_minutes
                }
            }
        }

    except Exception as e:
        logger.error(f"get_error_rate failed: {e}")
        return {
            "success": False,
            "error": f"Failed to get error rate: {str(e)}"
        }


@tool(
    name="get_top_errors",
    description="Get top errors by frequency with correlation data (deterministic, time-limited)",
    category=ToolCategory.DATABASE_QUERY,
    read_only=True,
    parameters={
        "services": {
            "type": "array",
            "description": "List of service names (empty for all services)",
            "items": {"type": "string"}
        },
        "time_range_minutes": {
            "type": "integer",
            "description": "Time range in minutes (max: 1440)",
            "minimum": 1,
            "maximum": 1440
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of errors to return (max: 100)",
            "minimum": 1,
            "maximum": 100
        },
        "group_by": {
            "type": "string",
            "description": "Group errors by field",
            "enum": ["message", "type", "service"]
        }
    }
)
async def get_top_errors(
    services: List[str] = [],
    time_range_minutes: int = 60,
    limit: int = 20,
    group_by: str = "message"
) -> Dict[str, Any]:
    """
    Get top errors with correlation data.

    Returns structured error data with trace correlation.
    Enforces time limits and result size limits.

    Args:
        services: List of service names (empty for all services)
        time_range_minutes: Time range in minutes (max: 1440)
        limit: Maximum number of errors (max: 100)
        group_by: Group errors by message, type, or service

    Returns:
        Structured top errors data
    """
    try:
        from database.clickhouse_client import get_clickhouse_client

        # Validate inputs
        time_range = TimeRange.from_minutes(time_range_minutes)
        if not time_range.validate(max_minutes=1440):
            return {
                "success": False,
                "error": "Time range exceeds maximum"
            }

        limit = min(limit, 100)

        client = get_clickhouse_client()

        # Build service filter
        service_filter = ""
        if services:
            service_list = "', '".join(services)
            service_filter = f"AND service IN ('{service_list}')"

        # Build group by clause
        group_mapping = {
            "message": "error_message",
            "type": "error_type",
            "service": "service"
        }
        group_field = group_mapping.get(group_by, "error_message")

        query = f"""
        SELECT
            {group_field} as group_key,
            service,
            count() as error_count,
            min(timestamp) as first_seen,
            max(timestamp) as last_seen,
            countDistinct(trace_id) as affected_traces,
            any(trace_id) as example_trace_id
        FROM logs
        WHERE timestamp >= now() - INTERVAL {time_range_minutes} MINUTE
            AND status_code >= 400
            {service_filter}
        GROUP BY group_key, service
        ORDER BY error_count DESC
        LIMIT {limit}
        """

        result = await client.execute_query(query)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message
            }

        # Process into structured format
        errors = []
        for row in result.data:
            errors.append({
                "error_message": row.get('error_message') if group_by == "message" else None,
                "error_type": row.get('error_type') if group_by == "type" else None,
                "service": row.get('service'),
                "count": row.get('error_count'),
                "first_seen": row.get('first_seen'),
                "last_seen": row.get('last_seen'),
                "affected_traces": row.get('affected_traces'),
                "example_trace_id": row.get('example_trace_id')
            })

        return {
            "success": True,
            "time_range": {
                "start": time_range.start.isoformat(),
                "end": time_range.end.isoformat(),
                "duration_minutes": time_range.duration_minutes
            },
            "grouped_by": group_by,
            "errors": errors,
            "metadata": {
                "total_errors": len(errors),
                "limit": limit,
                "enforced_limits": {
                    "max_time_range_minutes": 1440,
                    "max_limit": 100
                }
            }
        }

    except Exception as e:
        logger.error(f"get_top_errors failed: {e}")
        return {
            "success": False,
            "error": f"Failed to get top errors: {str(e)}"
        }


@tool(
    name="get_latency_metrics",
    description="Get latency metrics with span breakdown (deterministic, time-limited)",
    category=ToolCategory.DATABASE_QUERY,
    read_only=True,
    parameters={
        "services": {
            "type": "array",
            "description": "List of service names",
            "items": {"type": "string"}
        },
        "time_range_minutes": {
            "type": "integer",
            "description": "Time range in minutes (max: 1440)",
            "minimum": 1,
            "maximum": 1440
        },
        "percentiles": {
            "type": "array",
            "description": "Percentiles to calculate",
            "items": {"type": "number"}
        }
    }
)
async def get_latency_metrics(
    services: List[str],
    time_range_minutes: int = 60,
    percentiles: List[float] = [50, 95, 99]
) -> Dict[str, Any]:
    """
    Get latency metrics with span breakdown.

    Returns structured latency data with percentiles and span analysis.
    Enforces time limits.

    Args:
        services: List of service names (required)
        time_range_minutes: Time range in minutes (max: 1440)
        percentiles: Percentiles to calculate

    Returns:
        Structured latency metrics
    """
    try:
        from database.clickhouse_client import get_clickhouse_client

        if not services:
            return {
                "success": False,
                "error": "At least one service must be specified"
            }

        time_range = TimeRange.from_minutes(time_range_minutes)
        if not time_range.validate(max_minutes=1440):
            return {
                "success": False,
                "error": "Time range exceeds maximum"
            }

        client = get_clickhouse_client()
        service_list = "', '".join(services)

        # Build percentile functions
        percentile_funcs = ", ".join([
            f"quantile({p/100})(duration_ms) as p{p}"
            for p in percentiles
        ])

        query = f"""
        SELECT
            service,
            {percentile_funcs},
            max(duration_ms) as max_latency,
            avg(duration_ms) as avg_latency,
            count() as request_count
        FROM logs
        WHERE timestamp >= now() - INTERVAL {time_range_minutes} MINUTE
            AND service IN ('{service_list}')
            AND status_code < 400
        GROUP BY service
        ORDER BY service
        """

        result = await client.execute_query(query)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message
            }

        # Get span breakdown
        span_query = f"""
        SELECT
            service,
            span_name,
            avg(duration_ms) as avg_duration,
            count() as span_count
        FROM spans
        WHERE timestamp >= now() - INTERVAL {time_range_minutes} MINUTE
            AND service IN ('{service_list}')
        GROUP BY service, span_name
        ORDER BY service, avg_duration DESC
        """

        span_result = await client.execute_query(span_query)

        # Process results
        metrics = {}
        for row in result.data:
            service = row.get('service')
            metrics[service] = {
                "service": service,
                "time_range_minutes": time_range_minutes,
                "percentiles": {},
                "max": round(row.get('max_latency', 0), 2),
                "avg": round(row.get('avg_latency', 0), 2),
                "request_count": row.get('request_count'),
                "span_breakdown": {}
            }

            for p in percentiles:
                metrics[service]["percentiles"][f"p{p}"] = round(row.get(f'p{p}', 0), 2)

        # Add span breakdown
        if span_result.success:
            for row in span_result.data:
                service = row.get('service')
                span_name = row.get('span_name')
                if service in metrics:
                    metrics[service]["span_breakdown"][span_name] = {
                        "avg_duration_ms": round(row.get('avg_duration', 0), 2),
                        "count": row.get('span_count')
                    }

        return {
            "success": True,
            "time_range": {
                "start": time_range.start.isoformat(),
                "end": time_range.end.isoformat(),
                "duration_minutes": time_range.duration_minutes
            },
            "services": metrics,
            "metadata": {
                "services_queried": list(metrics.keys()),
                "percentiles_calculated": percentiles
            }
        }

    except Exception as e:
        logger.error(f"get_latency_metrics failed: {e}")
        return {
            "success": False,
            "error": f"Failed to get latency metrics: {str(e)}"
        }


@tool(
    name="correlate_error_with_traces",
    description="Correlate errors with trace data (deterministic, time-limited)",
    category=ToolCategory.DATABASE_QUERY,
    read_only=True,
    parameters={
        "trace_id": {
            "type": "string",
            "description": "Trace ID to correlate"
        },
        "error_message": {
            "type": "string",
            "description": "Error message to search for"
        },
        "service": {
            "type": "string",
            "description": "Service to search in"
        },
        "time_range_minutes": {
            "type": "integer",
            "description": "Time range in minutes (max: 1440)",
            "minimum": 1,
            "maximum": 1440
        },
        "limit": {
            "type": "integer",
            "description": "Maximum traces to return (max: 50)",
            "minimum": 1,
            "maximum": 50
        }
    }
)
async def correlate_error_with_traces(
    trace_id: Optional[str] = None,
    error_message: Optional[str] = None,
    service: Optional[str] = None,
    time_range_minutes: int = 60,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Correlate errors with trace data.

    Returns traces associated with errors for root cause analysis.
    Enforces time and result limits.

    Args:
        trace_id: Specific trace ID (takes precedence)
        error_message: Error message to search for
        service: Service to scope search
        time_range_minutes: Time range (max: 1440)
        limit: Maximum traces (max: 50)

    Returns:
        Correlated trace data
    """
    try:
        from database.clickhouse_client import get_clickhouse_client

        time_range = TimeRange.from_minutes(time_range_minutes)
        if not time_range.validate(max_minutes=1440):
            return {
                "success": False,
                "error": "Time range exceeds maximum"
            }

        limit = min(limit, 50)
        client = get_clickhouse_client()

        # Build query based on input
        if trace_id:
            query = f"""
            SELECT
                trace_id,
                service,
                error_message,
                timestamp,
                duration_ms,
                count() as span_count,
                status_code,
                endpoint
            FROM logs
            WHERE trace_id = '{trace_id}'
            GROUP BY trace_id, service, error_message, timestamp, duration_ms, status_code, endpoint
            LIMIT {limit}
            """
        else:
            conditions = [f"timestamp >= now() - INTERVAL {time_range_minutes} MINUTE"]
            if error_message:
                conditions.append(f"error_message LIKE '%{error_message}%'")
            if service:
                conditions.append(f"service = '{service}'")

            where_clause = " AND ".join(conditions)

            query = f"""
            SELECT
                trace_id,
                any(service) as service,
                any(error_message) as error_message,
                min(timestamp) as timestamp,
                sum(duration_ms) as duration_ms,
                count() as span_count,
                any(status_code) as status_code,
                any(endpoint) as endpoint
            FROM logs
            WHERE {where_clause}
            GROUP BY trace_id
            ORDER BY timestamp DESC
            LIMIT {limit}
            """

        result = await client.execute_query(query)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message
            }

        traces = []
        for row in result.data:
            traces.append({
                "trace_id": row.get('trace_id'),
                "service": row.get('service'),
                "error_message": row.get('error_message'),
                "timestamp": row.get('timestamp'),
                "duration_ms": row.get('duration_ms'),
                "span_count": row.get('span_count'),
                "status_code": row.get('status_code'),
                "endpoint": row.get('endpoint')
            })

        return {
            "success": True,
            "traces": traces,
            "metadata": {
                "trace_count": len(traces),
                "limit": limit,
                "search_criteria": {
                    "trace_id": trace_id,
                    "error_message": error_message,
                    "service": service
                }
            }
        }

    except Exception as e:
        logger.error(f"correlate_error_with_traces failed: {e}")
        return {
            "success": False,
            "error": f"Failed to correlate traces: {str(e)}"
        }


@tool(
    name="compare_before_after",
    description="Compare metrics before and after a timestamp (deterministic, time-limited)",
    category=ToolCategory.DATABASE_QUERY,
    read_only=True,
    parameters={
        "timestamp": {
            "type": "string",
            "description": "Timestamp to compare around (ISO format)"
        },
        "before_minutes": {
            "type": "integer",
            "description": "Minutes before timestamp (max: 1440)",
            "minimum": 1,
            "maximum": 1440
        },
        "after_minutes": {
            "type": "integer",
            "description": "Minutes after timestamp (max: 1440)",
            "minimum": 1,
            "maximum": 1440
        },
        "services": {
            "type": "array",
            "description": "Services to compare",
            "items": {"type": "string"}
        },
        "metrics": {
            "type": "array",
            "description": "Metrics to compare",
            "items": {"type": "string"},
            "enum": ["error_rate", "latency_p95", "request_count"]
        }
    }
)
async def compare_before_after(
    timestamp: str,
    before_minutes: int = 60,
    after_minutes: int = 60,
    services: List[str] = [],
    metrics: List[str] = ["error_rate", "latency_p95", "request_count"]
) -> Dict[str, Any]:
    """
    Compare metrics before and after a timestamp.

    Returns comparison data for change detection.
    Enforces time limits.

    Args:
        timestamp: Timestamp to compare around
        before_minutes: Minutes before (max: 1440)
        after_minutes: Minutes after (max: 1440)
        services: Services to compare
        metrics: Metrics to compare

    Returns:
        Before/after comparison data
    """
    try:
        from database.clickhouse_client import get_clickhouse_client

        # Validate time ranges
        before_range = TimeRange(
            start=datetime.fromisoformat(timestamp) - timedelta(minutes=before_minutes),
            end=datetime.fromisoformat(timestamp)
        )
        after_range = TimeRange(
            start=datetime.fromisoformat(timestamp),
            end=datetime.fromisoformat(timestamp) + timedelta(minutes=after_minutes)
        )

        if not before_range.validate(max_minutes=1440) or not after_range.validate(max_minutes=1440):
            return {
                "success": False,
                "error": "Time range exceeds maximum"
            }

        client = get_clickhouse_client()
        service_list = "', '".join(services) if services else None

        # Build comparison query
        service_filter = f"AND service IN ('{service_list}')" if services else ""

        query = f"""
        SELECT
            'before' as period,
            service,
            count() as request_count,
            countIf(status_code >= 400) / count() * 100 as error_rate,
            quantile(0.95)(duration_ms) as latency_p95
        FROM logs
        WHERE timestamp >= '{before_range.start.isoformat()}'
            AND timestamp < '{before_range.end.isoformat()}'
            {service_filter}
        GROUP BY service

        UNION ALL

        SELECT
            'after' as period,
            service,
            count() as request_count,
            countIf(status_code >= 400) / count() * 100 as error_rate,
            quantile(0.95)(duration_ms) as latency_p95
        FROM logs
        WHERE timestamp >= '{after_range.start.isoformat()}'
            AND timestamp < '{after_range.end.isoformat()}'
            {service_filter}
        GROUP BY service
        ORDER BY service, period
        """

        result = await client.execute_query(query)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message
            }

        # Process into before/after format
        comparisons = {}
        for row in result.data:
            service = row.get('service')
            period = row.get('period')

            if service not in comparisons:
                comparisons[service] = {
                    "service": service,
                    "before": {},
                    "after": {},
                    "changes": {}
                }

            comparisons[service][period] = {
                "request_count": row.get('request_count'),
                "error_rate": round(row.get('error_rate', 0), 2),
                "latency_p95": round(row.get('latency_p95', 0), 2)
            }

        # Calculate changes
        for service, data in comparisons.items():
            before = data["before"]
            after = data["after"]

            if before and after:
                data["changes"] = {
                    "request_count_change": after.get("request_count", 0) - before.get("request_count", 0),
                    "request_count_change_percent": round(
                        ((after.get("request_count", 0) - before.get("request_count", 0)) / before.get("request_count", 1)) * 100, 2
                    ) if before.get("request_count", 0) > 0 else 0,
                    "error_rate_change": round(after.get("error_rate", 0) - before.get("error_rate", 0), 2),
                    "latency_p95_change": round(after.get("latency_p95", 0) - before.get("latency_p95", 0), 2)
                }

        return {
            "success": True,
            "timestamp": timestamp,
            "comparisons": comparisons,
            "metadata": {
                "before_range": {
                    "start": before_range.start.isoformat(),
                    "end": before_range.end.isoformat(),
                    "duration_minutes": before_range.duration_minutes
                },
                "after_range": {
                    "start": after_range.start.isoformat(),
                    "end": after_range.end.isoformat(),
                    "duration_minutes": after_range.duration_minutes
                }
            }
        }

    except Exception as e:
        logger.error(f"compare_before_after failed: {e}")
        return {
            "success": False,
            "error": f"Failed to compare before/after: {str(e)}"
        }
