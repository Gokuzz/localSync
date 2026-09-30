from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.stored_file import StoredFile


class StoredFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_identity(self, device_id: str, size: int, sha256: str) -> StoredFile | None:
        statement = select(StoredFile).where(
            StoredFile.device_id == device_id,
            StoredFile.size == size,
            StoredFile.sha256 == sha256,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def find_by_stored_path(self, stored_path: str) -> StoredFile | None:
        statement = select(StoredFile).where(StoredFile.stored_path == stored_path)
        return self.session.execute(statement).scalar_one_or_none()

    def add(self, stored_file: StoredFile) -> StoredFile:
        self.session.add(stored_file)
        self.session.flush()
        return stored_file
