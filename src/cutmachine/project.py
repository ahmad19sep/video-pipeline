"""CutMachine project creation and integrity verification."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.config import load_config
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import read_validated_json, write_validated_json_atomic
from cutmachine.state import ProjectState, StateStore

SUPPORTED_MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
MODES = {"fast", "balanced", "energetic", "cinematic"}
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class ProjectError(RuntimeError):
    """Raised when a project cannot be safely created or verified."""


@dataclass(frozen=True)
class ProjectContext:
    repository_root: Path
    project_dir: Path
    project: dict[str, Any]

    @property
    def state_store(self) -> StateStore:
        return StateStore(self.repository_root, self.project_dir)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")[:64].rstrip("-")
    if not slug:
        slug = "video"
    if slug in WINDOWS_RESERVED_NAMES:
        slug = f"video-{slug}"
    return slug


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_project_dir(workspace_root: Path, base_slug: str) -> Path:
    candidate = workspace_root / base_slug
    suffix = 2
    while candidate.exists():
        candidate = workspace_root / f"{base_slug}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _create_project_directories(project_dir: Path) -> None:
    relative_directories = (
        "logs",
        "input",
        "media/frames",
        "audio",
        "transcript",
        "analysis",
        "timeline",
        "planning",
        "assets/broll",
        "assets/sfx",
        "assets/music",
        "assets/images",
        "assets/luts",
        "review",
        "renders",
    )
    for relative in relative_directories:
        (project_dir / relative).mkdir(parents=True, exist_ok=True)


def _copy_source_immutably(source: Path, destination: Path) -> tuple[str, int]:
    before = source.stat()
    if before.st_size <= 0:
        raise ProjectError(f"Source media is empty: {source}")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    digest = hashlib.sha256()
    copied = 0
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                digest.update(chunk)
                output_handle.write(chunk)
                copied += len(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ProjectError("Source media changed while it was being copied; retry the run.")
        if copied != before.st_size:
            raise ProjectError("Source media copy size does not match the original.")
        os.replace(temporary, destination)
    except OSError as exc:
        raise ProjectError(f"Could not copy source media: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return digest.hexdigest(), copied


def create_project(repository_root: Path, source: Path, mode: str) -> ProjectContext:
    repository_root = repository_root.resolve()
    source = source.expanduser().resolve()
    if mode not in MODES:
        raise ProjectError(f"Unknown editing mode: {mode}")
    if not source.is_file():
        raise ProjectError(f"Source media does not exist: {source}")
    extension = source.suffix.lower()
    if extension not in SUPPORTED_MEDIA_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_MEDIA_EXTENSIONS))
        raise ProjectError(
            f"Unsupported source extension {extension!r}; expected one of: {supported}"
        )

    config = load_config(repository_root, style=mode)
    workspace_root = repository_root / cast(str, config["project"]["workspace_root"])
    workspace_root.mkdir(parents=True, exist_ok=True)
    project_dir = _unique_project_dir(workspace_root, slugify(source.stem))
    _create_project_directories(project_dir)
    stored_path = Path("input") / f"raw{extension}"
    digest, size = _copy_source_immutably(source, project_dir / stored_path)

    created_at = datetime.now(UTC).isoformat()
    slug = project_dir.name
    project_id = f"prj_{datetime.now(UTC):%Y%m%d}_{slug}_{uuid.uuid4().hex[:8]}"
    project: dict[str, Any] = {
        "version": 1,
        "projectId": project_id,
        "slug": slug,
        "createdAt": created_at,
        "sourceHash": f"sha256:{digest}",
        "mode": mode,
        "source": {
            "originalName": source.name,
            "storedPath": stored_path.as_posix(),
            "extension": extension,
            "sizeBytes": size,
            "sha256": digest,
        },
        "settings": {
            "language": cast(str, config["transcription"]["language"]),
            "captionLanguage": cast(str, config["captions"]["language"]),
            "networkEnabled": cast(bool, config["network"]["enabled"]),
        },
    }
    write_validated_json_atomic(
        repository_root,
        project_dir / "project.json",
        "project",
        project,
    )
    state_store = StateStore(repository_root, project_dir)
    state_store.save(ProjectState.initialize(project_id))
    return ProjectContext(repository_root, project_dir, project)


def resolve_project_dir(repository_root: Path, raw: Path) -> Path:
    config = load_config(repository_root, style="balanced")
    workspace_root = (repository_root / cast(str, config["project"]["workspace_root"])).resolve()
    candidate = raw.expanduser()
    if not candidate.is_absolute():
        direct = (repository_root / candidate).resolve()
        candidate = direct if direct.is_dir() else (workspace_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.is_relative_to(workspace_root):
        raise ProjectError(f"Project must be inside the workspace root: {workspace_root}")
    if not candidate.is_dir():
        raise ProjectError(f"Project directory does not exist: {candidate}")
    return candidate


def open_project(repository_root: Path, raw: Path) -> ProjectContext:
    repository_root = repository_root.resolve()
    project_dir = resolve_project_dir(repository_root, raw)
    project = read_validated_json(repository_root, project_dir / "project.json", "project")
    return ProjectContext(repository_root, project_dir, project)


def verify_project(context: ProjectContext) -> None:
    source = cast(dict[str, Any], context.project["source"])
    try:
        stored = resolve_inside(context.project_dir, cast(str, source["storedPath"]))
    except UnsafePathError as exc:
        raise ProjectError(f"Project source path is unsafe: {exc}") from exc
    if not stored.is_file():
        raise ProjectError(f"Immutable project source is missing: {stored}")
    size = stored.stat().st_size
    expected_size = cast(int, source["sizeBytes"])
    if size != expected_size:
        raise ProjectError(
            f"Immutable project source size changed: expected {expected_size}, found {size}."
        )
    actual_hash = sha256_file(stored)
    expected_hash = cast(str, source["sha256"])
    if actual_hash != expected_hash:
        raise ProjectError("Immutable project source hash mismatch; refusing to resume.")
    state = context.state_store.load()
    if state.project_id != context.project["projectId"]:
        raise ProjectError("project.json and state.json refer to different project IDs.")
