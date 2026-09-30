import hashlib
from collections.abc import Iterator
from pathlib import Path

DEFAULT_CHUNK_SIZE = 1024 * 1024


def iter_file_chunks(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
    with path.open("rb") as file:
        yield from iter(lambda: file.read(chunk_size), b"")


def compute_sha256(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    hasher = hashlib.sha256()
    for chunk in iter_file_chunks(path, chunk_size=chunk_size):
        hasher.update(chunk)
    return hasher.hexdigest()
