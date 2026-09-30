from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileCandidate:
    path: Path
    filename: str
    size: int
    sha256: str
    content_type: str | None = None


@dataclass(frozen=True)
class TransferResult:
    filename: str
    status: str
    ok: bool
    detail: str | None = None
