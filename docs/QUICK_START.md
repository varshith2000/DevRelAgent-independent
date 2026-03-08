# Complete Setup Guide - DevRelAgent with OpenTelemetry

## One-Line Setup

### Linux/macOS:
```bash
chmod +x setup.sh && ./setup.sh
```

### Windows:
```cmd
setup.bat
```

---

## What Gets Installed

The setup script installs and configures:

| Component | Purpose | URL/Port |
|-----------|---------|----------|
| **ClickHouse** | Database for logs/metrics/traces | `http://localhost:8123` |
| **Grafana** | Dashboards | `http://localhost:3000` |
| **OTel Collector** | Receives telemetry from services | `localhost:4317` (gRPC) |
| **DevRelAgent** | Investigation & automation | `http://localhost:8000` |

---

## Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐     ┌──────────────┐
│ Your Service│ ──> │ OTel Collector│ ──> │ ClickHouse │ ──> │ DevRelAgent  │
│ (with OTel) │     │ (port 4317)   │     │ (port 8123)│     │  (CLI/API)   │
└─────────────┘     └──────────────┘     └────────────┘     └──────────────┘
                                                ↓
                                          ┌───────────┐
                                          │  Grafana  │
                                          │ (port 3000)│
                                          └───────────┘
```

---

## Manual Setup Steps

If you prefer manual setup instead of the script:

### 1. Start Services

```bash
docker-compose up -d
```

### 2. Initialize ClickHouse

```bash
docker exec -i devrelagent-clickhouse clickhouse-client --multiquery < scripts/init_clickhouse.sql
```

### 3. Configure Grafana

1. Open `http://localhost:3000`
2. Login with `admin/admin`
3. Create API token:
   - Go to **Configuration** → **API Keys**
   - Click **Add API key**
   - Name: `DevRelAgent`
   - Role: `Admin`
   - Copy token

4. Configure ClickHouse datasource:
   - Go to **Configuration** → **Data sources**
   - Click **Add data source**
   - Select **ClickHouse**
   - Host: `clickhouse:9000` (or `localhost:9000` if outside Docker)
   - Database: `logs`
   - Click **Save & Test**

### 4. Update Environment Variables

Edit `.env`:
```bash
GRAFANA_API_TOKEN=your_copied_token_here
```

### 5. Test Connection

```bash
cd apps/backend
python cli.py grafana test-connection
```

### 6. Create Dashboard

```bash
python cli.py grafana create-dashboard --service my-api
```

---

## Instrumenting Your Service

### Python Example

```python
# Install OpenTelemetry
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-flask opentelemetry-exporter-otlp

# Add to your Flask/FastAPI app
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Setup
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="localhost:4317"))
)

# Instrument Flask
app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
```

### Node.js Example

```javascript
// Install
npm install @opentelemetry/api @opentelemetry/sdk-node @opentelemetry/auto-instrumentations

// Add to your app
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations');

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({
    url: 'http://localhost:4317/v1/traces',
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();
```

### Go Example

```go
// Install
go get go.opentelemetry.io/otel
go get go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc

// Add to your app
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func initTracer() {
    exporter, _ := otlptracegrpc.New(context.Background(),
        otlptracegrpc.WithEndpoint("localhost:4317"),
        otlptracegrpc.WithInsecure(),
    )
    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exporter),
    )
    otel.SetTracerProvider(tp)
}
```

---

## Generate OTel Config Automatically

Use DevRelAgent to generate OpenTelemetry config for your language:

```bash
# Python
python cli.py investigate "Generate OpenTelemetry config for Python"

# Node.js
python cli.py investigate "Generate OpenTelemetry config for Node.js"

# Go
python cli.py investigate "Generate OpenTelemetry config for Go"

# Java
python cli.py investigate "Generate OpenTelemetry config for Java"

# .NET
python cli.py investigate "Generate OpenTelemetry config for .NET"
```

---

## Verify Data Flow

### 1. Check OTel Collector is receiving data

```bash
# View collector metrics
curl http://localhost:8888/metrics | grep otelcol_receiver_accepted
```

### 2. Check ClickHouse is receiving data

```bash
# View recent traces
docker exec -it devrelagent-clickhouse clickhouse-client --query "
SELECT service_name, span_name, timestamp
FROM logs.otel_traces
ORDER BY timestamp DESC
LIMIT 10
"

# View recent logs
docker exec -it devrelagent-clickhouse clickhouse-client --query "
SELECT service, level, message
FROM logs.logs
ORDER BY timestamp DESC
LIMIT 10
"
```

### 3. Check Grafana dashboards

1. Open `http://localhost:3000`
2. Find your dashboard: `devrelagent-my-api`
3. Verify panels are showing data

---

## Troubleshooting

### No data in dashboard

**Check 1: Service sending data?**
```bash
curl http://localhost:8888/metrics | grep receiver
```

**Check 2: OTel Collector receiving?**
```bash
docker-compose logs otel-collector | tail -20
```

**Check 3: ClickHouse receiving?**
```bash
docker exec devrelagent-clickhouse clickhouse-client --query "SELECT count(*) FROM logs.otel_traces"
```

**Check 4: Grafana datasource configured?**
- Go to Configuration → Data sources
- Test connection

### Connection refused errors

**OTel Collector not accessible:**
```bash
# Check if running
docker ps | grep otel-collector

# Check logs
docker-compose logs otel-collector

# Restart
docker-compose restart otel-collector
```

### High memory usage

Adjust limits in `otel-collector-config.yaml`:
```yaml
processors:
  memory_limiter:
    limit_mib: 512  # Reduce if needed
```

---

## Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (deletes all data!)
docker-compose down -v
```

---

## Next Steps

1. ✅ Run setup script
2. ✅ Configure Grafana API token
3. ✅ Create dashboard for your service
4. ✅ Instrument your service with OTel
5. ✅ Verify data appears in dashboard
6. ✅ Start investigating issues!

```bash
# Example investigation
python cli.py investigate "Why is my API showing errors?"
```

---

## Support

- **Documentation**: See `docs/` folder
- **Issues**: Create GitHub issue
- **Setup Help**: See `INSTALLATION_SETUP_GUIDE.md`

**Happy monitoring! 🚀**
