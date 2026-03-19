from __future__ import annotations

from fastapi.testclient import TestClient

from maiecho_py.app import create_app


def test_status_endpoint_returns_runtime_metrics() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["threads"] >= 1
    assert payload["memory_usage_mb"] >= 0
    assert payload["active_tasks"] == 0
    assert payload["queued_tasks"] >= 0
    assert isinstance(payload["periodic_jobs"], list)
    assert isinstance(payload["collector_health"], list)
    assert isinstance(payload["recent_tasks"], list)


def test_unmigrated_song_routes_are_explicit() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/songs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 0
    assert isinstance(payload["items"], list)
