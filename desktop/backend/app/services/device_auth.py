from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import credential_matches, device_credential_verifier, utc_now
from app.models.paired_device import PairedDevice
from app.repositories.paired_devices import PairedDeviceRepository


@dataclass(frozen=True)
class AuthenticatedDevice:
    id: str
    display_name: str


class DeviceAuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PairedDeviceRepository(session)

    def authenticate(self, credential: str) -> AuthenticatedDevice:
        try:
            verifier = device_credential_verifier(credential)
        except ValueError as exc:
            raise _auth_error() from exc

        device = self.repository.find_by_verifier(verifier)
        if device is None or not credential_matches(credential, device.credential_verifier):
            raise _auth_error()
        if device.revoked_at is not None:
            raise AppError("device_revoked", "Device credential is revoked.", status_code=401)

        device.last_seen_at = utc_now()
        self.session.commit()
        return AuthenticatedDevice(id=device.id, display_name=device.display_name)


def device_principal(device: PairedDevice) -> AuthenticatedDevice:
    return AuthenticatedDevice(id=device.id, display_name=device.display_name)


def _auth_error() -> AppError:
    return AppError("authentication_failed", "Device authentication failed.", status_code=401)
