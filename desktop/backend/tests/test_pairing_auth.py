from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.security import (
    PAIRING_MAX_ATTEMPTS,
    credential_matches,
    ensure_server_identity,
    generate_device_credential,
    utc_now,
)
from app.models.paired_device import PairedDevice
from app.models.pairing_session import PairingSession
from app.models.upload_session import UploadSession
from app.repositories.paired_devices import PairedDeviceRepository
from app.services.pairing import PairingService
from tests.conftest import auth_headers, create_test_device


def test_server_identity_persists_and_fingerprint_is_stable(api_client: TestClient) -> None:
    data_root = api_client.app.state.settings.data_root

    first = ensure_server_identity(data_root)
    second = ensure_server_identity(data_root)

    assert first.certificate_path.exists()
    assert first.private_key_path.exists()
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint.startswith("spki-sha256:")


def test_device_credential_is_high_entropy_and_verifier_only() -> None:
    generated = generate_device_credential()

    assert generated.credential not in generated.verifier
    assert generated.verifier.startswith("sha256-v1:")
    assert credential_matches(generated.credential, generated.verifier)
    assert not credential_matches("wrong", generated.verifier)


def test_pairing_completion_creates_device_and_consumes_session(api_client: TestClient) -> None:
    with api_client.app.state.session_factory() as session:
        service = PairingService(
            session,
            server_fingerprint=api_client.app.state.server_identity.fingerprint,
        )
        created = service.create_pairing_session(server_url="https://127.0.0.1:8000")

    raw_client = TestClient(api_client.app)
    response = raw_client.post(
        f"/api/v1/pairing-sessions/{created.pairing_id}/complete",
        json={
            "pairing_code": created.pairing_code,
            "display_name": "Android test",
            "platform": "android",
            "client_instance_id": "android-local-id",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["device_credential"]
    assert body["device_credential"] not in body["server_fingerprint"]
    with api_client.app.state.session_factory() as session:
        pairing = session.get(PairingSession, created.pairing_id)
        device = session.get(PairedDevice, body["device_id"])
        assert pairing.consumed_at is not None
        assert device is not None
        assert body["device_credential"] not in device.credential_verifier

    reused = raw_client.post(
        f"/api/v1/pairing-sessions/{created.pairing_id}/complete",
        json={"pairing_code": created.pairing_code, "display_name": "Again"},
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "pairing_consumed"


def test_pairing_expiry_and_attempt_lock(api_client: TestClient) -> None:
    with api_client.app.state.session_factory() as session:
        service = PairingService(
            session,
            server_fingerprint=api_client.app.state.server_identity.fingerprint,
        )
        expired = service.create_pairing_session()
        active = service.create_pairing_session()
        session.get(PairingSession, expired.pairing_id).expires_at = utc_now() - timedelta(
            seconds=1
        )
        session.commit()

    raw_client = TestClient(api_client.app)
    expired_response = raw_client.post(
        f"/api/v1/pairing-sessions/{expired.pairing_id}/complete",
        json={"pairing_code": expired.pairing_code, "display_name": "Expired"},
    )
    assert expired_response.status_code == 410
    assert expired_response.json()["error"]["code"] == "pairing_expired"

    for attempt in range(PAIRING_MAX_ATTEMPTS):
        response = raw_client.post(
            f"/api/v1/pairing-sessions/{active.pairing_id}/complete",
            json={"pairing_code": "WRNG-WRNG-WRNG", "display_name": "Wrong"},
        )
        assert response.status_code in {401, 409}
        if attempt == PAIRING_MAX_ATTEMPTS - 1:
            assert response.json()["error"]["code"] == "pairing_locked"

    locked = raw_client.post(
        f"/api/v1/pairing-sessions/{active.pairing_id}/complete",
        json={"pairing_code": active.pairing_code, "display_name": "Locked"},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "pairing_locked"


def test_transfer_endpoints_reject_missing_invalid_and_revoked_credentials(
    api_client: TestClient,
) -> None:
    raw_client = TestClient(api_client.app)
    missing = raw_client.post(
        "/api/v1/files/check",
        json={"filename": "a.bin", "size": 0, "sha256": "a" * 64},
    )
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_required"

    invalid = raw_client.post(
        "/api/v1/files/check",
        json={"filename": "a.bin", "size": 0, "sha256": "a" * 64},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "authentication_failed"

    credential = create_test_device(api_client.app, "revoked-device")
    with api_client.app.state.session_factory() as session:
        PairingService(
            session,
            server_fingerprint=api_client.app.state.server_identity.fingerprint,
        ).revoke_device("revoked-device")
    revoked = raw_client.post(
        "/api/v1/files/check",
        json={"filename": "a.bin", "size": 0, "sha256": "a" * 64},
        headers=auth_headers(api_client.app, credential),
    )
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "device_revoked"

    with api_client.app.state.session_factory() as session:
        PairingService(
            session,
            server_fingerprint=api_client.app.state.server_identity.fingerprint,
        ).activate_device("revoked-device")
    activated = raw_client.post(
        "/api/v1/files/check",
        json={"filename": "a.bin", "size": 0, "sha256": "a" * 64},
        headers=auth_headers(api_client.app, credential),
    )
    assert activated.status_code == 200


def test_client_supplied_device_id_cannot_impersonate_other_device(api_client: TestClient) -> None:
    content = b"same"
    other_credential = create_test_device(api_client.app, "other-device")

    response = api_client.post(
        "/api/v1/uploads",
        json={
            "device_id": "other-device",
            "filename": "same.bin",
            "expected_size": len(content),
            "expected_sha256": "a" * 64,
        },
    )

    assert response.status_code == 200
    upload_id = response.json()["upload_id"]
    with api_client.app.state.session_factory() as session:
        assert session.get(PairedDevice, "other-device") is not None
        stored_session = session.get(UploadSession, upload_id)
        assert stored_session.device_id == "fake-device-1"

    other_status = api_client.get(
        f"/api/v1/uploads/{upload_id}",
        headers=auth_headers(api_client.app, other_credential),
    )
    assert other_status.status_code == 404


def test_revocation_does_not_delete_completed_backup(api_client: TestClient) -> None:
    content = b"backup survives revocation"
    response = api_client.post(
        "/api/v1/files",
        content=content,
        headers={
            "X-localSync-Filename": "survives.bin",
            "X-localSync-Size": str(len(content)),
            "X-localSync-Sha256": __import__("hashlib").sha256(content).hexdigest(),
        },
    )
    assert response.status_code == 200
    stored_path = response.json()["stored_path"]
    final_path = api_client.app.state.storage.final_path(stored_path)
    assert final_path.exists()

    with api_client.app.state.session_factory() as session:
        PairingService(
            session,
            server_fingerprint=api_client.app.state.server_identity.fingerprint,
        ).revoke_device("fake-device-1")

    assert final_path.exists()
    assert final_path.read_bytes() == content


def test_device_repository_lists_devices(api_client: TestClient) -> None:
    with api_client.app.state.session_factory() as session:
        devices = PairedDeviceRepository(session).list_all()

    assert [device.id for device in devices] == ["fake-device-1"]
