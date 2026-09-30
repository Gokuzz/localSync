from typing import Protocol

from app.core.config import Settings, get_settings


class AlembicConfig(Protocol):
    def set_main_option(self, name: str, value: str) -> None: ...


def migration_database_url(settings: Settings | None = None) -> str:
    app_settings = settings or get_settings()
    return app_settings.effective_database_url


def configure_alembic_database_url(
    alembic_config: AlembicConfig, settings: Settings | None = None
) -> str:
    database_url = migration_database_url(settings)
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    return database_url
