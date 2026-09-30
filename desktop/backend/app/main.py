from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.security import ensure_server_identity
from app.db.session import create_db_engine, create_session_factory
from app.services.discovery import LocalNetworkAdvertiser
from app.storage.local_filesystem import LocalFilesystemStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.discovery_advertiser.start()
        try:
            yield
        finally:
            app.state.discovery_advertiser.stop()

    app = FastAPI(title="localSync desktop backend", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.engine = create_db_engine(app_settings.effective_database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.storage = LocalFilesystemStorage(app_settings.data_root)
    app.state.server_identity = ensure_server_identity(app_settings.data_root)
    app.state.discovery_advertiser = LocalNetworkAdvertiser.from_settings(
        app_settings,
        app.state.server_identity,
    )
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
