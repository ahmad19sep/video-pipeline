"""Versioned JSON Schema discovery and validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class SchemaError(ValueError):
    """Raised for missing or invalid schema contracts."""


def load_schema(root: Path, name: str) -> dict[str, Any]:
    path = root / "schemas" / f"{name}.schema.json"
    if not path.is_file():
        raise SchemaError(f"Unknown schema: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "$schema" not in data or "$id" not in data:
        raise SchemaError(f"Schema is not a versioned object: {path}")
    Draft202012Validator.check_schema(data)
    return data


@lru_cache(maxsize=64)
def _validator_for(root: Path, name: str, mtime_ns: int) -> Draft202012Validator:
    return Draft202012Validator(load_schema(root, name))


def validate_document(root: Path, name: str, document: object) -> list[str]:
    path = root / "schemas" / f"{name}.schema.json"
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError as error:
        raise SchemaError(f"Unknown schema: {name}") from error
    validator = _validator_for(root, name, mtime_ns)
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: [str(part) for part in item.absolute_path],
    )
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]
