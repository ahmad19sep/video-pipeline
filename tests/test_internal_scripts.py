import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "script",
    [
        "ingest.py",
        "transcribe.py",
        "normalize_transcript.py",
        "analyze_timeline.py",
        "plan_edit.py",
    ],
)
def test_internal_script_help(script: str) -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--help"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
