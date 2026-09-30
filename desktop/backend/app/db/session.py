from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    ensure_sqlite_parent_directory(database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, echo=echo, future=True, connect_args=connect_args)


def ensure_sqlite_parent_directory(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        return
    if url.database in {":memory:", ""}:
        return
    Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_engine(settings: Settings | None = None) -> Engine:
    app_settings = settings or get_settings()
    return create_db_engine(app_settings.effective_database_url)


def get_db_session(settings: Settings | None = None) -> Generator[Session]:
    session_factory = create_session_factory(get_engine(settings))
    with session_factory() as session:
        yield session
