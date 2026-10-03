"""Phase 5: metrics registry and Prometheus exposition."""

from observability.metrics import Histogram, MetricsRegistry, get_metrics, reset_metrics


def test_counter_accumulates_with_labels():
    registry = MetricsRegistry()
    counter = registry.counter("requests_total", "Total requests", ("method", "status"))

    counter.inc(labels={"method": "GET", "status": "200"})
    counter.inc(2, labels={"method": "GET", "status": "200"})
    counter.inc(labels={"method": "POST", "status": "500"})

    assert counter.value({"method": "GET", "status": "200"}) == 3
    assert counter.value({"method": "POST", "status": "500"}) == 1


def test_gauge_can_inc_and_dec():
    registry = MetricsRegistry()
    gauge = registry.gauge("in_flight", "In-flight")

    gauge.inc()
    gauge.inc()
    gauge.dec()
    assert gauge.value() == 1


def test_histogram_buckets_are_cumulative():
    registry = MetricsRegistry()
    histogram = registry.histogram("latency_seconds", "Latency", buckets=(0.1, 0.5, 1.0))

    for value in (0.05, 0.3, 0.9, 5.0):
        histogram.observe(value)

    assert histogram.count() == 4
    assert histogram.total() == 0.05 + 0.3 + 0.9 + 5.0
    text = registry.render()
    assert 'latency_seconds_bucket{le="0.1"} 1' in text
    assert 'latency_seconds_bucket{le="0.5"} 2' in text
    assert 'latency_seconds_bucket{le="1.0"} 3' in text
    assert 'latency_seconds_bucket{le="+Inf"} 4' in text
    assert "latency_seconds_count 4" in text


def test_render_includes_help_and_type():
    registry = MetricsRegistry()
    registry.counter("c_total", "A counter").inc()
    registry.gauge("g", "A gauge").set(3)

    text = registry.render()
    assert "# HELP c_total A counter" in text
    assert "# TYPE c_total counter" in text
    assert "c_total 1" in text
    assert "# TYPE g gauge" in text
    assert "g 3" in text


def test_same_name_returns_same_metric():
    registry = MetricsRegistry()
    first = registry.counter("shared_total", "Shared")
    second = registry.counter("shared_total", "Shared")
    first.inc()
    assert second.value() == 1


def test_get_metrics_is_a_singleton_and_resets():
    first = get_metrics()
    assert first is get_metrics()
    first.counter("temp_total", "Temp").inc()
    reset_metrics()
    assert get_metrics() is not first


def test_histogram_rejects_unsorted_buckets():
    registry = MetricsRegistry()
    try:
        registry.histogram("bad", "Bad", buckets=(0.5, 0.1))
    except ValueError:
        return
    raise AssertionError("unsorted buckets should be rejected")


def test_histogram_class_direct():
    histogram = Histogram("h", "H", buckets=(1.0, 2.0))
    histogram.observe(1.5)
    assert histogram.count() == 1
