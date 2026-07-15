import subprocess
import sys
from pathlib import Path


def test_repository_entrypoint_does_not_shadow_package() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from cutmachine.transcription import ModelSettings; print(ModelSettings.__name__)",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ModelSettings"
