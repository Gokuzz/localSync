import ipaddress
import logging
import socket
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from app.core.config import Settings
from app.core.security import SERVER_IDENTITY_HOSTNAME, ServerIdentity

LOGGER = logging.getLogger(__name__)

DISCOVERY_SERVICE_TYPE = "_localsync._tcp."
ZEROCONF_SERVICE_TYPE = "_localsync._tcp.local."
DISCOVERY_PROTOCOL_VERSION = "1"
DISCOVERY_TLS_VALUE = "required"


class ServiceRegistrar(Protocol):
    def register(
        self, service_type: str, instance_name: str, port: int, properties: dict[str, str]
    ) -> None: ...

    def unregister(self) -> None: ...


@dataclass(frozen=True)
class DiscoveryAdvertisement:
    service_type: str
    instance_name: str
    port: int
    properties: dict[str, str]


class ZeroconfRegistrar:
    def __init__(self) -> None:
        self._zeroconf = None
        self._service_info = None

    def register(
        self, service_type: str, instance_name: str, port: int, properties: dict[str, str]
    ) -> None:
        from zeroconf import ServiceInfo, Zeroconf

        server_name = _server_name()
        addresses = _local_ipv4_addresses()
        # FastAPI runs an asyncio loop. Keep Zeroconf's synchronous registration
        # API on its own worker loop so registration cannot block application startup.
        self._zeroconf = Zeroconf(use_asyncio=False)
        self._service_info = ServiceInfo(
            service_type,
            f"{instance_name}.{service_type}",
            addresses=addresses,
            port=port,
            properties=properties,
            server=server_name,
        )
        self._zeroconf.register_service(self._service_info)

    def unregister(self) -> None:
        if self._zeroconf is None:
            return
        try:
            if self._service_info is not None:
                self._zeroconf.unregister_service(self._service_info)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
            self._service_info = None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.unregister()


class LocalNetworkAdvertiser:
    def __init__(
        self,
        advertisement: DiscoveryAdvertisement,
        registrar: ServiceRegistrar | None = None,
        enabled: bool = True,
    ) -> None:
        self.advertisement = advertisement
        self._registrar = registrar or ZeroconfRegistrar()
        self._enabled = enabled
        self._started = False

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        server_identity: ServerIdentity,
        registrar: ServiceRegistrar | None = None,
    ) -> "LocalNetworkAdvertiser":
        instance_name = settings.discovery_instance_name or f"{socket.gethostname()} localSync"
        return cls(
            advertisement=DiscoveryAdvertisement(
                service_type=ZEROCONF_SERVICE_TYPE,
                instance_name=_sanitize_instance_name(instance_name),
                port=settings.server_port,
                properties=discovery_txt_records(server_identity.fingerprint),
            ),
            registrar=registrar,
            enabled=settings.discovery_enabled and settings.environment != "test",
        )

    def start(self) -> None:
        if not self._enabled or self._started:
            return
        try:
            self._registrar.register(
                self.advertisement.service_type,
                self.advertisement.instance_name,
                self.advertisement.port,
                self.advertisement.properties,
            )
            self._started = True
            LOGGER.info(
                "localSync discovery advertisement registered: service_type=%s port=%s",
                DISCOVERY_SERVICE_TYPE,
                self.advertisement.port,
            )
        except Exception:
            LOGGER.exception("localSync discovery advertisement failed to start")

    def stop(self) -> None:
        if not self._started:
            return
        try:
            self._registrar.unregister()
            LOGGER.info("localSync discovery advertisement stopped")
        finally:
            self._started = False


def discovery_txt_records(spki_fingerprint: str) -> dict[str, str]:
    return {
        "protocol": DISCOVERY_PROTOCOL_VERSION,
        "tls": DISCOVERY_TLS_VALUE,
        "host": SERVER_IDENTITY_HOSTNAME,
        "spki": spki_fingerprint,
    }


def _sanitize_instance_name(value: str) -> str:
    return value.replace(".", "-").strip() or "localSync"


def _server_name() -> str:
    hostname = socket.gethostname().replace(".", "-") or "localsync"
    return f"{hostname}.local."


def _local_ipv4_addresses() -> list[bytes]:
    addresses: list[bytes] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        infos = []
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or not isinstance(ip, ipaddress.IPv4Address):
            continue
        packed = socket.inet_aton(address)
        if packed not in addresses:
            addresses.append(packed)
    return addresses
