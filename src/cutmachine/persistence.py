"""Durable JSON persistence primitives."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cutmachine.schemas import validate_document


class PersistenceError(RuntimeError):
    """Raised when validated project data cannot be loaded or stored."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PersistenceError(f"Could not read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PersistenceError(f"JSON root must be an object: {path}")
    return value


def read_validated_json(repository_root: Path, path: Path, schema_name: str) -> dict[str, Any]:
    value = read_json(path)
    errors = validate_document(repository_root, schema_name, value)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise PersistenceError(f"Invalid {schema_name} document at {path}:\n{joined}")
    return value


def write_validated_json_atomic(
    repository_root: Path,
    path: Path,
    schema_name: str,
    value: dict[str, Any],
) -> None:
    errors = validate_document(repository_root, schema_name, value)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise PersistenceError(f"Refusing to write invalid {schema_name} document:\n{joined}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise PersistenceError(f"Could not atomically write {path}: {exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)
