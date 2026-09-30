from sqlalchemy.orm import Session

from app.models.pairing_session import PairingSession


class PairingSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, pairing_id: str) -> PairingSession | None:
        return self.session.get(PairingSession, pairing_id)

    def add(self, pairing_session: PairingSession) -> PairingSession:
        self.session.add(pairing_session)
        self.session.flush()
        return pairing_session
