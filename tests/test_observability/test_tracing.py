"""Phase 5: W3C traceparent handling and span tracing."""

from observability.tracing import (
    Tracer,
    format_traceparent,
    parse_traceparent,
)

VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_parse_valid_traceparent():
    parsed = parse_traceparent(VALID)
    assert parsed == ("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7", True)


def test_parse_unsampled_traceparent():
    parsed = parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00")
    assert parsed is not None
    assert parsed[2] is False


def test_parse_rejects_malformed_and_all_zero():
    assert parse_traceparent(None) is None
    assert parse_traceparent("") is None
    assert parse_traceparent("garbage") is None
    assert parse_traceparent("00-" + "0" * 32 + "-00f067aa0ba902b7-01") is None
    assert parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-" + "0" * 16 + "-01") is None


def test_format_round_trips():
    value = format_traceparent("a" * 32, "b" * 16, sampled=True)
    assert value == f"00-{'a' * 32}-{'b' * 16}-01"
    assert parse_traceparent(value) == ("a" * 32, "b" * 16, True)


def test_span_lifecycle_records_history():
    tracer = Tracer(enabled=True)
    span = tracer.start_span("unit.work", attributes={"k": "v"})
    tracer.finish_span(span, status="ok")

    assert span.end_time is not None
    assert span.duration_ms >= 0
    recent = tracer.get_recent_spans()
    assert len(recent) == 1
    assert recent[0]["name"] == "unit.work"
    assert recent[0]["status"] == "ok"
    assert recent[0]["attributes"] == {"k": "v"}


def test_span_context_manager_marks_errors():
    tracer = Tracer(enabled=True)
    try:
        with tracer.span("failing") as span:
            raise ValueError("boom")
    except ValueError:
        pass

    recent = tracer.get_recent_spans()
    assert len(recent) == 1
    assert recent[0]["status"] == "error"
    assert recent[0]["error"] == "boom"
    assert span.status == "error"


def test_disabled_tracer_keeps_no_history():
    tracer = Tracer(enabled=False)
    with tracer.span("noop"):
        pass
    assert tracer.get_recent_spans() == []


def test_spans_are_bounded():
    tracer = Tracer(enabled=True, max_spans=3)
    for index in range(5):
        with tracer.span(f"span-{index}"):
            pass
    names = [s["name"] for s in tracer.get_recent_spans(limit=10)]
    assert names == ["span-4", "span-3", "span-2"]
