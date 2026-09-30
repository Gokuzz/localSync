import base64
import hashlib
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import serialization

LOGICAL_SERVER_HOST = "localsync.local"
FINGERPRINT_PREFIX = "spki-sha256:"


@dataclass(frozen=True)
class ObservedServerIdentity:
    server: str
    fingerprint: str


def observe_server_identity(server: str) -> ObservedServerIdentity:
    parsed = urlparse(server.rstrip("/"))
    if parsed.scheme != "https":
        raise ValueError("Pairing and authenticated backup require an https:// server URL.")
    if not parsed.hostname:
        raise ValueError("Server URL must include a hostname or IP address.")
    port = parsed.port or 443

    context = ssl._create_unverified_context()  # noqa: S323
    with (
        socket.create_connection((parsed.hostname, port), timeout=10.0) as tcp,
        context.wrap_socket(tcp, server_hostname=LOGICAL_SERVER_HOST) as tls,
    ):
        certificate_der = tls.getpeercert(binary_form=True)
    if not certificate_der:
        raise ValueError("Server did not present a TLS certificate.")
    return ObservedServerIdentity(
        server=server.rstrip("/"),
        fingerprint=spki_fingerprint_from_der(certificate_der),
    )


def spki_fingerprint_from_der(certificate_der: bytes) -> str:
    certificate = x509.load_der_x509_certificate(certificate_der)
    spki_der = certificate.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(spki_der).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{FINGERPRINT_PREFIX}{encoded}"


def verify_observed_fingerprint(server: str, expected_fingerprint: str) -> str:
    observed = observe_server_identity(server).fingerprint
    if observed != expected_fingerprint:
        raise ValueError("Server identity changed; refusing to send credentials.")
    return observed
