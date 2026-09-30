import logging

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.main import create_app


def test_app_error_returns_structured_response() -> None:
    app = create_app(Settings(LOCALSYNC_ENV="test"))

    @app.get("/raise-app-error")
    def raise_app_error() -> None:
        raise AppError("storage_path_invalid", "Invalid storage path.", status_code=422)

    response = TestClient(app).get("/raise-app-error")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "storage_path_invalid",
            "message": "Invalid storage path.",
        }
    }


def test_configure_logging_uses_requested_level() -> None:
    configure_logging("WARNING")

    assert logging.getLogger().getEffectiveLevel() == logging.WARNING
