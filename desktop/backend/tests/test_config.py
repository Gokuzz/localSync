from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_are_local_development_paths() -> None:
    settings = Settings()

    assert settings.environment == "development"
    assert settings.data_root == Path("data")
    assert settings.backup_root == Path("data") / "backups"
    assert settings.temp_upload_root == Path("data") / ".localsync-temp"
    assert settings.effective_database_url == "sqlite:///data/localsync.db"


def test_settings_accept_environment_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "localsync-data"
    monkeypatch.setenv("LOCALSYNC_ENV", "test")
    monkeypatch.setenv("LOCALSYNC_DATA_ROOT", str(data_root))
    monkeypatch.setenv("LOCALSYNC_DATABASE_URL", "sqlite:///custom.db")
    monkeypatch.setenv("LOCALSYNC_LOG_LEVEL", "debug")

    settings = Settings()

    assert settings.environment == "test"
    assert settings.data_root == data_root
    assert settings.backup_root == data_root / "backups"
    assert settings.temp_upload_root == data_root / ".localsync-temp"
    assert settings.effective_database_url == "sqlite:///custom.db"
    assert settings.log_level == "DEBUG"


def test_settings_accept_discovery_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALSYNC_SERVER_PORT", "8443")
    monkeypatch.setenv("LOCALSYNC_DISCOVERY_ENABLED", "false")
    monkeypatch.setenv("LOCALSYNC_DISCOVERY_INSTANCE_NAME", "  Laptop.localSync  ")

    settings = Settings()

    assert settings.server_port == 8443
    assert settings.discovery_enabled is False
    assert settings.discovery_instance_name == "Laptop.localSync"


def test_settings_reject_unknown_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(LOCALSYNC_LOG_LEVEL="verbose")
