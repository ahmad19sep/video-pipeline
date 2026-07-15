"""Local-first asset indexing, ranking, caching, and plan resolution."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from cutmachine.config import load_config
from cutmachine.media import MediaError, probe_media, run_media_command
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_json,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.planning import PlanningError, validate_plan_outputs
from cutmachine.project import ProjectContext, sha256_file
from cutmachine.schemas import validate_document


class AssetError(RuntimeError):
    """Raised when an asset boundary, cache entry, or resolution is unsafe."""


SearchTransport = Callable[[str, dict[str, str], int], dict[str, Any]]
DownloadTransport = Callable[[str, dict[str, str], int, int], tuple[bytes, str]]

_MEDIA_TYPES = {
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".webm": "video",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
    ".flac": "audio",
    ".cube": "lut",
    ".ttf": "font",
    ".otf": "font",
}
_LICENSES = {"owned", "cc0", "cc-by", "pexels license"}
_SIDECAR_KEYS = {"tags", "license", "creator", "attributionRequired", "colorSpace"}
_TIER_ORDER = {"local": 0, "cache": 1, "provider": 2}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


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
        raise AssetError(f"Could not copy asset atomically: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _orientation(width: int | None, height: int | None, asset_type: str) -> str:
    if asset_type == "audio":
        return "audio"
    if width is None or height is None:
        return "unknown"
    if abs(width - height) / max(width, height) <= 0.05:
        return "square"
    return "landscape" if width > height else "portrait"


def _first_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any] | None:
    streams = probe.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
                return stream
    return None


def _optional_float(value: object) -> float | None:
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _media_metadata(path: Path, asset_type: str, log_path: Path) -> tuple[Any, ...]:
    if asset_type in {"lut", "font"}:
        return None, None, None, _orientation(None, None, asset_type)
    try:
        probe = probe_media(path, log_path=log_path)
    except MediaError as exc:
        raise AssetError(f"Could not inspect local asset {path.name}: {exc}") from exc
    video = _first_stream(probe, "video")
    audio = _first_stream(probe, "audio")
    if asset_type in {"video", "image"} and video is None:
        raise AssetError(f"Asset extension indicates {asset_type}, but no video stream exists.")
    if asset_type == "audio" and audio is None:
        raise AssetError("Asset extension indicates audio, but no audio stream exists.")
    width = int(video["width"]) if video is not None and video.get("width") else None
    height = int(video["height"]) if video is not None and video.get("height") else None
    format_info = probe.get("format")
    duration = None
    if asset_type in {"video", "audio"} and isinstance(format_info, dict):
        duration = _optional_float(format_info.get("duration"))
    return duration, width, height, _orientation(width, height, asset_type)


def _default_tags(path: Path) -> list[str]:
    values = re.findall(r"[A-Za-z0-9]+", path.stem.casefold())
    return list(dict.fromkeys(values))[:50] or ["untagged"]


def _asset_preview(
    repository_root: Path,
    source: Path,
    asset_type: str,
    digest: str,
    log_path: Path,
) -> str | None:
    if asset_type not in {"video", "image", "audio"}:
        return None
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise AssetError("FFmpeg is required to index asset previews.")
    extension = ".png" if asset_type == "audio" else ".jpg"
    destination = repository_root / ".cache" / "assets" / "previews" / f"{digest}{extension}"
    if destination.is_file() and destination.stat().st_size > 0:
        return _relative(repository_root, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.stem}.{os.urandom(8).hex()}.tmp{destination.suffix}"
    )
    if asset_type == "audio":
        media_arguments = [
            "-i",
            str(source),
            "-filter_complex",
            "showwavespic=s=640x120:colors=0x67e8f9",
            "-frames:v",
            "1",
        ]
    else:
        media_arguments = [
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-2",
            "-q:v",
            "3",
        ]
    try:
        run_media_command(
            [
                executable,
                "-hide_banner",
                "-nostdin",
                "-y",
                *media_arguments,
                str(temporary),
            ],
            log_path=log_path,
            timeout_seconds=120,
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise AssetError("FFmpeg did not generate an asset preview.")
        os.replace(temporary, destination)
    except MediaError as exc:
        raise AssetError(f"Could not create asset preview: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return _relative(repository_root, destination)


def _sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".asset.json")
    if not sidecar.is_file():
        return {
            "tags": _default_tags(path),
            "license": "owned",
            "creator": None,
            "attributionRequired": False,
            "colorSpace": None,
        }
    try:
        value = read_json(sidecar)
    except PersistenceError as exc:
        raise AssetError(f"Invalid asset sidecar {sidecar.name}: {exc}") from exc
    unknown = set(value) - _SIDECAR_KEYS
    if unknown:
        raise AssetError(f"Asset sidecar has unknown fields: {', '.join(sorted(unknown))}")
    tags = value.get("tags")
    license_name = value.get("license")
    creator = value.get("creator")
    attribution = value.get("attributionRequired")
    color_space = value.get("colorSpace")
    if (
        not isinstance(tags, list)
        or not tags
        or len(tags) > 50
        or any(not isinstance(item, str) or not item.strip() for item in tags)
        or not isinstance(license_name, str)
        or not license_name.strip()
        or (creator is not None and not isinstance(creator, str))
        or not isinstance(attribution, bool)
        or (color_space is not None and not isinstance(color_space, str))
    ):
        raise AssetError(f"Asset sidecar has invalid metadata: {sidecar.name}")
    return {
        "tags": [cast(str, item).strip().casefold() for item in tags],
        "license": license_name.strip(),
        "creator": creator,
        "attributionRequired": attribution,
        "colorSpace": color_space,
    }


def _usage_counts(repository_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    workspace = repository_root / "workspace"
    if not workspace.is_dir():
        return counts
    for manifest_path in workspace.glob("*/assets/manifest.json"):
        try:
            manifest = read_validated_json(repository_root, manifest_path, "asset-manifest")
        except PersistenceError:
            continue
        for asset in cast(list[dict[str, Any]], manifest["assets"]):
            provider_id = cast(str, asset["providerId"])
            counts[provider_id] = counts.get(provider_id, 0) + 1
    return counts


def index_local_assets(repository_root: Path, assets_root: Path) -> dict[str, Any]:
    assets_root = assets_root.resolve()
    if not assets_root.is_dir():
        raise AssetError(f"Local asset library does not exist: {assets_root}")
    usage = _usage_counts(repository_root)
    entries: list[dict[str, Any]] = []
    log_path = repository_root / ".cache" / "assets" / "index-probe.jsonl"
    for path in sorted(assets_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.name.startswith(".") or path.name.endswith(".asset.json"):
            continue
        asset_type = _MEDIA_TYPES.get(path.suffix.casefold())
        if asset_type is None or "references" in path.relative_to(assets_root).parts:
            continue
        digest = sha256_file(path)
        metadata = _sidecar(path)
        duration, width, height, orientation = _media_metadata(path, asset_type, log_path)
        provider_id = _relative(assets_root, path)
        preview_path = _asset_preview(repository_root, path, asset_type, digest, log_path)
        entries.append(
            {
                "id": f"local_{digest[:16]}",
                "path": provider_id,
                "type": asset_type,
                "sha256": digest,
                "tags": metadata["tags"],
                "license": metadata["license"],
                "creator": metadata["creator"],
                "attributionRequired": metadata["attributionRequired"],
                "colorSpace": metadata["colorSpace"],
                "duration": duration,
                "width": width,
                "height": height,
                "orientation": orientation,
                "usageCount": usage.get(provider_id, 0),
                "previewPath": preview_path,
            }
        )
    document = {"version": 1, "generatedAt": _now(), "assets": entries}
    errors = validate_document(repository_root, "asset-index", document)
    if errors:
        raise AssetError("Generated asset index is invalid:\n" + "\n".join(errors))
    return document


def _query(value: object) -> str:
    if not isinstance(value, str):
        raise AssetError("Asset query must be a short English visual phrase.")
    normalized = " ".join(value.strip().split())
    if (
        not normalized
        or len(normalized) > 80
        or any(ord(character) < 32 or ord(character) > 126 for character in normalized)
        or not re.search(r"[A-Za-z]", normalized)
    ):
        raise AssetError("Asset query must be a short English visual phrase.")
    return normalized


def build_asset_requests(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    targets: dict[str, Any] = {}
    video = cast(dict[str, Any], plan["video"])
    orientation = "portrait" if int(video["height"]) > int(video["width"]) else "landscape"
    for scene_index, scene in enumerate(cast(list[dict[str, Any]], plan["scenes"])):
        broll = cast(dict[str, Any], scene["broll"])
        if broll.get("query") and broll.get("assetId") is None:
            request_id = f"request_{len(requests) + 1:06d}"
            requests.append(
                {
                    "id": request_id,
                    "kind": "broll",
                    "query": _query(broll["query"]),
                    "sceneId": scene["id"],
                    "orientation": orientation,
                    "targetDuration": float(scene["end"]) - float(scene["start"]),
                    "optional": True,
                }
            )
            targets[request_id] = ("broll", scene_index, None)
        for sfx_index, sfx in enumerate(cast(list[dict[str, Any]], scene["sfx"])):
            if sfx.get("assetId") is None:
                request_id = f"request_{len(requests) + 1:06d}"
                requests.append(
                    {
                        "id": request_id,
                        "kind": "sfx",
                        "query": _query(sfx.get("query")),
                        "sceneId": scene["id"],
                        "orientation": "any",
                        "targetDuration": None,
                        "optional": True,
                    }
                )
                targets[request_id] = ("sfx", scene_index, sfx_index)
    audio = cast(dict[str, Any], plan["globalAudio"])
    if audio.get("musicQuery") and audio.get("musicAssetId") is None:
        request_id = f"request_{len(requests) + 1:06d}"
        requests.append(
            {
                "id": request_id,
                "kind": "music",
                "query": _query(audio["musicQuery"]),
                "sceneId": None,
                "orientation": "any",
                "targetDuration": float(video["durationInSeconds"]),
                "optional": True,
            }
        )
        targets[request_id] = ("music", None, None)
    return (
        {
            "version": 1,
            "projectId": plan["projectId"],
            "createdAt": _now(),
            "requests": requests,
        },
        targets,
    )


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _candidate_for_local(request: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"candidate_{asset['id']}",
        "requestId": request["id"],
        "tier": "local",
        "provider": "local",
        "providerId": asset["path"],
        "type": asset["type"],
        "localPath": asset["path"],
        "downloadUrl": None,
        "sourcePage": None,
        "creator": asset["creator"],
        "license": asset["license"],
        "attributionRequired": asset["attributionRequired"],
        "tags": asset["tags"],
        "duration": asset["duration"],
        "width": asset["width"],
        "height": asset["height"],
        "orientation": asset["orientation"],
        "watermark": False,
        "usageCount": asset["usageCount"],
    }


def _kind_matches(kind: str, asset_type: str) -> bool:
    return (kind == "broll" and asset_type in {"video", "image"}) or (
        kind in {"music", "sfx"} and asset_type == "audio"
    )


def local_candidates(requests: dict[str, Any], index: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for request in cast(list[dict[str, Any]], requests["requests"]):
        for asset in cast(list[dict[str, Any]], index["assets"]):
            if _kind_matches(cast(str, request["kind"]), cast(str, asset["type"])):
                values.append(_candidate_for_local(request, asset))
    return values


def _cache_path(root: Path) -> Path:
    return root / ".cache" / "assets" / "cache.json"


def _empty_cache() -> dict[str, Any]:
    return {"version": 1, "updatedAt": _now(), "entries": []}


def load_asset_cache(repository_root: Path) -> dict[str, Any]:
    path = _cache_path(repository_root)
    if not path.is_file():
        return _empty_cache()
    try:
        cache = read_validated_json(repository_root, path, "asset-cache")
    except PersistenceError:
        return _empty_cache()
    valid: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for entry in cast(list[dict[str, Any]], cache["entries"]):
        try:
            expires = datetime.fromisoformat(cast(str, entry["expiresAt"]))
            object_path = resolve_inside(repository_root, cast(str, entry["objectPath"]))
        except (ValueError, UnsafePathError):
            continue
        if expires > now and object_path.is_file() and sha256_file(object_path) == entry["sha256"]:
            valid.append(entry)
    cache["entries"] = valid
    return cache


def _request_key(request: dict[str, Any]) -> str:
    payload = "|".join(
        (
            cast(str, request["kind"]),
            cast(str, request["query"]).casefold(),
            cast(str, request["orientation"]),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_candidates(requests: dict[str, Any], cache: dict[str, Any]) -> list[dict[str, Any]]:
    by_key = {
        cast(str, entry["key"]): entry for entry in cast(list[dict[str, Any]], cache["entries"])
    }
    values: list[dict[str, Any]] = []
    for request in cast(list[dict[str, Any]], requests["requests"]):
        entry = by_key.get(_request_key(request))
        if entry is None or not _kind_matches(cast(str, request["kind"]), cast(str, entry["type"])):
            continue
        values.append(
            {
                "id": f"candidate_cache_{entry['sha256'][:16]}",
                "requestId": request["id"],
                "tier": "cache",
                "provider": entry["provider"],
                "providerId": entry["providerId"],
                "type": entry["type"],
                "localPath": entry["objectPath"],
                "downloadUrl": None,
                "sourcePage": entry["sourcePage"],
                "creator": entry["creator"],
                "license": entry["license"],
                "attributionRequired": entry["attributionRequired"],
                "tags": entry["tags"],
                "duration": entry["duration"],
                "width": entry["width"],
                "height": entry["height"],
                "orientation": entry["orientation"],
                "watermark": False,
                "usageCount": 0,
            }
        )
    return values


def _default_search(url: str, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            payload = response.read(2 * 1024 * 1024 + 1)
    except OSError as exc:
        raise AssetError(f"Provider search failed: {exc}") from exc
    if content_type != "application/json" or len(payload) > 2 * 1024 * 1024:
        raise AssetError("Provider search returned an invalid or oversized response.")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AssetError("Provider search returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise AssetError("Provider search JSON root must be an object.")
    return value


def _https(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) > 2000:
        raise AssetError(f"Pexels candidate has invalid {label}.")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise AssetError(f"Pexels candidate has unsafe {label}.")
    return value


class PexelsAdapter:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        *,
        timeout_seconds: int,
        max_candidates: int,
        transport: SearchTransport = _default_search,
    ) -> None:
        if not api_key.strip():
            raise AssetError("Pexels is enabled but its API key is unavailable.")
        self.api_key = api_key
        self.endpoint = _https(endpoint, "endpoint")
        self.timeout_seconds = timeout_seconds
        self.max_candidates = max_candidates
        self.transport = transport

    def search(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        if request["kind"] != "broll":
            return []
        parameters = {
            "query": _query(request["query"]),
            "per_page": str(self.max_candidates),
        }
        if request["orientation"] != "any":
            parameters["orientation"] = cast(str, request["orientation"])
        url = f"{self.endpoint}?{urllib.parse.urlencode(parameters)}"
        response = self.transport(url, {"Authorization": self.api_key}, self.timeout_seconds)
        videos = response.get("videos")
        if not isinstance(videos, list) or len(videos) > 80:
            raise AssetError("Pexels response has an invalid videos collection.")
        candidates: list[dict[str, Any]] = []
        for video in videos[: self.max_candidates]:
            if not isinstance(video, dict):
                raise AssetError("Pexels response contains a non-object video.")
            provider_id = video.get("id")
            files = video.get("video_files")
            if not isinstance(provider_id, int | str) or not isinstance(files, list):
                raise AssetError("Pexels video is missing its ID or files.")
            usable: list[dict[str, Any]] = []
            for item in files:
                if (
                    isinstance(item, dict)
                    and item.get("file_type") == "video/mp4"
                    and isinstance(item.get("width"), int)
                    and isinstance(item.get("height"), int)
                    and isinstance(item.get("link"), str)
                ):
                    usable.append(item)
            if not usable:
                continue
            chosen = max(
                usable,
                key=lambda item: (int(item["width"]) * int(item["height"]), str(item.get("id"))),
            )
            user = video.get("user")
            creator = user.get("name") if isinstance(user, dict) else None
            width, height = int(chosen["width"]), int(chosen["height"])
            candidates.append(
                {
                    "id": f"candidate_pexels_{provider_id}_{chosen.get('id', 0)}",
                    "requestId": request["id"],
                    "tier": "provider",
                    "provider": "pexels",
                    "providerId": str(provider_id),
                    "type": "video",
                    "localPath": None,
                    "downloadUrl": _https(chosen["link"], "download URL"),
                    "sourcePage": _https(video.get("url"), "source page"),
                    "creator": creator if isinstance(creator, str) else None,
                    "license": "Pexels License",
                    "attributionRequired": True,
                    "tags": sorted(_tokens(cast(str, request["query"]))),
                    "duration": _optional_float(video.get("duration")),
                    "width": width,
                    "height": height,
                    "orientation": _orientation(width, height, "video"),
                    "watermark": False,
                    "usageCount": 0,
                }
            )
        return candidates


def _score(request: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, dict[str, float]]:
    query_tokens = _tokens(cast(str, request["query"]))
    candidate_tokens = set(cast(list[str], candidate["tags"])) | _tokens(
        cast(str, candidate["providerId"])
    )
    query_score = len(query_tokens & candidate_tokens) / len(query_tokens) if query_tokens else 0.0
    wanted = request["orientation"]
    actual = candidate["orientation"]
    orientation_score = (
        1.0 if wanted == "any" or wanted == actual else (0.5 if actual == "unknown" else 0.0)
    )
    target = request["targetDuration"]
    duration = candidate["duration"]
    duration_score = 1.0
    if target is not None and duration is not None:
        duration_score = min(float(target), float(duration)) / max(float(target), float(duration))
    width, height = candidate["width"], candidate["height"]
    resolution_score = (
        min(1.0, int(width) * int(height) / (1280 * 720))
        if width is not None and height is not None
        else (1.0 if candidate["type"] == "audio" else 0.4)
    )
    quality_score = 0.0 if candidate["watermark"] else 1.0
    license_score = 1.0 if cast(str, candidate["license"]).casefold() in _LICENSES else 0.0
    reuse_score = 1 / (1 + int(candidate["usageCount"]))
    scores = {
        "query": round(query_score, 6),
        "orientation": round(orientation_score, 6),
        "duration": round(duration_score, 6),
        "resolution": round(resolution_score, 6),
        "quality": round(quality_score, 6),
        "license": round(license_score, 6),
        "reuse": round(reuse_score, 6),
    }
    total = (
        query_score * 0.4
        + orientation_score * 0.15
        + duration_score * 0.1
        + resolution_score * 0.1
        + quality_score * 0.1
        + license_score * 0.1
        + reuse_score * 0.05
    )
    return round(total, 6), scores


def rank_candidates(
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
    minimum_score: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    compatible = [
        candidate
        for candidate in candidates
        if candidate["requestId"] == request["id"]
        and not candidate["watermark"]
        and cast(str, candidate["license"]).casefold() in _LICENSES
    ]
    if not compatible:
        empty_scores = {
            key: 0.0
            for key in (
                "query",
                "orientation",
                "duration",
                "resolution",
                "quality",
                "license",
                "reuse",
            )
        }
        return None, {
            "requestId": request["id"],
            "candidateId": None,
            "status": "missing",
            "tier": "none",
            "totalScore": None,
            "scores": empty_scores,
            "reason": "No safe license-compatible candidate was available.",
        }
    best_below: tuple[float, dict[str, float]] | None = None
    for tier in sorted(_TIER_ORDER, key=lambda value: _TIER_ORDER[value]):
        tier_candidates = [item for item in compatible if item["tier"] == tier]
        if not tier_candidates:
            continue
        scored = [(_score(request, item), item) for item in tier_candidates]
        scored.sort(key=lambda value: (-value[0][0], cast(str, value[1]["id"])))
        (total, scores), selected = scored[0]
        if best_below is None or total > best_below[0]:
            best_below = total, scores
        if total >= minimum_score:
            return selected, {
                "requestId": request["id"],
                "candidateId": selected["id"],
                "status": "resolved",
                "tier": selected["tier"],
                "totalScore": total,
                "scores": scores,
                "reason": (
                    "Selected deterministically from the earliest qualifying "
                    "resolution tier, then score and candidate ID."
                ),
            }
    assert best_below is not None
    total, scores = best_below
    return None, {
        "requestId": request["id"],
        "candidateId": None,
        "status": "missing",
        "tier": "none",
        "totalScore": None,
        "scores": scores,
        "reason": f"Best candidate score {total:.3f} was below the configured threshold.",
    }


def _default_download(
    url: str, headers: dict[str, str], timeout: int, maximum: int
) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            payload = response.read(maximum + 1)
    except OSError as exc:
        raise AssetError(f"Asset download failed: {exc}") from exc
    if len(payload) > maximum:
        raise AssetError("Asset download exceeded the configured size limit.")
    return payload, content_type


def _cache_provider_asset(
    repository_root: Path,
    request: dict[str, Any],
    candidate: dict[str, Any],
    cache: dict[str, Any],
    config: dict[str, Any],
    download: DownloadTransport,
) -> Path:
    url = _https(candidate["downloadUrl"], "download URL")
    maximum = int(config["assets"]["max_download_mb"]) * 1024 * 1024
    payload, content_type = download(
        url, {}, int(config["assets"]["provider_timeout_seconds"]), maximum
    )
    if (
        not payload
        or len(payload) > maximum
        or content_type not in {"video/mp4", "image/jpeg", "image/png"}
    ):
        raise AssetError("Provider download has an unsupported type or size.")
    extension = {"video/mp4": ".mp4", "image/jpeg": ".jpg", "image/png": ".png"}[content_type]
    digest = hashlib.sha256(payload).hexdigest()
    relative = f".cache/assets/objects/{digest}{extension}"
    destination = resolve_inside(repository_root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".download.", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    duration, width, height, orientation = _media_metadata(
        destination,
        cast(str, candidate["type"]),
        repository_root / ".cache" / "assets" / "download-probe.jsonl",
    )
    now = datetime.now(UTC)
    entry = {
        "key": _request_key(request),
        "provider": candidate["provider"],
        "providerId": candidate["providerId"],
        "objectPath": relative,
        "sha256": digest,
        "sourcePage": candidate["sourcePage"],
        "creator": candidate["creator"],
        "license": candidate["license"],
        "attributionRequired": candidate["attributionRequired"],
        "type": candidate["type"],
        "tags": candidate["tags"],
        "duration": duration,
        "width": width,
        "height": height,
        "orientation": orientation,
        "cachedAt": now.isoformat(),
        "expiresAt": (now + timedelta(days=int(config["network"]["cache_days"]))).isoformat(),
    }
    entries = [
        item for item in cast(list[dict[str, Any]], cache["entries"]) if item["key"] != entry["key"]
    ]
    entries.append(entry)
    cache["entries"] = sorted(entries, key=lambda item: cast(str, item["key"]))
    cache["updatedAt"] = _now()
    write_validated_json_atomic(repository_root, _cache_path(repository_root), "asset-cache", cache)
    candidate.update(
        {
            "localPath": relative,
            "duration": duration,
            "width": width,
            "height": height,
            "orientation": orientation,
        }
    )
    return destination


def _write_project_documents(
    context: ProjectContext,
    index: dict[str, Any],
    requests: dict[str, Any],
    candidates: dict[str, Any],
    ranking: dict[str, Any],
) -> list[str]:
    values = (
        ("planning/asset-index.json", "asset-index", index),
        ("planning/asset-requests.json", "asset-requests", requests),
        ("planning/asset-candidates.json", "asset-candidates", candidates),
        ("planning/asset-ranking.json", "asset-ranking", ranking),
    )
    for relative, schema, document in values:
        write_validated_json_atomic(
            context.repository_root, context.project_dir / relative, schema, document
        )
    return [relative for relative, _schema, _document in values]


def _resolved_plan(
    plan: dict[str, Any],
    targets: dict[str, Any],
    selections: list[dict[str, Any]],
    request_assets: dict[str, str],
) -> dict[str, Any]:
    resolved = copy.deepcopy(plan)
    scenes = cast(list[dict[str, Any]], resolved["scenes"])
    for selection in selections:
        request_id = cast(str, selection["requestId"])
        asset_id = request_assets.get(request_id)
        if asset_id is None:
            continue
        kind, scene_index, item_index = targets[request_id]
        if kind == "broll":
            scene = scenes[cast(int, scene_index)]
            scene["broll"]["assetId"] = asset_id
            if scene["broll"]["mode"] == "none":
                scene["broll"]["mode"] = "overlay"
            if scene["layout"] == "speaker-fullscreen":
                scene["layout"] = "speaker-with-broll"
        elif kind == "sfx":
            scenes[cast(int, scene_index)]["sfx"][cast(int, item_index)]["assetId"] = asset_id
        else:
            resolved["globalAudio"]["musicAssetId"] = asset_id
    resolved["provenance"]["createdBy"] = "cutmachine-asset-resolver"
    resolved["provenance"]["createdAt"] = _now()
    return resolved


def prepare_assets(
    context: ProjectContext,
    *,
    pexels_transport: SearchTransport | None = None,
    download_transport: DownloadTransport = _default_download,
) -> list[str]:
    try:
        validate_plan_outputs(context)
        plan = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "edit-plan.json",
            "edit-plan",
        )
    except (PlanningError, PersistenceError) as exc:
        raise AssetError(f"Cannot resolve assets for an invalid plan: {exc}") from exc
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    assets_root = context.repository_root / cast(str, config["project"]["assets_root"])
    index = index_local_assets(context.repository_root, assets_root)
    requests, targets = build_asset_requests(plan)
    cache = load_asset_cache(context.repository_root)
    candidates = local_candidates(requests, index) + cached_candidates(requests, cache)
    request_values = cast(list[dict[str, Any]], requests["requests"])
    scene_graphics = {
        cast(str, scene["id"]): bool(scene["graphics"])
        for scene in cast(list[dict[str, Any]], plan["scenes"])
    }
    pexels_config = cast(dict[str, Any], config["assets"]["pexels"])
    adapter: PexelsAdapter | None = None
    if (
        bool(pexels_config["enabled"])
        and bool(context.project["settings"]["networkEnabled"])
        and bool(config["network"]["enabled"])
    ):
        key_name = cast(str, pexels_config["api_key_env"])
        adapter = PexelsAdapter(
            os.environ.get(key_name, ""),
            cast(str, pexels_config["endpoint"]),
            timeout_seconds=int(config["assets"]["provider_timeout_seconds"]),
            max_candidates=int(config["assets"]["max_candidates"]),
            transport=pexels_transport or _default_search,
        )
    selections: list[dict[str, Any]] = []
    selected_candidates: dict[str, dict[str, Any]] = {}
    minimum = float(config["assets"]["minimum_score"])
    for request in request_values:
        selected, evidence = rank_candidates(request, candidates, minimum)
        has_graphic = bool(request["sceneId"] and scene_graphics.get(cast(str, request["sceneId"])))
        if selected is None and request["kind"] == "broll" and has_graphic:
            evidence["status"] = "graphic-fallback"
            evidence["reason"] = "An existing scene graphic takes precedence over a network search."
        elif selected is None and adapter is not None:
            provider_values = adapter.search(request)
            candidates.extend(provider_values)
            selected, evidence = rank_candidates(request, provider_values, minimum)
        selections.append(evidence)
        if selected is not None:
            selected_candidates[cast(str, request["id"])] = selected
    candidate_document = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "candidates": candidates,
    }
    ranking = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "selections": selections,
    }
    artifacts = _write_project_documents(context, index, requests, candidate_document, ranking)
    request_assets: dict[str, str] = {}
    manifest_assets: dict[str, dict[str, Any]] = {}
    request_by_id = {cast(str, value["id"]): value for value in request_values}
    for request_id, candidate in selected_candidates.items():
        request = request_by_id[request_id]
        if candidate["tier"] == "local":
            source = resolve_inside(assets_root, cast(str, candidate["localPath"]))
        elif candidate["tier"] == "cache":
            source = resolve_inside(context.repository_root, cast(str, candidate["localPath"]))
        else:
            source = _cache_provider_asset(
                context.repository_root,
                request,
                candidate,
                cache,
                config,
                download_transport,
            )
        digest = sha256_file(source)
        asset_id = f"asset_{digest[:16]}"
        destination = (
            context.project_dir / "assets" / "resolved" / f"{digest[:16]}{source.suffix.casefold()}"
        )
        _atomic_copy(source, destination)
        request_assets[request_id] = asset_id
        score = next(
            cast(float, item["totalScore"])
            for item in selections
            if item["requestId"] == request_id
        )
        manifest_assets[asset_id] = {
            "id": asset_id,
            "path": _relative(context.project_dir, destination),
            "type": candidate["type"],
            "query": request["query"],
            "provider": candidate["provider"],
            "providerId": candidate["providerId"],
            "creator": candidate["creator"],
            "license": candidate["license"],
            "attributionRequired": candidate["attributionRequired"],
            "sourcePage": candidate["sourcePage"],
            "retrievedAt": _now(),
            "sha256": digest,
            "duration": candidate["duration"],
            "width": candidate["width"],
            "height": candidate["height"],
            "selectedScene": request["sceneId"],
            "relevanceScore": score,
        }
    manifest_requests = []
    for selection in selections:
        request_id = cast(str, selection["requestId"])
        request = request_by_id[request_id]
        manifest_requests.append(
            {
                "requestId": request_id,
                "status": selection["status"],
                "assetId": request_assets.get(request_id),
                "selectedScene": request["sceneId"],
                "relevanceScore": selection["totalScore"],
            }
        )
    manifest = {
        "version": 2,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "assets": sorted(manifest_assets.values(), key=lambda item: cast(str, item["id"])),
        "requests": manifest_requests,
    }
    resolved = _resolved_plan(plan, targets, selections, request_assets)
    manifest_path = context.project_dir / "assets" / "manifest.json"
    resolved_path = context.project_dir / "planning" / "resolved-edit-plan.json"
    write_validated_json_atomic(context.repository_root, manifest_path, "asset-manifest", manifest)
    write_validated_json_atomic(context.repository_root, resolved_path, "edit-plan", resolved)
    artifacts.extend(
        [
            _relative(context.project_dir, resolved_path),
            _relative(context.project_dir, manifest_path),
            *[cast(str, item["path"]) for item in manifest["assets"]],
        ]
    )
    return artifacts


def _validate_resolved_plan(
    original: dict[str, Any], resolved: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if original["projectId"] != resolved["projectId"]:
        raise AssetError("Resolved plan belongs to another project.")
    for key in (
        "version",
        "projectId",
        "timelineVersion",
        "style",
        "video",
        "captions",
        "globalColor",
    ):
        if original[key] != resolved[key]:
            raise AssetError(f"Resolved plan changed authoritative field {key}.")
    assets = {
        cast(str, item["id"]): item for item in cast(list[dict[str, Any]], manifest["assets"])
    }
    music_id = resolved["globalAudio"]["musicAssetId"]
    if music_id is not None and music_id not in assets:
        raise AssetError("Resolved plan references unknown music.")
    original_scenes = cast(list[dict[str, Any]], original["scenes"])
    resolved_scenes = cast(list[dict[str, Any]], resolved["scenes"])
    if len(original_scenes) != len(resolved_scenes):
        raise AssetError("Resolved plan changed the scene count.")
    for before, after in zip(original_scenes, resolved_scenes, strict=True):
        for key in (
            "id",
            "start",
            "end",
            "purpose",
            "sourceTimelineIds",
            "camera",
            "colorOverride",
            "graphics",
            "transitionOut",
            "screenTreatment",
        ):
            if before[key] != after[key]:
                raise AssetError(f"Resolved plan changed authoritative scene field {key}.")
        broll_id = after["broll"]["assetId"]
        if broll_id is not None and broll_id not in assets:
            raise AssetError("Resolved plan references unknown B-roll.")
        for sfx in after["sfx"]:
            if sfx["assetId"] is not None and sfx["assetId"] not in assets:
                raise AssetError("Resolved plan references unknown SFX.")


def validate_asset_readiness(context: ProjectContext) -> None:
    try:
        validate_plan_outputs(context)
        original = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "edit-plan.json",
            "edit-plan",
        )
        resolved = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "resolved-edit-plan.json",
            "edit-plan",
        )
        manifest = read_validated_json(
            context.repository_root,
            context.project_dir / "assets" / "manifest.json",
            "asset-manifest",
        )
        requests = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "asset-requests.json",
            "asset-requests",
        )
        candidates = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "asset-candidates.json",
            "asset-candidates",
        )
        ranking = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "asset-ranking.json",
            "asset-ranking",
        )
        read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "asset-index.json",
            "asset-index",
        )
    except (PersistenceError, PlanningError) as exc:
        raise AssetError(f"Asset readiness artifact is missing or invalid: {exc}") from exc
    project_id = context.project["projectId"]
    if any(
        document["projectId"] != project_id
        for document in (manifest, requests, candidates, ranking)
    ):
        raise AssetError("Asset readiness artifacts refer to different projects.")
    request_ids = {item["id"] for item in requests["requests"]}
    if {item["requestId"] for item in ranking["selections"]} != request_ids:
        raise AssetError("Asset ranking does not cover every request exactly once.")
    if {item["requestId"] for item in manifest["requests"]} != request_ids:
        raise AssetError("Asset manifest does not cover every request exactly once.")
    for asset in cast(list[dict[str, Any]], manifest["assets"]):
        path = resolve_inside(context.project_dir, cast(str, asset["path"]))
        if not path.is_file() or sha256_file(path) != asset["sha256"]:
            raise AssetError(f"Resolved asset is missing or has changed: {asset['id']}")
    _validate_resolved_plan(original, resolved, manifest)
