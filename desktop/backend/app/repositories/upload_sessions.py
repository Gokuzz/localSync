from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.upload_session import UploadSession


class UploadSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, upload_id: str) -> UploadSession | None:
        return self.session.get(UploadSession, upload_id)

    def find_receiving_session(
        self,
        *,
        device_id: str,
        expected_size: int,
        expected_sha256: str,
        original_filename: str,
    ) -> UploadSession | None:
        statement = (
            select(UploadSession)
            .where(
                UploadSession.device_id == device_id,
                UploadSession.expected_size == expected_size,
                UploadSession.expected_sha256 == expected_sha256,
                UploadSession.original_filename == original_filename,
                UploadSession.status == "receiving",
            )
            .order_by(UploadSession.created_at.asc(), UploadSession.id.asc())
        )
        return self.session.execute(statement).scalars().first()

    def add(self, upload_session: UploadSession) -> UploadSession:
        self.session.add(upload_session)
        self.session.flush()
        return upload_session
