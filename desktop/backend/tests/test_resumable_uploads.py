import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models.upload_session import UploadSession
from app.storage.local_filesystem import DiskUsage
from tests.conftest import auth_headers, create_test_device


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def create_upload(
    api_client: TestClient,
    *,
    content: bytes,
    filename: str = "sample.bin",
    device_id: str = "fake-device-1",
    sha256: str | None = None,
    size: int | None = None,
) -> dict:
    response = api_client.post(
        "/api/v1/uploads",
        json={
            "device_id": device_id,
            "filename": filename,
            "expected_size": len(content) if size is None else size,
            "expected_sha256": sha256 or sha256_bytes(content),
            "content_type": "application/octet-stream",
        },
    )
    assert response.status_code == 200
    return response.json()


def create_upload_with_headers(
    api_client: TestClient,
    *,
    content: bytes,
    headers: dict[str, str],
    filename: str = "sample.bin",
) -> dict:
    response = api_client.post(
        "/api/v1/uploads",
        json={
            "filename": filename,
            "expected_size": len(content),
            "expected_sha256": sha256_bytes(content),
            "content_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def completed_files(api_client: TestClient) -> list[Path]:
    backup_root = api_client.app.state.storage.backup_root
    if not backup_root.exists():
        return []
    return [path for path in backup_root.rglob("*") if path.is_file()]


def put_chunk(
    api_client: TestClient,
    upload_id: str,
    offset: int,
    chunk: bytes,
    headers: dict[str, str] | None = None,
):
    return api_client.put(
        f"/api/v1/uploads/{upload_id}",
        content=chunk,
        headers={
            "X-localSync-Offset": str(offset),
            "Content-Length": str(len(chunk)),
            **(headers or {}),
        },
    )


def test_session_creation_and_repeated_creation_recovers_session(api_client: TestClient) -> None:
    content = b"abcdef"

    first = create_upload(api_client, content=content)
    second = create_upload(api_client, content=content)

    assert first["status"] == "receiving"
    assert first["next_offset"] == 0
    assert first["chunk_size_hint"] == 8 * 1024 * 1024
    assert second["upload_id"] == first["upload_id"]
    assert second["next_offset"] == 0


def test_normal_multi_chunk_upload_preserves_bytes_and_hash(api_client: TestClient) -> None:
    content = b"0123456789abcdef" * 128
    created = create_upload(api_client, content=content)
    upload_id = created["upload_id"]

    offset = 0
    for chunk in (content[:1000], content[1000:2000], content[2000:]):
        response = put_chunk(api_client, upload_id, offset, chunk)
        assert response.status_code == 200
        offset = response.json()["next_offset"]

    completed = api_client.post(f"/api/v1/uploads/{upload_id}/complete")

    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    destination = api_client.app.state.storage.final_path(body["stored_path"])
    assert destination.read_bytes() == content
    assert sha256_bytes(destination.read_bytes()) == sha256_bytes(content)
    assert completed_files(api_client) == [destination]


def test_old_offset_retry_reports_next_offset_without_duplication(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]

    first = put_chunk(api_client, upload_id, 0, content[:4])
    retry = put_chunk(api_client, upload_id, 0, content[:4])

    assert first.status_code == 200
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "offset_mismatch"
    assert retry.json()["error"]["details"]["expected_offset"] == 4
    partials = list(api_client.app.state.storage.temp_root.glob("*.partial"))
    assert len(partials) == 1
    assert partials[0].read_bytes() == content[:4]


def test_future_offset_rejected_without_hole(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]

    response = put_chunk(api_client, upload_id, 4, content[4:])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "offset_mismatch"
    assert response.json()["error"]["details"]["expected_offset"] == 0
    partials = list(api_client.app.state.storage.temp_root.glob("*.partial"))
    assert len(partials) == 1
    assert partials[0].read_bytes() == b""


def test_completion_before_all_bytes_reports_next_offset(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content[:4]).status_code == 200

    response = api_client.post(f"/api/v1/uploads/{upload_id}/complete")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_incomplete"
    assert response.json()["error"]["details"]["next_offset"] == 4
    assert completed_files(api_client) == []


def test_hash_mismatch_marks_failed_and_cleans_partial(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content, sha256="0" * 64)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content).status_code == 200

    response = api_client.post(f"/api/v1/uploads/{upload_id}/complete")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "hash_mismatch"
    assert completed_files(api_client) == []
    assert list(api_client.app.state.storage.temp_root.glob("*.partial")) == []
    with api_client.app.state.session_factory() as session:
        upload_session = session.get(UploadSession, upload_id)
        assert upload_session.status == "failed"


def test_source_mutation_between_chunks_fails_completion(api_client: TestClient) -> None:
    original = b"abcdefgh"
    mixed = b"abcdWXYZ"
    upload_id = create_upload(api_client, content=original)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, mixed[:4]).status_code == 200
    assert put_chunk(api_client, upload_id, 4, mixed[4:]).status_code == 200

    response = api_client.post(f"/api/v1/uploads/{upload_id}/complete")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "hash_mismatch"
    assert completed_files(api_client) == []


