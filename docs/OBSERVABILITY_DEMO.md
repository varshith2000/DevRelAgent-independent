# Observability demo: logs, traces, metrics, and alerts

This walkthrough creates a small **synthetic** `orders-api` incident so you can test searches and diagnosis without waiting for a real outage. It contains a pre-deployment baseline, a post-deployment period, request failures, child database spans, and metrics. It contains no real customer data.

## Start here: test without ClickHouse

The fixture can be queried in-process without any database or credentials:

```bash
# Run from the repository root
python - <<'PY'
import asyncio
import sys

sys.path.insert(0, "apps/backend")
from database.observability_store import InMemoryObservabilityStore
from scripts.load_demo_observability import read_fixture
from tools import observability_tool

observability_tool.get_observability_store = lambda: InMemoryObservabilityStore(read_fixture())
errors = asyncio.run(observability_tool.get_top_errors(services=["orders-api"], time_range_minutes=60))
print(errors)
PY
```

Fixture source: [demo_incident.jsonl](../scripts/fixtures/demo_incident.jsonl). Its timestamps are offsets from the current time at load, not fixed dates, so current-window analysis keeps working. Signal row counts are 12 request logs, 8 spans, and 4 metrics. The in-memory store exercises deterministic analysis queries; it is a lightweight demo/test adapter, not a production backend.

Try the API chat on a running backend:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Email: dev@localhost' \
  -H 'X-Dev-User-Name: Demo User' \
  -H 'X-Dev-Workspace: dev-workspace' \
  -d '{"message":"Show recent errors for orders-api and correlate the failure with traces."}'
```

The regular chat endpoint currently routes most natural-language observability prompts to the ClickHouse NL-to-SQL tool. To run the API prompt end-to-end, connect ClickHouse and load the fixture as described below. In-memory mode is for Python-level tool/tests only; it is not activated in the server automatically.

Suggested investigation prompts once data is loaded:

- “Show recent errors for orders-api.”
- “What is the error rate for orders-api in the last hour?”
- “Show latency for orders-api in the last hour.”
- “Correlate trace `30000000000000000000000000000001` with the database error.”
- “Compare orders-api before and after the deployment.”

## Optional: load into local ClickHouse

The loader accepts **loopback HTTP URLs only**, checks for rows with its reserved scenario marker, and refuses duplicates unless you explicitly request a replacement. It never targets a hosted ClickHouse service. It expects the schema in `scripts/init_clickhouse.sql` to have already been applied.

1. Start the local ClickHouse service from the repository root with `docker compose up -d clickhouse`.
2. Initialize the `logs` schema:

   ```bash
   docker exec -i devrelagent-clickhouse clickhouse-client --multiquery < scripts/init_clickhouse.sql
   ```

3. Load once (safe if an identical demo is already present; duplicate check aborts without inserting):

   ```bash
   python scripts/load_demo_observability.py
   ```

   For a non-default local account, pass `--username` and `--password` flags. Never paste secrets into chat or commit them.

4. Inspect the loaded data:

   ```bash
   docker exec devrelagent-clickhouse clickhouse-client --query \
     "SELECT service, level, status_code, error_message, trace_id FROM logs.logs WHERE attributes['demo.scenario_id']='devrel-orders-pool-v1' ORDER BY timestamp DESC"
   docker exec devrelagent-clickhouse clickhouse-client --query \
     "SELECT service_name, span_name, trace_id, parent_span_id FROM logs.otel_traces WHERE resource_attributes['service.namespace']='demo' ORDER BY timestamp DESC"
   docker exec devrelagent-clickhouse clickhouse-client --query \
     "SELECT service_name, metric_name, value FROM logs.otel_metrics WHERE resource_attributes['deployment.environment']='demo' ORDER BY timestamp DESC"
   ```

5. To refresh only these fixture rows, opt in explicitly:

   ```bash
   python scripts/load_demo_observability.py --replace-demo
   ```

   The command deletes rows carrying its reserved marker in the three telemetry tables, and then reloads the deterministic fixture with fresh timestamps. It does not truncate tables. If loading partially fails, rerun with `--replace-demo` to clean up only the fixture's tagged rows.

## What the data says

- Baseline (`deployment.version=2026.10.04-17`): successful order requests around 84–126 ms.
- After deployment (`2026.10.05-02`): successful requests remain, then error responses increase.
- Incident: three HTTP 500 pool timeouts and one HTTP 503 inventory timeout. Error rows carry error type/message, stack excerpt, endpoint, status, environment, deployment version, and trace/span IDs.
- Traces: each failed request has a server span and a child PostgreSQL client span linked by `trace_id` and `parent_span_id`; that points investigation toward database connection acquisition rather than guessing from a message alone.
- Metrics: request latency rises from 155 ms to 5,200 ms (the fixture stores durations in milliseconds), error rate is 40%, and pool wait time is 5 seconds.

## What to connect in a real environment

```text
Your services / hosts / Kubernetes
  ├─ OTel SDK/auto-instrumentation → OTLP gRPC :4317 or HTTP :4318 ─┐
  └─ existing logs → OTel filelog/syslog/other receiver (configure it) ─┤
                                                                     v
                                                        OTel Collector
                                                        receive → process → export
                                                                     v
                                                     telemetry backend/storage
                                                                     v
                                              DevRelAgent query adapter + credentials
                                                                     v
                                            agent investigation / evidence / response
