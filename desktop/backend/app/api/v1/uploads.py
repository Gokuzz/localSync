from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_authenticated_device, get_session
from app.services.device_auth import AuthenticatedDevice
from app.services.upload_sessions import UploadMetadata, UploadSessionResult, UploadSessionService

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadCreateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    expected_size: int = Field(ge=0)
    expected_sha256: str = Field(min_length=64, max_length=64)
    content_type: str | None = Field(default=None, max_length=255)


class UploadSessionResponse(BaseModel):
    status: str
    upload_id: str | None = None
    next_offset: int | None = None
    expected_size: int | None = None
    chunk_size_hint: int | None = None
    stored_file_id: str | None = None
    stored_path: str | None = None


def _response(result: UploadSessionResult) -> UploadSessionResponse:
    return UploadSessionResponse(
        status=result.status,
        upload_id=result.upload_id,
        next_offset=result.next_offset,
        expected_size=result.expected_size,
        chunk_size_hint=result.chunk_size_hint,
        stored_file_id=result.stored_file_id,
        stored_path=result.stored_path,
    )


def _service(request: Request, session: Session) -> UploadSessionService:
    return UploadSessionService(
        session,
        request.app.state.storage,
        max_chunk_size=request.app.state.settings.max_upload_chunk_size,
    )


@router.post("", response_model=UploadSessionResponse)
def create_upload(
    payload: UploadCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[AuthenticatedDevice, Depends(get_authenticated_device)],
) -> UploadSessionResponse:
    result = _service(request, session).create_or_recover(
        UploadMetadata(
            device_id=device.id,
            filename=payload.filename,
            expected_size=payload.expected_size,
            expected_sha256=payload.expected_sha256,
            content_type=payload.content_type,
        )
    )
    return _response(result)


@router.get("/{upload_id}", response_model=UploadSessionResponse)
def get_upload(
    upload_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[AuthenticatedDevice, Depends(get_authenticated_device)],
) -> UploadSessionResponse:
    return _response(_service(request, session).get_status(upload_id, device_id=device.id))


@router.put("/{upload_id}", response_model=UploadSessionResponse)
async def append_upload(
    upload_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[AuthenticatedDevice, Depends(get_authenticated_device)],
    offset: Annotated[int, Header(alias="X-localSync-Offset", ge=0)],
    content_length: Annotated[str | None, Header(alias="Content-Length")] = None,
) -> UploadSessionResponse:
    parsed_content_length: int | None
    try:
        parsed_content_length = None if content_length is None else int(content_length)
    except ValueError:
        parsed_content_length = -1
    result = await _service(request, session).append(
        upload_id,
        device_id=device.id,
        offset=offset,
        content_length=parsed_content_length,
        chunks=request.stream(),
    )
    return _response(result)


@router.post("/{upload_id}/complete", response_model=UploadSessionResponse)
def complete_upload(
    upload_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[AuthenticatedDevice, Depends(get_authenticated_device)],
) -> UploadSessionResponse:
    return _response(_service(request, session).complete(upload_id, device_id=device.id))
