import json
import os
from pathlib import Path

import pytest

from cutmachine.locking import ProjectLock, ProjectLockedError


def test_concurrent_project_lock_is_rejected(tmp_path: Path) -> None:
    with (
        ProjectLock(tmp_path),
        pytest.raises(ProjectLockedError, match="locked by another process"),
        ProjectLock(tmp_path),
    ):
        pass


def test_stale_project_lock_is_reclaimed(tmp_path: Path) -> None:
    lock_path = tmp_path / ".cutmachine.lock"
    lock_path.write_text(json.dumps({"pid": 999_999_999}), encoding="ascii")

    with ProjectLock(tmp_path):
        owner = json.loads(lock_path.read_text(encoding="ascii"))
        assert owner["pid"] == os.getpid()

    assert not lock_path.exists()
