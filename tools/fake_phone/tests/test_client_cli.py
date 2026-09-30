import hashlib
from contextlib import suppress

import httpx

from fake_phone.cli import main
from fake_phone.client import PairingClient, TransferClient
from fake_phone.config import load_config
from fake_phone.models import FileCandidate


def candidate(tmp_path, content: bytes = b"content") -> FileCandidate:
    path = tmp_path / "sample.bin"
    path.write_bytes(content)
    return FileCandidate(
        path=path,
        filename=path.name,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="application/octet-stream",
    )


def test_transfer_client_checks_before_upload(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/files/check":
            return httpx.Response(200, json={"exists": True})
        raise AssertionError("upload should not be called")

    client = TransferClient(
        "http://testserver",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.transfer(candidate(tmp_path))

    assert result.ok is True
    assert result.status == "already backed up"
    assert [request.url.path for request in requests] == ["/api/v1/files/check"]
    assert requests[0].headers["Authorization"] == "Bearer secret"


def test_transfer_client_streams_upload_after_missing_check(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/files/check":
            return httpx.Response(200, json={"exists": False})
        if request.url.path == "/api/v1/uploads":
            return httpx.Response(
                200,
                json={
                    "status": "receiving",
                    "upload_id": "upload-1",
                    "next_offset": 0,
                    "expected_size": 7,
                    "chunk_size_hint": 8388608,
                },
            )
        if request.url.path == "/api/v1/uploads/upload-1" and request.method == "PUT":
            assert request.headers["X-localSync-Offset"] == "0"
            assert request.read() == b"content"
            return httpx.Response(
                200, json={"status": "receiving", "upload_id": "upload-1", "next_offset": 7}
            )
        if request.url.path == "/api/v1/uploads/upload-1/complete":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "upload_id": "upload-1",
                    "stored_file_id": "1",
                    "stored_path": "p",
                },
            )
        raise AssertionError("unexpected request")

    client = TransferClient(
        "http://testserver",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.transfer(candidate(tmp_path))

    assert result.ok is True
    assert result.status == "uploaded"
    assert [request.url.path for request in requests] == [
        "/api/v1/files/check",
        "/api/v1/uploads",
        "/api/v1/uploads/upload-1",
        "/api/v1/uploads/upload-1/complete",
    ]


def test_transfer_client_recovers_from_offset_mismatch(tmp_path) -> None:
    requests: list[httpx.Request] = []
    content = b"abcdefgh"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/files/check":
            return httpx.Response(200, json={"exists": False})
        if request.url.path == "/api/v1/uploads":
            return httpx.Response(
                200,
                json={
                    "status": "receiving",
                    "upload_id": "upload-1",
                    "next_offset": 0,
                    "expected_size": len(content),
                    "chunk_size_hint": 4,
                },
            )
        if request.url.path == "/api/v1/uploads/upload-1" and request.method == "PUT":
            offset = request.headers["X-localSync-Offset"]
            if offset == "0":
                return httpx.Response(
                    409,
                    json={
                        "error": {
                            "code": "offset_mismatch",
                            "message": "mismatch",
                            "details": {"expected_offset": 4},
                        }
                    },
                )
            assert offset == "4"
            assert request.read() == content[4:]
            return httpx.Response(
                200, json={"status": "receiving", "upload_id": "upload-1", "next_offset": 8}
            )
        if request.url.path == "/api/v1/uploads/upload-1/complete":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "upload_id": "upload-1",
                    "stored_file_id": "1",
                    "stored_path": "p",
                },
            )
        raise AssertionError("unexpected request")

    client = TransferClient(
        "http://testserver",
        "secret",
        chunk_size=4,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.transfer(candidate(tmp_path, content))

    assert result.ok is True
    assert result.status == "uploaded"
    assert [
        request.headers.get("X-localSync-Offset") for request in requests if request.method == "PUT"
    ] == [
        "0",
        "4",
    ]


def test_transfer_client_reports_backend_error(tmp_path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "database_error", "message": "failed"}})

    client = TransferClient(
        "http://testserver",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.transfer(candidate(tmp_path))

    assert result.ok is False
    assert result.status == "failed"


def test_transfer_client_verifies_fingerprint_before_authorization(tmp_path, monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"exists": True})

    def fail_preflight(_server: str, _expected: str) -> str:
        raise ValueError("Server identity changed; refusing to send credentials.")

    monkeypatch.setattr("fake_phone.client.verify_observed_fingerprint", fail_preflight)
    client = TransferClient(
        "https://testserver",
        "secret",
        server_fingerprint="spki-sha256:pin-a",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client._skip_pin_preflight = False

    result = client.transfer(candidate(tmp_path))

    assert result.ok is False
    assert requests == []


def test_pairing_client_completes_pairing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/pairing-sessions/pairing-1/complete"
        return httpx.Response(
            200,
            json={
                "device_id": "device-1",
                "device_credential": "secret",
                "server_fingerprint": "spki-sha256:test",
                "server_display_name": "localSync laptop",
            },
        )

    client = PairingClient(
        "http://testserver",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.complete_pairing(
        pairing_id="pairing-1",
        pairing_code="ABCD-EFGH-JKMP",
        display_name="fake device",
    )

    assert result["device_credential"] == "secret"


def test_pairing_client_verifies_fingerprint_before_sending_code(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    def fail_preflight(_server: str, _expected: str) -> str:
        raise ValueError("Server identity changed; refusing to send credentials.")

    monkeypatch.setattr("fake_phone.client.verify_observed_fingerprint", fail_preflight)
    client = PairingClient(
        "https://testserver",
        expected_server_fingerprint="spki-sha256:pin-a",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client._skip_pin_preflight = False

    try:
        with suppress(ValueError):
            client.complete_pairing(
                pairing_id="pairing-1",
                pairing_code="ABCD-EFGH-JKMP",
                display_name="fake device",
            )

        assert requests == []
    finally:
        client.close()


def test_cli_pair_writes_config(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "fake-config.json"
    original_client = httpx.Client

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "device_id": "device-1",
                "device_credential": "secret",
                "server_fingerprint": "spki-sha256:test",
                "server_display_name": "localSync laptop",
            },
        )

    monkeypatch.setattr(
        "fake_phone.client.httpx.Client",
        lambda timeout=30.0: original_client(
            transport=httpx.MockTransport(handler), timeout=timeout
        ),
    )
    monkeypatch.setattr(
        "fake_phone.client.verify_observed_fingerprint",
        lambda _server, expected: expected,
    )

    exit_code = main(
        [
            "pair",
            "--server",
            "https://testserver",
            "--pairing-id",
            "pairing-1",
            "--pairing-code",
            "ABCD-EFGH-JKMP",
            "--server-fingerprint",
            "spki-sha256:test",
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0
    assert "paired" in capsys.readouterr().out
    config = load_config(config_path)
    assert config.device_id == "device-1"
    assert config.device_credential == "secret"


def test_cli_returns_zero_when_files_are_backed_up(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "sample.bin").write_bytes(b"content")
    config_path = tmp_path / "fake-config.json"
    config_path.write_text(
        '{"server":"https://testserver","server_fingerprint":"spki-sha256:test",'
        '"device_id":"device-1","device_credential":"secret"}',
        encoding="utf-8",
    )
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/files/check":
            return httpx.Response(200, json={"exists": True})
        raise AssertionError("upload should not be called")

    monkeypatch.setattr(
        "fake_phone.client.httpx.Client",
        lambda timeout=30.0: original_client(
            transport=httpx.MockTransport(handler), timeout=timeout
        ),
    )
    monkeypatch.setattr(
        "fake_phone.client.verify_observed_fingerprint",
        lambda _server, expected: expected,
    )

    exit_code = main(["backup", "--config", str(config_path), "--source", str(tmp_path)])

    assert exit_code == 0
    assert "already backed up" in capsys.readouterr().out


def test_cli_returns_nonzero_on_backend_error(tmp_path, monkeypatch) -> None:
    (tmp_path / "sample.bin").write_bytes(b"content")
    config_path = tmp_path / "fake-config.json"
    config_path.write_text(
        '{"server":"https://testserver","server_fingerprint":"spki-sha256:test",'
        '"device_id":"device-1","device_credential":"secret"}',
        encoding="utf-8",
    )
    original_client = httpx.Client

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "database_error", "message": "failed"}})

    monkeypatch.setattr(
        "fake_phone.client.httpx.Client",
        lambda timeout=30.0: original_client(
            transport=httpx.MockTransport(handler), timeout=timeout
        ),
    )
    monkeypatch.setattr(
        "fake_phone.client.verify_observed_fingerprint",
        lambda _server, expected: expected,
    )

    exit_code = main(["backup", "--config", str(config_path), "--source", str(tmp_path)])

    assert exit_code == 1
