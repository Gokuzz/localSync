import hashlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.stored_file import StoredFile
from app.repositories.stored_files import StoredFileRepository
from app.storage.local_filesystem import LocalFilesystemStorage
from app.storage.names import build_storage_key, sanitize_device_id, sanitize_filename

LOGGER = logging.getLogger(__name__)
MAX_DECLARED_SIZE = 10 * 1024 * 1024 * 1024 * 1024
HASH_LENGTHS = (12, 16, 24, 32, 64)


@dataclass(frozen=True)
class FileMetadata:
    device_id: str
    filename: str
    size: int
    sha256: str
    content_type: str | None = None


@dataclass(frozen=True)
class FileStatus:
    exists: bool
    stored_file_id: str | None = None
    stored_path: str | None = None


def validate_file_metadata(metadata: FileMetadata) -> FileMetadata:
    try:
        device_id = sanitize_device_id(metadata.device_id)
        filename = sanitize_filename(metadata.filename)
    except ValueError as exc:
        raise AppError("metadata_invalid", str(exc), status_code=422) from exc

    if not 0 <= metadata.size <= MAX_DECLARED_SIZE:
        raise AppError("metadata_invalid", "size is outside the supported range", status_code=422)

    sha256 = metadata.sha256.lower()
    if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
        raise AppError(
            "metadata_invalid",
            "sha256 must be 64 lowercase hexadecimal characters",
            status_code=422,
        )

    content_type = metadata.content_type
    if content_type is not None and len(content_type) > 255:
        raise AppError("metadata_invalid", "content_type is too long", status_code=422)

    return FileMetadata(
        device_id=device_id,
        filename=filename,
        size=metadata.size,
        sha256=sha256,
        content_type=content_type,
    )


