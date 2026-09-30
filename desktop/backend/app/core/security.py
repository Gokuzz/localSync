import base64
import hashlib
import hmac
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

DEVICE_CREDENTIAL_DOMAIN = b"localsync-device-credential-v1\x00"
PAIRING_SECRET_DOMAIN = b"localsync-pairing-secret-v1\x00"
PAIRING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 12
PAIRING_TTL_SECONDS = 5 * 60
PAIRING_MAX_ATTEMPTS = 5
SERVER_IDENTITY_HOSTNAME = "localsync.local"
FINGERPRINT_PREFIX = "spki-sha256:"


@dataclass(frozen=True)
class GeneratedCredential:
    credential: str
    verifier: str


@dataclass(frozen=True)
class GeneratedPairingCode:
    code: str
    verifier: str


@dataclass(frozen=True)
class ServerIdentity:
    certificate_path: Path
    private_key_path: Path
    fingerprint: str
    logical_hostname: str = SERVER_IDENTITY_HOSTNAME


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def pairing_expires_at(now: datetime | None = None) -> datetime:
    return (now or utc_now()) + timedelta(seconds=PAIRING_TTL_SECONDS)


def generate_device_credential() -> GeneratedCredential:
    raw = secrets.token_bytes(32)
    credential = _base64url(raw)
    return GeneratedCredential(
        credential=credential,
        verifier=device_credential_verifier(credential),
    )


def device_credential_verifier(credential: str) -> str:
    raw = _decode_base64url(credential)
    digest = hashlib.sha256(DEVICE_CREDENTIAL_DOMAIN + raw).hexdigest()
    return f"sha256-v1:{digest}"


def credential_matches(credential: str, verifier: str) -> bool:
    try:
        candidate = device_credential_verifier(credential)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, verifier)


def generate_pairing_code() -> GeneratedPairingCode:
    code = "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))
    grouped = "-".join(code[index : index + 4] for index in range(0, len(code), 4))
    return GeneratedPairingCode(code=grouped, verifier=pairing_code_verifier(grouped))


def normalize_pairing_code(code: str) -> str:
    return "".join(character for character in code.upper() if character != "-")


def pairing_code_verifier(code: str) -> str:
    normalized = normalize_pairing_code(code).encode("ascii")
    digest = hashlib.sha256(PAIRING_SECRET_DOMAIN + normalized).hexdigest()
    return f"sha256-v1:{digest}"


def pairing_code_matches(code: str, verifier: str) -> bool:
    return hmac.compare_digest(pairing_code_verifier(code), verifier)


def ensure_server_identity(data_root: Path) -> ServerIdentity:
    security_root = data_root / "security"
    cert_path = security_root / "server-cert.pem"
    key_path = security_root / "server-key.pem"
    security_root.mkdir(parents=True, exist_ok=True)

    if not cert_path.exists() or not key_path.exists():
        private_key = ec.generate_private_key(ec.SECP256R1())
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, SERVER_IDENTITY_HOSTNAME),
            ]
        )
        now = utc_now()
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(SERVER_IDENTITY_HOSTNAME)]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )
        key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        cert_bytes = certificate.public_bytes(serialization.Encoding.PEM)
        key_path.write_bytes(key_bytes)
        cert_path.write_bytes(cert_bytes)
        _restrict_owner_only(key_path)
        _restrict_owner_only(cert_path)

    return ServerIdentity(
        certificate_path=cert_path,
        private_key_path=key_path,
        fingerprint=server_certificate_fingerprint(cert_path),
    )


def server_certificate_fingerprint(certificate_path: Path) -> str:
    certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
    spki = certificate.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return f"{FINGERPRINT_PREFIX}{_base64url(hashlib.sha256(spki).digest())}"


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    if not value or any(character in value for character in "\r\n\t "):
        raise ValueError("credential contains unsupported whitespace")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as exc:
        raise ValueError("credential is not valid base64url") from exc


def _restrict_owner_only(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows and some filesystems may not honor POSIX mode bits.
        return
