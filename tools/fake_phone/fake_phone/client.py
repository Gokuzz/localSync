from collections.abc import Iterable

import httpx

from fake_phone.models import FileCandidate, TransferResult
from fake_phone.tls import verify_observed_fingerprint

DEFAULT_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024


class TransferClient:
    def __init__(
        self,
        server: str,
        device_credential: str,
        *,
        server_fingerprint: str | None = None,
        chunk_size: int = DEFAULT_UPLOAD_CHUNK_SIZE,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.server = server.rstrip("/")
        self.device_credential = device_credential
        self.server_fingerprint = server_fingerprint
        self.chunk_size = chunk_size
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self._owns_client = http_client is None
        self._skip_pin_preflight = http_client is not None

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def check(self, candidate: FileCandidate) -> bool:
        response = self.http_client.post(
            f"{self.server}/api/v1/files/check",
            json={
                "filename": candidate.filename,
                "size": candidate.size,
                "sha256": candidate.sha256,
                "content_type": candidate.content_type,
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return bool(response.json()["exists"])

    def create_upload(self, candidate: FileCandidate) -> dict:
        response = self.http_client.post(
            f"{self.server}/api/v1/uploads",
            json={
                "filename": candidate.filename,
                "expected_size": candidate.size,
                "expected_sha256": candidate.sha256,
                "content_type": candidate.content_type,
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return dict(response.json())

    def append_chunk(self, upload_id: str, offset: int, chunk: bytes) -> int:
        response = self.http_client.put(
            f"{self.server}/api/v1/uploads/{upload_id}",
            headers={
                **self._auth_headers(),
                "X-localSync-Offset": str(offset),
                "Content-Length": str(len(chunk)),
            },
            content=chunk,
        )
        if response.status_code == 409:
            body = response.json()
            details = body.get("error", {}).get("details") or {}
            expected_offset = details.get("expected_offset")
            if expected_offset is None:
                expected_offset = details.get("next_offset")
            if expected_offset is not None:
                return int(expected_offset)
        response.raise_for_status()
        return int(response.json()["next_offset"])

    def complete_upload(self, upload_id: str) -> dict:
        response = self.http_client.post(
            f"{self.server}/api/v1/uploads/{upload_id}/complete",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return dict(response.json())

    def upload(self, candidate: FileCandidate) -> str:
        created = self.create_upload(candidate)
        if created["status"] == "already_stored":
            return "already_stored"

        upload_id = str(created["upload_id"])
        next_offset = int(created["next_offset"])
        with candidate.path.open("rb") as file:
            while next_offset < candidate.size:
                file.seek(next_offset)
                chunk = file.read(min(self.chunk_size, candidate.size - next_offset))
                if not chunk:
                    raise httpx.TransportError("source file ended before expected size")
                updated_offset = self.append_chunk(upload_id, next_offset, chunk)
                if updated_offset == next_offset:
                    raise httpx.TransportError("server did not advance upload offset")
                next_offset = updated_offset

        completed = self.complete_upload(upload_id)
        return str(completed["status"])

    def transfer(self, candidate: FileCandidate) -> TransferResult:
        try:
            if self.check(candidate):
                return TransferResult(candidate.filename, "already backed up", True)
            status = self.upload(candidate)
            label = "uploaded" if status in {"completed", "stored"} else status
            if status == "already_stored":
                label = "already backed up"
            return TransferResult(candidate.filename, label, True)
        except (httpx.HTTPError, ValueError) as exc:
            return TransferResult(candidate.filename, "failed", False, str(exc))

    def transfer_all(self, candidates: Iterable[FileCandidate]) -> list[TransferResult]:
        return [self.transfer(candidate) for candidate in candidates]

    def _auth_headers(self) -> dict[str, str]:
        if self.server_fingerprint and not self._skip_pin_preflight:
            verify_observed_fingerprint(self.server, self.server_fingerprint)
        return {"Authorization": f"Bearer {self.device_credential}"}


class PairingClient:
    def __init__(
        self,
        server: str,
        *,
        expected_server_fingerprint: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.server = server.rstrip("/")
        self.expected_server_fingerprint = expected_server_fingerprint
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self._owns_client = http_client is None
        self._skip_pin_preflight = http_client is not None

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def complete_pairing(
        self,
        *,
        pairing_id: str,
        pairing_code: str,
        display_name: str,
        platform: str = "fake_client",
        client_instance_id: str | None = None,
    ) -> dict:
        if self.expected_server_fingerprint and not self._skip_pin_preflight:
            verify_observed_fingerprint(self.server, self.expected_server_fingerprint)
        response = self.http_client.post(
            f"{self.server}/api/v1/pairing-sessions/{pairing_id}/complete",
            json={
                "pairing_code": pairing_code,
                "display_name": display_name,
                "platform": platform,
                "client_instance_id": client_instance_id,
            },
        )
        response.raise_for_status()
        return dict(response.json())


class DeviceClient:
    def __init__(self, transfer_client: TransferClient) -> None:
        self.transfer_client = transfer_client

    def transfer_all(self, candidates: Iterable[FileCandidate]) -> list[TransferResult]:
        return self.transfer_client.transfer_all(candidates)
