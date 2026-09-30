import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.stored_file import StoredFile


def test_file_check_returns_false_for_missing_file(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/files/check",
        json={
            "device_id": "fake-device-1",
            "filename": "normal.bin",
            "size": 3,
            "sha256": "a" * 64,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"exists": False, "stored_file_id": None, "stored_path": None}


def test_file_check_returns_existing_record(api_client: TestClient) -> None:
    app = api_client.app
    stored_path = "fake-device-1/normal_aaaaaaaaaaaa.bin"
    final_path = app.state.storage.final_path(stored_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"abc")
    stored_id = str(uuid4())
    with app.state.session_factory() as session:
        session.add(
            StoredFile(
                id=stored_id,
                device_id="fake-device-1",
                original_filename="normal.bin",
                size=3,
                sha256=hashlib.sha256(b"abc").hexdigest(),
                stored_path=stored_path,
                content_type=None,
            )
        )
        session.commit()

    response = api_client.post(
        "/api/v1/files/check",
        json={
            "device_id": "fake-device-1",
            "filename": "normal.bin",
            "size": 3,
            "sha256": hashlib.sha256(b"abc").hexdigest(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "exists": True,
        "stored_file_id": stored_id,
        "stored_path": stored_path,
    }


def test_file_check_reconciles_existing_final_file_without_metadata(
    api_client: TestClient,
) -> None:
    app = api_client.app
    content = b"abc"
    digest = hashlib.sha256(content).hexdigest()
    stored_path = f"fake-device-1/normal_{digest[:12]}.bin"
    final_path = app.state.storage.final_path(stored_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(content)

    response = api_client.post(
        "/api/v1/files/check",
        json={
            "device_id": "fake-device-1",
            "filename": "normal.bin",
            "size": len(content),
            "sha256": digest,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is True
    assert body["stored_path"] == stored_path

    with app.state.session_factory() as session:
        stored = session.get(StoredFile, body["stored_file_id"])

    assert stored is not None
    assert stored.sha256 == digest


def test_file_check_rejects_invalid_metadata(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/files/check",
        json={
            "device_id": "../device",
            "filename": "../normal.bin",
            "size": 3,
            "sha256": "a" * 64,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "metadata_invalid"
