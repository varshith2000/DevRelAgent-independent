"""Phase 4: HTTP edge rate limiting (shared, per-project budget)."""

import pytest


@pytest.fixture
def rate_settings(monkeypatch):
    """Force a tiny edge budget so tests stay fast."""
    from config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "http_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "http_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "http_rate_limit_window_seconds", 60)
    return settings


def test_edge_limit_rejects_after_budget(api_client, rate_settings):
    assert api_client.get("/").status_code == 200
    assert api_client.get("/").status_code == 200

    response = api_client.get("/")
    assert response.status_code == 429
    assert response.headers.get("retry-after") == "60"
    assert response.headers.get("x-ratelimit-remaining") == "0"


def test_edge_limit_exposes_headers(api_client, rate_settings):
    response = api_client.get("/")
    assert response.status_code == 200
    assert response.headers.get("x-ratelimit-limit") == "2"
    assert response.headers.get("x-ratelimit-remaining") == "1"


def test_exempt_paths_are_never_limited(api_client, rate_settings):
    for _ in range(5):
        assert api_client.get("/health").status_code == 200


def test_limit_is_scoped_per_project(api_client, rate_settings, monkeypatch):
    monkeypatch.setattr(rate_settings, "http_rate_limit_requests", 1)

    assert api_client.get("/", headers={"X-Project-Id": "proj-a"}).status_code == 200
    assert api_client.get("/", headers={"X-Project-Id": "proj-a"}).status_code == 429
    # A different project has its own budget.
    assert api_client.get("/", headers={"X-Project-Id": "proj-b"}).status_code == 200


def test_disabled_limiter_allows_everything(api_client, monkeypatch):
    from config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "http_rate_limit_enabled", False)
    monkeypatch.setattr(settings, "http_rate_limit_requests", 1)

    for _ in range(5):
        assert api_client.get("/").status_code == 200
