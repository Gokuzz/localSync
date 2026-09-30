import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FakeDeviceConfig:
    server: str
    server_fingerprint: str
    device_id: str
    device_credential: str


def load_config(path: Path) -> FakeDeviceConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return FakeDeviceConfig(
        server=str(data["server"]),
        server_fingerprint=str(data["server_fingerprint"]),
        device_id=str(data["device_id"]),
        device_credential=str(data["device_credential"]),
    )


def save_config(path: Path, config: FakeDeviceConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True), encoding="utf-8")