class FileTransferService:
    def __init__(self, session: Session, storage: LocalFilesystemStorage) -> None:
        self.session = session
        self.storage = storage
        self.repository = StoredFileRepository(session)

    def check_file(self, metadata: FileMetadata) -> FileStatus:
        metadata = validate_file_metadata(metadata)
        stored = self._find_record(metadata)
        if stored is not None:
            return FileStatus(exists=True, stored_file_id=stored.id, stored_path=stored.stored_path)

        reconciled = self._reconcile_existing_final_file(metadata)
        if reconciled is not None:
            self.session.commit()
            return FileStatus(
                exists=True, stored_file_id=reconciled.id, stored_path=reconciled.stored_path
            )

        return FileStatus(exists=False)

    def find_record(self, metadata: FileMetadata) -> StoredFile | None:
        return self._find_record(validate_file_metadata(metadata))

    def reconcile_existing_final_file(self, metadata: FileMetadata) -> StoredFile | None:
        return self._reconcile_existing_final_file(validate_file_metadata(metadata))

    def select_storage_key(self, metadata: FileMetadata) -> str:
        return self._select_storage_key(validate_file_metadata(metadata))

    def record_finalized_file(
        self, metadata: FileMetadata, storage_key: str, final_path: Path
    ) -> StoredFile:
        return self._record_finalized_file(
            validate_file_metadata(metadata), storage_key, final_path
        )

    async def receive_file(
        self, metadata: FileMetadata, chunks: AsyncIterator[bytes]
    ) -> tuple[str, StoredFile]:
        metadata = validate_file_metadata(metadata)
        existing = self.check_file(metadata)
        if existing.exists:
            stored = self.repository.find_by_identity(
                metadata.device_id, metadata.size, metadata.sha256
            )
            if stored is None:
                raise AppError(
                    "database_error", "Stored file metadata could not be loaded.", status_code=500
                )
            return "already_stored", stored

        self.storage.ensure_directories()
        partial_path = self.storage.partial_path(str(uuid4()))
        hasher = hashlib.sha256()
        received_size = 0

        LOGGER.info("transfer started")
        try:
            with partial_path.open("wb") as partial_file:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    received_size += len(chunk)
                    if received_size > metadata.size:
                        raise AppError(
                            "size_mismatch", "Received more bytes than declared.", status_code=422
                        )
                    hasher.update(chunk)
                    partial_file.write(chunk)

            actual_sha256 = hasher.hexdigest()
            if received_size != metadata.size:
                raise AppError(
                    "size_mismatch",
                    "Received byte count does not match declared size.",
                    status_code=422,
                )
            if actual_sha256 != metadata.sha256:
                raise AppError(
                    "hash_mismatch",
                    "Received SHA-256 does not match declared hash.",
                    status_code=422,
                )

            storage_key = self._select_storage_key(metadata)
            final_path = self.storage.finalize_partial(partial_path, storage_key)
            stored_file = self._record_finalized_file(metadata, storage_key, final_path)
            LOGGER.info("transfer finalized")
            return "stored", stored_file
        except AppError:
            _delete_if_exists(partial_path)
            LOGGER.info("transfer verification failed")
            raise
        except OSError as exc:
            _delete_if_exists(partial_path)
            raise AppError(
                "storage_error", "File storage operation failed.", status_code=500
            ) from exc

    def _find_record(self, metadata: FileMetadata) -> StoredFile | None:
        stored = self.repository.find_by_identity(
            metadata.device_id, metadata.size, metadata.sha256
        )
        if stored is None:
            return None

        final_path = self.storage.final_path(stored.stored_path)
        if not final_path.exists():
            raise AppError(
                "storage_error",
                "Stored file metadata exists but finalized bytes are missing.",
                status_code=500,
            )
        return stored

    def _reconcile_existing_final_file(self, metadata: FileMetadata) -> StoredFile | None:
        for hash_length in HASH_LENGTHS:
            storage_key = build_storage_key(
                metadata.device_id, metadata.filename, metadata.sha256, hash_length=hash_length
            )
            final_path = self.storage.final_path(storage_key)
            if not final_path.exists():
                continue
            if file_matches(final_path, metadata.size, metadata.sha256):
                return self._record_finalized_file(metadata, storage_key, final_path)
        return None

    def _select_storage_key(self, metadata: FileMetadata) -> str:
        for hash_length in HASH_LENGTHS:
            storage_key = build_storage_key(
                metadata.device_id, metadata.filename, metadata.sha256, hash_length=hash_length
            )
            final_path = self.storage.final_path(storage_key)
            if not final_path.exists():
                return storage_key
            if file_matches(final_path, metadata.size, metadata.sha256):
                self._record_finalized_file(metadata, storage_key, final_path)
                return storage_key

        raise AppError(
            "storage_conflict", "Could not choose a non-conflicting storage path.", status_code=409
        )

    def _record_finalized_file(
        self, metadata: FileMetadata, storage_key: str, final_path: Path
    ) -> StoredFile:
        existing = self.repository.find_by_identity(
            metadata.device_id, metadata.size, metadata.sha256
        )
        if existing is not None:
            return existing

        if not file_matches(final_path, metadata.size, metadata.sha256):
            raise AppError(
                "storage_error", "Finalized file did not match expected identity.", status_code=500
            )

        stored_file = StoredFile(
            id=str(uuid4()),
            device_id=metadata.device_id,
            original_filename=metadata.filename,
            size=metadata.size,
            sha256=metadata.sha256,
            stored_path=storage_key,
            content_type=metadata.content_type,
        )
        try:
            self.repository.add(stored_file)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            LOGGER.error("metadata persistence failed")
            raise AppError(
                "database_error", "Could not persist stored file metadata.", status_code=500
            ) from exc
        return stored_file


def file_matches(path: Path, expected_size: int, expected_sha256: str) -> bool:
    if path.stat().st_size != expected_size:
        return False

    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest() == expected_sha256


def _delete_if_exists(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("failed to remove invalid partial file")
