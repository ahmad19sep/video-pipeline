"""Local Remotion draft rendering and Phase 6 artifact validation."""

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
from cutmachine.media import MediaError, probe_media, run_media_command
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext, sha256_file
from cutmachine.technical import (
    TechnicalError,
    finalize_draft,
    finish_project,
    validate_final_pass,
    validate_technical_outputs,
)


class RenderError(RuntimeError):
    """Raised when a render boundary or local Remotion operation fails."""


def _relative(context: ProjectContext, path: Path) -> str:
    return path.resolve().relative_to(context.project_dir.resolve()).as_posix()


def _load_inputs(
    context: ProjectContext,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        resolved_plan = context.project_dir / "planning" / "resolved-edit-plan.json"
        plan = read_validated_json(
            context.repository_root,
            resolved_plan
            if resolved_plan.is_file()
            else context.project_dir / "planning" / "edit-plan.json",
            "edit-plan",
        )
        timeline = read_validated_json(
            context.repository_root,
            context.project_dir / "timeline" / "source-timeline.json",
            "timeline",
        )
        manifest = read_validated_json(
            context.repository_root,
            context.project_dir / "assets" / "manifest.json",
            "asset-manifest",
        )
    except PersistenceError as exc:
        raise RenderError(f"Phase 6 input is missing or invalid: {exc}") from exc
    project_id = context.project["projectId"]
    if any(document["projectId"] != project_id for document in (plan, timeline, manifest)):
        raise RenderError("Phase 6 inputs refer to different projects.")
    return plan, timeline, manifest


def preprocess_project(context: ProjectContext) -> list[str]:
    try:
        return finish_project(context)
    except TechnicalError as exc:
        raise RenderError(str(exc)) from exc


def validate_preprocess_outputs(context: ProjectContext) -> None:
    try:
        validate_technical_outputs(context)
    except TechnicalError as exc:
        raise RenderError(str(exc)) from exc


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as source_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(source_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise RenderError(f"Could not stage Remotion media: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def build_render_input(
    context: ProjectContext,
    *,
    remotion_root: Path | None = None,
    final: bool = False,
) -> Path:
    plan, timeline, manifest = _load_inputs(context)
    video = cast(dict[str, Any], plan["video"])
    try:
        preprocess = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "preprocess-record.json",
            "preprocess-record",
        )
    except PersistenceError as exc:
        raise RenderError(f"Technical preprocessing is missing or invalid: {exc}") from exc
    source = resolve_inside(context.project_dir, cast(str, preprocess["technicalVideo"]))
    public_relative = f"cutmachine/{context.project['projectId']}/proxy.mp4"
    effective_remotion_root = remotion_root or context.repository_root / "remotion"
    public_source = effective_remotion_root / "public" / Path(public_relative)
    _atomic_copy(source, public_source)
    staged_assets: dict[str, str] = {}
    for item in cast(list[dict[str, Any]], manifest["assets"]):
        asset_source = resolve_inside(context.project_dir, cast(str, item["path"]))
        if not asset_source.is_file() or sha256_file(asset_source) != item["sha256"]:
            raise RenderError(f"Resolved asset is missing or changed: {item['id']}")
        staged_relative = (
            f"cutmachine/{context.project['projectId']}/assets/"
            f"{item['sha256'][:16]}{asset_source.suffix.casefold()}"
        )
        _atomic_copy(
            asset_source,
            effective_remotion_root / "public" / Path(staged_relative),
        )
        staged_assets[cast(str, item["id"])] = staged_relative

    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    if final:
        width, height = int(video["width"]), int(video["height"])
    else:
        short = int(config["render"]["draft_width"])
        long = int(config["render"]["draft_height"])
        portrait = int(video["height"]) > int(video["width"])
        width, height = (short, long) if portrait else (long, short)

    scenes: list[dict[str, Any]] = []
    for raw_scene in cast(list[dict[str, Any]], plan["scenes"]):
        raw_broll = cast(dict[str, Any], raw_scene["broll"])
        scenes.append(
            {
                "id": raw_scene["id"],
                "start": raw_scene["start"],
                "end": raw_scene["end"],
                "layout": raw_scene["layout"],
                "camera": raw_scene["camera"],
                "broll": {
                    "mode": raw_broll["mode"],
                    "assetId": raw_broll["assetId"],
                    "effect": raw_broll["effect"],
                    "fit": raw_broll["fit"],
                },
                "graphics": raw_scene["graphics"],
                "sfx": [
                    {
                        "assetId": item["assetId"],
                        "offset": item["offset"],
                        "gainDb": item["gainDb"],
                    }
                    for item in cast(list[dict[str, Any]], raw_scene["sfx"])
                    if item["assetId"] is not None
                ],
                "transitionOut": raw_scene["transitionOut"],
                "screenTreatment": raw_scene.get("screenTreatment"),
            }
        )
    captions = cast(dict[str, Any], plan["captions"])
    audio = cast(dict[str, Any], plan["globalAudio"])
    bundled_font = effective_remotion_root / "public" / "fonts" / "NotoNaskhArabic-Variable.ttf"
    font_available = (
        bundled_font.is_file()
        and sha256_file(bundled_font)
        == "67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f"
    )
    render_input: dict[str, Any] = {
        "version": 2,
        "projectId": context.project["projectId"],
        "videoSrc": public_relative,
        "video": {
            "fps": video["fps"],
            "width": width,
            "height": height,
            "durationInSeconds": video["durationInSeconds"],
        },
        "timelineSegments": [
            {
                key: segment[key]
                for key in ("id", "sourceStart", "sourceEnd", "outputStart", "outputEnd")
            }
            for segment in cast(list[dict[str, Any]], timeline["segments"])
        ],
        "captions": {
            "enabled": captions.get("enabled", True),
            "preset": plan["style"]["captionPreset"],
            "language": captions["language"],
            "safeZone": captions["safeZone"],
            "maxLines": captions["maxLines"],
            "wordsPerPage": captions["wordsPerPage"],
            "words": captions["words"],
        },
        "scenes": scenes,
        "globalAudio": {
            "voiceGainDb": audio["voiceGainDb"],
            "musicAssetId": audio["musicAssetId"],
            "musicGainDb": audio["musicGainDb"],
            "duckingEnabled": audio["duckingEnabled"],
        },
        "design": {
            "stylePreset": plan["style"]["preset"],
            "colorPreset": plan["globalColor"]["preset"],
            "colorIntensity": plan["globalColor"]["intensity"],
            "font": {
                "family": "Noto Naskh Arabic",
                "path": "fonts/NotoNaskhArabic-Variable.ttf" if font_available else None,
                "sha256": (
                    "67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f"
                    if font_available
                    else None
                ),
                "license": "OFL-1.1" if font_available else None,
                "fallback": "Arial, sans-serif",
            },
        },
        "assets": staged_assets,
    }
    input_path = (
        context.project_dir / "renders" / ("final-input.json" if final else "draft-input.json")
    )
    write_validated_json_atomic(context.repository_root, input_path, "render-input", render_input)
    return input_path


def _append_render_log(
    path: Path, arguments: list[str], result: subprocess.CompletedProcess[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "arguments": arguments,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any]:
    streams = probe.get("streams")
    if isinstance(streams, list):
        for value in streams:
            if isinstance(value, dict) and value.get("codec_type") == codec_type:
                return value
    raise RenderError(f"Draft output has no {codec_type} stream.")


def _positive(value: object, label: str) -> float:
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise RenderError(f"Draft output has invalid {label}.") from exc
    if not math.isfinite(number) or number <= 0:
        raise RenderError(f"Draft output has invalid {label}.")
    return number


def _verify_render_file(
    context: ProjectContext, output: Path, render_input: dict[str, Any]
) -> tuple[float, str, str]:
    try:
        probe = probe_media(output, log_path=context.project_dir / "logs" / "render-verify.jsonl")
    except MediaError as exc:
        raise RenderError(f"Could not inspect draft output: {exc}") from exc
    video_stream = _stream(probe, "video")
    audio_stream = _stream(probe, "audio")
    expected = cast(dict[str, Any], render_input["video"])
    if (
        int(video_stream.get("width", 0)) != expected["width"]
        or int(video_stream.get("height", 0)) != expected["height"]
    ):
        raise RenderError("Draft output dimensions do not match the render input.")
    format_info = probe.get("format")
    if not isinstance(format_info, dict):
        raise RenderError("Draft output has no container metadata.")
    duration = _positive(format_info.get("duration"), "duration")
    tolerance = max(0.15, 2 / float(expected["fps"]))
    if abs(duration - float(expected["durationInSeconds"])) > tolerance:
        raise RenderError(
            f"Draft duration {duration:.3f}s differs from expected "
            f"{expected['durationInSeconds']:.3f}s."
        )
    return (
        duration,
        str(video_stream.get("codec_name") or "unknown"),
        str(audio_stream.get("codec_name") or "unknown"),
    )


def render_draft(context: ProjectContext, *, remotion_root: Path | None = None) -> list[str]:
    effective_remotion_root = remotion_root or context.repository_root / "remotion"
    input_path = build_render_input(context, remotion_root=effective_remotion_root)
    render_input = read_validated_json(context.repository_root, input_path, "render-input")
    executable = (
        effective_remotion_root
        / "node_modules"
        / ".bin"
        / ("remotion.cmd" if os.name == "nt" else "remotion")
    )
    if not executable.is_file():
        raise RenderError(
            "The local Remotion CLI is missing. Run `npm install` in the remotion directory."
        )
    output = context.project_dir / "review" / "draft.mp4"
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.remotion{output.suffix}")
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    arguments = [
        str(executable),
        "render",
        "src/index.ts",
        "CutMachineDraft",
        str(temporary),
        f"--props={input_path.resolve()}",
        f"--public-dir={(effective_remotion_root / 'public').resolve()}",
        "--codec=h264",
        f"--crf={int(config['render']['draft_crf'])}",
        f"--concurrency={int(config['render']['concurrency'])}",
        "--overwrite",
    ]
    try:
        try:
            result = subprocess.run(
                arguments,
                cwd=effective_remotion_root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(config["render"]["timeout_seconds"]),
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError("Remotion draft render timed out.") from exc
        except OSError as exc:
            raise RenderError(f"Could not start Remotion: {exc}") from exc
        _append_render_log(context.project_dir / "logs" / "render.jsonl", arguments, result)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-4000:]
            raise RenderError(f"Remotion failed with exit code {result.returncode}: {detail}")
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RenderError("Remotion did not create a usable draft output.")
        try:
            final_pass_path = finalize_draft(context, temporary, output)
        except TechnicalError as exc:
            raise RenderError(str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)

    duration, video_codec, audio_codec = _verify_render_file(context, output, render_input)
    video = cast(dict[str, Any], render_input["video"])
    record_path = context.project_dir / "renders" / "draft-render.json"
    record: dict[str, Any] = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": datetime.now(UTC).isoformat(),
        "inputPath": _relative(context, input_path),
        "outputPath": _relative(context, output),
        "composition": "CutMachineDraft",
        "fps": video["fps"],
        "width": video["width"],
        "height": video["height"],
        "expectedDuration": video["durationInSeconds"],
        "actualDuration": duration,
        "videoCodec": video_codec,
        "audioCodec": audio_codec,
    }
    write_validated_json_atomic(context.repository_root, record_path, "draft-render", record)
    return [
        _relative(context, input_path),
        _relative(context, output),
        _relative(context, record_path),
        _relative(context, final_pass_path),
    ]


def validate_draft_outputs(context: ProjectContext) -> None:
    try:
        record = read_validated_json(
            context.repository_root,
            context.project_dir / "renders" / "draft-render.json",
            "draft-render",
        )
        render_input = read_validated_json(
            context.repository_root,
            resolve_inside(context.project_dir, cast(str, record["inputPath"])),
            "render-input",
        )
    except PersistenceError as exc:
        raise RenderError(f"Draft render record is missing or invalid: {exc}") from exc
    if record["projectId"] != context.project["projectId"]:
        raise RenderError("Draft render record belongs to another project.")
    output = resolve_inside(context.project_dir, cast(str, record["outputPath"]))
    if not output.is_file() or output.stat().st_size == 0:
        raise RenderError("Draft render is missing or empty.")
    duration, video_codec, audio_codec = _verify_render_file(context, output, render_input)
    if abs(duration - float(record["actualDuration"])) > 0.01:
        raise RenderError("Draft render record duration no longer matches the file.")
    if video_codec != record["videoCodec"] or audio_codec != record["audioCodec"]:
        raise RenderError("Draft render codecs no longer match the render record.")
    try:
        validate_final_pass(context)
    except TechnicalError as exc:
        raise RenderError(str(exc)) from exc


def _validated_approval_decision(context: ProjectContext) -> dict[str, Any]:
    try:
        decision = read_validated_json(
            context.repository_root,
            context.project_dir / "review" / "decision.json",
            "review-decision",
        )
        qc_path = resolve_inside(context.project_dir, cast(str, decision["qcReportPath"]))
        qc = read_validated_json(context.repository_root, qc_path, "qc-report")
    except (PersistenceError, UnsafePathError) as exc:
        raise RenderError(f"Final delivery requires a valid review decision: {exc}") from exc
    if (
        decision["projectId"] != context.project["projectId"]
        or decision["action"] != "approved"
        or any(
            decision[key] is not None
            for key in ("revisionPath", "revisionSha256", "invalidateFrom")
        )
        or qc["projectId"] != context.project["projectId"]
        or qc["status"] != "passed"
        or qc["counts"]["blocking"] != 0
        or not qc_path.is_file()
        or sha256_file(qc_path) != decision["qcReportSha256"]
    ):
        raise RenderError("Final delivery requires the current project to be explicitly approved.")
    return decision


def render_final_delivery(
    context: ProjectContext, *, remotion_root: Path | None = None
) -> list[str]:
    effective_remotion_root = remotion_root or context.repository_root / "remotion"
    _validated_approval_decision(context)
    decision_path = context.project_dir / "review" / "decision.json"
    decision_hash = sha256_file(decision_path)
    input_path = build_render_input(context, remotion_root=effective_remotion_root, final=True)
    render_input = read_validated_json(context.repository_root, input_path, "render-input")
    executable = (
        effective_remotion_root
        / "node_modules"
        / ".bin"
        / ("remotion.cmd" if os.name == "nt" else "remotion")
    )
    if not executable.is_file():
        raise RenderError(
            "The local Remotion CLI is missing. Run `npm install` in the remotion directory."
        )
    workspace_output = context.project_dir / "renders" / "final.mp4"
    remotion_temporary = workspace_output.with_name(
        f".{workspace_output.stem}.{uuid.uuid4().hex}.remotion{workspace_output.suffix}"
    )
    faststart_temporary = workspace_output.with_name(
        f".{workspace_output.stem}.{uuid.uuid4().hex}.faststart{workspace_output.suffix}"
    )
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    arguments = [
        str(executable),
        "render",
        "src/index.ts",
        "CutMachineDraft",
        str(remotion_temporary),
        f"--props={input_path.resolve()}",
        f"--public-dir={(effective_remotion_root / 'public').resolve()}",
        "--codec=h264",
        f"--crf={int(config['technical']['crf'])}",
        f"--concurrency={int(config['render']['concurrency'])}",
        "--overwrite",
    ]
    try:
        try:
            result = subprocess.run(
                arguments,
                cwd=effective_remotion_root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(config["render"]["timeout_seconds"]),
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError("Remotion final render timed out.") from exc
        except OSError as exc:
            raise RenderError(f"Could not start Remotion final render: {exc}") from exc
        _append_render_log(context.project_dir / "logs" / "final-render.jsonl", arguments, result)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-4000:]
            raise RenderError(
                f"Remotion final render failed with exit code {result.returncode}: {detail}"
            )
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RenderError("FFmpeg is required for the final fast-start pass.")
        run_media_command(
            [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(remotion_temporary),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(faststart_temporary),
            ],
            log_path=context.project_dir / "logs" / "final-delivery-pass.jsonl",
            timeout_seconds=300,
        )
        workspace_output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(faststart_temporary, workspace_output)
    except MediaError as exc:
        raise RenderError(f"Final delivery fast-start pass failed: {exc}") from exc
    finally:
        remotion_temporary.unlink(missing_ok=True)
        faststart_temporary.unlink(missing_ok=True)

    duration, video_codec, audio_codec = _verify_render_file(
        context, workspace_output, render_input
    )
    delivery = context.repository_root / "output" / f"{context.project['slug']}.mp4"
    _atomic_copy(workspace_output, delivery)
    digest = sha256_file(workspace_output)
    if sha256_file(delivery) != digest:
        raise RenderError("Final delivery copy hash does not match the workspace master.")
    video = cast(dict[str, Any], render_input["video"])
    record = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": datetime.now(UTC).isoformat(),
        "inputPath": _relative(context, input_path),
        "workspaceOutputPath": _relative(context, workspace_output),
        "deliveryPath": delivery.relative_to(context.repository_root).as_posix(),
        "sha256": digest,
        "fps": video["fps"],
        "width": video["width"],
        "height": video["height"],
        "duration": duration,
        "videoCodec": video_codec,
        "audioCodec": audio_codec,
        "approvedDecisionSha256": decision_hash,
    }
    record_path = context.project_dir / "renders" / "delivery-record.json"
    write_validated_json_atomic(context.repository_root, record_path, "delivery-record", record)
    return [
        _relative(context, input_path),
        _relative(context, workspace_output),
        _relative(context, record_path),
    ]


