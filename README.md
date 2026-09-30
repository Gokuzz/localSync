# localSync

localSync is a local-first device backup and file-transfer application in early development.

Its first product goal is to automatically back up original photos and videos from a phone to a laptop over the local network, without cloud storage and without changing media bytes. The laptop copy is a backup archive, not a two-way sync mirror. Deleting media on the phone must never automatically delete the laptop backup.

Documents and arbitrary files are planned as manual transfers in V1, not automatic backup content.

## Current Status

This repository is in Phase 0: repository structure, durable agent context, architecture documentation, planning conventions, and engineering guardrails. No application behavior has been implemented.

## Planned Platforms

- V1 mobile client: Android
- V1 desktop/laptop application: Windows
- Future-compatible concepts: iOS, macOS, Linux, NAS, and other trusted devices

Protocol and domain language must stay platform-neutral: Device, Client, UploadSession, MediaItem, Transfer, and Backup.

## Planned Architecture

- Android client: Kotlin, Jetpack Compose, MediaStore, Room, WorkManager, OkHttp, Android NSD/mDNS, Storage Access Framework, Android Keystore
- Desktop backend: Python, FastAPI, SQLAlchemy, SQLite, Alembic, pytest, Uvicorn, Zeroconf/mDNS
- Desktop frontend: React, TypeScript, Vite
- Protocol: local-network, versioned under `/api/v1/`, with pairing, authenticated devices, resumable uploads, chunk status, and SHA-256 verification

## Repository Layout

- `AGENTS.md`: repository-wide agent instructions and invariants
- `.agent/PLANS.md`: ExecPlan format for complex work
- `docs/`: product, architecture, protocol, security, testing, roadmap, and ADRs
- `android/`: future Android client
- `desktop/backend/`: future desktop API and storage service
- `desktop/frontend/`: future desktop UI
- `tools/fake_phone/`: future generic fake-device protocol test client
- `scripts/`: future development automation

Start with [docs/index.md](docs/index.md) for the project knowledge map.
