import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.services.pairing import PairingService

REPO_ROOT = Path(__file__).resolve().parents[3]
FAKE_PHONE_ROOT = REPO_ROOT / "tools" / "fake_phone"
if str(FAKE_PHONE_ROOT) not in sys.path:
    sys.path.insert(0, str(FAKE_PHONE_ROOT))

import fake_phone.client as fake_phone_client  # noqa: E402
from fake_phone.cli import main as fake_phone_main  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def completed_files(data_root: Path) -> list[Path]:
    backup_root = data_root / "backups"
    if not backup_root.exists():
        return []
    return [path for path in backup_root.rglob("*") if path.is_file()]


def test_fake_client_transfers_skips_duplicate_and_preserves_collision_content(tmp_path) -> None:
    data_root = tmp_path / "backend-data"
    source_root = tmp_path / "source"
    source_root.mkdir()
    sample = source_root / "IMG_0001.bin"
    first_content = b"first opaque bytes"
    second_content = b"second opaque bytes"
    sample.write_bytes(first_content)

    settings = Settings(
        LOCALSYNC_ENV="test",
        LOCALSYNC_DATA_ROOT=data_root,
        LOCALSYNC_DATABASE_URL=f"sqlite:///{(tmp_path / 'server.db').as_posix()}",
        LOCALSYNC_LOG_LEVEL="WARNING",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        pairing = PairingService(
            session,
            server_fingerprint=app.state.server_identity.fingerprint,
        ).create_pairing_session(server_url="https://127.0.0.1")
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            ssl_certfile=str(app.state.server_identity.certificate_path),
            ssl_keyfile=str(app.state.server_identity.private_key_path),
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    server_url = f"https://127.0.0.1:{port}"
    original_http_client = fake_phone_client.httpx.Client
    fake_phone_client.httpx.Client = lambda timeout=30.0: original_http_client(
        timeout=timeout,
        verify=False,
    )
    try:
        for _ in range(50):
            try:
                if (
                    httpx.get(f"{server_url}/api/v1/health", timeout=1.0, verify=False).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise AssertionError("test server did not start")

        config_path = tmp_path / "fake-config.json"
        pair_exit = fake_phone_main(
            [
                "pair",
                "--server",
                server_url,
                "--pairing-id",
                pairing.pairing_id,
                "--pairing-code",
                pairing.pairing_code,
                "--server-fingerprint",
                pairing.server_fingerprint,
                "--config",
                str(config_path),
            ]
        )
        assert pair_exit == 0

        first_exit = fake_phone_main(
            ["backup", "--config", str(config_path), "--source", str(source_root)]
        )
        assert first_exit == 0
        first_files = completed_files(data_root)
        assert len(first_files) == 1
        assert first_files[0].read_bytes() == first_content

        duplicate_exit = fake_phone_main(
            ["backup", "--config", str(config_path), "--source", str(source_root)]
        )
        assert duplicate_exit == 0
        assert completed_files(data_root) == first_files

        sample.write_bytes(second_content)
        collision_exit = fake_phone_main(
            ["backup", "--config", str(config_path), "--source", str(source_root)]
        )
        assert collision_exit == 0

        final_files = sorted(completed_files(data_root))
        assert len(final_files) == 2
        assert sorted(path.read_bytes() for path in final_files) == sorted(
            [first_content, second_content]
        )
        assert first_files[0].read_bytes() == first_content
    finally:
        fake_phone_client.httpx.Client = original_http_client
        server.should_exit = True
        thread.join(timeout=5)
