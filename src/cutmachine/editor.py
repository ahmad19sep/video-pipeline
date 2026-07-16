"""Schema-bound domain helpers for the optional loopback editor."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.assets import AssetError, index_local_assets
from cutmachine.config import load_config
from cutmachine.media import MediaError, probe_media
from cutmachine.paths import UnsafePathError, resolve_inside, validate_relative_path
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext, sha256_file, slugify
from cutmachine.schemas import validate_document


class EditorError(RuntimeError):
    """Raised when an interactive editor request crosses a safety boundary."""


CAPTION_PRESETS = (
    "roman-word-highlight",
    "clean-two-line",
    "hook",
    "definition",
    "question",
    "viral-punch",
    "boxed-keyword",
    "urdu-script",
)
BROLL_MODES = ("auto", "manual", "graphics-only", "cowork")
VISUAL_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"}
_EDITOR_SETTINGS_PATH = Path("planning/editor-settings.json")
_ASSET_PINS_PATH = Path("planning/asset-pins.json")
_COWORK_REQUEST_PATH = Path("planning/cowork-editor-request.json")
_COWORK_REVISION_PATH = Path("planning/cowork-editor-revision.json")


@dataclass(frozen=True)
class EditorMutation:
    settings: dict[str, Any]
    pins: dict[str, Any]
    revision: dict[str, Any] | None
    invalidate_from: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _plan(context: ProjectContext) -> dict[str, Any]:
    try:
        return read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "edit-plan.json",
            "edit-plan",
        )
    except PersistenceError as exc:
        raise EditorError(f"Editor requires a valid edit plan: {exc}") from exc


def _auto_queries(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "sceneId": scene["id"],
            "query": cast(dict[str, Any], scene["broll"])["query"],
        }
        for scene in cast(list[dict[str, Any]], plan["scenes"])
    ]


def current_editor_settings(context: ProjectContext) -> dict[str, Any]:
    plan = _plan(context)
    path = context.project_dir / _EDITOR_SETTINGS_PATH
    if path.is_file():
        try:
            settings = read_validated_json(context.repository_root, path, "editor-settings")
        except PersistenceError as exc:
            raise EditorError(f"Saved editor settings are invalid: {exc}") from exc
        if settings["projectId"] != context.project["projectId"]:
            raise EditorError("Saved editor settings belong to another project.")
        return settings
    return {
        "version": 1,
        "projectId": context.project["projectId"],
        "updatedAt": _now(),
        "captionsEnabled": plan["captions"].get("enabled", True),
        "captionPreset": plan["style"]["captionPreset"],
        "brollMode": "auto",
        "autoQueries": _auto_queries(plan),
        "pins": [],
    }


def local_visual_assets(context: ProjectContext) -> list[dict[str, Any]]:
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    root = context.repository_root / cast(str, config["project"]["assets_root"])
    try:
        index = index_local_assets(context.repository_root, root)
    except AssetError as exc:
        raise EditorError(f"Could not refresh the owned asset library: {exc}") from exc
    write_validated_json_atomic(
        context.repository_root,
        context.project_dir / "planning" / "editor-asset-index.json",
        "asset-index",
        index,
    )
    return [
        asset
        for asset in cast(list[dict[str, Any]], index["assets"])
        if asset["type"] in {"video", "image"} and cast(str, asset["license"]).casefold() == "owned"
    ]


def _request_value(payload: dict[str, Any], key: str, expected: type[Any]) -> Any:
    value = payload.get(key)
    if not isinstance(value, expected):
        raise EditorError(f"Editor field {key!r} has an invalid type.")
    return value


def prepare_editor_mutation(context: ProjectContext, payload: object) -> EditorMutation:
    if not isinstance(payload, dict):
        raise EditorError("Editor settings request must be a JSON object.")
    typed = cast(dict[str, Any], payload)
    expected_keys = {"captionsEnabled", "captionPreset", "brollMode", "pins"}
    unknown = set(typed) - expected_keys
    if unknown:
        raise EditorError(f"Editor settings contain unknown fields: {', '.join(sorted(unknown))}")
    captions_enabled = cast(bool, _request_value(typed, "captionsEnabled", bool))
    caption_preset = cast(str, _request_value(typed, "captionPreset", str))
    broll_mode = cast(str, _request_value(typed, "brollMode", str))
    raw_pins = cast(list[Any], _request_value(typed, "pins", list))
    if caption_preset not in CAPTION_PRESETS:
        raise EditorError("Editor caption preset is not allowlisted.")
    if broll_mode not in BROLL_MODES:
        raise EditorError("Editor B-roll mode is not allowlisted.")
    if broll_mode != "manual" and raw_pins:
        raise EditorError("Owned B-roll pins are allowed only in manual mode.")

    plan = _plan(context)
    if caption_preset == "urdu-script" and plan["captions"]["language"] != "urdu-script":
        raise EditorError("Urdu-script style requires an Urdu-script caption project.")
    previous = current_editor_settings(context)
    scenes = {cast(str, scene["id"]): scene for scene in cast(list[dict[str, Any]], plan["scenes"])}
    auto_queries = cast(list[dict[str, Any]], previous["autoQueries"])
    if {item["sceneId"] for item in auto_queries} != set(scenes):
        raise EditorError("Saved automatic B-roll queries are stale for this scene plan.")

    pins_document = {
        "version": 1,
        "projectId": context.project["projectId"],
        "pins": raw_pins if broll_mode == "manual" else [],
    }
    pin_errors = validate_document(context.repository_root, "asset-pins", pins_document)
    if pin_errors:
        raise EditorError("Invalid owned B-roll pins:\n" + "\n".join(pin_errors))
    pins = cast(list[dict[str, Any]], pins_document["pins"])
    pin_scenes = [cast(str, item["sceneId"]) for item in pins]
    if len(pin_scenes) != len(set(pin_scenes)):
        raise EditorError("Only one owned B-roll asset may be pinned to each scene.")
    assets = (
        {cast(str, asset["id"]): asset for asset in local_visual_assets(context)} if pins else {}
    )
    for pin in pins:
        if pin["sceneId"] not in scenes:
            raise EditorError("Owned B-roll pin references an unknown scene.")
        if pin["localAssetId"] not in assets:
            raise EditorError("Owned B-roll pin references an unavailable owned asset.")

    auto_by_scene = {
        cast(str, item["sceneId"]): cast(str | None, item["query"]) for item in auto_queries
    }
    pins_by_scene = {
        cast(str, item["sceneId"]): assets[cast(str, item["localAssetId"])] for item in pins
    }
    operations: list[dict[str, Any]] = []
    if bool(plan["captions"].get("enabled", True)) != captions_enabled:
        operations.append({"op": "set-captions-enabled", "enabled": captions_enabled})
    if plan["style"]["captionPreset"] != caption_preset:
        operations.append({"op": "set-caption-preset", "captionPreset": caption_preset})
    for scene_id, scene in scenes.items():
        current_query = cast(str | None, cast(dict[str, Any], scene["broll"])["query"])
        if broll_mode == "graphics-only":
            target_query: str | None = None
        elif broll_mode == "cowork":
            target_query = current_query
        else:
            target_query = auto_by_scene[scene_id]
        if scene_id in pins_by_scene and target_query is None:
            tags = cast(list[str], pins_by_scene[scene_id]["tags"])
            candidate = " ".join(tags)[:80].strip()
            target_query = candidate if re.search(r"[A-Za-z]", candidate) else "creator owned broll"
        if target_query != current_query:
            operations.append(
                {"op": "set-scene-broll-query", "sceneId": scene_id, "query": target_query}
            )

    settings = {
        "version": 1,
        "projectId": context.project["projectId"],
        "updatedAt": _now(),
        "captionsEnabled": captions_enabled,
        "captionPreset": caption_preset,
        "brollMode": broll_mode,
        "autoQueries": auto_queries,
        "pins": pins,
    }
    settings_errors = validate_document(context.repository_root, "editor-settings", settings)
    if settings_errors:
        raise EditorError("Invalid editor settings:\n" + "\n".join(settings_errors))
    previous_pin_path = context.project_dir / _ASSET_PINS_PATH
    previous_pins: dict[str, Any] | None = None
    if previous_pin_path.is_file():
        try:
            previous_pins = read_validated_json(
                context.repository_root, previous_pin_path, "asset-pins"
            )
        except PersistenceError as exc:
            raise EditorError(f"Existing owned B-roll pins are invalid: {exc}") from exc
    pins_changed = previous_pins != pins_document
    revision = (
        {
            "version": 1,
            "projectId": context.project["projectId"],
            "operations": operations,
        }
        if operations
        else None
    )
    invalidate_from = "plan_ready" if operations else ("assets_ready" if pins_changed else None)
    return EditorMutation(settings, pins_document, revision, invalidate_from)


def write_editor_documents(context: ProjectContext, mutation: EditorMutation) -> list[str]:
    settings_path = context.project_dir / _EDITOR_SETTINGS_PATH
    pins_path = context.project_dir / _ASSET_PINS_PATH
    write_validated_json_atomic(
        context.repository_root, settings_path, "editor-settings", mutation.settings
    )
    write_validated_json_atomic(context.repository_root, pins_path, "asset-pins", mutation.pins)
    return [_EDITOR_SETTINGS_PATH.as_posix(), _ASSET_PINS_PATH.as_posix()]


def write_cowork_request(context: ProjectContext, instruction: object) -> list[str]:
    if not isinstance(instruction, str):
        raise EditorError("Cowork instruction must be text.")
    normalized = " ".join(instruction.strip().split())
    if not normalized or len(normalized) > 1000:
        raise EditorError("Cowork instruction must contain 1 to 1000 characters.")
    inputs = [
        "planning/cowork-input.json",
        "planning/edit-plan.json",
        "planning/component-catalog.json",
        "transcript/transcript.remapped.json",
        "planning/asset-index.json",
    ]
    for relative in inputs:
        if not (context.project_dir / relative).is_file():
            raise EditorError(f"Cowork input is missing: {relative}")
    document = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "instruction": normalized,
        "inputPaths": inputs,
        "outputPath": _COWORK_REVISION_PATH.as_posix(),
        "constraints": {
            "jsonOnly": True,
            "typedRevisionOnly": True,
            "preserveTranscript": True,
            "allowExecutableContent": False,
        },
    }
    path = context.project_dir / _COWORK_REQUEST_PATH
    write_validated_json_atomic(context.repository_root, path, "cowork-editor-request", document)
    return [_COWORK_REQUEST_PATH.as_posix()]


def cowork_revision_relative() -> str:
    return _COWORK_REVISION_PATH.as_posix()


def load_editor_request(context: ProjectContext, relative: str) -> dict[str, Any]:
    try:
        validated = validate_relative_path(relative).as_posix()
        path = resolve_inside(context.project_dir, validated)
    except UnsafePathError as exc:
        raise EditorError(f"Editor settings path is unsafe: {exc}") from exc
    if not path.is_file():
        raise EditorError(f"Editor settings file is missing: {validated}")
    if path.stat().st_size > 1_000_000:
        raise EditorError("Editor settings file exceeds the 1 MB limit.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EditorError(f"Editor settings file is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EditorError("Editor settings root must be a JSON object.")
    return cast(dict[str, Any], value)


def stage_editor_upload(repository_root: Path, source: Path) -> Path:
    if not source.is_file():
        raise EditorError(f"Owned B-roll source file does not exist: {source}")
    upload_root = repository_root / ".cache" / "editor-uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    staged = upload_root / f"{os.urandom(8).hex()}{source.suffix.casefold()}"
    _atomic_copy(source, staged)
    return staged


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.urandom(8).hex()}.tmp")
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise EditorError(f"Could not store owned B-roll: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_sidecar(path: Path, tags: list[str]) -> None:
    value = {
        "tags": tags,
        "license": "owned",
        "creator": None,
        "attributionRequired": False,
        "colorSpace": None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise EditorError(f"Could not store owned B-roll metadata: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def register_owned_broll(
    context: ProjectContext,
    upload: Path,
    original_name: str,
    raw_tags: str,
) -> dict[str, Any]:
    upload_root = (context.repository_root / ".cache" / "editor-uploads").resolve()
    source = upload.resolve()
    if not source.is_relative_to(upload_root) or not source.is_file():
        raise EditorError("Owned B-roll upload is outside the controlled upload directory.")
    extension = Path(original_name).suffix.casefold()
    if extension not in VISUAL_EXTENSIONS:
        raise EditorError("Owned B-roll has an unsupported visual-media extension.")
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    maximum = int(config["assets"]["max_download_mb"]) * 1024 * 1024
    size = source.stat().st_size
    if size <= 0 or size > maximum:
        raise EditorError("Owned B-roll is empty or exceeds the configured upload limit.")
    try:
        probe = probe_media(
            source,
            log_path=context.repository_root / ".cache" / "assets" / "editor-probe.jsonl",
        )
    except MediaError as exc:
        raise EditorError(f"Owned B-roll is not decodable media: {exc}") from exc
    streams = probe.get("streams")
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
    ):
        raise EditorError("Owned B-roll does not contain a visual stream.")
    tags = list(
        dict.fromkeys(
            token.casefold() for token in re.findall(r"[A-Za-z0-9]+", raw_tags) if token.strip()
        )
    )[:50]
    if not tags:
        tags = re.findall(r"[A-Za-z0-9]+", Path(original_name).stem.casefold())[:50]
    if not tags:
        tags = ["creator", "owned", "broll"]
    digest = sha256_file(source)
    assets_root = context.repository_root / cast(str, config["project"]["assets_root"])
    name = slugify(Path(original_name).stem)[:40]
    destination = assets_root / "broll" / "user-uploads" / f"{digest[:12]}-{name}{extension}"
    if not destination.is_file():
        _atomic_copy(source, destination)
    elif sha256_file(destination) != digest:
        raise EditorError("Owned B-roll destination hash collision detected.")
    _atomic_sidecar(destination.with_suffix(destination.suffix + ".asset.json"), tags)
    assets = local_visual_assets(context)
    local_id = f"local_{digest[:16]}"
    selected = next((item for item in assets if item["id"] == local_id), None)
    if selected is None:
        raise EditorError("Owned B-roll was stored but failed local indexing.")
    return selected
