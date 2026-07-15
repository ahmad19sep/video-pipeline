"""Layered CutMachine configuration loading."""

from __future__ import annotations

import copy
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

Config = dict[str, Any]
ENV_PREFIX = "CUTMACHINE__"


class ConfigError(ValueError):
    """Raised when a configuration layer is invalid."""


def _read_yaml(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(f"Configuration file does not exist: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"Configuration root must be a mapping: {path}")
    return {str(key): value for key, value in loaded.items()}


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Config:
    """Return a recursively merged copy without mutating either input."""
    result: Config = copy.deepcopy(dict(base))
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge(current, value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_env_value(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError("Invalid CUTMACHINE environment override") from exc


def environment_layer(environment: Mapping[str, str] | None = None) -> Config:
    source = os.environ if environment is None else environment
    result: Config = {}
    for name, raw_value in source.items():
        if not name.startswith(ENV_PREFIX):
            continue
        parts = [part.lower() for part in name[len(ENV_PREFIX) :].split("__") if part]
        if not parts:
            continue
        cursor = result
        for part in parts[:-1]:
            nested = cursor.setdefault(part, {})
            if not isinstance(nested, dict):
                raise ConfigError(f"Conflicting environment override: {name}")
            cursor = nested
        cursor[parts[-1]] = _parse_env_value(raw_value)
    return result


def load_config(
    root: Path,
    *,
    style: str = "balanced",
    project_config: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> Config:
    config_dir = root / "config"
    merged = _read_yaml(config_dir / "defaults.yaml")
    merged = deep_merge(merged, _read_yaml(config_dir / "styles" / f"{style}.yaml"))
    if project_config is not None:
        merged = deep_merge(merged, _read_yaml(project_config))
    return deep_merge(merged, environment_layer(environment))
