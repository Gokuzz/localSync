# Product Scope

localSync is a local-first backup and file-transfer application.

## V1 Purpose

- Automatically back up photos and videos from a phone-like device to a laptop over the local network.
- Preserve original media exactly: no resizing, recompression, transcoding, format conversion, metadata stripping, or content modification.
- Keep backup files as normal filesystem files.
- Use metadata and transfer state in a database only.
- Support manual transfer for documents and arbitrary files.

## Non-Negotiable Backup Behavior

Automatic backup is one-way from source device to laptop backup storage. The laptop copy is a backup archive, not a normal bidirectional synchronization mirror.

Deleting media from the source device must never automatically delete the laptop backup.

## V1 Boundaries

- Automatic backup includes photos and videos only.
- Documents, ZIPs, PDFs, DOCX files, and other arbitrary files are manual transfer only.
- V1 does not require cloud storage, mandatory online accounts, Google Drive, AWS storage, or Firebase storage.

## Platform Direction

V1 targets Android and Windows, but protocol and domain concepts must stay platform-neutral so future iOS, macOS, Linux, NAS, or other trusted device clients can participate.
