import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.models.stored_file import StoredFile
from app.repositories import stored_files as stored_files_module
from app.services.file_transfers import FileMetadata, FileTransferService
from tests.conftest import auth_headers, create_test_device


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def upload_headers(
    *,
    device_id: str = "fake-device-1",
    filename: str = "normal.bin",
    content: bytes,
    sha256: str | None = None,
    size: int | None = None,
) -> dict[str, str]:
    return {
        "X-localSync-Device-Id": device_id,
        "X-localSync-Filename": filename,
        "X-localSync-Size": str(len(content) if size is None else size),
        "X-localSync-Sha256": sha256 or sha256_bytes(content),
        "X-localSync-Content-Type": "application/octet-stream",
    }


def completed_files(api_client: TestClient) -> list[Path]:
    backup_root = api_client.app.state.storage.backup_root
    if not backup_root.exists():
        return []
    return [path for path in backup_root.rglob("*") if path.is_file()]


def test_successful_upload_preserves_bytes(api_client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    content = b"opaque bytes\0with binary-ish data"
    source.write_bytes(content)

    response = api_client.post(
        "/api/v1/files",
        content=source.read_bytes(),
        headers=upload_headers(filename="source.bin", content=content),
    )

    assert source.read_bytes() == content
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stored"
    destination = api_client.app.state.storage.final_path(body["stored_path"])
    assert destination.exists()
    assert destination.read_bytes() == source.read_bytes()
    assert sha256_bytes(destination.read_bytes()) == sha256_bytes(source.read_bytes())


def test_duplicate_exact_content_does_not_create_duplicate(api_client: TestClient) -> None:
    content = b"same content"
    headers = upload_headers(filename="same.bin", content=content)

    first = api_client.post("/api/v1/files", content=content, headers=headers)
    second = api_client.post("/api/v1/files", content=content, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "already_stored"
    assert len(completed_files(api_client)) == 1


def test_same_filename_different_content_does_not_overwrite(api_client: TestClient) -> None:
    first_content = b"first"
    second_content = b"second"

    first = api_client.post(
        "/api/v1/files",
        content=first_content,
        headers=upload_headers(filename="IMG_0001.bin", content=first_content),
    )
    second = api_client.post(
        "/api/v1/files",
        content=second_content,
        headers=upload_headers(filename="IMG_0001.bin", content=second_content),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_path = api_client.app.state.storage.final_path(first.json()["stored_path"])
    second_path = api_client.app.state.storage.final_path(second.json()["stored_path"])
    assert first_path != second_path
    assert first_path.read_bytes() == first_content
    assert second_path.read_bytes() == second_content


def test_hash_mismatch_fails_and_cleans_partial(api_client: TestClient) -> None:
    content = b"content"

    response = api_client.post(
        "/api/v1/files",
        content=content,
        headers=upload_headers(filename="bad.bin", content=content, sha256="0" * 64),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "hash_mismatch"
    assert completed_files(api_client) == []
    assert list(api_client.app.state.storage.temp_root.glob("*.partial")) == []


def test_size_mismatch_fails_and_cleans_partial(api_client: TestClient) -> None:
    content = b"content"

    response = api_client.post(
        "/api/v1/files",
        content=content,
        headers=upload_headers(filename="bad.bin", content=content, size=len(content) + 1),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "size_mismatch"
    assert completed_files(api_client) == []
    assert list(api_client.app.state.storage.temp_root.glob("*.partial")) == []


@pytest.mark.parametrize(
    ("device_id", "filename"),
    [
        ("fake-device-1", "../secret.txt"),
        ("fake-device-1", r"..\secret.txt"),
        ("fake-device-1", r"C:\secret.txt"),
        ("fake-device-1", "/foo.jpg"),
    ],
)
def test_upload_rejects_traversal_metadata(
    api_client: TestClient, device_id: str, filename: str
) -> None:
    content = b"content"

    response = api_client.post(
        "/api/v1/files",
        content=content,
        headers=upload_headers(device_id=device_id, filename=filename, content=content),
    )

    assert response.status_code == 422
    assert completed_files(api_client) == []


def test_multiple_device_namespaces_do_not_collide(api_client: TestClient) -> None:
    content = b"same bytes"
    second_credential = create_test_device(api_client.app, "fake-device-2")

    first = api_client.post(
        "/api/v1/files",
        content=content,
        headers=upload_headers(device_id="fake-device-1", filename="same.bin", content=content),
    )
    second = api_client.post(
        "/api/v1/files",
        content=content,
        headers={
            **upload_headers(device_id="fake-device-1", filename="same.bin", content=content),
            **auth_headers(api_client.app, second_credential),
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["stored_path"] != second.json()["stored_path"]
    assert len(completed_files(api_client)) == 2


def test_valid_final_file_without_metadata_is_reconciled_on_upload(api_client: TestClient) -> None:
    content = b"recover me"
    digest = sha256_bytes(content)
    stored_path = f"fake-device-1/recovered_{digest[:12]}.bin"
    final_path = api_client.app.state.storage.final_path(stored_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(content)

    response = api_client.post(
        "/api/v1/files",
        content=content,
        headers=upload_headers(filename="recovered.bin", content=content),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_stored"
    assert final_path.read_bytes() == content
    assert len(completed_files(api_client)) == 1


def test_finalized_file_survives_metadata_insert_failure_and_later_reconciles(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"durable bytes"
    original_add = stored_files_module.StoredFileRepository.add
    calls = 0

    def fail_once(self, stored_file: StoredFile) -> StoredFile:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SQLAlchemyError("simulated insert failure")
        return original_add(self, stored_file)

    monkeypatch.setattr(stored_files_module.StoredFileRepository, "add", fail_once)

    first = api_client.post(
        "/api/v1/files",
        content=content,
        headers=upload_headers(filename="durable.bin", content=content),
    )

    assert first.status_code == 500
    assert first.json()["error"]["code"] == "database_error"
    assert len(completed_files(api_client)) == 1

    second = api_client.post(
        "/api/v1/files/check",
        json={
            "device_id": "fake-device-1",
            "filename": "durable.bin",
            "size": len(content),
            "sha256": sha256_bytes(content),
        },
    )

    assert second.status_code == 200
    assert second.json()["exists"] is True
    assert len(completed_files(api_client)) == 1


def test_service_processes_multiple_bounded_chunks(api_client: TestClient) -> None:
    chunks = [b"stream", b"ed", b"-content"]
    content = b"".join(chunks)

    async def chunk_stream() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    async def receive() -> tuple[str, StoredFile]:
        with api_client.app.state.session_factory() as session:
            service = FileTransferService(session, api_client.app.state.storage)
            return await service.receive_file(
                FileMetadata(
                    device_id="fake-device-1",
                    filename="streamed.bin",
                    size=len(content),
                    sha256=sha256_bytes(content),
                ),
                chunk_stream(),
            )

    status, stored = asyncio.run(receive())

    destination = api_client.app.state.storage.final_path(stored.stored_path)
    assert status == "stored"
    assert destination.read_bytes() == content
