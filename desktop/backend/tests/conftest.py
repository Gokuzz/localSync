from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import generate_device_credential
from app.db.base import Base
from app.main import create_app
from app.models.paired_device import PairedDevice

DEFAULT_TEST_DEVICE_ID = "fake-device-1"


def backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def api_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        LOCALSYNC_ENV="test",
        LOCALSYNC_DATA_ROOT=tmp_path / "data",
        LOCALSYNC_DATABASE_URL=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        credential = generate_device_credential()
        session.add(
            PairedDevice(
                id=DEFAULT_TEST_DEVICE_ID,
                display_name="Test device",
                credential_verifier=credential.verifier,
                platform="test",
                client_instance_id="test-default",
            )
        )
        app.state.test_device_credential = credential.credential
        session.commit()
    return TestClient(app, headers=auth_headers(app))


def auth_headers(app, credential: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential or app.state.test_device_credential}"}


def create_test_device(app, device_id: str) -> str:
    credential = generate_device_credential()
    with app.state.session_factory() as session:
        session.add(
            PairedDevice(
                id=device_id,
                display_name=device_id,
                credential_verifier=credential.verifier,
                platform="test",
                client_instance_id=device_id,
            )
        )
        session.commit()
    return credential.credential
