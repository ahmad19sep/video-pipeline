#!/usr/bin/env python3
"""Generate and verify a CutMachine Phase 9 QC review package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cutmachine.logging import configure_logging  # noqa: E402
from cutmachine.orchestrator import run_internal_stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Workspace project path or slug.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    args = parser.parse_args()
    configure_logging()
    try:
        result = run_internal_stage(args.root.resolve(), args.project, "awaiting_review")
    except RuntimeError as exc:
        print(f"CutMachine review error: {exc}", file=sys.stderr)
        return 1
    print(result.to_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
