import argparse
from pathlib import Path

from fake_phone.client import DEFAULT_UPLOAD_CHUNK_SIZE, DeviceClient, PairingClient, TransferClient
from fake_phone.config import FakeDeviceConfig, load_config, save_config
from fake_phone.scanner import scan_source_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generic localSync fake device client.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    pair = subcommands.add_parser("pair", help="Pair this fake client with a localSync backend.")
    pair.add_argument("--server", required=True, help="localSync backend URL.")
    pair.add_argument("--pairing-id", required=True, help="Pairing session ID from backend CLI.")
    pair.add_argument("--pairing-code", required=True, help="Pairing code from backend CLI.")
    pair.add_argument(
        "--server-fingerprint",
        required=True,
        help="Server fingerprint displayed by the backend CLI.",
    )
    pair.add_argument("--display-name", default="fake device", help="Paired device display name.")
    pair.add_argument("--config", required=True, type=Path, help="Credential config to write.")

    backup = subcommands.add_parser("backup", help="Back up files from a source directory.")
    backup.add_argument("--config", required=True, type=Path, help="Paired credential config.")
    backup.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Directory containing files to send.",
    )
    backup.add_argument(
        "--chunk-size-mib",
        type=int,
        default=DEFAULT_UPLOAD_CHUNK_SIZE // (1024 * 1024),
        help="Resumable upload chunk size in MiB.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "pair":
        pairing_client = PairingClient(
            args.server,
            expected_server_fingerprint=args.server_fingerprint,
        )
        try:
            result = pairing_client.complete_pairing(
                pairing_id=args.pairing_id,
                pairing_code=args.pairing_code,
                display_name=args.display_name,
            )
            server_fingerprint = str(result["server_fingerprint"])
            if server_fingerprint != args.server_fingerprint:
                print("failed: server fingerprint did not match pairing confirmation")
                return 1
            save_config(
                args.config,
                FakeDeviceConfig(
                    server=args.server.rstrip("/"),
                    server_fingerprint=server_fingerprint,
                    device_id=str(result["device_id"]),
                    device_credential=str(result["device_credential"]),
                ),
            )
        except Exception as exc:
            print(f"failed: {exc}")
            return 1
        finally:
            pairing_client.close()
        print(f"paired\t{args.config}")
        return 0

    config = load_config(args.config)
    transfer_client = TransferClient(
        config.server,
        config.device_credential,
        server_fingerprint=config.server_fingerprint,
        chunk_size=args.chunk_size_mib * 1024 * 1024,
    )
    device_client = DeviceClient(transfer_client)

    try:
        candidates = scan_source_directory(args.source)
        results = device_client.transfer_all(candidates)
    except Exception as exc:
        print(f"failed: {exc}")
        return 1
    finally:
        transfer_client.close()

    for result in results:
        if result.ok:
            print(f"{result.filename}\t{result.status}")
        else:
            print(f"{result.filename}\tfailed: {result.detail or result.status}")

    return 0 if all(result.ok for result in results) else 1