def test_complete_is_idempotent(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content).status_code == 200

    first = api_client.post(f"/api/v1/uploads/{upload_id}/complete")
    second = api_client.post(f"/api/v1/uploads/{upload_id}/complete")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["stored_file_id"] == second.json()["stored_file_id"]
    assert len(completed_files(api_client)) == 1


def test_already_completed_content_does_not_create_session(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content).status_code == 200
    completed = api_client.post(f"/api/v1/uploads/{upload_id}/complete")

    duplicate = create_upload(api_client, content=content)

    assert completed.status_code == 200
    assert duplicate["status"] == "already_stored"
    assert duplicate["stored_file_id"] == completed.json()["stored_file_id"]
    with api_client.app.state.session_factory() as session:
        assert len(session.query(UploadSession).all()) == 1


def test_same_filename_different_content_stays_non_destructive(api_client: TestClient) -> None:
    first_content = b"first"
    second_content = b"second"
    first_upload = create_upload(api_client, content=first_content, filename="IMG_0001.bin")
    second_upload = create_upload(api_client, content=second_content, filename="IMG_0001.bin")

    assert put_chunk(api_client, first_upload["upload_id"], 0, first_content).status_code == 200
    assert put_chunk(api_client, second_upload["upload_id"], 0, second_content).status_code == 200
    first_done = api_client.post(f"/api/v1/uploads/{first_upload['upload_id']}/complete")
    second_done = api_client.post(f"/api/v1/uploads/{second_upload['upload_id']}/complete")

    first_path = api_client.app.state.storage.final_path(first_done.json()["stored_path"])
    second_path = api_client.app.state.storage.final_path(second_done.json()["stored_path"])
    assert first_path != second_path
    assert first_path.read_bytes() == first_content
    assert second_path.read_bytes() == second_content


def test_device_namespaces_remain_isolated(api_client: TestClient) -> None:
    content = b"same"
    second_credential = create_test_device(api_client.app, "fake-device-2")
    first = create_upload(api_client, content=content, device_id="fake-device-1")
    second = create_upload_with_headers(
        api_client,
        content=content,
        headers=auth_headers(api_client.app, second_credential),
    )

    assert first["upload_id"] != second["upload_id"]
    assert put_chunk(api_client, first["upload_id"], 0, content).status_code == 200
    assert (
        put_chunk(
            api_client,
            second["upload_id"],
            0,
            content,
            auth_headers(api_client.app, second_credential),
        ).status_code
        == 200
    )
    first_done = api_client.post(f"/api/v1/uploads/{first['upload_id']}/complete")
    second_done = api_client.post(
        f"/api/v1/uploads/{second['upload_id']}/complete",
        headers=auth_headers(api_client.app, second_credential),
    )

    assert first_done.json()["stored_path"] != second_done.json()["stored_path"]
    assert len(completed_files(api_client)) == 2


