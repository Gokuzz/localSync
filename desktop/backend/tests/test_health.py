from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_create_app_mounts_versioned_health_route() -> None:
    app = create_app()

    assert "/api/v1/health" in app.openapi()["paths"]


def test_health_endpoint_returns_minimal_status() -> None:
    client = TestClient(create_app(Settings(LOCALSYNC_ENV="test")))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
