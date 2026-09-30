from dataclasses import dataclass

from app.core.config import Settings
from app.core.security import ServerIdentity
from app.services.discovery import (
    DISCOVERY_SERVICE_TYPE,
    ZEROCONF_SERVICE_TYPE,
    LocalNetworkAdvertiser,
    discovery_txt_records,
)


@dataclass
class FakeRegistrar:
    registrations: list[tuple[str, str, int, dict[str, str]]]
    unregister_count: int = 0

    def register(
        self, service_type: str, instance_name: str, port: int, properties: dict[str, str]
    ) -> None:
        self.registrations.append((service_type, instance_name, port, properties))

    def unregister(self) -> None:
        self.unregister_count += 1


def test_discovery_txt_records_are_minimal_and_non_secret() -> None:
    records = discovery_txt_records("spki-sha256:abc")

    assert records == {
        "protocol": "1",
        "tls": "required",
        "host": "localsync.local",
        "spki": "spki-sha256:abc",
    }
    assert "credential" not in records
    assert "pairing_code" not in records


def test_advertiser_uses_configured_port_and_phase5_identity() -> None:
    registrar = FakeRegistrar([])
    settings = Settings(LOCALSYNC_ENV="development", LOCALSYNC_SERVER_PORT=8443)
    identity = ServerIdentity(
        certificate_path=settings.data_root / "security/server-cert.pem",
        private_key_path=settings.data_root / "security/server-key.pem",
        fingerprint="spki-sha256:test",
    )
    advertiser = LocalNetworkAdvertiser.from_settings(settings, identity, registrar)

    advertiser.start()

    assert len(registrar.registrations) == 1
    service_type, _, port, properties = registrar.registrations[0]
    assert service_type == ZEROCONF_SERVICE_TYPE
    assert port == 8443
    assert properties["spki"] == "spki-sha256:test"
    assert DISCOVERY_SERVICE_TYPE in service_type

    advertiser.stop()
    assert registrar.unregister_count == 1


def test_advertiser_does_not_start_for_test_environment() -> None:
    registrar = FakeRegistrar([])
    settings = Settings(LOCALSYNC_ENV="test")
    identity = ServerIdentity(
        certificate_path=settings.data_root / "security/server-cert.pem",
        private_key_path=settings.data_root / "security/server-key.pem",
        fingerprint="spki-sha256:test",
    )
    advertiser = LocalNetworkAdvertiser.from_settings(settings, identity, registrar)

    advertiser.start()

    assert registrar.registrations == []
