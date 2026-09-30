from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_authenticated_device, get_session
from app.services.device_auth import AuthenticatedDevice
from app.services.file_transfers import FileMetadata, FileTransferService

router = APIRouter(prefix="/files", tags=["files"])


class FileCheckRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    content_type: str | None = Field(default=None, max_length=255)


class FileCheckResponse(BaseModel):
    exists: bool
    stored_file_id: str | None = None
    stored_path: str | None = None


class FileUploadResponse(BaseModel):
    status: str
    stored_file_id: str
    stored_path: str


@router.post("/check", response_model=FileCheckResponse)
def check_file(
    payload: FileCheckRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[AuthenticatedDevice, Depends(get_authenticated_device)],
) -> FileCheckResponse:
    service = FileTransferService(session, request.app.state.storage)
    status = service.check_file(
        FileMetadata(
            device_id=device.id,
            filename=payload.filename,
            size=payload.size,
            sha256=payload.sha256,
            content_type=payload.content_type,
        )
    )
    return FileCheckResponse(
        exists=status.exists,
        stored_file_id=status.stored_file_id,
        stored_path=status.stored_path,
    )


@router.post("", response_model=FileUploadResponse)
async def upload_file(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[AuthenticatedDevice, Depends(get_authenticated_device)],
    filename: Annotated[str, Header(alias="X-localSync-Filename", min_length=1, max_length=255)],
    size: Annotated[int, Header(alias="X-localSync-Size", ge=0)],
    sha256: Annotated[str, Header(alias="X-localSync-Sha256", min_length=64, max_length=64)],
    content_type: Annotated[
        str | None, Header(alias="X-localSync-Content-Type", max_length=255)
    ] = None,
) -> FileUploadResponse:
    service = FileTransferService(session, request.app.state.storage)
    status, stored = await service.receive_file(
        FileMetadata(
            device_id=device.id,
            filename=filename,
            size=size,
            sha256=sha256,
            content_type=content_type,
        ),
        request.stream(),
    )
    return FileUploadResponse(
        status=status, stored_file_id=stored.id, stored_path=stored.stored_path
    )
