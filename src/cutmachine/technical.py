"""Conservative local technical finishing for CutMachine Phase 8."""

from __future__ import annotations

import math
import os
import re
import shutil
import statistics
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.config import load_config
from cutmachine.media import MediaError, probe_media, run_media_command
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext, sha256_file


class TechnicalError(RuntimeError):
    """Raised when technical analysis or finishing is invalid."""


FaceDetector = Callable[[Path, list[float]], list[dict[str, float]]]

_LICENSES = {"owned", "cc0", "cc-by"}
_SIGNAL_KEYS = {
    "YAVG": "lumaAverage",
    "YLOW": "lumaLow",
    "YHIGH": "lumaHigh",
    "UAVG": "chromaU",
    "VAVG": "chromaV",
    "SATAVG": "saturationAverage",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _relative(context: ProjectContext, path: Path) -> str:
    return path.resolve().relative_to(context.project_dir.resolve()).as_posix()


def _executable(name: str) -> str:
    value = shutil.which(name)
    if value is None:
        raise TechnicalError(f"{name} is unavailable. Run `python cutmachine.py doctor`.")
    return value


def _load_inputs(
    context: ProjectContext,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        plan = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "resolved-edit-plan.json",
            "edit-plan",
        )
        media_info = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "media-info.json",
            "media-info",
        )
        index = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "asset-index.json",
            "asset-index",
        )
    except PersistenceError as exc:
        raise TechnicalError(f"Technical input is missing or invalid: {exc}") from exc
    project_id = context.project["projectId"]
    if plan["projectId"] != project_id or media_info["projectId"] != project_id:
        raise TechnicalError("Technical inputs refer to different projects.")
    return plan, media_info, index


