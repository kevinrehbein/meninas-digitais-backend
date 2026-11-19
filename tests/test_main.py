import pytest
from fastapi.testclient import TestClient

from api import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_api_info_endpoint(client):
    response = client.get("/api")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["endpoints"]["chat"].startswith("POST /api/chat")


def test_health_returns_ok_when_configuration_is_valid(client, monkeypatch):
    monkeypatch.setattr(main, "validate_config", lambda: None)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "meninas-digitais-api",
        "version": 1,
    }


def test_health_returns_503_when_configuration_is_missing(client, monkeypatch):
    def invalid_config():
        raise RuntimeError("NEO4J_URI ausente")
    monkeypatch.setattr(main, "validate_config", invalid_config)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert "NEO4J_URI ausente" in response.json()["detail"]


def test_openapi_document_is_available(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "/api/chat" in response.json()["paths"]


def test_cors_preflight_allows_configured_origin(client):
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_does_not_allow_unconfigured_origin(client):
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "https://malicioso.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers
