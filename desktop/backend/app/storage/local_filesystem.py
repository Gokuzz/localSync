import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.storage.paths import resolve_contained_path


@dataclass(frozen=True)
class DiskUsage:
    total: int
    used: int
    free: int


class LocalFilesystemStorage:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.expanduser().resolve(strict=False)
        self.temp_root = self.data_root / ".localsync-temp"
        self.backup_root = self.data_root / "backups"

    def ensure_directories(self) -> None:
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def partial_path(self, session_id: str) -> Path:
        return resolve_contained_path(self.temp_root, f"{session_id}.partial")

    def partial_path_for_key(self, temp_relative_path: str) -> Path:
        return resolve_contained_path(self.temp_root, temp_relative_path)

    def partial_size(self, temp_relative_path: str) -> int | None:
        partial_path = self.partial_path_for_key(temp_relative_path)
        if not partial_path.exists():
            return None
        return partial_path.stat().st_size

    def ensure_empty_partial(self, temp_relative_path: str) -> Path:
        partial_path = self.partial_path_for_key(temp_relative_path)
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.touch(exist_ok=True)
        return partial_path

    def remove_partial(self, temp_relative_path: str) -> None:
        self.partial_path_for_key(temp_relative_path).unlink(missing_ok=True)

    def final_path(self, storage_key: str) -> Path:
        return resolve_contained_path(self.backup_root, storage_key)

    def reserve_final_path(self, storage_key: str) -> Path:
        final_path = self.final_path(storage_key)
        if final_path.exists():
            raise FileExistsError("final storage path already exists")
        return final_path

    def final_path_exists(self, storage_key: str) -> bool:
        return self.final_path(storage_key).exists()

    def finalize_partial(self, partial_path: Path, storage_key: str) -> Path:
        resolved_partial = partial_path.resolve(strict=True)
        try:
            resolved_partial.relative_to(self.temp_root.resolve(strict=False))
        except ValueError as exc:
            raise ValueError("partial path is outside temporary storage") from exc

        final_path = self.reserve_final_path(storage_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.rename(resolved_partial, final_path)
        return final_path

    def disk_usage(self) -> DiskUsage:
        usage = shutil.disk_usage(self.data_root)
        return DiskUsage(total=usage.total, used=usage.used, free=usage.free)
