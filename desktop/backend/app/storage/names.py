import re
from pathlib import PurePath

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SAFE_DEVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def sanitize_filename(filename: str, *, fallback: str = "file") -> str:
    if PurePath(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("filename must not contain path separators")

    sanitized = UNSAFE_FILENAME_CHARS.sub("_", filename).strip(" .")
    sanitized = re.sub(r"_+", "_", sanitized)

    if not sanitized:
        sanitized = fallback

    stem = sanitized.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        sanitized = f"{sanitized}_"

    return sanitized[:128]


def sanitize_device_id(device_id: str) -> str:
    if not SAFE_DEVICE_ID.fullmatch(device_id):
        raise ValueError("device_id contains unsupported characters")
    if device_id in {".", ".."} or ":" in device_id:
        raise ValueError("device_id is not a safe namespace")
    return device_id


def build_storage_filename(filename: str, sha256: str, *, hash_length: int = 12) -> str:
    sanitized = sanitize_filename(filename)
    if "." in sanitized:
        stem, extension = sanitized.rsplit(".", 1)
        suffix = f".{extension}"
    else:
        stem = sanitized
        suffix = ""

    short_hash = sha256[:hash_length]
    max_stem_length = max(1, 128 - len(short_hash) - len(suffix) - 1)
    return f"{stem[:max_stem_length]}_{short_hash}{suffix}"


def build_storage_key(device_id: str, filename: str, sha256: str, *, hash_length: int = 12) -> str:
    safe_device_id = sanitize_device_id(device_id)
    safe_filename = build_storage_filename(filename, sha256, hash_length=hash_length)
    return f"{safe_device_id}/{safe_filename}"