def validate_final_delivery(context: ProjectContext) -> None:
    try:
        record = read_validated_json(
            context.repository_root,
            context.project_dir / "renders" / "delivery-record.json",
            "delivery-record",
        )
        render_input = read_validated_json(
            context.repository_root,
            resolve_inside(context.project_dir, cast(str, record["inputPath"])),
            "render-input",
        )
        decision = _validated_approval_decision(context)
        workspace_output = resolve_inside(
            context.project_dir, cast(str, record["workspaceOutputPath"])
        )
        delivery = resolve_inside(context.repository_root, cast(str, record["deliveryPath"]))
    except (PersistenceError, UnsafePathError) as exc:
        raise RenderError(f"Final delivery evidence is missing or invalid: {exc}") from exc
    expected_input = (context.project_dir / "renders" / "final-input.json").resolve()
    expected_workspace = (context.project_dir / "renders" / "final.mp4").resolve()
    expected_delivery = (
        context.repository_root / "output" / f"{context.project['slug']}.mp4"
    ).resolve()
    if (
        record["projectId"] != context.project["projectId"]
        or render_input["projectId"] != context.project["projectId"]
        or decision["projectId"] != context.project["projectId"]
        or decision["action"] != "approved"
        or resolve_inside(context.project_dir, cast(str, record["inputPath"])).resolve()
        != expected_input
        or workspace_output.resolve() != expected_workspace
        or delivery.resolve() != expected_delivery
        or sha256_file(context.project_dir / "review" / "decision.json")
        != record["approvedDecisionSha256"]
    ):
        raise RenderError("Final delivery approval evidence is stale or project-mismatched.")
    if (
        not workspace_output.is_file()
        or not delivery.is_file()
        or sha256_file(workspace_output) != record["sha256"]
        or sha256_file(delivery) != record["sha256"]
    ):
        raise RenderError("Final delivery output is missing or changed.")
    duration, video_codec, audio_codec = _verify_render_file(
        context, workspace_output, render_input
    )
    video = cast(dict[str, Any], render_input["video"])
    if (
        abs(duration - float(record["duration"])) > 0.01
        or video_codec != record["videoCodec"]
        or audio_codec != record["audioCodec"]
        or video["width"] != record["width"]
        or video["height"] != record["height"]
        or video["fps"] != record["fps"]
    ):
        raise RenderError("Final delivery record no longer matches its media output.")
