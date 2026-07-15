"""Timestamped logging with conservative secret redaction."""

from __future__ import annotations

import logging
import re
from pathlib import Path

_SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\b(\s*[:=]\s*)([^\s,;]+)")


def redact(value: str) -> str:
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(log_file: Path | None = None, *, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = RedactingFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=handlers, force=True)
