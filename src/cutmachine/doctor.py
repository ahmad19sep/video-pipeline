"""Environment diagnostics for the local CutMachine pipeline."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Status = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    summary: str
    remediation: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    version: int
    platform: str
    root: str
    checks: tuple[CheckResult, ...]

    @property
    def has_failures(self) -> bool:
        return any(check.status == "fail" for check in self.checks)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["ok"] = not self.has_failures
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        icons: dict[Status, str] = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
        lines = ["CutMachine environment doctor", f"Platform: {self.platform}"]
        for check in self.checks:
            lines.append(f"[{icons[check.status]}] {check.name}: {check.summary}")
            if check.remediation:
                lines.append(f"       Fix: {check.remediation}")
        lines.append("Result: BLOCKED" if self.has_failures else "Result: READY")
        return "\n".join(lines)


def _run_version(command: str, *arguments: str) -> tuple[bool, str]:
    executable = shutil.which(command)
    if executable is None:
        return False, "not found on PATH"
    try:
        result = subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not execute ({exc})"
    output = (result.stdout or result.stderr).splitlines()
    summary = output[0].strip() if output else f"exit code {result.returncode}"
    return result.returncode == 0, summary


def check_python() -> CheckResult:
    version = sys.version_info
    current = f"{version.major}.{version.minor}.{version.micro}"
    if version < (3, 11):
        return CheckResult("Python", "fail", current, "Install Python 3.11 or newer.")
    return CheckResult("Python", "pass", current)


def check_command(
    name: str,
    arguments: tuple[str, ...],
    *,
    core: bool,
    remediation: str,
) -> CheckResult:
    ok, summary = _run_version(name, *arguments)
    if ok:
        return CheckResult(name, "pass", summary)
    return CheckResult(name, "fail" if core else "warn", summary, remediation)


def check_node() -> CheckResult:
    ok, summary = _run_version("node", "--version")
    if not ok:
        return CheckResult("Node.js", "fail", summary, "Install Node.js 20 or newer.")
    try:
        major = int(summary.lstrip("v").split(".", maxsplit=1)[0])
    except ValueError:
        return CheckResult("Node.js", "fail", summary, "Install a supported Node.js 20+ release.")
    if major < 20:
        return CheckResult("Node.js", "fail", summary, "Upgrade to Node.js 20 or newer.")
    return CheckResult("Node.js", "pass", summary)


def check_writable(root: Path) -> CheckResult:
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".cutmachine-doctor-", delete=True):
            pass
    except OSError as exc:
        return CheckResult(
            "Writable workspace",
            "fail",
            str(exc),
            "Grant the current user write access to the repository and workspace.",
        )
    return CheckResult("Writable workspace", "pass", str(root))


def check_disk(root: Path, minimum_gb: float = 5.0) -> CheckResult:
    free_gb = shutil.disk_usage(root).free / (1024**3)
    if free_gb < minimum_gb:
        return CheckResult(
            "Disk space",
            "fail",
            f"{free_gb:.1f} GiB free",
            f"Free at least {minimum_gb:.0f} GiB before processing media.",
        )
    return CheckResult("Disk space", "pass", f"{free_gb:.1f} GiB free")


def check_virtual_environment() -> CheckResult:
    active = sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(os.getenv("VIRTUAL_ENV"))
    if active:
        return CheckResult("Python virtual environment", "pass", sys.prefix)
    return CheckResult(
        "Python virtual environment",
        "warn",
        "not active",
        "Create one with `python -m venv .venv` and activate it before installing dependencies.",
    )


def check_python_module(module: str, display_name: str) -> CheckResult:
    if importlib.util.find_spec(module) is not None:
        return CheckResult(display_name, "pass", "importable")
    return CheckResult(
        display_name,
        "warn",
        "not installed",
        f"Install the optional `{module.replace('_', '-')}` package before its pipeline phase.",
    )


def check_faster_whisper() -> CheckResult:
    try:
        sys.modules.setdefault("av", types.ModuleType("av"))
        module = importlib.import_module("faster_whisper")
    except Exception as exc:
        return CheckResult(
            "Faster-Whisper",
            "warn",
            f"import failed ({exc})",
            "Install or repair Faster-Whisper before running Phase 2 transcription.",
        )
    version = str(getattr(module, "__version__", "unknown version"))
    return CheckResult("Faster-Whisper", "pass", version)


def check_cuda() -> CheckResult:
    ok, summary = _run_version(
        "nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"
    )
    if ok:
        return CheckResult("CUDA GPU", "pass", summary)
    return CheckResult(
        "CUDA GPU", "warn", "not detected", "CPU transcription fallback will be used."
    )


def check_remotion(root: Path) -> CheckResult:
    package = root / "remotion" / "package.json"
    modules = root / "remotion" / "node_modules"
    if not package.is_file():
        return CheckResult("Remotion scaffold", "warn", "package.json missing")
    if not modules.is_dir():
        return CheckResult(
            "Remotion dependencies",
            "warn",
            "not installed",
            "Run `npm install` in the remotion directory.",
        )
    return CheckResult("Remotion dependencies", "pass", "installed")


def check_optional_keys() -> CheckResult:
    names = ("PEXELS_API_KEY", "PIXABAY_API_KEY", "FREESOUND_API_KEY")
    configured = [name for name in names if os.getenv(name)]
    if configured:
        return CheckResult("Optional API adapters", "pass", f"{len(configured)} configured")
    return CheckResult(
        "Optional API adapters",
        "warn",
        "none configured (local fallbacks remain available)",
    )


def run_doctor(root: Path) -> DoctorReport:
    checks = (
        check_python(),
        check_node(),
        check_command(
            "ffmpeg",
            ("-version",),
            core=True,
            remediation="Install FFmpeg and add its bin directory to PATH.",
        ),
        check_command(
            "ffprobe",
            ("-version",),
            core=True,
            remediation="Install FFmpeg (which includes FFprobe) and add it to PATH.",
        ),
        check_command(
            "git",
            ("--version",),
            core=False,
            remediation="Install Git for source-control workflows.",
        ),
        check_writable(root),
        check_disk(root),
        check_virtual_environment(),
        check_faster_whisper(),
        check_cuda(),
        check_remotion(root),
        check_optional_keys(),
    )
    return DoctorReport(version=1, platform=platform.platform(), root=str(root), checks=checks)
