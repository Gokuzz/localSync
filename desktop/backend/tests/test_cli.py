from pathlib import Path

from app.cli.__main__ import main
from app.core.config import get_settings
from app.core.security import generate_device_credential
from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.models.paired_device import PairedDevice


def test_cli_creates_pairing_session_and_lists_device_tables(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    database_path = tmp_path / "cli.db"
    monkeypatch.setenv("LOCALSYNC_ENV", "test")
    monkeypatch.setenv("LOCALSYNC_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALSYNC_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    engine = create_db_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    exit_code = main(["pairing", "create", "--server-url", "https://127.0.0.1:8000"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Pairing ID:" in output
    assert "Pairing code:" in output
    assert "Server fingerprint: spki-sha256:" in output

    get_settings.cache_clear()


def test_cli_can_revoke_and_activate_paired_device(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    database_path = tmp_path / "cli.db"
    monkeypatch.setenv("LOCALSYNC_ENV", "test")
    monkeypatch.setenv("LOCALSYNC_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALSYNC_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    engine = create_db_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        credential = generate_device_credential()
        session.add(
            PairedDevice(
                id="device-to-toggle",
                display_name="Device to toggle",
                credential_verifier=credential.verifier,
                platform="test",
                client_instance_id="test-toggle",
            )
        )
        session.commit()
    engine.dispose()

    revoke_exit = main(["devices", "revoke", "device-to-toggle"])
    revoke_output = capsys.readouterr().out
    assert revoke_exit == 0
    assert "Revoked device: device-to-toggle" in revoke_output

    list_revoked_exit = main(["devices", "list"])
    list_revoked_output = capsys.readouterr().out
    assert list_revoked_exit == 0
    assert "device-to-toggle\tDevice to toggle\trevoked" in list_revoked_output

    activate_exit = main(["devices", "activate", "device-to-toggle"])
    activate_output = capsys.readouterr().out
    assert activate_exit == 0
    assert "Activated device: device-to-toggle" in activate_output

    list_active_exit = main(["devices", "list"])
    list_active_output = capsys.readouterr().out
    assert list_active_exit == 0
    assert "device-to-toggle\tDevice to toggle\tactive" in list_active_output

    get_settings.cache_clear()
