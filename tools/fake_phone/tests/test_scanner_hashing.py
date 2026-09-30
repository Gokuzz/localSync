import hashlib

import pytest

from fake_phone.hashing import compute_sha256, iter_file_chunks
from fake_phone.scanner import scan_source_directory


def test_compute_sha256_reads_incrementally(tmp_path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abcdef")

    assert list(iter_file_chunks(path, chunk_size=2)) == [b"ab", b"cd", b"ef"]
    assert compute_sha256(path, chunk_size=2) == hashlib.sha256(b"abcdef").hexdigest()


def test_scan_source_directory_finds_files_and_ignores_directories(tmp_path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.bin").write_bytes(b"a")
    (tmp_path / "b.bin").write_bytes(b"bb")

    candidates = scan_source_directory(tmp_path)

    assert [candidate.filename for candidate in candidates] == ["a.bin", "b.bin"]
    assert [candidate.size for candidate in candidates] == [1, 2]


def test_scan_source_directory_requires_directory(tmp_path) -> None:
    file_path = tmp_path / "not-a-dir"
    file_path.write_bytes(b"content")

    with pytest.raises(ValueError):
        scan_source_directory(file_path)
