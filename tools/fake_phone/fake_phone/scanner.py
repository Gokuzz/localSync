import mimetypes
from pathlib import Path

from fake_phone.hashing import compute_sha256
from fake_phone.models import FileCandidate


def scan_source_directory(source: Path) -> list[FileCandidate]:
    if not source.is_dir():
        raise ValueError("source must be a directory")

    candidates: list[FileCandidate] = []
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        candidates.append(
            FileCandidate(
                path=path,
                filename=path.name,
                size=path.stat().st_size,
                sha256=compute_sha256(path),
                content_type=mimetypes.guess_type(path.name)[0],
            )
        )
    return candidates
