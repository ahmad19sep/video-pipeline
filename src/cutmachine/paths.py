"""Path validation for imported project data."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class UnsafePathError(ValueError):
    """Raised when imported data references an unsafe path."""


def validate_relative_path(raw: str) -> Path:
    """Validate an imported relative path on both Windows and POSIX hosts."""
    if not raw or raw.startswith(("/", "\\", "~")) or _DRIVE_PREFIX.match(raw):
        raise UnsafePathError(f"Path must be relative: {raw!r}")
    windows_parts = PureWindowsPath(raw).parts
    posix_parts = PurePosixPath(raw.replace("\\", "/")).parts
    if ".." in windows_parts or ".." in posix_parts:
        raise UnsafePathError(f"Path traversal is not allowed: {raw!r}")
    return Path(*posix_parts)


def resolve_inside(root: Path, raw: str) -> Path:
    candidate = (root / validate_relative_path(raw)).resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise UnsafePathError(f"Path escapes allowed root: {raw!r}")
    return candidate
