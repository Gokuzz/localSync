from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import Settings, get_settings
from app.db.migrations import migration_database_url
from app.db.session import create_db_engine, create_session_factory


def test_sqlalchemy_session_uses_isolated_sqlite_database(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    engine = create_db_engine(f"sqlite:///{database_path.as_posix()}")
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        result = session.execute(text("select 1")).scalar_one()

    assert result == 1
    assert database_path.exists()


def test_sqlite_engine_creation_creates_missing_parent_directory(tmp_path: Path) -> None:
    database_path = tmp_path / "missing" / "nested" / "test.db"

    engine = create_db_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        connection.execute(text("select 1"))

    assert database_path.exists()


def test_migration_database_url_matches_default_app_settings() -> None:
    settings = Settings()

    assert migration_database_url(settings) == settings.effective_database_url
    assert migration_database_url(settings) == "sqlite:///data/localsync.db"


def test_migration_database_url_matches_custom_data_root(tmp_path: Path) -> None:
    settings = Settings(LOCALSYNC_DATA_ROOT=tmp_path / "custom-root")

    expected = f"sqlite:///{(tmp_path / 'custom-root' / 'localsync.db').as_posix()}"
    assert settings.effective_database_url == expected
    assert migration_database_url(settings) == expected


def test_migration_database_url_matches_explicit_database_override(tmp_path: Path) -> None:
    database_path = tmp_path / "explicit.db"
    settings = Settings(
        LOCALSYNC_DATA_ROOT=tmp_path / "ignored-root",
        LOCALSYNC_DATABASE_URL=f"sqlite:///{database_path.as_posix()}",
    )

    assert migration_database_url(settings) == settings.effective_database_url
    assert migration_database_url(settings) == f"sqlite:///{database_path.as_posix()}"


def test_alembic_migration_uses_default_app_settings_without_touching_repo_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCALSYNC_DATA_ROOT", raising=False)
    monkeypatch.delenv("LOCALSYNC_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    database_path = tmp_path / "data" / "localsync.db"
    _run_alembic_upgrade()

    _assert_migrated_database(database_path)


def test_alembic_migration_uses_custom_data_root(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "custom-root"
    monkeypatch.setenv("LOCALSYNC_DATA_ROOT", str(data_root))
    monkeypatch.delenv("LOCALSYNC_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    expected_database_path = data_root / "localsync.db"
    hardcoded_default_path = tmp_path / "data" / "localsync.db"

    _run_alembic_upgrade()

    _assert_migrated_database(expected_database_path)
    assert not hardcoded_default_path.exists()


def test_alembic_migration_uses_explicit_database_url_override(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "custom-root"
    database_path = tmp_path / "explicit" / "override.db"
    monkeypatch.setenv("LOCALSYNC_DATA_ROOT", str(data_root))
    monkeypatch.setenv("LOCALSYNC_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    _run_alembic_upgrade()

    _assert_migrated_database(database_path)
    assert not (data_root / "localsync.db").exists()


def _run_alembic_upgrade() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "migrations"))

    command.upgrade(alembic_cfg, "head")


def _assert_migrated_database(database_path: Path) -> None:
    engine = create_db_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "paired_devices",
        "pairing_sessions",
        "stored_files",
        "upload_sessions",
    }
    columns = {column["name"] for column in inspector.get_columns("stored_files")}
    assert "size" in columns
    assert "sha256" in columns
    assert "stored_path" in columns