```

1. **Instrument the workload or collect its output.** Install an OpenTelemetry SDK and framework/database instrumentation, or configure a collector file/host/Kubernetes receiver for existing logs. OTLP defines a vendor-neutral way for producers to send logs, traces, and metrics. An endpoint alone does not generate signals: the app/agent must emit or collect them.
2. **Set stable identity/context.** At minimum set `service.name`, environment, and service version. Keep `trace_id`/`span_id` on logs if your logging integration supports it. Propagate W3C trace context across service boundaries so spans form one trace. Include HTTP route/method/status, database system/operation, and deployment version where available; redact secrets and sensitive user data before export.
3. **Point the exporter at the Collector.** In this Compose stack, a process on the host uses `localhost:4317` (gRPC) or OTLP HTTP `http://localhost:4318`; a service inside the Compose network uses `otel-collector:4317` / `http://otel-collector:4318`. Those two addresses are not interchangeable. The current collector configuration receives OTLP traces/logs/metrics, Prometheus-scraped metrics, and Jaeger traces; the configured exporter writes telemetry to ClickHouse. It does **not** currently tail arbitrary app log files: configure a filelog/host receiver if needed. The collector's actual exporter support/schema must match its image/version.
4. **Connect the DevRelAgent reader.** Current query tools and scheduler use ClickHouse SQL and ClickHouse-specific tables. For local Compose, set the backend's ClickHouse host/database/credentials for `logs` and use HTTP port `8123`; set the ClickHouse client TLS option off for local HTTP and on only for a TLS endpoint. For the agent container, use hostname `clickhouse` on the Compose network. For a hosted database use that provider's host, port, credentials, and TLS settings. Use a read-only account with only the required tables and no secrets in prompts.
5. **Validate each hop.** Check collector logs/receiver accepted counters, query the destination tables for recent service names and timestamps, then ask DevRelAgent a scoped error/trace question. A green `/health` checks the API process and tool listing; it does **not** prove ClickHouse or telemetry ingestion is working. Grafana is a separate visualization client, not the route by which data reaches DevRelAgent.

## Is it platform agnostic today?

**The telemetry protocol at the producer edge can be vendor-neutral; the current analysis backend is not.** OpenTelemetry standardizes telemetry generation/transport, and the Collector can route to exporters it actually has installed/configured. DevRelAgent's observability query functions and periodic health poll currently issue ClickHouse SQL. A Prometheus scrape receiver is present in Collector configuration for metrics input; that does not make DevRelAgent's query engine a Prometheus/Datadog/Splunk/Elastic adapter. Connecting another vendor requires a reader/query adapter for its API or query language, authentication/configuration, common field mapping, and provider-specific tests. Do not assume a vendor works just because it accepts OTLP.

A provider-neutral query contract and deterministic in-memory fixture store now support the analysis functions and tests; **ClickHouse is still the only live adapter implemented**. This is the safe incremental foundation for additional read adapters. Existing free-form ClickHouse NL-to-SQL and scheduler polling remain ClickHouse-specific.

## How environment notifications work here

The service does not currently push alerts into DevRelAgent merely because a log was written. Telemetry flows from the workload to the collector, then to the configured store; DevRelAgent reads it when asked. Separately, when `HEALTH_CHECK_ENABLED=true` and the backend successfully connects to ClickHouse, an APScheduler job polls the `logs` table at `HEALTH_CHECK_INTERVAL_MINUTES`, calculates per-service ERROR-level rates, and compares them to `ERROR_SPIKE_THRESHOLD` (default 5%). It emits an in-memory alert and the dashboard SSE route can stream dashboard events. The current setup does not provide a general incoming alert webhook, durable alert store, or vendor alert-manager receiver. `/dashboard/test-alert` only broadcasts a transient dashboard test event; it does not insert a real alert or exercise data ingestion.

To make a real third-party monitor notify this application directly, connect its webhook/alert manager to a future authenticated alert-ingest endpoint, or configure the collector/backend to receive and store its signals, then implement the corresponding provider adapter. Do not expose an unauthenticated webhook or let external alerts trigger remediation automatically; validate signatures, deduplicate/replay-protect events, and require human approval for consequential actions.

## Current wiring gaps to fix before production

- The checked-in Collector exporter configuration should be validated against the pinned Collector Contrib release and ClickHouse exporter schema. The exporter documented by Collector Contrib uses one `clickhouse` exporter with `logs_table_name`, `traces_table_name`, and metrics table names; receiver configuration must not be treated as proof that exporters are valid.
- The SQL initialization schema defines `logs.otel_traces`, `logs.otel_metrics`, and `logs.otel_logs`; ClickHouse Contrib exporter defaults/versioned schemas may differ (especially metric tables). Keep the collector and DDL in a compatible, tested version pair.
- The setup example's demo loader inserts trace and metric rows into the repository's declared DDL and request summaries into `logs.logs`, because existing agent queries require those request-shaped columns. Real OTLP exporter logs are stored in `otel_logs` and need a production normalization/materialized view/adapter before current request/error analysis tools can treat them as HTTP access rows.
- Current analysis tools use a row-normalizing interface but hard-code ClickHouse SQL and table names. Additional stores need provider-specific query implementations, not only a settings switch.

## Telemetry schema fields worth emitting

| Signal | Useful fields | Why DevRelAgent needs them |
|---|---|---|
| Logs | timestamp, service, severity, message, environment, version, trace_id, span_id, route, status, error type/message | Find recurring errors and pivot to traces |
| Traces/spans | trace_id, span_id, parent_span_id, service, span name/kind, start/duration, status, HTTP/database attributes | Locate the slow/failing dependency and preserve causality |
| Metrics | timestamp, service, metric name/type/value/unit, route/dependency dimensions | Quantify latency/error/resource trends against baseline |
| Deployment/context | service version, environment, deployment time or change marker | Compare behavior before vs after a change |

Keep high-cardinality identifiers (request IDs, user IDs) out of metric labels; use trace/log fields for per-request correlation. Never send credentials, authorization headers, payment data, or unredacted personal data into telemetry.
