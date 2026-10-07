"""Provider-neutral query contract and ClickHouse adapter for telemetry tools.

ClickHouse is the only live adapter currently implemented. The in-memory
adapter is a small deterministic fixture engine for development and tests; it
is not intended to execute arbitrary SQL or serve production requests.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ObservabilityQueryResult:
    """Provider-neutral query result used by observability analysis tools."""

    success: bool
    data: List[Dict[str, Any]]
    error_message: Optional[str] = None


class ObservabilityStore(Protocol):
    """Minimal read-only query surface required by analysis tools."""

    async def execute_query(self, query: str) -> ObservabilityQueryResult:
        """Execute a read query and return rows keyed by column name."""
        ...


class InMemoryObservabilityStore:
    """Read-only, deterministic adapter for the synthetic fixture signals."""

    def __init__(self, rows: Dict[str, List[Dict[str, Any]]]):
        self.rows = rows

    async def execute_query(self, query: str) -> ObservabilityQueryResult:
        normalized = " ".join(query.lower().split())
        if "from logs.otel_traces" in normalized:
            data = self._query_traces(normalized)
        elif "from logs.logs" in normalized:
            data = self._query_logs(query)
        else:
            data = []
        return ObservabilityQueryResult(success=True, data=data)

    def _query_logs(self, query: str) -> List[Dict[str, Any]]:
        raw_query = query
        query = " ".join(query.lower().split())
        records = self.rows.get("logs", [])
        service_filter = _in_filter(query, "service")

        if "group_key" in query:
            group_field = "error_message" if "error_message as group_key" in query else "error_type"
            service_filter = _in_filter(query, "service")
            groups: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
            for record in records:
                if record.get("status_code", 0) < 400:
                    continue
                if not record.get("error_message") or not _in_scope(record.get("service"), service_filter):
                    continue
                key = (str(record.get(group_field, "")), str(record.get("service", "unknown")))
                groups.setdefault(key, []).append(record)
            rows = [
                {
                    "group_key": value,
                    "service": service,
                    "error_count": len(group),
                    "first_seen": min(item["timestamp"] for item in group),
                    "last_seen": max(item["timestamp"] for item in group),
                    "affected_traces": len({item.get("trace_id") for item in group}),
                    "example_trace_id": group[0].get("trace_id"),
                }
                for (value, service), group in groups.items()
            ]
            return sorted(rows, key=lambda row: row["error_count"], reverse=True)

        if "group by service, interval" in query:
            groups: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
            for record in records:
                if not _in_scope(record.get("service"), service_filter):
                    continue
                interval = _interval_label(record["timestamp"], _interval_minutes(query))
                groups.setdefault((record.get("service", "unknown"), interval), []).append(record)
            return [
                {
                    "service": service,
                    "interval": interval,
                    "total_requests": len(group),
                    "error_count": sum(item.get("status_code", 0) >= 400 for item in group),
                    "error_rate": sum(item.get("status_code", 0) >= 400 for item in group)
                    / len(group)
                    * 100,
                }
                for (service, interval), group in groups.items()
            ]

        if "'before' as period" in query and "union all" in query:
            split = _before_after_split(raw_query)
            if not split:
                return []
            result = []
            second_lower_bound = _second_timestamp(raw_query)
            for period, lower, upper in (
                ("before", _first_timestamp(raw_query), split),
                ("after", second_lower_bound, _second_timestamp(raw_query, upper=True)),
            ):
                scoped = [
                    record for record in records
                    if _in_scope(record.get("service"), service_filter)
                    and (not lower or lower <= record["timestamp"])
                    and (not upper or record["timestamp"] < upper)
                    and (
                        (period == "before" and record["timestamp"] < split)
                        or (period == "after" and record["timestamp"] >= split)
                    )
                ]
                result.extend(_aggregate_requests(scoped, period))
            return result

        if "group by trace_id" in query:
            conditions = _query_conditions(query)
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for record in records:
                if not _in_scope(record.get("service"), service_filter):
                    continue
                if conditions.get("errors_only") and (
                    record.get("status_code", 0) < 400 or not record.get("error_message")
                ):
                    continue
                if conditions.get("trace_id") and record.get("trace_id") != conditions["trace_id"]:
                    continue
                if conditions.get("service") and record.get("service") != conditions["service"]:
                    continue
                if conditions.get("error_text") and conditions["error_text"] not in record.get("error_message", ""):
                    continue
                grouped.setdefault(record.get("trace_id", ""), []).append(record)
            result = [
                {
                    "trace_id": trace_id,
                    "service": group[0].get("service"),
                    "error_message": next(
                        (row["error_message"] for row in group if row.get("error_message")), ""
                    ),
                    "timestamp": min(row["timestamp"] for row in group),
                    "duration_ms": sum(row.get("duration_ms", 0) for row in group),
                    "span_count": len(group),
                    "status_code": max(row.get("status_code", 0) for row in group),
                    "endpoint": group[0].get("endpoint", ""),
                }
                for trace_id, group in grouped.items()
            ]
            return sorted(result, key=lambda row: row["timestamp"], reverse=True)

        if "count()" in query and "from logs.logs" in query:
            good_requests = [
                record for record in records
                if _in_scope(record.get("service"), service_filter)
                and 0 < record.get("status_code", 0) < 400
            ]
            return _aggregate_requests(good_requests)

        return []

    def _query_traces(self, query: str) -> List[Dict[str, Any]]:
        records = self.rows.get("otel_traces", [])
        service_filter = _in_filter(query, "service_name")

        if "group by service_name, span_name" in query:
            groups: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
            for record in records:
                if not _in_scope(record.get("service_name"), service_filter):
                    continue
                if "attributes['demo.phase'] != 'baseline'" in query and record.get("attributes", {}).get("demo.phase") == "baseline":
                    continue
                groups.setdefault((record["service_name"], record["span_name"]), []).append(record)
            return [
                {
                    "service": service,
                    "span_name": span_name,
                    "avg_duration": sum(row["duration_ns"] / 1_000_000 for row in group)
                    / len(group),
                    "span_count": len(group),
                }
                for (service, span_name), group in groups.items()
            ]

        if "where trace_id =" in query:
            trace_id = _equals_filter(query, "trace_id")
            group = [row for row in records if row.get("trace_id") == trace_id]
            if not group:
                return []
            root = next((row for row in group if not row.get("parent_span_id")), group[0])
            return [{
                "trace_id": trace_id,
                "service": root.get("service_name"),
                "error_message": next((row["status_message"] for row in group if row.get("status_message")), ""),
                "timestamp": min(row["timestamp"] for row in group),
                "duration_ms": max(row.get("duration_ns", 0) for row in group) / 1_000_000,
                "span_count": len(group),
                "status_code": int(root.get("attributes", {}).get("http.response.status_code", "200")),
                "endpoint": root.get("attributes", {}).get("http.route", ""),
            }]

        return []


class ClickHouseObservabilityStore:
    """Adapt the synchronous ClickHouse client to the async row contract."""

    async def execute_query(self, query: str) -> ObservabilityQueryResult:
        from database.clickhouse_client import get_clickhouse_client

        try:
            client = get_clickhouse_client()
            result = await asyncio.to_thread(client.execute_query, query)
            columns = list(getattr(result, "column_names", []) or [])
            rows = [dict(zip(columns, row)) for row in getattr(result, "result_rows", [])]
            return ObservabilityQueryResult(success=True, data=rows)
        except Exception as exc:
            return ObservabilityQueryResult(success=False, data=[], error_message=str(exc))


def get_observability_store() -> ObservabilityStore:
    """Return the ClickHouse adapter; tests can inject an in-memory snapshot adapter."""
    return ClickHouseObservabilityStore()


def _aggregate_requests(records: List[Dict[str, Any]], period: Optional[str] = None) -> List[Dict[str, Any]]:
    if not records:
        return []
    by_service: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        by_service.setdefault(record.get("service", "unknown"), []).append(record)
    result = []
    for service, group in by_service.items():
        durations = sorted(record.get("duration_ms", 0) for record in group)
        errors = sum(record.get("status_code", 0) >= 400 for record in group)
        if period:
            result.append({
                "service": service,
                "period": period,
                "request_count": len(group),
                "error_rate": errors / len(group) * 100,
                "latency_p95": _quantile(durations, 0.95),
            })
        else:
            result.append({
                "service": service,
                **{f"p{p}": _quantile(durations, p / 100) for p in (50, 95, 99)},
                "max_latency": max(durations, default=0),
                "avg_latency": sum(durations) / len(durations),
                "request_count": len(group),
            })
    return result


def _query_conditions(query: str) -> Dict[str, Any]:
    trace_match = re.search(r"trace_id\s*=\s*'([^']*)'", query)
    service_match = re.search(r"service\s*=\s*'([^']*)'", query)
    error_match = re.search(r"error_message\s+like\s+'%([^']*)%'", query)
    return {
        "trace_id": trace_match.group(1) if trace_match else None,
        "service": service_match.group(1) if service_match else None,
        "error_text": error_match.group(1) if error_match else None,
        "errors_only": "status_code >= 400" in query,
    }


def _in_filter(query: str, field: str) -> Optional[set[str]]:
    match = re.search(rf"\b{field}\s+in\s*\(([^)]*)\)", query)
    if not match:
        return None
    return {value.strip().strip("'") for value in match.group(1).split(",")}


def _equals_filter(query: str, field: str) -> Optional[str]:
    match = re.search(rf"\b{field}\s*=\s*'([^']*)'", query)
    return match.group(1) if match else None


def _interval_minutes(query: str) -> int:
    match = re.search(r"interval\s+(\d+)\s+minute", query)
    return int(match.group(1)) if match else 5


def _interval_label(value: str, minutes: int) -> str:
    timestamp = datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
    minute = timestamp.minute - timestamp.minute % minutes
    return timestamp.replace(minute=minute, second=0, microsecond=0).isoformat(sep=" ")


def _quantile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile)))
    return values[index]


def _before_after_split(query: str) -> str:
    match = re.search(r"timestamp\s*<\s*'([^']+)'", query, re.IGNORECASE)
    return match.group(1).replace("T", " ") if match else ""


def _timestamp_bounds(query: str) -> List[str]:
    return [
        value.replace("T", " ")
        for value in re.findall(r"timestamp\s*>=\s*'([^']+)'", query, re.IGNORECASE)
    ]


def _first_timestamp(query: str) -> str:
    values = _timestamp_bounds(query)
    return values[0] if values else ""


def _second_timestamp(query: str, upper: bool = False) -> str:
    matches = [
        value.replace("T", " ")
        for value in re.findall(r"timestamp\s*<\s*'([^']+)'", query, re.IGNORECASE)
    ]
    if upper:
        return matches[1] if len(matches) > 1 else ""
    values = _timestamp_bounds(query)
    return values[1] if len(values) > 1 else ""


def _in_scope(value: Any, values: Optional[set[str]]) -> bool:
    return values is None or str(value) in values
