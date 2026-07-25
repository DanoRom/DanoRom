"""Browser-facing behaviour of the middleware stack.

A response that loses its CORS headers is invisible to the browser: fetch() rejects
with a bare "Failed to fetch" and the real status never reaches the UI. That makes
the rate limiter's 429 the easiest response in the app to get wrong, so it is
pinned here along with the preflight it must not throttle.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

ORIGIN = "http://localhost:3000"


@pytest.fixture
def client(monkeypatch):
    """App instance with a 2-request budget so the limiter is easy to trip."""
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setenv("CORS_ORIGINS", ORIGIN)

    from app import config

    importlib.reload(config)
    from app import main

    importlib.reload(main)
    yield TestClient(main.app)

    # Restore module state for tests that import these afterwards.
    monkeypatch.undo()
    importlib.reload(config)
    importlib.reload(main)


def _exhaust(client, budget=2):
    for _ in range(budget):
        client.get("/api/projects", headers={"Origin": ORIGIN})


def test_rate_limited_response_keeps_cors_headers(client):
    _exhaust(client)
    res = client.get("/api/projects", headers={"Origin": ORIGIN})

    assert res.status_code == 429
    # Without this header the browser reports "Failed to fetch" and the user
    # never sees the message below.
    assert res.headers.get("access-control-allow-origin") == ORIGIN
    assert "Rate limit exceeded" in res.json()["detail"]


def test_preflight_is_not_throttled(client):
    """A 429'd preflight fails the whole request, so OPTIONS must stay exempt."""
    _exhaust(client)
    res = client.options(
        "/api/projects/import",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == ORIGIN


def test_health_and_version_are_exempt(client):
    _exhaust(client)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/version").status_code == 200
