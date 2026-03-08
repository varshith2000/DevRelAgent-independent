-- ClickHouse initialization script for DevRelAgent
-- This creates the necessary tables for OpenTelemetry data

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS logs;

-- Switch to logs database
USE logs;

-- ============================================
-- OPENTELEMETRY TRACES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS otel_traces (
    timestamp DateTime64(9),
    trace_id String,
    span_id String,
    parent_span_id String,
    service_name String,
    service_namespace String,
    span_name String,
    span_kind String,
    status_code String,
    status_message String,
    duration_ns UInt64,
    attributes Map(String, String),
    resource_attributes Map(String, String),
    events Array(Map(String, String)),
    links Array(Map(String, String)),
    -- Additional fields for querying
    environment String DEFAULT 'production',
    host_name String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service_name, timestamp, trace_id, span_id)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_traces_service_name ON otel_traces (service_name) TYPE bloom_filter GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON otel_traces (trace_id) TYPE bloom_filter GRANULARITY 1;

-- ============================================
-- OPENTELEMETRY METRICS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS otel_metrics (
    timestamp DateTime64(9),
    metric_name String,
    metric_type String,
    service_name String,
    value Float64,
    attributes Map(String, String),
    resource_attributes Map(String, String),
    -- Additional fields
    environment String DEFAULT 'production',
    host_name String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service_name, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_metrics_service_name ON otel_metrics (service_name) TYPE bloom_filter GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_metrics_metric_name ON otel_metrics (metric_name) TYPE bloom_filter GRANULARITY 1;

-- ============================================
-- OPENTELEMETRY LOGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS otel_logs (
    timestamp DateTime64(9),
    severity_number Int32,
    severity_text String,
    service_name String,
    body String,
    attributes Map(String, String),
    resource_attributes Map(String, String),
    trace_id String,
    span_id String,
    -- Additional fields
    environment String DEFAULT 'production',
    host_name String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service_name, timestamp, severity_text)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_logs_service_name ON otel_logs (service_name) TYPE bloom_filter GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_logs_severity ON otel_logs (severity_text) TYPE bloom_filter GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_logs_trace_id ON otel_logs (trace_id) TYPE bloom_filter GRANULARITY 1;

-- ============================================
-- GENERIC LOGS TABLE (for non-OTel logs)
-- ============================================
CREATE TABLE IF NOT EXISTS logs (
    timestamp DateTime64(9) DEFAULT now64(),
    service String,
    level String,
    message String,
    trace_id String DEFAULT '',
    span_id String DEFAULT '',
    attributes Map(String, String) DEFAULT map(),
    -- HTTP request fields
    method String DEFAULT '',
    endpoint String DEFAULT '',
    status_code UInt16 DEFAULT 0,
    duration_ms UInt32 DEFAULT 0,
    -- Error fields
    error_type String DEFAULT '',
    error_message String DEFAULT '',
    stack_trace String DEFAULT '',
    -- Additional fields
    environment String DEFAULT 'production',
    host_name String DEFAULT getHostName()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service, timestamp, level)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_logs_service ON logs (service) TYPE bloom_filter GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs (level) TYPE bloom_filter GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_logs_trace_id_2 ON logs (trace_id) TYPE bloom_filter GRANULARITY 1;

-- ============================================
-- ERRORS TABLE (for quick error queries)
-- ============================================
CREATE TABLE IF NOT EXISTS errors (
    timestamp DateTime64(9) DEFAULT now64(),
    service String,
    error_type String,
    error_message String,
    severity String,
    count UInt32 DEFAULT 1,
    attributes Map(String, String) DEFAULT map(),
    trace_id String DEFAULT '',
    first_seen DateTime64(9) DEFAULT now64(),
    last_seen DateTime64(9) DEFAULT now64()
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service, error_type, timestamp)
TTL timestamp + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- SERVICE HEALTH TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS service_health (
    timestamp DateTime64(9) DEFAULT now64(),
    service String,
    status String DEFAULT 'unknown',  -- green, yellow, red
    error_rate Float32 DEFAULT 0.0,
    p95_latency_ms Float32 DEFAULT 0.0,
    p99_latency_ms Float32 DEFAULT 0.0,
    requests_per_second Float32 DEFAULT 0.0,
    availability Float32 DEFAULT 100.0,
    attributes Map(String, String) DEFAULT map()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service, timestamp)
TTL timestamp + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- CREATE VIEWS FOR COMMON QUERIES
-- ============================================

-- Error rate view
CREATE VIEW IF NOT EXISTS v_error_rate AS
SELECT
    toStartOfInterval(timestamp, INTERVAL 60 second) AS time_bucket,
    service,
    countIf(level = 'ERROR') AS error_count,
    count(*) AS total_count,
    error_count / total_count * 100 AS error_rate
FROM logs
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY service, time_bucket
ORDER BY time_bucket DESC, service;

-- Latency percentiles view
CREATE VIEW IF NOT EXISTS v_latency AS
SELECT
    toStartOfInterval(timestamp, INTERVAL 60 second) AS time_bucket,
    service,
    quantile(0.50)(duration_ms) AS p50_ms,
    quantile(0.95)(duration_ms) AS p95_ms,
    quantile(0.99)(duration_ms) AS p99_ms,
    avg(duration_ms) AS avg_ms
FROM logs
WHERE duration_ms > 0 AND timestamp > now() - INTERVAL 24 HOUR
GROUP BY service, time_bucket
ORDER BY time_bucket DESC, service;

-- Top errors view
CREATE VIEW IF NOT EXISTS v_top_errors AS
SELECT
    service,
    error_type,
    error_message,
    count(*) AS error_count,
    max(timestamp) AS last_seen
FROM logs
WHERE level = 'ERROR' AND timestamp > now() - INTERVAL 24 HOUR
GROUP BY service, error_type, error_message
ORDER BY error_count DESC
LIMIT 100;

-- Availability view
CREATE VIEW IF NOT EXISTS v_availability AS
SELECT
    toStartOfInterval(timestamp, INTERVAL 60 second) AS time_bucket,
    service,
    (1 - (countIf(status_code >= 500 OR level = 'ERROR') / count(*))) * 100 AS availability,
    count(*) AS total_requests,
    countIf(status_code >= 500 OR level = 'ERROR') AS error_requests
FROM logs
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY service, time_bucket
ORDER BY time_bucket DESC, service;

-- ============================================
-- SAMPLE DATA (for testing)
-- ============================================
-- Uncomment to insert sample data
/*
INSERT INTO logs (service, level, message, endpoint, method, status_code, duration_ms) VALUES
    ('api', 'INFO', 'Request received', '/api/users', 'GET', 200, 45),
    ('api', 'INFO', 'Request received', '/api/users', 'GET', 200, 52),
    ('api', 'ERROR', 'Database timeout', '/api/orders', 'POST', 500, 5000),
    ('database', 'INFO', 'Query executed', '', '', 0, 15),
    ('api', 'INFO', 'Request received', '/api/products', 'GET', 200, 38);
*/
