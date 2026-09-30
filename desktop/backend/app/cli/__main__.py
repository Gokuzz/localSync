import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import ensure_server_identity
from app.db.session import create_db_engine, create_session_factory
from app.repositories.paired_devices import PairedDeviceRepository
from app.services.pairing import PairingService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="localSync backend administrative CLI.")
    subcommands = parser.add_subparsers(dest="resource", required=True)

    pairing = subcommands.add_parser("pairing", help="Manage pairing sessions.")
    pairing_commands = pairing.add_subparsers(dest="command", required=True)
    pairing_create = pairing_commands.add_parser("create", help="Create a pairing session.")
    pairing_create.add_argument("--server-url", help="Current HTTPS server URL shown to clients.")

    devices = subcommands.add_parser("devices", help="Manage paired devices.")
    device_commands = devices.add_subparsers(dest="command", required=True)
    device_commands.add_parser("list", help="List paired devices.")
    revoke = device_commands.add_parser("revoke", help="Revoke a paired device.")
    revoke.add_argument("device_id")
    activate = device_commands.add_parser("activate", help="Reactivate a revoked paired device.")
    activate.add_argument("device_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    engine = create_db_engine(settings.effective_database_url)
    session_factory = create_session_factory(engine)
    identity = ensure_server_identity(settings.data_root)

    try:
        with session_factory() as session:
            service = PairingService(session, server_fingerprint=identity.fingerprint)
            if args.resource == "pairing" and args.command == "create":
                created = service.create_pairing_session(server_url=args.server_url)
                print(f"Pairing ID: {created.pairing_id}")
                print(f"Pairing code: {created.pairing_code}")
                print(f"Expires at: {created.expires_at.isoformat()}")
                print(f"Server fingerprint: {created.server_fingerprint}")
                if created.server_url:
                    print(f"Server URL: {created.server_url}")
                print("Compare this fingerprint on the client before completing pairing.")
                return 0

            if args.resource == "devices" and args.command == "list":
                devices = PairedDeviceRepository(session).list_all()
                for device in devices:
                    revoked = "revoked" if device.revoked_at else "active"
                    print(f"{device.id}\t{device.display_name}\t{revoked}")
                return 0

            if args.resource == "devices" and args.command == "revoke":
                service.revoke_device(args.device_id)
                print(f"Revoked device: {args.device_id}")
                return 0

            if args.resource == "devices" and args.command == "activate":
                service.activate_device(args.device_id)
                print(f"Activated device: {args.device_id}")
                return 0
    except AppError as exc:
        print(f"failed: {exc.code}: {exc.message}")
        return 1
    finally:
        engine.dispose()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
