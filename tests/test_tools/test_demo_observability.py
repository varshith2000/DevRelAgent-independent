import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from database.observability_store import (
    ClickHouseObservabilityStore,
    InMemoryObservabilityStore,
)
from tools import observability_tool

from scripts.load_demo_observability import SCENARIO_ID, load_demo, read_fixture


def test_fixture_materializes_recent_correlated_signals_deterministically():
    now = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
    first = read_fixture(now)
    second = read_fixture(now)

    assert first == second
    assert len(first["logs"]) == 12
    assert len(first["otel_traces"]) == 8
    assert len(first["otel_metrics"]) == 4
    assert all(
        row["attributes"]["demo.scenario_id"] == SCENARIO_ID
        for signal in first.values()
        for row in signal
    )
    assert all(
        0 <= (
            now
            - datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S.%f").replace(
                tzinfo=timezone.utc
            )
        ).total_seconds() <= 1800
        for signal in first.values()
        for row in signal
    )

    failed_log = next(row for row in first["logs"] if row["status_code"] == 500)
    correlated_spans = [
        row for row in first["otel_traces"] if row["trace_id"] == failed_log["trace_id"]
    ]
    assert len(correlated_spans) == 2
    assert correlated_spans[0]["span_id"] == failed_log["span_id"]
    assert correlated_spans[1]["parent_span_id"] == failed_log["span_id"]
    assert any(
        row["metric_name"] == "http.server.error_rate" and row["value"] == 40.0
        for row in first["otel_metrics"]
    )


def test_demo_snapshot_supports_error_latency_and_trace_analysis(monkeypatch):
    rows = read_fixture(datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(
        observability_tool,
        "get_observability_store",
        lambda: InMemoryObservabilityStore(rows),
    )

    async def check():
        errors = await observability_tool.get_top_errors(
            services=["orders-api"], time_range_minutes=60
        )
        latency = await observability_tool.get_latency_metrics(
            services=["orders-api"], time_range_minutes=60
        )
        comparison = await observability_tool.compare_before_after(
            timestamp="2026-10-05 11:57:00",
            before_minutes=30,
            after_minutes=30,
            services=["orders-api"],
        )
        traces = await observability_tool.correlate_error_with_traces(
            trace_id="30000000000000000000000000000001"
        )
        return errors, latency, traces, comparison

    errors, latency, traces, comparison = asyncio.run(check())

    assert errors["success"] is True
    assert errors["errors"][0]["error_message"] == "Database connection pool exhausted after 5s"
    assert errors["errors"][0]["count"] == 3
    assert latency["success"] is True
    assert (
        latency["services"]["orders-api"]["span_breakdown"]["SELECT inventory for order"][
            "count"
        ]
        == 4
    )
    assert traces["success"] is True
    assert traces["traces"][0]["span_count"] == 2
    assert traces["traces"][0]["status_code"] == 500
    assert comparison["success"] is True
    assert comparison["comparisons"]["orders-api"]["before"]["request_count"] == 5
    assert comparison["comparisons"]["orders-api"]["after"]["request_count"] == 7


def test_loader_refuses_non_loopback_before_making_requests():
    with pytest.raises(ValueError, match="localhost"):
        load_demo("https://clickhouse.example.com")


def test_loader_refuses_duplicate_fixture_without_mutating_tables(monkeypatch):
    calls = []

    def fake_request(url, query, username, password):
        calls.append(query)
        return "11" if "logs.logs" in query else "0"

    monkeypatch.setattr("scripts.load_demo_observability._request", fake_request)

    with pytest.raises(RuntimeError, match="--replace-demo"):
        load_demo("http://localhost:8123")

    assert len(calls) == 3
    assert all("SELECT count()" in query for query in calls)
    assert all("ALTER TABLE" not in query and "INSERT INTO" not in query for query in calls)


def test_clickhouse_adapter_normalizes_rows_off_event_loop(monkeypatch):
    class FakeClient:
        def execute_query(self, query):
            return SimpleNamespace(
                column_names=["service", "total_requests"],
                result_rows=[("orders-api", 7)],
            )

    monkeypatch.setattr("database.clickhouse_client.get_clickhouse_client", FakeClient)
    result = asyncio.run(ClickHouseObservabilityStore().execute_query("SELECT service, count()"))

    assert result.success is True
    assert result.data == [{"service": "orders-api", "total_requests": 7}]
