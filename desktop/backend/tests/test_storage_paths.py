from pathlib import Path

import pytest

from app.storage.local_filesystem import LocalFilesystemStorage
from app.storage.names import build_storage_key, sanitize_device_id, sanitize_filename
from app.storage.paths import resolve_contained_path


def test_storage_creates_temp_and_final_roots_under_data_root(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "LocalSyncData")

    storage.ensure_directories()

    assert storage.temp_root == storage.data_root / ".localsync-temp"
    assert storage.backup_root == storage.data_root / "backups"
    assert storage.temp_root.is_dir()
    assert storage.backup_root.is_dir()


def test_partial_and_final_paths_are_separate_under_same_data_root(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "LocalSyncData")

    partial = storage.partial_path("session-1")
    final = storage.final_path("file-1")

    assert partial.parent == storage.temp_root
    assert partial.name == "session-1.partial"
    assert final.parent == storage.backup_root
    assert storage.temp_root.parent == storage.backup_root.parent == storage.data_root


@pytest.mark.parametrize("unsafe", ["..", "../escape", r"nested\name"])
def test_resolve_contained_path_rejects_traversal_and_separators(
    tmp_path: Path, unsafe: str
) -> None:
    with pytest.raises(ValueError):
        resolve_contained_path(tmp_path, unsafe)


def test_resolve_contained_path_allows_server_generated_nested_key(tmp_path: Path) -> None:
    resolved = resolve_contained_path(tmp_path, "device/file.bin")

    assert resolved == tmp_path.resolve() / "device" / "file.bin"


def test_resolve_contained_path_rejects_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_contained_path(tmp_path, str((tmp_path / "absolute").resolve()))


def test_sanitize_filename_removes_unsafe_path_content() -> None:
    assert sanitize_filename("CON?.jpg") == "CON_.jpg"
    assert sanitize_filename("  ...  ") == "file"


@pytest.mark.parametrize(
    "unsafe", ["../secret.txt", r"..\secret.txt", "/foo.jpg", r"C:\secret.txt"]
)
def test_sanitize_filename_rejects_path_like_names(unsafe: str) -> None:
    with pytest.raises(ValueError):
        sanitize_filename(unsafe)


@pytest.mark.parametrize("unsafe", ["../device", r"..\device", "/device", r"C:\device", ""])
def test_sanitize_device_id_rejects_path_like_names(unsafe: str) -> None:
    with pytest.raises(ValueError):
        sanitize_device_id(unsafe)


def test_build_storage_key_namespaces_by_device_and_hash() -> None:
    key = build_storage_key("fake-device-1", "IMG_0001.jpg", "a" * 64)

    assert key == "fake-device-1/IMG_0001_aaaaaaaaaaaa.jpg"


def test_same_filename_different_hashes_get_different_storage_keys() -> None:
    first = build_storage_key("fake-device-1", "IMG_0001.jpg", "a" * 64)
    second = build_storage_key("fake-device-1", "IMG_0001.jpg", "b" * 64)

    assert first != second


def test_reserve_final_path_rejects_existing_file(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "LocalSyncData")
    storage.ensure_directories()
    final_path = storage.final_path("fake-device-1/existing-file")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text("already here", encoding="utf-8")

    with pytest.raises(FileExistsError):
        storage.reserve_final_path("fake-device-1/existing-file")


def test_finalize_partial_moves_file_to_final_storage(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "LocalSyncData")
    storage.ensure_directories()
    partial = storage.partial_path("session-1")
    partial.write_bytes(b"opaque bytes")

    final = storage.finalize_partial(partial, "final-file")

    assert final == storage.final_path("final-file")
    assert final.read_bytes() == b"opaque bytes"
    assert not partial.exists()


def test_finalize_partial_rejects_partial_outside_temp_root(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path / "LocalSyncData")
    storage.ensure_directories()
    outside = tmp_path / "outside.partial"
    outside.write_bytes(b"nope")

    with pytest.raises(ValueError):
        storage.finalize_partial(outside, "final-file")
