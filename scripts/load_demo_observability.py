"""Load the synthetic incident fixture into a local ClickHouse instance.

This importer only targets a loopback URL and only touches rows tagged with the
fixture's fixed scenario ID. Existing rows are never removed unless
``--replace-demo`` is explicitly supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

FIXTURE = Path(__file__).parent / "fixtures" / "demo_incident.jsonl"
SCENARIO_ID = "devrel-orders-pool-v1"
LOG_COLUMNS = (
    "timestamp,service,level,message,trace_id,span_id,attributes,method,endpoint,"
    "status_code,duration_ms,error_type,error_message,stack_trace,environment,host_name"
)
TRACE_COLUMNS = (
    "timestamp,trace_id,span_id,parent_span_id,service_name,service_namespace,span_name,"
    "span_kind,status_code,status_message,duration_ns,attributes,resource_attributes,events,"
    "links,environment,host_name"
)
METRIC_COLUMNS = (
    "timestamp,metric_name,metric_type,service_name,value,attributes,resource_attributes,"
    "environment,host_name"
)


def read_fixture(now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    """Materialize fixture rows relative to now so query windows include them."""
    current = now or datetime.now(timezone.utc)
    rows: dict[str, list[dict[str, Any]]] = {
        "logs": [],
        "otel_traces": [],
        "otel_metrics": [],
    }

    for line_number, line in enumerate(FIXTURE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        signal = item.pop("signal")
        age = item.pop("age_seconds")
        item["timestamp"] = (current - timedelta(seconds=age)).strftime("%Y-%m-%d %H:%M:%S.%f")
        item["attributes"] = {
            **item.get("attributes", {}),
            "demo.scenario_id": SCENARIO_ID,
        }

        if signal == "log":
            item["environment"] = "demo"
            item["host_name"] = "demo-orders-api"
        elif signal == "trace":
            item["service_name"] = item.pop("service")
            item["service_namespace"] = "demo"
            item["duration_ns"] = int(item.pop("duration_ms") * 1_000_000)
            item["resource_attributes"] = {
                "service.name": item["service_name"],
                "service.namespace": "demo",
                "deployment.environment": "demo",
            }
            item["events"] = []
            item["links"] = []
            item["environment"] = "demo"
            item["host_name"] = "demo-orders-api"
        elif signal == "metric":
            item["service_name"] = item.pop("service")
            item["resource_attributes"] = {
                "service.name": item["service_name"],
                "deployment.environment": "demo",
            }
            item["environment"] = "demo"
            item["host_name"] = "demo-orders-api"
        else:
            raise ValueError(f"Unknown signal on fixture line {line_number}: {signal}")

        table = {"log": "logs", "trace": "otel_traces", "metric": "otel_metrics"}[signal]
        rows[table].append(item)

    return rows


def _request(url: str, query: str, username: str, password: str) -> str:
    """Send one ClickHouse HTTP query without printing credentials or SQL data."""
    body = query.encode("utf-8")
    request = Request(url, data=body, method="POST")
    request.add_header("Content-Type", "text/plain; charset=utf-8")
    if username:
        import base64

        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    with urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8").strip()


def _insert_json_rows(
    url: str, table: str, columns: str, data: list[dict[str, Any]], username: str, password: str
) -> None:
    if not data:
        return
    statement = f"INSERT INTO logs.{table} ({columns}) FORMAT JSONEachRow\n"
    payload = statement + "\n".join(json.dumps(row, separators=(",", ":")) for row in data)
    _request(url, payload, username, password)


def load_demo(url: str, username: str = "default", password: str = "", replace: bool = False) -> dict[str, int]:
    """Insert the tagged sample into initialized local ClickHouse tables."""
    host = urlparse(url).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Safety check: the demo loader only accepts a localhost ClickHouse URL")
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("ClickHouse URL must use http or https")

    rows = read_fixture()
    tables = {"logs": "logs", "otel_traces": "trace", "otel_metrics": "metric"}
    existing_by_table = {
        table: int(
            _request(
                url,
                f"SELECT count() FROM logs.{table} WHERE attributes['demo.scenario_id'] = "
                f"'{SCENARIO_ID}' FORMAT TabSeparated",
                username,
                password,
            )
            or "0"
        )
        for table in tables
    }
    existing = sum(existing_by_table.values())

    if existing and not replace:
        raise RuntimeError(
            f"Found {existing} rows from this demo. Nothing changed. "
            "Use --replace-demo to replace only rows tagged with this synthetic scenario."
        )

    if existing and replace:
        # Remove only the reserved fixture id across all three target tables.
        for table, count in existing_by_table.items():
            if count:
                _request(
                    url,
                    f"ALTER TABLE logs.{table} DELETE WHERE "
                    f"attributes['demo.scenario_id'] = '{SCENARIO_ID}' SETTINGS mutations_sync = 1",
                    username,
                    password,
                )

    # Mirror request summaries into the generic logs table used by current
    # error-rate/latency tools; the duplicate carries an explicit demo marker.
    _insert_json_rows(url, "logs", LOG_COLUMNS, rows["logs"], username, password)
    _insert_json_rows(url, "otel_traces", TRACE_COLUMNS, rows["otel_traces"], username, password)
    _insert_json_rows(url, "otel_metrics", METRIC_COLUMNS, rows["otel_metrics"], username, password)
    return {
        "logs": len(rows["logs"]),
        "traces": len(rows["otel_traces"]),
        "metrics": len(rows["otel_metrics"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8123", help="Local ClickHouse HTTP URL")
    parser.add_argument("--username", default="default")
    parser.add_argument("--password", default="")
    parser.add_argument(
        "--replace-demo",
        action="store_true",
        help="Delete only rows tagged with this fixture ID before inserting them again",
    )
    args = parser.parse_args()

    try:
        counts = load_demo(args.url, args.username, args.password, args.replace_demo)
    except Exception as exc:
        print(f"Demo telemetry load failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Loaded synthetic orders incident telemetry: "
        f"{counts['logs']} logs, {counts['traces']} spans, {counts['metrics']} metrics."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
