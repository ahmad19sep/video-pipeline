"""Deterministic FFmpeg/FFprobe media ingest."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.config import load_config
from cutmachine.paths import resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext


class MediaError(RuntimeError):
    """Raised when source media or an FFmpeg operation is invalid."""


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise MediaError(f"{name} is not available on PATH. Run `python cutmachine.py doctor`.")
    return executable


def _append_log(
    log_path: Path, arguments: list[str], result: subprocess.CompletedProcess[str]
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "arguments": arguments,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_media_command(
    arguments: list[str],
    *,
    log_path: Path,
    timeout_seconds: int = 600,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"Media command timed out after {timeout_seconds} seconds.") from exc
    except OSError as exc:
        raise MediaError(f"Could not execute media command: {exc}") from exc
    _append_log(log_path, arguments, result)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-3000:]
        raise MediaError(f"Media command failed with exit code {result.returncode}: {detail}")
    return result


def _atomic_ffmpeg(
    input_arguments: list[str],
    output: Path,
    *,
    log_path: Path,
    timeout_seconds: int = 600,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp{output.suffix}")
    command = [
        _executable("ffmpeg"),
        "-hide_banner",
        "-nostdin",
        "-y",
        *input_arguments,
        str(temporary),
    ]
    try:
        run_media_command(command, log_path=log_path, timeout_seconds=timeout_seconds)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise MediaError(f"FFmpeg did not create a usable output: {output}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def probe_media(path: Path, *, log_path: Path) -> dict[str, Any]:
    command = [
        _executable("ffprobe"),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = run_media_command(command, log_path=log_path, timeout_seconds=60)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"FFprobe returned invalid JSON for {path}.") from exc
    if not isinstance(value, dict):
        raise MediaError(f"FFprobe returned an invalid document for {path}.")
    return value


def _positive_float(value: object, label: str) -> float:
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise MediaError(f"Invalid {label}: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise MediaError(f"Invalid {label}: {value!r}")
    return number


def _optional_integer(value: object) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(cast(str | int, value))
    except (TypeError, ValueError):
        return None


def _frame_rate(value: object) -> float:
    if not isinstance(value, str) or "/" not in value:
        return _positive_float(value, "video frame rate")
    numerator, denominator = value.split("/", maxsplit=1)
    denominator_value = _positive_float(denominator, "frame-rate denominator")
    return _positive_float(numerator, "frame-rate numerator") / denominator_value


def _rotation(stream: dict[str, Any]) -> int:
    tags = stream.get("tags")
    if isinstance(tags, dict) and "rotate" in tags:
        try:
            return int(tags["rotate"])
        except (TypeError, ValueError):
            pass
    side_data = stream.get("side_data_list")
    if isinstance(side_data, list):
        for item in side_data:
            if isinstance(item, dict) and "rotation" in item:
                try:
                    return int(item["rotation"])
                except (TypeError, ValueError):
                    continue
    return 0


def _first_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any]:
    streams = probe.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
                return stream
    raise MediaError(f"Source media has no {codec_type} stream.")


def _duration(stream: dict[str, Any], format_info: dict[str, Any], label: str) -> float:
    value = stream.get("duration")
    if value in (None, "", "N/A"):
        value = format_info.get("duration")
    return _positive_float(value, f"{label} duration")


def _relative(project_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(project_dir.resolve()).as_posix()


def _bounded_scale_filter(max_dimension: int) -> str:
    return (
        "scale="
        f"w='if(gte(iw,ih),min(iw,{max_dimension}),-2)':"
        f"h='if(gte(iw,ih),-2,min(ih,{max_dimension}))':"
        "force_divisible_by=2"
    )


def ingest_project(context: ProjectContext) -> list[str]:
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    source_info = cast(dict[str, Any], context.project["source"])
    source = resolve_inside(context.project_dir, cast(str, source_info["storedPath"]))
    log_path = context.project_dir / "logs" / "ingest.jsonl"
    probe = probe_media(source, log_path=log_path)
    format_info = probe.get("format")
    if not isinstance(format_info, dict):
        raise MediaError("FFprobe did not return container format information.")
    video_stream = _first_stream(probe, "video")
    audio_stream = _first_stream(probe, "audio")
    duration = _positive_float(format_info.get("duration"), "container duration")
    try:
        coded_width = int(video_stream["width"])
        coded_height = int(video_stream["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError("Source video stream does not declare valid dimensions.") from exc
    rotation = _rotation(video_stream)
    # FFmpeg auto-rotates derived media, so record display-oriented dimensions.
    if rotation % 180 == 90:
        display_width, display_height = coded_height, coded_width
    else:
        display_width, display_height = coded_width, coded_height

    proxy = context.project_dir / "media" / "proxy.mp4"
    original_audio = context.project_dir / "audio" / "original.wav"
    transcription_audio = context.project_dir / "audio" / "source.wav"
    contact_sheet = context.project_dir / "analysis" / "contact-sheet.jpg"
    frames_dir = context.project_dir / "media" / "frames"
    max_dimension = int(config["ingest"]["proxy_max_dimension"])
    crf = int(config["ingest"]["proxy_crf"])

    _atomic_ffmpeg(
        [
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-vf",
            _bounded_scale_filter(max_dimension),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
        ],
        proxy,
        log_path=log_path,
    )
    _atomic_ffmpeg(
        ["-i", str(source), "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le"],
        original_audio,
        log_path=log_path,
    )
    _atomic_ffmpeg(
        [
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
        ],
        transcription_audio,
        log_path=log_path,
    )

    frame_count = int(config["ingest"]["representative_frames"])
    frame_paths: list[Path] = []
    for index in range(frame_count):
        timestamp = duration * (index + 1) / (frame_count + 1)
        frame = frames_dir / f"frame-{index + 1:03d}.jpg"
        _atomic_ffmpeg(
            [
                "-ss",
                f"{timestamp:.6f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                _bounded_scale_filter(640),
                "-q:v",
                "2",
            ],
            frame,
            log_path=log_path,
            timeout_seconds=120,
        )
        frame_paths.append(frame)

    columns = int(config["ingest"]["contact_sheet_columns"])
    rows = int(config["ingest"]["contact_sheet_rows"])
    interval = max(duration / (columns * rows), 0.04)
    _atomic_ffmpeg(
        [
            "-i",
            str(source),
            "-vf",
            f"fps=1/{interval:.8f},scale=320:-2,tile={columns}x{rows}:padding=4:margin=4",
            "-frames:v",
            "1",
            "-q:v",
            "3",
        ],
        contact_sheet,
        log_path=log_path,
        timeout_seconds=180,
    )

    media_info: dict[str, Any] = {
        "version": 1,
        "projectId": context.project["projectId"],
        "generatedAt": datetime.now(UTC).isoformat(),
        "source": {
            "path": cast(str, source_info["storedPath"]),
            "sha256": cast(str, source_info["sha256"]),
            "sizeBytes": cast(int, source_info["sizeBytes"]),
        },
        "format": {
            "name": str(format_info.get("format_name") or "unknown"),
            "durationSeconds": duration,
            "bitRate": _optional_integer(format_info.get("bit_rate")),
        },
        "video": {
            "codec": str(video_stream.get("codec_name") or "unknown"),
            "width": display_width,
            "height": display_height,
            "pixelFormat": video_stream.get("pix_fmt"),
            "frameRate": _frame_rate(
                video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
            ),
            "rotation": rotation,
            "durationSeconds": _duration(video_stream, format_info, "video"),
        },
        "audio": {
            "codec": str(audio_stream.get("codec_name") or "unknown"),
            "sampleRate": int(audio_stream["sample_rate"]),
            "channels": int(audio_stream["channels"]),
            "channelLayout": audio_stream.get("channel_layout"),
            "durationSeconds": _duration(audio_stream, format_info, "audio"),
        },
        "artifacts": {
            "proxy": _relative(context.project_dir, proxy),
            "originalAudio": _relative(context.project_dir, original_audio),
            "transcriptionAudio": _relative(context.project_dir, transcription_audio),
            "contactSheet": _relative(context.project_dir, contact_sheet),
            "frames": [_relative(context.project_dir, frame) for frame in frame_paths],
        },
    }
    media_info_path = context.project_dir / "analysis" / "media-info.json"
    write_validated_json_atomic(
        context.repository_root,
        media_info_path,
        "media-info",
        media_info,
    )
    return [
        _relative(context.project_dir, media_info_path),
        _relative(context.project_dir, proxy),
        _relative(context.project_dir, original_audio),
        _relative(context.project_dir, transcription_audio),
        _relative(context.project_dir, contact_sheet),
        *[_relative(context.project_dir, frame) for frame in frame_paths],
    ]


def validate_ingest_outputs(context: ProjectContext) -> None:
    media_info_path = context.project_dir / "analysis" / "media-info.json"
    try:
        media_info = read_validated_json(
            context.repository_root,
            media_info_path,
            "media-info",
        )
    except PersistenceError as exc:
        raise MediaError(f"Ingest metadata is missing or invalid: {exc}") from exc
    artifacts = cast(dict[str, Any], media_info["artifacts"])
    paths = [
        cast(str, artifacts["proxy"]),
        cast(str, artifacts["originalAudio"]),
        cast(str, artifacts["transcriptionAudio"]),
        cast(str, artifacts["contactSheet"]),
        *cast(list[str], artifacts["frames"]),
    ]
    for relative in paths:
        artifact = resolve_inside(context.project_dir, relative)
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise MediaError(f"Ingest artifact is missing or empty: {relative}")
    log_path = context.project_dir / "logs" / "ingest-verify.jsonl"
    proxy_probe = probe_media(
        resolve_inside(context.project_dir, cast(str, artifacts["proxy"])), log_path=log_path
    )
    _first_stream(proxy_probe, "video")
    _first_stream(proxy_probe, "audio")
    audio_probe = probe_media(
        resolve_inside(context.project_dir, cast(str, artifacts["transcriptionAudio"])),
        log_path=log_path,
    )
    audio_stream = _first_stream(audio_probe, "audio")
    if (
        int(audio_stream.get("sample_rate", 0)) != 16000
        or int(audio_stream.get("channels", 0)) != 1
    ):
        raise MediaError("Transcription audio must be mono 16 kHz PCM.")
