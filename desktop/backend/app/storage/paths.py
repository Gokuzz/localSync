from pathlib import Path


def resolve_contained_path(root: Path, relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("relative path must not be empty")

    if "\\" in relative_path:
        raise ValueError("backslash separators are not allowed")

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("absolute paths are not allowed")

    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("path traversal is not allowed")

    resolved_root = root.resolve(strict=False)
    resolved_path = (resolved_root / candidate).resolve(strict=False)

    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("resolved path escapes storage root") from exc

    return resolved_path
