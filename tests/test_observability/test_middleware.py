"""Phase 5: HTTP observability middleware and the /metrics endpoint."""

from observability.middleware import template_path


def _traceparent(trace_id: str, span_id: str) -> str:
    return f"00-{trace_id}-{span_id}-01"


def test_response_carries_request_and_trace_ids(api_client):
    response = api_client.get("/")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert response.headers.get("x-trace-id")
    assert response.headers.get("traceparent")


def test_incoming_request_id_is_honoured(api_client):
    response = api_client.get("/", headers={"X-Request-Id": "req-abc-123"})
    assert response.headers.get("x-request-id") == "req-abc-123"


def test_incoming_trace_context_is_propagated(api_client):
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    response = api_client.get("/", headers={"traceparent": _traceparent(trace_id, "b" * 16)})

    returned = response.headers.get("traceparent", "").split("-")
    assert returned[1] == trace_id
    # A new child span id is minted for the server span.
    assert returned[2] != "b" * 16
    assert response.headers.get("x-trace-id") == trace_id


def test_metrics_endpoint_exposes_http_metrics(api_client):
    api_client.get("/")
    api_client.get("/")

    response = api_client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "devrel_http_requests_total" in body
    assert "devrel_http_request_duration_seconds" in body
    assert "devrel_http_requests_in_flight" in body
    assert 'path="/"' in body


def test_metrics_endpoint_404_when_disabled(api_client, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setattr(get_settings(), "metrics_enabled", False)
    assert api_client.get("/metrics").status_code == 404


def test_template_path_collapses_high_cardinality_segments():
    assert template_path("/projects/12345/api-keys/42") == "/projects/{id}/api-keys/{id}"
    assert template_path("/projects/550e8400-e29b-41d4-a716-446655440000") == "/projects/{id}"
    assert template_path("/health") == "/health"
    assert template_path("/projects/my-slug") == "/projects/my-slug"