def analyze_color_metrics(
    source: Path,
    *,
    sample_frames: int,
    duration: float,
    log_path: Path,
) -> tuple[int, dict[str, Any]]:
    if sample_frames < 1 or sample_frames > 100:
        raise TechnicalError("Color sample count is outside the supported range.")
    rate = max(sample_frames / duration, 0.01)
    result = run_media_command(
        [
            _executable("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-vf",
            f"fps={rate:.8f},scale=320:-2,signalstats,metadata=print",
            "-frames:v",
            str(sample_frames),
            "-f",
            "null",
            "-",
        ],
        log_path=log_path,
        timeout_seconds=180,
    )
    values: dict[str, list[float]] = {target: [] for target in _SIGNAL_KEYS.values()}
    for key, target in _SIGNAL_KEYS.items():
        matches = re.findall(
            rf"lavfi\.signalstats\.{key}=(-?[0-9]+(?:\.[0-9]+)?)",
            result.stderr,
        )
        values[target] = [float(item) for item in matches]
    counts = {len(items) for items in values.values()}
    if len(counts) != 1 or not counts or next(iter(counts)) < 1:
        raise TechnicalError("FFmpeg did not return complete signal statistics.")
    count = next(iter(counts))
    metrics = {key: round(statistics.fmean(items), 6) for key, items in values.items()}
    metrics["clippedShadows"] = metrics["lumaLow"] <= 18
    metrics["clippedHighlights"] = metrics["lumaHigh"] >= 235
    return count, metrics


def classify_scenes(
    project_id: str,
    plan: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    low_light = float(metrics["lumaAverage"]) < 65
    for scene in cast(list[dict[str, Any]], plan["scenes"]):
        layout = cast(str, scene["layout"])
        purpose = cast(str, scene["purpose"])
        broll = cast(dict[str, Any], scene["broll"])
        query = cast(str | None, broll.get("query"))
        evidence = [f"layout={layout}", f"purpose={purpose}"]
        preserve = False
        if layout == "browser-demo":
            classification, confidence, preserve = "screen-recording", 0.98, True
        elif layout == "mobile-demo":
            classification, confidence, preserve = "mobile-screen", 0.98, True
        elif layout in {"fullscreen-broll", "graphic-fullscreen"} and broll.get("assetId"):
            classification, confidence = "stock-footage", 0.9
        elif query and set(re.findall(r"[a-z]+", query.casefold())) & {
            "outdoor",
            "nature",
            "street",
            "park",
        }:
            classification, confidence = "outdoor", 0.72
            evidence.append("visual-query=outdoor")
        elif low_light:
            classification, confidence = "low-light", 0.78
            evidence.append(f"lumaAverage={metrics['lumaAverage']:.2f}")
        elif layout.startswith("speaker") or layout == "picture-in-picture":
            classification, confidence = "talking-head", 0.88
        else:
            classification, confidence, preserve = "uncertain", 0.4, True
        scenes.append(
            {
                "sceneId": scene["id"],
                "start": scene["start"],
                "end": scene["end"],
                "classification": classification,
                "confidence": confidence,
                "preserveNeutral": preserve,
                "evidence": evidence,
            }
        )
    return {"version": 1, "projectId": project_id, "createdAt": _now(), "scenes": scenes}


def _even(value: float, maximum: int) -> int:
    return max(2, min(maximum, int(math.floor(value / 2) * 2)))


def _even_offset(value: float, maximum: int) -> int:
    return max(0, min(maximum, int(math.floor(value / 2) * 2)))


def build_reframe_analysis(
    project_id: str,
    plan: dict[str, Any],
    source_width: int,
    source_height: int,
    classifications: dict[str, Any],
    observations: list[dict[str, float]],
    config: dict[str, Any],
) -> dict[str, Any]:
    video = cast(dict[str, Any], plan["video"])
    target_aspect = float(video["width"]) / float(video["height"])
    source_aspect = source_width / source_height
    preserve_neutral = any(
        bool(item["preserveNeutral"])
        for item in cast(list[dict[str, Any]], classifications["scenes"])
    )
    confidence_threshold = float(config["technical"]["face_confidence"])
    alpha = float(config["technical"]["face_smoothing"])
    if not 0 < alpha <= 1:
        raise TechnicalError("Face smoothing must be within (0, 1].")
    valid = [
        item
        for item in sorted(observations, key=lambda value: float(value["time"]))
        if float(item["confidence"]) >= confidence_threshold
        and 0 <= float(item["centerX"]) <= 1
        and 0 <= float(item["centerY"]) <= 1
    ]
    smoothed: list[dict[str, float]] = []
    for item in valid:
        if not smoothed:
            x, y = float(item["centerX"]), float(item["centerY"])
        else:
            x = alpha * float(item["centerX"]) + (1 - alpha) * smoothed[-1]["centerX"]
            y = alpha * float(item["centerY"]) + (1 - alpha) * smoothed[-1]["centerY"]
        smoothed.append(
            {
                "time": float(item["time"]),
                "centerX": round(x, 6),
                "centerY": round(y, 6),
                "confidence": round(float(item["confidence"]), 6),
            }
        )
    reason: str | None
    if preserve_neutral or math.isclose(target_aspect, source_aspect, rel_tol=0.03):
        mode = "neutral"
        detector = "disabled-neutral"
        center_x, center_y = 0.5, 0.5
        crop_width, crop_height = source_width, source_height
        reason = "Neutral framing preserves a screen/uncertain scene or matching aspect."
    else:
        mode = "face-aware" if smoothed else "center-fallback"
        detector = "injected-local" if smoothed else "unavailable"
        center_x = statistics.median(item["centerX"] for item in smoothed) if smoothed else 0.5
        center_y = statistics.median(item["centerY"] for item in smoothed) if smoothed else 0.5
        if source_aspect > target_aspect:
            crop_height = source_height
            crop_width = _even(source_height * target_aspect, source_width)
        else:
            crop_width = source_width
            crop_height = _even(source_width / target_aspect, source_height)
        reason = None if smoothed else "No confident local face samples; center crop selected."
    headroom = float(config["technical"]["headroom"])
    desired_x = center_x * source_width - crop_width / 2
    desired_y = (center_y - headroom / 2) * source_height - crop_height / 2
    x = _even_offset(max(0, min(source_width - crop_width, desired_x)), source_width - crop_width)
    y = _even_offset(
        max(0, min(source_height - crop_height, desired_y)), source_height - crop_height
    )
    return {
        "version": 1,
        "projectId": project_id,
        "createdAt": _now(),
        "detector": detector,
        "mode": mode,
        "targetAspect": round(target_aspect, 6),
        "maxDigitalZoom": float(config["technical"]["max_digital_zoom"]),
        "headroom": headroom,
        "samples": smoothed,
        "crop": {
            "sourceWidth": source_width,
            "sourceHeight": source_height,
            "x": x,
            "y": y,
            "width": crop_width,
            "height": crop_height,
            "centerX": round(center_x, 6),
            "centerY": round(center_y, 6),
        },
        "fallbackReason": reason,
    }


def choose_color_adjustments(
    metrics: dict[str, Any], *, preserve_neutral: bool, enabled: bool, sharpen: float
) -> dict[str, Any]:
    if preserve_neutral or not enabled:
        return {
            "enabled": False,
            "reason": "Neutral/disabled color path selected; no correction applied.",
            "brightness": 0.0,
            "contrast": 1.0,
            "saturation": 1.0,
            "temperature": 0.0,
            "sharpen": 0.0,
        }
    luma = float(metrics["lumaAverage"])
    spread = float(metrics["lumaHigh"]) - float(metrics["lumaLow"])
    saturation = float(metrics["saturationAverage"])
    cast_value = float(metrics["chromaV"]) - float(metrics["chromaU"])
    brightness = 0.06 if luma < 75 else (-0.04 if luma > 180 else 0.0)
    contrast = 1.05 if spread < 85 else (0.96 if spread > 205 else 1.0)
    saturation_adjustment = 1.05 if saturation < 35 else (0.95 if saturation > 90 else 1.0)
    temperature = max(-0.08, min(0.08, cast_value / 1024))
    values = (brightness, contrast - 1, saturation_adjustment - 1, temperature)
    active = any(abs(value) > 0.000001 for value in values) or sharpen > 0
    return {
        "enabled": active,
        "reason": (
            "Bounded signal-statistics correction selected."
            if active
            else "Frame statistics are already inside neutral bounds."
        ),
        "brightness": round(brightness, 6),
        "contrast": round(contrast, 6),
        "saturation": round(saturation_adjustment, 6),
        "temperature": round(temperature, 6),
        "sharpen": round(max(0.0, min(0.5, sharpen)), 6),
    }


def resolve_lut(
    context: ProjectContext,
    index: dict[str, Any],
    config: dict[str, Any],
    *,
    preserve_neutral: bool,
) -> dict[str, Any]:
    lut_config = cast(dict[str, Any], config["technical"]["lut"])
    disabled = {
        "enabled": False,
        "path": None,
        "sha256": None,
        "license": None,
        "colorSpace": None,
        "intensity": 0.0,
        "reason": "LUT disabled or neutral scene preservation required.",
    }
    if not bool(lut_config["enabled"]) or preserve_neutral:
        return disabled
    raw_path = lut_config.get("path")
    intensity = float(lut_config["intensity"])
    if not isinstance(raw_path, str) or not raw_path or not 0 < intensity <= 0.5:
        raise TechnicalError("Enabled LUT requires a safe path and intensity within (0, 0.5].")
    assets_root = context.repository_root / cast(str, config["project"]["assets_root"])
    try:
        path = resolve_inside(assets_root, raw_path)
    except UnsafePathError as exc:
        raise TechnicalError(f"LUT path is unsafe: {exc}") from exc
    entries = [
        item
        for item in cast(list[dict[str, Any]], index["assets"])
        if item["path"] == raw_path and item["type"] == "lut"
    ]
    if len(entries) != 1 or not path.is_file() or sha256_file(path) != entries[0]["sha256"]:
        raise TechnicalError("Configured LUT is not present in the validated local index.")
    entry = entries[0]
    color_space = lut_config.get("color_space") or entry.get("colorSpace")
    if cast(str, entry["license"]).casefold() not in _LICENSES or color_space not in {
        "rec709",
        "srgb",
    }:
        raise TechnicalError("LUT license or declared color space is not supported.")
    return {
        "enabled": True,
        "path": (Path(cast(str, config["project"]["assets_root"])) / raw_path).as_posix(),
        "sha256": entry["sha256"],
        "license": entry["license"],
        "colorSpace": color_space,
        "intensity": intensity,
        "reason": "Validated licensed local LUT selected below full strength.",
    }


def analyze_loudness(source: Path, log_path: Path) -> dict[str, float]:
    result = run_media_command(
        [
            _executable("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        log_path=log_path,
        timeout_seconds=180,
    )
    loudness = re.findall(r"I:\s+(-?[0-9]+(?:\.[0-9]+)?) LUFS", result.stderr)
    peaks = re.findall(r"Peak:\s+(-?[0-9]+(?:\.[0-9]+)?) dBFS", result.stderr)
    if not loudness or not peaks:
        raise TechnicalError("FFmpeg did not return complete loudness metrics.")
    return {"integratedLufs": float(loudness[-1]), "truePeakDb": float(peaks[-1])}


def _validate_audio_targets(audio: dict[str, Any]) -> None:
    after = cast(dict[str, Any], audio["after"])
    if abs(float(after["integratedLufs"]) - float(audio["targetLufs"])) > 1.5:
        raise TechnicalError("Mastered audio is outside the loudness tolerance.")
    if float(after["truePeakDb"]) > float(audio["targetTruePeakDb"]) + 0.5:
        raise TechnicalError("Mastered audio exceeds the true-peak tolerance.")


def _lut_filter_path(path: Path) -> str:
    value = path.resolve().as_posix().replace("\\", "/")
    return value.replace(":", "\\:").replace("'", "\\'")


def _video_filters(
    context: ProjectContext,
    reframe: dict[str, Any],
    adjustments: dict[str, Any],
    lut: dict[str, Any],
) -> tuple[list[str], list[str], str | None]:
    crop = cast(dict[str, Any], reframe["crop"])
    filters: list[str] = []
    operations: list[str] = []
    if crop["width"] != crop["sourceWidth"] or crop["height"] != crop["sourceHeight"]:
        filters.append(f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']}")
        operations.append("face-aware-crop" if reframe["mode"] == "face-aware" else "center-crop")
    else:
        operations.append("neutral-framing")
    if adjustments["enabled"]:
        filters.append(
            "eq="
            f"brightness={adjustments['brightness']}:"
            f"contrast={adjustments['contrast']}:"
            f"saturation={adjustments['saturation']}"
        )
        if abs(float(adjustments["temperature"])) > 0.000001:
            value = float(adjustments["temperature"])
            filters.append(f"colorbalance=rs={value}:bs={-value}")
        if float(adjustments["sharpen"]) > 0:
            filters.append(f"unsharp=5:5:{adjustments['sharpen']}:5:5:0")
        operations.append("bounded-color")
    complex_filter: str | None = None
    if lut["enabled"]:
        lut_path = resolve_inside(context.repository_root, cast(str, lut["path"]))
        prefix = ",".join(filters) if filters else "null"
        intensity = float(lut["intensity"])
        complex_filter = (
            f"[0:v]{prefix},split=2[base][grade];"
            f"[grade]lut3d=file='{_lut_filter_path(lut_path)}'[lut];"
            f"[base][lut]blend=all_expr='A*{1 - intensity:.6f}+B*{intensity:.6f}'[vout]"
        )
        operations.append("licensed-lut")
    return filters, operations, complex_filter


def _technical_probe(context: ProjectContext, output: Path) -> tuple[Any, ...]:
    try:
        probe = probe_media(
            output, log_path=context.project_dir / "logs" / "technical-verify.jsonl"
        )
    except MediaError as exc:
        raise TechnicalError(f"Could not inspect technical output: {exc}") from exc
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise TechnicalError("Technical output has no streams.")
    video = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    audio = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"),
        None,
    )
    format_info = probe.get("format")
    if video is None or audio is None or not isinstance(format_info, dict):
        raise TechnicalError("Technical output must contain video, audio, and format metadata.")
    try:
        duration = float(format_info["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TechnicalError("Technical output duration is invalid.") from exc
    return (
        duration,
        int(video["width"]),
        int(video["height"]),
        str(video.get("codec_name") or "unknown"),
        str(audio.get("codec_name") or "unknown"),
    )


def finish_project(
    context: ProjectContext, *, face_detector: FaceDetector | None = None
) -> list[str]:
    plan, media_info, index = _load_inputs(context)
    video = cast(dict[str, Any], plan["video"])
    source = resolve_inside(context.project_dir, cast(str, video["source"]))
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    technical = cast(dict[str, Any], config["technical"])
    log_path = context.project_dir / "logs" / "technical.jsonl"
    sample_count, metrics = analyze_color_metrics(
        source,
        sample_frames=int(technical["sample_frames"]),
        duration=float(cast(dict[str, Any], media_info["format"])["durationSeconds"]),
        log_path=log_path,
    )
    classifications = classify_scenes(cast(str, context.project["projectId"]), plan, metrics)
    source_probe = probe_media(source, log_path=log_path)
    video_streams = [
        item
        for item in cast(list[dict[str, Any]], source_probe.get("streams", []))
        if item.get("codec_type") == "video"
    ]
    if not video_streams:
        raise TechnicalError("Technical source has no video stream.")
    source_video = video_streams[0]
    duration = float(cast(dict[str, Any], media_info["format"])["durationSeconds"])
    times = [
        duration * (index + 1) / (int(technical["sample_frames"]) + 1)
        for index in range(int(technical["sample_frames"]))
    ]
    observations = face_detector(source, times) if face_detector is not None else []
    reframe = build_reframe_analysis(
        cast(str, context.project["projectId"]),
        plan,
        int(source_video["width"]),
        int(source_video["height"]),
        classifications,
        observations,
        config,
    )
    preserve_neutral = any(
        bool(item["preserveNeutral"])
        for item in cast(list[dict[str, Any]], classifications["scenes"])
    )
    adjustments = choose_color_adjustments(
        metrics,
        preserve_neutral=preserve_neutral,
        enabled=bool(technical["color_enabled"]),
        sharpen=float(technical["sharpen"]),
    )
    lut = resolve_lut(context, index, config, preserve_neutral=preserve_neutral)
    color = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "sampleCount": sample_count,
        "metrics": metrics,
        "adjustments": adjustments,
        "lut": lut,
    }
    before_audio = analyze_loudness(source, log_path)
    output = context.project_dir / "media" / "technical-proxy.mp4"
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp{output.suffix}")
    video_filters, operations, complex_filter = _video_filters(context, reframe, adjustments, lut)
    target_lufs = float(cast(dict[str, Any], plan["globalAudio"])["targetLufs"])
    target_peak = float(cast(dict[str, Any], plan["globalAudio"])["truePeakDb"])
    limiter = 10 ** (target_peak / 20)
    audio_filter = (
        "highpass=f=70,equalizer=f=3000:t=q:w=1:g=1.5,"
        "acompressor=threshold=-18dB:ratio=2:attack=20:release=200,"
        f"loudnorm=I={target_lufs}:TP={target_peak}:LRA=11,"
        f"alimiter=limit={limiter:.6f},"
        "aresample=48000"
    )
    arguments = [
        _executable("ffmpeg"),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(source),
    ]
    if complex_filter is not None:
        arguments.extend(["-filter_complex", complex_filter, "-map", "[vout]"])
    else:
        arguments.extend(
            ["-vf", ",".join(video_filters) if video_filters else "null", "-map", "0:v:0"]
        )
    arguments.extend(
        [
            "-map",
            "0:a:0",
            "-af",
            audio_filter,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(int(technical["crf"])),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    try:
        run_media_command(
            arguments,
            log_path=log_path,
            timeout_seconds=int(technical["timeout_seconds"]),
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise TechnicalError("FFmpeg did not create a technical output.")
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    except MediaError as exc:
        raise TechnicalError(f"Technical FFmpeg pass failed: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    after_audio = analyze_loudness(output, log_path)
    audio = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "targetLufs": target_lufs,
        "targetTruePeakDb": target_peak,
        "speechPresent": bool(cast(list[Any], plan["captions"]["words"])),
        "chain": [
            "highpass",
            "gentle-eq",
            "compression",
            "loudness-normalization",
            "true-peak-limit",
        ],
        "before": before_audio,
        "after": after_audio,
    }
    _validate_audio_targets(audio)
    actual_duration, width, height, video_codec, audio_codec = _technical_probe(context, output)
    tolerance = max(0.15, 2 / float(video["fps"]))
    if abs(actual_duration - duration) > tolerance:
        raise TechnicalError("Technical finishing changed authoritative duration.")
    operations.append("speech-mastering")
    paths = {
        "scene": context.project_dir / "analysis" / "scene-classification.json",
        "reframe": context.project_dir / "analysis" / "reframe-analysis.json",
        "color": context.project_dir / "analysis" / "color-analysis.json",
        "audio": context.project_dir / "analysis" / "audio-mastering.json",
    }
    for key, schema, document in (
        ("scene", "scene-classification", classifications),
        ("reframe", "reframe-analysis", reframe),
        ("color", "color-analysis", color),
        ("audio", "audio-mastering", audio),
    ):
        write_validated_json_atomic(context.repository_root, paths[key], schema, document)
    finish_path = context.project_dir / "analysis" / "technical-finish.json"
    finish = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "sourcePath": _relative(context, source),
        "outputPath": _relative(context, output),
        "sceneClassificationPath": _relative(context, paths["scene"]),
        "reframePath": _relative(context, paths["reframe"]),
        "colorPath": _relative(context, paths["color"]),
        "audioPath": _relative(context, paths["audio"]),
        "operations": operations,
        "sha256": sha256_file(output),
        "duration": actual_duration,
        "width": width,
        "height": height,
        "videoCodec": video_codec,
        "audioCodec": audio_codec,
    }
    write_validated_json_atomic(context.repository_root, finish_path, "technical-finish", finish)
    preprocess_path = context.project_dir / "analysis" / "preprocess-record.json"
    preprocess = {
        "version": 2,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "strategy": "conservative-technical-finishing",
        "videoSource": _relative(context, source),
        "technicalVideo": _relative(context, output),
        "timelinePath": "timeline/source-timeline.json",
        "editPlanPath": "planning/resolved-edit-plan.json",
        "assetManifestPath": "assets/manifest.json",
        "technicalFinishPath": _relative(context, finish_path),
    }
    write_validated_json_atomic(
        context.repository_root, preprocess_path, "preprocess-record", preprocess
    )
    return [
        *[_relative(context, path) for path in paths.values()],
        _relative(context, finish_path),
        _relative(context, preprocess_path),
        _relative(context, output),
    ]


def validate_technical_outputs(context: ProjectContext) -> None:
    documents: list[dict[str, Any]] = []
    try:
        preprocess = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "preprocess-record.json",
            "preprocess-record",
        )
        finish = read_validated_json(
            context.repository_root,
            resolve_inside(context.project_dir, cast(str, preprocess["technicalFinishPath"])),
            "technical-finish",
        )
        for key, schema in (
            ("sceneClassificationPath", "scene-classification"),
            ("reframePath", "reframe-analysis"),
            ("colorPath", "color-analysis"),
            ("audioPath", "audio-mastering"),
        ):
            documents.append(
                read_validated_json(
                    context.repository_root,
                    resolve_inside(context.project_dir, cast(str, finish[key])),
                    schema,
                )
            )
        project_id = context.project["projectId"]
        if any(
            document["projectId"] != project_id for document in (preprocess, finish, *documents)
        ):
            raise TechnicalError("Technical artifacts belong to another project.")
        for key in ("videoSource", "timelinePath", "editPlanPath", "assetManifestPath"):
            path = resolve_inside(context.project_dir, cast(str, preprocess[key]))
            if not path.is_file() or path.stat().st_size == 0:
                raise TechnicalError(f"Technical dependency is missing: {preprocess[key]}")
        output = resolve_inside(context.project_dir, cast(str, finish["outputPath"]))
    except (PersistenceError, UnsafePathError) as exc:
        raise TechnicalError(f"Technical artifact is missing or invalid: {exc}") from exc
    if not output.is_file() or sha256_file(output) != finish["sha256"]:
        raise TechnicalError("Technical output is missing or has changed.")
    audio = documents[3]
    _validate_audio_targets(audio)
    duration, width, height, video_codec, audio_codec = _technical_probe(context, output)
    if (
        abs(duration - float(finish["duration"])) > 0.01
        or width != finish["width"]
        or height != finish["height"]
        or video_codec != finish["videoCodec"]
        or audio_codec != finish["audioCodec"]
    ):
        raise TechnicalError("Technical finish record no longer matches its output.")


def finalize_draft(context: ProjectContext, source: Path, output: Path) -> Path:
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp{output.suffix}")
    try:
        run_media_command(
            [
                _executable("ffmpeg"),
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            log_path=context.project_dir / "logs" / "final-pass.jsonl",
            timeout_seconds=300,
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise TechnicalError("Final FFmpeg pass did not create an output.")
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    except MediaError as exc:
        raise TechnicalError(f"Final FFmpeg pass failed: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    duration, _width, _height, video_codec, audio_codec = _technical_probe(context, output)
    record_path = context.project_dir / "renders" / "final-pass.json"
    record = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "inputKind": "remotion-draft",
        "outputPath": _relative(context, output),
        "operation": "stream-copy-faststart",
        "sha256": sha256_file(output),
        "duration": duration,
        "videoCodec": video_codec,
        "audioCodec": audio_codec,
    }
    write_validated_json_atomic(context.repository_root, record_path, "final-pass", record)
    return record_path


def validate_final_pass(context: ProjectContext) -> None:
    try:
        record = read_validated_json(
            context.repository_root,
            context.project_dir / "renders" / "final-pass.json",
            "final-pass",
        )
        output = resolve_inside(context.project_dir, cast(str, record["outputPath"]))
    except (PersistenceError, UnsafePathError) as exc:
        raise TechnicalError(f"Final pass record is missing or invalid: {exc}") from exc
    if (
        record["projectId"] != context.project["projectId"]
        or not output.is_file()
        or sha256_file(output) != record["sha256"]
    ):
        raise TechnicalError("Final pass output is missing, changed, or project-mismatched.")
    duration, _width, _height, video_codec, audio_codec = _technical_probe(context, output)
    if (
        abs(duration - float(record["duration"])) > 0.01
        or video_codec != record["videoCodec"]
        or audio_codec != record["audioCodec"]
    ):
        raise TechnicalError("Final pass record no longer matches its output.")
