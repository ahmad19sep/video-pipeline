#!/usr/bin/env python3
# ruff: noqa: E402,I001
"""Repository-local CutMachine entry point."""

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent / "src"
_PACKAGE_DIRECTORY = _PACKAGE_ROOT / "cutmachine"
sys.path.insert(0, str(_PACKAGE_ROOT))

# Keep the required `python cutmachine.py ...` entry point without preventing
# `import cutmachine.transcription` when the repository root is on sys.path.
if __name__ == "cutmachine":
    __path__ = [str(_PACKAGE_DIRECTORY)]

from cutmachine.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
