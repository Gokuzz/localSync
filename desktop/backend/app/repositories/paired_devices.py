from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.paired_device import PairedDevice


class PairedDeviceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, device_id: str) -> PairedDevice | None:
        return self.session.get(PairedDevice, device_id)

    def find_by_verifier(self, credential_verifier: str) -> PairedDevice | None:
        statement = select(PairedDevice).where(
            PairedDevice.credential_verifier == credential_verifier
        )
        return self.session.execute(statement).scalar_one_or_none()

    def list_all(self) -> list[PairedDevice]:
        statement = select(PairedDevice).order_by(PairedDevice.created_at.asc())
        return list(self.session.execute(statement).scalars())

    def add(self, paired_device: PairedDevice) -> PairedDevice:
        self.session.add(paired_device)
        self.session.flush()
        return paired_device
