# Fake Device Client

Development utility for simulating a generic localSync device client during protocol and transfer testing.

Despite the directory name, this tool models platform-neutral client behavior and must not make the protocol Android-specific.

## Setup

```powershell
cd tools/fake_phone
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run

Start the backend first, create a pairing session with the backend CLI, then run:

```powershell
python -m fake_phone pair --server https://127.0.0.1:8000 --pairing-id <pairing-id> --pairing-code <pairing-code> --server-fingerprint <fingerprint> --config .\fake-device.json
python -m fake_phone backup --config .\fake-device.json --source ./sample-media --chunk-size-mib 8
```

The client scans files in the source directory, computes SHA-256 incrementally, checks whether each file is already backed up, creates or recovers a resumable upload session, and sends missing files sequentially in bounded chunks.

If the client exits mid-transfer, rerunning the backup command asks the backend to recover a compatible active session and resume from the authoritative next offset.

The fake client uses the same bearer-authenticated transfer APIs as other clients. Its local config is a development credential store and is not equivalent to Android Keystore.

During pairing, the fake client observes the backend TLS certificate, computes the canonical `spki-sha256:` fingerprint, and refuses to send the pairing code if it does not match the fingerprint printed by the backend CLI. During backup, it preflights the stored fingerprint before attaching the bearer credential.

## Validate

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```
