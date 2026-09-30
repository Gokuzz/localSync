import hashlib
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.stored_file import StoredFile
from app.models.upload_session import UploadSession
from app.repositories.upload_sessions import UploadSessionRepository
from app.services.file_transfers import FileMetadata, FileTransferService, validate_file_metadata
from app.storage.local_filesystem import LocalFilesystemStorage

LOGGER = logging.getLogger(__name__)
DEFAULT_CHUNK_SIZE_HINT = 8 * 1024 * 1024


@dataclass(frozen=True)
class UploadMetadata:
    device_id: str
    filename: str
    expected_size: int
    expected_sha256: str
    content_type: str | None = None


@dataclass(frozen=True)
class UploadSessionResult:
    status: str
    upload_id: str | None = None
    next_offset: int | None = None
    expected_size: int | None = None
    chunk_size_hint: int | None = None
    stored_file_id: str | None = None
    stored_path: str | None = None


class UploadSessionService:
    def __init__(
        self,
        session: Session,
        storage: LocalFilesystemStorage,
        *,
        max_chunk_size: int,
    ) -> None:
        self.session = session
        self.storage = storage
        self.repository = UploadSessionRepository(session)
        self.file_service = FileTransferService(session, storage)
        self.max_chunk_size = max_chunk_size

    def create_or_recover(self, metadata: UploadMetadata) -> UploadSessionResult:
        file_metadata = self._file_metadata(metadata)
        stored = self.file_service.find_record(file_metadata)
        if stored is None:
            stored = self.file_service.reconcile_existing_final_file(file_metadata)
        if stored is not None:
            self.session.commit()
            return self._already_stored(stored)

        existing = self.repository.find_receiving_session(
            device_id=file_metadata.device_id,
            expected_size=file_metadata.size,
            expected_sha256=file_metadata.sha256,
            original_filename=file_metadata.filename,
        )
        if existing is not None:
            completed = self._try_reconcile_completed(existing)
            if completed is not None:
                return self._completed(existing, completed)
            next_offset = self._reconcile_receiving(existing)
            return self._receiving(existing, next_offset)

        self.storage.ensure_directories()
        self._check_free_space(file_metadata.size)
        upload_id = str(uuid4())
        temp_relative_path = f"{upload_id}.partial"
        self.storage.ensure_empty_partial(temp_relative_path)
        upload_session = UploadSession(
            id=upload_id,
            device_id=file_metadata.device_id,
            original_filename=file_metadata.filename,
            expected_size=file_metadata.size,
            expected_sha256=file_metadata.sha256,
            content_type=file_metadata.content_type,
            temp_relative_path=temp_relative_path,
            bytes_received=0,
            status="receiving",
        )
        self.repository.add(upload_session)
        self.session.commit()
        return self._receiving(upload_session, 0)

    def get_status(self, upload_id: str, *, device_id: str | None = None) -> UploadSessionResult:
        upload_session = self._get_session(upload_id, device_id=device_id)
        if upload_session.status == "completed":
            stored = self._completed_stored_file(upload_session)
            return self._completed(upload_session, stored)
        completed = self._try_reconcile_completed(upload_session)
        if completed is not None:
            return self._completed(upload_session, completed)
        next_offset = self._reconcile_receiving(upload_session)
        return self._receiving(upload_session, next_offset)

    async def append(
        self,
        upload_id: str,
        *,
        device_id: str | None = None,
        offset: int,
        content_length: int | None,
        chunks: AsyncIterator[bytes],
    ) -> UploadSessionResult:
        upload_session = self._get_session(upload_id, device_id=device_id)
        current_offset = self._reconcile_receiving(upload_session)
        self._validate_content_length(upload_session, current_offset, content_length)
        if offset != current_offset:
            raise AppError(
                "offset_mismatch",
                "Upload offset does not match accepted bytes.",
                status_code=409,
                details={"expected_offset": current_offset},
            )

        assert content_length is not None
        self._check_free_space(content_length)
        partial_path = self.storage.partial_path_for_key(upload_session.temp_relative_path)
        received = 0
        try:
            with partial_path.open("ab") as partial_file:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > content_length:
                        raise AppError(
                            "chunk_size_mismatch",
                            "Received more chunk bytes than declared.",
                            status_code=422,
                        )
                    partial_file.write(chunk)
                if received != content_length:
                    raise AppError(
                        "chunk_size_mismatch",
                        "Received chunk byte count does not match Content-Length.",
                        status_code=422,
                    )
                partial_file.flush()
                os.fsync(partial_file.fileno())
        except AppError:
            raise
        except OSError as exc:
            raise AppError(
                "storage_error", "File storage operation failed.", status_code=500
            ) from exc

        actual_size = partial_path.stat().st_size
        if actual_size != current_offset + content_length:
            self._mark_failed(upload_session)
            raise AppError(
                "upload_state_invalid",
                "Partial file length diverged during append.",
                status_code=500,
            )
        upload_session.bytes_received = actual_size
        self.session.commit()
        LOGGER.info("upload chunk accepted")
        return self._receiving(upload_session, actual_size)

    def complete(self, upload_id: str, *, device_id: str | None = None) -> UploadSessionResult:
        upload_session = self._get_session(upload_id, device_id=device_id)
        if upload_session.status == "completed":
            stored = self._completed_stored_file(upload_session)
            return self._completed(upload_session, stored)
        completed = self._try_reconcile_completed(upload_session)
        if completed is not None:
            return self._completed(upload_session, completed)

        next_offset = self._reconcile_receiving(upload_session)
        if next_offset < upload_session.expected_size:
            raise AppError(
                "upload_incomplete",
                "Upload is not complete.",
                status_code=409,
                details={"next_offset": next_offset},
            )
        if next_offset > upload_session.expected_size:
            self._mark_failed(upload_session)
            raise AppError("size_mismatch", "Received more bytes than expected.", status_code=422)

        partial_path = self.storage.partial_path_for_key(upload_session.temp_relative_path)
        actual_sha256 = _sha256_file(partial_path)
        if actual_sha256 != upload_session.expected_sha256:
            self.storage.remove_partial(upload_session.temp_relative_path)
            self._mark_failed(upload_session)
            raise AppError(
                "hash_mismatch",
                "Completed upload SHA-256 does not match expected hash.",
                status_code=422,
            )

        metadata = FileMetadata(
            device_id=upload_session.device_id,
            filename=upload_session.original_filename,
            size=upload_session.expected_size,
            sha256=upload_session.expected_sha256,
            content_type=upload_session.content_type,
        )
        stored = self.file_service.find_record(metadata)
        if stored is None:
            stored = self.file_service.reconcile_existing_final_file(metadata)
        if stored is None:
            storage_key = self.file_service.select_storage_key(metadata)
            final_path = self.storage.finalize_partial(partial_path, storage_key)
            stored = self.file_service.record_finalized_file(metadata, storage_key, final_path)
        else:
            self.storage.remove_partial(upload_session.temp_relative_path)

        upload_session.status = "completed"
        upload_session.completed_file_id = stored.id
        upload_session.bytes_received = upload_session.expected_size
        self.session.commit()
        LOGGER.info("upload session completed")
        return self._completed(upload_session, stored)

    def _file_metadata(self, metadata: UploadMetadata) -> FileMetadata:
        return validate_file_metadata(
            FileMetadata(
                device_id=metadata.device_id,
                filename=metadata.filename,
                size=metadata.expected_size,
                sha256=metadata.expected_sha256,
                content_type=metadata.content_type,
            )
        )

    def _get_session(self, upload_id: str, *, device_id: str | None = None) -> UploadSession:
        upload_session = self.repository.get(upload_id)
        if upload_session is None:
            raise AppError("upload_not_found", "Upload session was not found.", status_code=404)
        if device_id is not None and upload_session.device_id != device_id:
            raise AppError("upload_not_found", "Upload session was not found.", status_code=404)
        return upload_session

    def _reconcile_receiving(self, upload_session: UploadSession) -> int:
        if upload_session.status == "failed":
            raise AppError("upload_failed", "Upload session has failed.", status_code=409)
        if upload_session.status == "completed":
            return upload_session.expected_size

        actual_size = self.storage.partial_size(upload_session.temp_relative_path)
        if actual_size is None:
            if upload_session.bytes_received == 0:
                self.storage.ensure_empty_partial(upload_session.temp_relative_path)
                return 0
            self._mark_failed(upload_session)
            raise AppError(
                "partial_missing",
                "Upload partial file is missing after bytes were accepted.",
                status_code=409,
            )
        if actual_size > upload_session.expected_size:
            self._mark_failed(upload_session)
            raise AppError(
                "size_mismatch", "Partial file is larger than expected.", status_code=422
            )
        if actual_size > upload_session.bytes_received:
            upload_session.bytes_received = actual_size
            self.session.commit()
        elif upload_session.bytes_received > actual_size:
            self._mark_failed(upload_session)
            raise AppError(
                "upload_state_invalid",
                "Upload session metadata exceeds partial file length.",
                status_code=409,
            )
        return actual_size

    def _validate_content_length(
        self, upload_session: UploadSession, current_offset: int, content_length: int | None
    ) -> None:
        if content_length is None:
            raise AppError(
                "content_length_required",
                "Content-Length is required for resumable upload chunks.",
                status_code=411,
            )
        if content_length <= 0:
            raise AppError(
                "content_length_invalid",
                "Content-Length must be greater than zero.",
                status_code=422,
            )
        if content_length > self.max_chunk_size:
            raise AppError(
                "chunk_too_large",
                "Upload chunk exceeds the configured maximum size.",
                status_code=413,
                details={"max_chunk_size": self.max_chunk_size},
            )
        if current_offset + content_length > upload_session.expected_size:
            raise AppError(
                "chunk_exceeds_expected_size",
                "Upload chunk exceeds expected file size.",
                status_code=422,
                details={"next_offset": current_offset},
            )

    def _check_free_space(self, required_bytes: int) -> None:
        self.storage.ensure_directories()
        if required_bytes > self.storage.disk_usage().free:
            raise AppError(
                "disk_space_insufficient",
                "Available storage is less than required upload bytes.",
                status_code=507,
            )

    def _completed_stored_file(self, upload_session: UploadSession) -> StoredFile:
        if upload_session.completed_file_id is not None:
            stored = self.session.get(StoredFile, upload_session.completed_file_id)
            if stored is not None and self.storage.final_path(stored.stored_path).exists():
                return stored

        metadata = FileMetadata(
            device_id=upload_session.device_id,
            filename=upload_session.original_filename,
            size=upload_session.expected_size,
            sha256=upload_session.expected_sha256,
            content_type=upload_session.content_type,
        )
        stored = self.file_service.find_record(metadata)
        if stored is None:
            stored = self.file_service.reconcile_existing_final_file(metadata)
        if stored is None:
            raise AppError(
                "storage_error",
                "Completed upload metadata could not be reconciled.",
                status_code=500,
            )
        upload_session.completed_file_id = stored.id
        upload_session.status = "completed"
        upload_session.bytes_received = upload_session.expected_size
        self.session.commit()
        return stored

    def _try_reconcile_completed(self, upload_session: UploadSession) -> StoredFile | None:
        if upload_session.status == "failed":
            return None
        metadata = FileMetadata(
            device_id=upload_session.device_id,
            filename=upload_session.original_filename,
            size=upload_session.expected_size,
            sha256=upload_session.expected_sha256,
            content_type=upload_session.content_type,
        )
        stored = self.file_service.find_record(metadata)
        if stored is None:
            stored = self.file_service.reconcile_existing_final_file(metadata)
        if stored is None:
            return None
        upload_session.status = "completed"
        upload_session.completed_file_id = stored.id
        upload_session.bytes_received = upload_session.expected_size
        self.session.commit()
        return stored

    def _mark_failed(self, upload_session: UploadSession) -> None:
        upload_session.status = "failed"
        try:
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def _receiving(self, upload_session: UploadSession, next_offset: int) -> UploadSessionResult:
        return UploadSessionResult(
            status="receiving",
            upload_id=upload_session.id,
            next_offset=next_offset,
            expected_size=upload_session.expected_size,
            chunk_size_hint=DEFAULT_CHUNK_SIZE_HINT,
        )

    def _completed(
        self, upload_session: UploadSession, stored_file: StoredFile
    ) -> UploadSessionResult:
        return UploadSessionResult(
            status="completed",
            upload_id=upload_session.id,
            next_offset=upload_session.expected_size,
            expected_size=upload_session.expected_size,
            stored_file_id=stored_file.id,
            stored_path=stored_file.stored_path,
        )

    def _already_stored(self, stored_file: StoredFile) -> UploadSessionResult:
        return UploadSessionResult(
            status="already_stored",
            stored_file_id=stored_file.id,
            stored_path=stored_file.stored_path,
        )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
