"""Cross-platform exclusive project mutation lock."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType


class ProjectLockedError(RuntimeError):
    """Raised when another live process owns a project lock."""


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return True
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) > 1 and row[1].isdigit() and int(row[1]) == pid:
                return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class ProjectLock(AbstractContextManager["ProjectLock"]):
    def __init__(self, project_dir: Path) -> None:
        self.path = project_dir / ".cutmachine.lock"
        self._owned = False

    def _try_create(self) -> bool:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError:
            return False
        payload = json.dumps(
            {"pid": os.getpid(), "createdAt": datetime.now(UTC).isoformat()},
            ensure_ascii=True,
        ).encode("ascii")
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._owned = True
        return True

    def _reclaim_if_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="ascii"))
            pid = int(data.get("pid", -1))
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            return False
        if _process_exists(pid):
            return False
        try:
            self.path.unlink()
        except OSError:
            return False
        return True

    def __enter__(self) -> ProjectLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._try_create():
            return self
        if self._reclaim_if_stale() and self._try_create():
            return self
        raise ProjectLockedError(
            f"Project is locked by another process: {self.path}. "
            "Wait for it to finish before retrying."
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._owned:
            self.path.unlink(missing_ok=True)
            self._owned = False
