from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import AppError
from app.services.pairing import PairingService

router = APIRouter(prefix="/pairing-sessions", tags=["pairing"])


class PairingCompleteRequest(BaseModel):
    pairing_code: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=120)
    platform: str | None = Field(default=None, max_length=80)
    client_instance_id: str | None = Field(default=None, max_length=120)


class PairingCompleteResponse(BaseModel):
    device_id: str
    device_credential: str
    server_fingerprint: str
    server_display_name: str


@router.post("/{pairing_id}/complete", response_model=PairingCompleteResponse)
def complete_pairing(
    pairing_id: str,
    payload: PairingCompleteRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> PairingCompleteResponse:
    if request.app.state.settings.environment != "test" and request.url.scheme != "https":
        raise AppError(
            "secure_transport_required",
            "Pairing completion requires HTTPS.",
            status_code=403,
        )
    result = PairingService(
        session,
        server_fingerprint=request.app.state.server_identity.fingerprint,
    ).complete_pairing(
        pairing_id,
        pairing_code=payload.pairing_code,
        display_name=payload.display_name,
        platform=payload.platform,
        client_instance_id=payload.client_instance_id,
    )
    return PairingCompleteResponse(
        device_id=result.device_id,
        device_credential=result.device_credential,
        server_fingerprint=result.server_fingerprint,
        server_display_name=result.server_display_name,
    )
