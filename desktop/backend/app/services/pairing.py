from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import (
    PAIRING_MAX_ATTEMPTS,
    generate_device_credential,
    generate_pairing_code,
    pairing_code_matches,
    pairing_expires_at,
    utc_now,
)
from app.models.paired_device import PairedDevice
from app.models.pairing_session import PairingSession
from app.repositories.paired_devices import PairedDeviceRepository
from app.repositories.pairing_sessions import PairingSessionRepository


@dataclass(frozen=True)
class PairingSessionCreated:
    pairing_id: str
    pairing_code: str
    expires_at: datetime
    server_fingerprint: str
    server_url: str | None


@dataclass(frozen=True)
class PairingCompleteResult:
    device_id: str
    device_credential: str
    server_fingerprint: str
    server_display_name: str


class PairingService:
    def __init__(
        self,
        session: Session,
        *,
        server_fingerprint: str,
        server_display_name: str = "localSync laptop",
    ) -> None:
        self.session = session
        self.server_fingerprint = server_fingerprint
        self.server_display_name = server_display_name
        self.pairing_sessions = PairingSessionRepository(session)
        self.paired_devices = PairedDeviceRepository(session)

    def create_pairing_session(self, *, server_url: str | None = None) -> PairingSessionCreated:
        generated = generate_pairing_code()
        pairing_session = PairingSession(
            id=str(uuid4()),
            secret_verifier=generated.verifier,
            expires_at=pairing_expires_at(),
            attempt_count=0,
        )
        self.pairing_sessions.add(pairing_session)
        self.session.commit()
        return PairingSessionCreated(
            pairing_id=pairing_session.id,
            pairing_code=generated.code,
            expires_at=_as_utc(pairing_session.expires_at),
            server_fingerprint=self.server_fingerprint,
            server_url=server_url,
        )

    def complete_pairing(
        self,
        pairing_id: str,
        *,
        pairing_code: str,
        display_name: str,
        platform: str | None = None,
        client_instance_id: str | None = None,
    ) -> PairingCompleteResult:
        pairing_session = self.pairing_sessions.get(pairing_id)
        if pairing_session is None:
            raise _pairing_failed()

        now = utc_now()
        if pairing_session.consumed_at is not None:
            raise AppError("pairing_consumed", "Pairing session was already used.", status_code=409)
        if _as_utc(pairing_session.expires_at) <= now:
            raise AppError("pairing_expired", "Pairing session has expired.", status_code=410)
        if pairing_session.attempt_count >= PAIRING_MAX_ATTEMPTS:
            raise AppError("pairing_locked", "Pairing session is locked.", status_code=409)

        if not pairing_code_matches(pairing_code, pairing_session.secret_verifier):
            pairing_session.attempt_count += 1
            self.session.commit()
            if pairing_session.attempt_count >= PAIRING_MAX_ATTEMPTS:
                raise AppError("pairing_locked", "Pairing session is locked.", status_code=409)
            raise _pairing_failed()

        credential = generate_device_credential()
        device = PairedDevice(
            id=str(uuid4()),
            display_name=_clean_display_name(display_name),
            credential_verifier=credential.verifier,
            platform=_clean_optional(platform, 80),
            client_instance_id=_clean_optional(client_instance_id, 120),
        )
        self.paired_devices.add(device)
        pairing_session.consumed_at = now
        self.session.commit()
        return PairingCompleteResult(
            device_id=device.id,
            device_credential=credential.credential,
            server_fingerprint=self.server_fingerprint,
            server_display_name=self.server_display_name,
        )

    def revoke_device(self, device_id: str) -> PairedDevice:
        device = self.paired_devices.get(device_id)
        if device is None:
            raise AppError("device_not_found", "Paired device was not found.", status_code=404)
        if device.revoked_at is None:
            device.revoked_at = utc_now()
            self.session.commit()
        return device

    def activate_device(self, device_id: str) -> PairedDevice:
        device = self.paired_devices.get(device_id)
        if device is None:
            raise AppError("device_not_found", "Paired device was not found.", status_code=404)
        if device.revoked_at is not None:
            device.revoked_at = None
            self.session.commit()
        return device


def _pairing_failed() -> AppError:
    return AppError("pairing_failed", "Pairing credentials were not accepted.", status_code=401)


def _clean_display_name(display_name: str) -> str:
    cleaned = display_name.strip()
    if not 1 <= len(cleaned) <= 120:
        raise AppError("pairing_invalid", "display_name must be 1-120 characters.", status_code=422)
    return cleaned


def _clean_optional(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise AppError("pairing_invalid", "Pairing metadata is too long.", status_code=422)
    return cleaned


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
