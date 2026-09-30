from collections.abc import Generator

from fastapi import Header, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services.device_auth import AuthenticatedDevice, DeviceAuthService


def get_session(request: Request) -> Generator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_authenticated_device(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthenticatedDevice:
    if authorization is None:
        raise AppError(
            "authentication_required",
            "Device authentication is required.",
            status_code=401,
        )
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise AppError("authentication_failed", "Device authentication failed.", status_code=401)

    settings = request.app.state.settings
    if settings.environment != "test" and request.url.scheme != "https":
        raise AppError(
            "secure_transport_required",
            "Authenticated device requests require HTTPS.",
            status_code=403,
        )

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        return DeviceAuthService(session).authenticate(credential)