def test_db_offset_behind_filesystem_reconciles_upward(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content[:4]).status_code == 200
    with api_client.app.state.session_factory() as session:
        upload_session = session.get(UploadSession, upload_id)
        upload_session.bytes_received = 2
        session.commit()

    response = api_client.get(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 200
    assert response.json()["next_offset"] == 4
    with api_client.app.state.session_factory() as session:
        assert session.get(UploadSession, upload_id).bytes_received == 4


def test_backend_restart_recovers_partial_offset(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    database_url = f"sqlite:///{(tmp_path / 'restart.db').as_posix()}"
    settings = Settings(
        LOCALSYNC_ENV="test",
        LOCALSYNC_DATA_ROOT=data_root,
        LOCALSYNC_DATABASE_URL=database_url,
    )
    first_app = create_app(settings)
    Base.metadata.create_all(first_app.state.engine)
    credential = create_test_device(first_app, "fake-device-1")
    first_client = TestClient(first_app, headers=auth_headers(first_app, credential))
    content = b"abcdefgh"
    upload_id = create_upload(first_client, content=content)["upload_id"]
    assert put_chunk(first_client, upload_id, 0, content[:4]).status_code == 200
    first_client.close()
    first_app.state.engine.dispose()

    restarted_app = create_app(settings)
    restarted_client = TestClient(restarted_app, headers=auth_headers(restarted_app, credential))

    status = restarted_client.get(f"/api/v1/uploads/{upload_id}")
    assert status.status_code == 200
    assert status.json()["next_offset"] == 4
    assert put_chunk(restarted_client, upload_id, 4, content[4:]).status_code == 200
    completed = restarted_client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert completed.status_code == 200
    destination = restarted_app.state.storage.final_path(completed.json()["stored_path"])
    assert destination.read_bytes() == content


def test_db_offset_ahead_of_filesystem_fails_session(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    with api_client.app.state.session_factory() as session:
        upload_session = session.get(UploadSession, upload_id)
        upload_session.bytes_received = 4
        session.commit()

    response = api_client.get(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_state_invalid"
    with api_client.app.state.session_factory() as session:
        assert session.get(UploadSession, upload_id).status == "failed"


def test_missing_partial_with_zero_offset_is_recreated(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    partial = next(api_client.app.state.storage.temp_root.glob("*.partial"))
    partial.unlink()

    response = api_client.get(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 200
    assert response.json()["next_offset"] == 0
    assert partial.exists()


def test_missing_partial_with_nonzero_offset_fails_session(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content[:4]).status_code == 200
    partial = next(api_client.app.state.storage.temp_root.glob("*.partial"))
    partial.unlink()

    response = api_client.get(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "partial_missing"
    with api_client.app.state.session_factory() as session:
        assert session.get(UploadSession, upload_id).status == "failed"


def test_completed_file_without_session_status_reconciles(api_client: TestClient) -> None:
    content = b"durable"
    upload_id = create_upload(api_client, content=content)["upload_id"]
    assert put_chunk(api_client, upload_id, 0, content).status_code == 200
    completed = api_client.post(f"/api/v1/uploads/{upload_id}/complete")
    with api_client.app.state.session_factory() as session:
        upload_session = session.get(UploadSession, upload_id)
        upload_session.status = "receiving"
        upload_session.completed_file_id = None
        session.commit()

    response = api_client.get(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["stored_file_id"] == completed.json()["stored_file_id"]


def test_chunk_larger_than_remaining_expected_bytes_is_rejected(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]

    response = put_chunk(api_client, upload_id, 0, content + b"extra")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "chunk_exceeds_expected_size"
    assert completed_files(api_client) == []


def test_chunk_larger_than_configured_limit_is_rejected(api_client: TestClient) -> None:
    content = b"a" * (api_client.app.state.settings.max_upload_chunk_size + 1)
    upload_id = create_upload(api_client, content=content)["upload_id"]

    response = put_chunk(api_client, upload_id, 0, content)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "chunk_too_large"


def test_content_length_required_is_validated_at_service_level(api_client: TestClient) -> None:
    content = b"abcdefgh"
    upload_id = create_upload(api_client, content=content)["upload_id"]

    response = api_client.put(
        f"/api/v1/uploads/{upload_id}",
        content=b"",
        headers={"X-localSync-Offset": "0"},
    )

    assert response.status_code in {411, 422}
    assert completed_files(api_client) == []


def test_free_space_rejection(api_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        api_client.app.state.storage,
        "disk_usage",
        lambda: DiskUsage(total=100, used=99, free=1),
    )

    response = api_client.post(
        "/api/v1/uploads",
        json={
            "device_id": "fake-device-1",
            "filename": "too-big.bin",
            "expected_size": 2,
            "expected_sha256": "a" * 64,
        },
    )

    assert response.status_code == 507
    assert response.json()["error"]["code"] == "disk_space_insufficient"


def test_path_traversal_metadata_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/uploads",
        json={
            "device_id": "../device",
            "filename": "../secret.txt",
            "expected_size": 1,
            "expected_sha256": "a" * 64,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "metadata_invalid"
