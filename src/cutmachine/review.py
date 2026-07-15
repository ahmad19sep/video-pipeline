"""Automated QC, static review packaging, and typed review decisions."""

# ruff: noqa: E501

from __future__ import annotations

import html
import os
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.assets import AssetError, validate_asset_readiness
from cutmachine.editorial import EditorialError, validate_timeline_outputs
from cutmachine.media import MediaError, probe_media, run_media_command
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.planning import PlanningError, apply_revision_document, validate_plan_outputs
from cutmachine.project import ProjectContext, sha256_file
from cutmachine.rendering import RenderError, validate_draft_outputs


class ReviewError(RuntimeError):
    """Raised when QC or review evidence is invalid."""


class QualityControlBlocked(ReviewError):
    """Raised after a blocking QC report and review page have been written."""


_REMOTE_RESOURCE = re.compile(r"(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _relative(context: ProjectContext, path: Path) -> str:
    return path.resolve().relative_to(context.project_dir.resolve()).as_posix()


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ReviewError(f"{name} is unavailable. Run `python cutmachine.py doctor`.")
    return executable


def _atomic_text(path: Path, payload: str) -> None:
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
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ReviewError(f"Could not atomically write review page: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, output)
    except OSError as exc:
        raise ReviewError(f"Could not copy review evidence: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _extract_frame(context: ProjectContext, source: Path, output: Path, time: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp{output.suffix}")
    try:
        run_media_command(
            [
                _executable("ffmpeg"),
                "-hide_banner",
                "-nostdin",
                "-y",
                "-ss",
                f"{max(0.0, time):.6f}",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-vf",
                "scale='min(960,iw)':-2",
                "-q:v",
                "2",
                str(temporary),
            ],
            log_path=context.project_dir / "logs" / "review.jsonl",
            timeout_seconds=180,
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ReviewError("FFmpeg did not create review frame evidence.")
        os.replace(temporary, output)
    except MediaError as exc:
        raise ReviewError(f"Could not extract review frame: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _read_inputs(context: ProjectContext) -> dict[str, dict[str, Any]]:
    documents = {
        "plan": ("planning/resolved-edit-plan.json", "edit-plan"),
        "timeline": ("timeline/source-timeline.json", "timeline"),
        "transcript": ("transcript/transcript.remapped.json", "remapped-transcript"),
        "normalization": (
            "analysis/transcript-normalization-report.json",
            "normalization-report",
        ),
        "silence": ("analysis/silence-candidates.json", "silence-candidates"),
        "repetition": ("analysis/repetition-candidates.json", "repetition-candidates"),
        "manifest": ("assets/manifest.json", "asset-manifest"),
        "index": ("planning/asset-index.json", "asset-index"),
        "color": ("analysis/color-analysis.json", "color-analysis"),
        "audio": ("analysis/audio-mastering.json", "audio-mastering"),
        "finish": ("analysis/technical-finish.json", "technical-finish"),
        "render": ("renders/draft-render.json", "draft-render"),
        "render_input": ("renders/draft-input.json", "render-input"),
        "final_pass": ("renders/final-pass.json", "final-pass"),
    }
    loaded: dict[str, dict[str, Any]] = {}
    try:
        for key, (relative, schema) in documents.items():
            loaded[key] = read_validated_json(
                context.repository_root, context.project_dir / relative, schema
            )
    except PersistenceError as exc:
        raise ReviewError(f"QC input is missing or invalid: {exc}") from exc
    project_id = context.project["projectId"]
    for key, document in loaded.items():
        if key != "index" and document.get("projectId") != project_id:
            raise ReviewError(f"QC input belongs to another project: {key}")
    return loaded


def _probe_draft(context: ProjectContext, draft: Path) -> tuple[float, bool, bool]:
    try:
        probe = probe_media(draft, log_path=context.project_dir / "logs" / "qc.jsonl")
        format_info = cast(dict[str, Any], probe["format"])
        streams = cast(list[dict[str, Any]], probe["streams"])
        duration = float(format_info["duration"])
    except (MediaError, KeyError, TypeError, ValueError) as exc:
        raise ReviewError(f"Draft is not decodable: {exc}") from exc
    return (
        duration,
        any(stream.get("codec_type") == "video" for stream in streams),
        any(stream.get("codec_type") == "audio" for stream in streams),
    )


def _longest_silence(context: ProjectContext, draft: Path) -> float:
    try:
        result = run_media_command(
            [
                _executable("ffmpeg"),
                "-hide_banner",
                "-nostdin",
                "-i",
                str(draft),
                "-map",
                "0:a:0",
                "-af",
                "silencedetect=n=-45dB:d=2.0",
                "-f",
                "null",
                "-",
            ],
            log_path=context.project_dir / "logs" / "qc.jsonl",
            timeout_seconds=300,
        )
    except MediaError as exc:
        raise ReviewError(f"Could not analyze output silence: {exc}") from exc
    durations = re.findall(r"silence_duration:\s*([0-9]+(?:\.[0-9]+)?)", result.stderr)
    return max((float(value) for value in durations), default=0.0)


def _stage_asset_previews(
    context: ProjectContext, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for asset in cast(list[dict[str, Any]], manifest["assets"]):
        asset_type = cast(str, asset["type"])
        if asset_type not in {"video", "image"}:
            continue
        try:
            source = resolve_inside(context.project_dir, cast(str, asset["path"]))
        except UnsafePathError as exc:
            raise ReviewError(f"Asset preview source is unsafe: {exc}") from exc
        if not source.is_file() or sha256_file(source) != asset["sha256"]:
            raise ReviewError(f"Asset preview source is missing or changed: {asset['id']}")
        output = context.project_dir / "review" / "assets" / f"{asset['id']}.jpg"
        if asset_type == "image" and source.suffix.casefold() in {".jpg", ".jpeg"}:
            _atomic_copy(source, output)
        elif asset_type == "image":
            _extract_frame(context, source, output, 0.0)
        else:
            duration = float(asset["duration"] or 0.0)
            _extract_frame(context, source, output, min(1.0, duration / 2))
        previews.append(
            {
                "assetId": asset["id"],
                "path": _relative(context, output),
                "sha256": sha256_file(output),
            }
        )
    return previews


def _caption_overflow(render_input: dict[str, Any]) -> bool:
    video = cast(dict[str, Any], render_input["video"])
    captions = cast(dict[str, Any], render_input["captions"])
    words = cast(list[dict[str, Any]], captions["words"])
    maximum = int(cast(dict[str, Any], captions["wordsPerPage"])["max"])
    width, height = int(video["width"]), int(video["height"])
    portrait = height > width
    font_size = min(width, height) * (0.065 if portrait else 0.052)
    characters_per_line = max(1, int((width * 0.85) / (font_size * 0.58)))
    capacity = characters_per_line * int(captions["maxLines"])
    return any(
        len(" ".join(cast(str, word["text"]) for word in words[index : index + maximum])) > capacity
        for index in range(0, len(words), maximum)
    )


def _html_page(
    context: ProjectContext,
    documents: dict[str, dict[str, Any]],
    report: dict[str, Any],
    previews: list[dict[str, Any]],
) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    plan = documents["plan"]
    normalization = documents["normalization"]
    silence = documents["silence"]
    repetition = documents["repetition"]
    manifest = documents["manifest"]
    preview_by_id = {item["assetId"]: Path(cast(str, item["path"])).name for item in previews}

    scene_rows = "".join(
        f"<tr><td>{esc(scene['id'])}</td><td>{float(scene['start']):.2f}-{float(scene['end']):.2f}s</td><td>{esc(scene['purpose'])}</td><td>{esc(scene['layout'])}</td></tr>"
        for scene in cast(list[dict[str, Any]], plan["scenes"])
    )
    transcript_items = (
        "".join(
            f"<li><strong>{esc(word['id'])}</strong>: {esc(word['raw'])} → {esc(word['display'])} ({float(word['confidence']):.2f})</li>"
            for word in cast(list[dict[str, Any]], normalization["lowConfidenceWords"])
        )
        or "<li>None.</li>"
    )
    uncertain = [
        *[
            f"Silence {item['id']} at {float(item['sourceStart']):.2f}-{float(item['sourceEnd']):.2f}s"
            for item in cast(list[dict[str, Any]], silence["candidates"])
            if item["decision"] == "review"
        ],
        *[
            f"Repetition {item['id']} at {float(item['sourceStart']):.2f}-{float(item['sourceEnd']):.2f}s"
            for item in cast(list[dict[str, Any]], repetition["candidates"])
        ],
    ]
    uncertain_items = "".join(f"<li>{esc(item)}</li>" for item in uncertain) or "<li>None.</li>"
    asset_cards: list[str] = []
    for asset in cast(list[dict[str, Any]], manifest["assets"]):
        preview = preview_by_id.get(cast(str, asset["id"]))
        image = (
            f'<img src="assets/{esc(preview)}" alt="Preview for {esc(asset["id"])}">'
            if preview
            else ""
        )
        source_page = esc(asset["sourcePage"] or "local asset")
        asset_cards.append(
            f'<article class="card">{image}<h3>{esc(asset["id"])}</h3><p>{esc(asset["query"])}</p><p>{esc(asset["provider"])} · {esc(asset["license"])}</p><p>{source_page}</p></article>'
        )
    missing = [
        item
        for item in cast(list[dict[str, Any]], manifest["requests"])
        if item["status"] == "missing"
    ]
    missing_items = (
        "".join(f"<li>{esc(item['requestId'])}</li>" for item in missing) or "<li>None.</li>"
    )
    finding_rows = (
        "".join(
            f'<tr class="{esc(item["severity"])}"><td>{esc(item["severity"])}</td><td>{esc(item["checkId"])}</td><td>{esc(item["message"])}</td><td>{esc(item["recommendation"])}</td></tr>'
            for item in cast(list[dict[str, Any]], report["findings"])
        )
        or '<tr><td colspan="4">No findings.</td></tr>'
    )
    audio = cast(dict[str, Any], report["audio"])
    status = cast(str, report["status"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CutMachine review · {esc(context.project["slug"])}</title>
<style>
:root{{--bg:#08111f;--panel:#101d31;--line:#28405f;--text:#eef6ff;--muted:#9db0c8;--accent:#67e8f9;--ok:#86efac;--warn:#fde68a;--bad:#fca5a5}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 Arial,sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 20px 72px}}header{{border-bottom:1px solid var(--line);margin-bottom:28px}}h1,h2,h3{{line-height:1.15}}h2{{margin-top:38px}}.badge{{display:inline-block;padding:5px 11px;border-radius:999px;background:{"var(--ok)" if status == "passed" else "var(--bad)"};color:#07111f;font-weight:800}}video{{display:block;width:min(100%,760px);max-height:70vh;background:#000;border:1px solid var(--line);border-radius:14px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;overflow-wrap:anywhere}}.card img,.compare img{{width:100%;border-radius:9px;background:#000}}.compare{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}}table{{width:100%;border-collapse:collapse;background:var(--panel)}}th,td{{padding:10px;border:1px solid var(--line);text-align:left;vertical-align:top}}th{{color:var(--accent)}}.warning td:first-child{{color:var(--warn)}}.error td:first-child{{color:var(--bad)}}code{{color:var(--accent)}}.muted{{color:var(--muted)}}
</style></head><body><main>
<header><p class="muted">CutMachine static review package · read-only · generated locally</p><h1>{esc(context.project["source"]["originalName"])}</h1><p><span class="badge">{esc(status.upper())}</span> Recommended action: <strong>{esc(report["recommendation"])}</strong></p></header>
<section id="draft"><h2>Draft video</h2><video controls preload="metadata" src="draft.mp4"></video></section>
<section id="scenes"><h2>Scene list</h2><table><thead><tr><th>ID</th><th>Range</th><th>Purpose</th><th>Layout</th></tr></thead><tbody>{scene_rows}</tbody></table></section>
<section id="transcript-warnings"><h2>Transcript warnings</h2><ul>{transcript_items}</ul></section>
<section id="uncertain-cuts"><h2>Proposed uncertain cuts</h2><ul>{uncertain_items}</ul></section>
<section id="assets"><h2>Assets and sources</h2><div class="grid">{"".join(asset_cards) or "<p>No external creative assets were needed.</p>"}</div><h3>Missing optional assets</h3><ul>{missing_items}</ul></section>
<section id="color"><h2>Color before / after</h2><div class="compare"><figure><img src="color-before.jpg" alt="Frame before technical color processing"><figcaption>Before</figcaption></figure><figure><img src="color-after.jpg" alt="Frame after technical color processing"><figcaption>After</figcaption></figure></div></section>
<section id="audio"><h2>Audio summary</h2><div class="grid"><div class="card"><strong>Integrated loudness</strong><br>{float(audio["actualLufs"]):.1f} LUFS <span class="muted">target {float(audio["targetLufs"]):.1f}</span></div><div class="card"><strong>True peak</strong><br>{float(audio["actualTruePeakDb"]):.1f} dBFS <span class="muted">target {float(audio["targetTruePeakDb"]):.1f}</span></div><div class="card"><strong>Longest silence</strong><br>{float(audio["longestSilenceSeconds"]):.2f}s</div><div class="card"><strong>Music ducking</strong><br>{"enabled" if audio["musicDuckingEnabled"] else "not used"}</div></div></section>
<section id="qc"><h2>QC findings</h2><table><thead><tr><th>Severity</th><th>Check</th><th>Finding</th><th>Recommended response</th></tr></thead><tbody>{finding_rows}</tbody></table></section>
<section id="action"><h2>Final recommended action</h2><p><strong>{esc(report["recommendation"])}</strong>. Communicate approval or a structured revision request through CutMachine/Cowork; this page has no mutable controls.</p></section>
</main></body></html>"""


def run_quality_control(context: ProjectContext) -> list[str]:
    documents = _read_inputs(context)
    project_id = cast(str, context.project["projectId"])
    render = documents["render"]
    render_input = documents["render_input"]
    finish = documents["finish"]
    audio_document = documents["audio"]
    plan = documents["plan"]
    try:
        draft = resolve_inside(context.project_dir, cast(str, render["outputPath"]))
        before_source = resolve_inside(context.project_dir, cast(str, finish["sourcePath"]))
        after_source = resolve_inside(context.project_dir, cast(str, finish["outputPath"]))
    except UnsafePathError as exc:
        raise ReviewError(f"QC media path is unsafe: {exc}") from exc

    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def add_check(
        check_id: str,
        status: str,
        message: str,
        *,
        severity: str | None = None,
        recommendation: str = "Inspect the reported evidence.",
        start: float | None = None,
        end: float | None = None,
    ) -> None:
        checks.append({"id": check_id, "status": status, "message": message})
        if severity is not None:
            findings.append(
                {
                    "id": f"qc_{len(findings) + 1:06d}",
                    "checkId": check_id,
                    "severity": severity,
                    "message": message,
                    "start": start,
                    "end": end,
                    "recommendation": recommendation,
                }
            )

    try:
        validate_plan_outputs(context)
        add_check("plan-valid", "pass", "Creative plan and component contract are valid.")
    except PlanningError as exc:
        add_check(
            "plan-valid",
            "fail",
            str(exc),
            severity="error",
            recommendation="Repair or regenerate the creative plan.",
        )
    try:
        validate_timeline_outputs(context)
        add_check("timeline-valid", "pass", "Source ranges and time map are valid.")
    except EditorialError as exc:
        add_check(
            "timeline-valid",
            "fail",
            str(exc),
            severity="error",
            recommendation="Regenerate the authoritative timeline.",
        )

    words = cast(list[dict[str, Any]], documents["transcript"]["words"])
    monotonic = all(
        float(word["start"]) >= (float(words[index - 1]["start"]) if index else 0)
        and float(word["end"]) >= float(word["start"])
        for index, word in enumerate(words)
    )
    add_check(
        "captions-monotonic",
        "pass" if monotonic else "fail",
        "Caption timing is monotonic." if monotonic else "Caption timing is not monotonic.",
        severity=None if monotonic else "error",
        recommendation="Regenerate transcript remapping before review.",
    )
    video = cast(dict[str, Any], render_input["video"])
    captions = cast(dict[str, Any], render_input["captions"])
    portrait = int(video["height"]) > int(video["width"])
    compatible_zones = (
        {"shorts-default", "reels-default", "tiktok-default"} if portrait else {"youtube-longform"}
    )
    safe_zone_valid = cast(str, captions["safeZone"]) in compatible_zones
    overflow = _caption_overflow(render_input)
    if not safe_zone_valid:
        add_check(
            "captions-safe-zone",
            "fail",
            "Caption safe-zone preset does not match the output orientation.",
            severity="error",
            recommendation="Select an orientation-compatible caption safe zone.",
        )
    elif overflow:
        add_check(
            "captions-safe-zone",
            "warning",
            "A caption page may exceed the configured line geometry.",
            severity="warning",
            recommendation="Shorten the caption page or reduce caption size after visual review.",
        )
    else:
        add_check(
            "captions-safe-zone",
            "pass",
            "Caption pages fit the configured deterministic safe-zone geometry.",
        )

    try:
        validate_draft_outputs(context)
        duration, video_present, audio_present = _probe_draft(context, draft)
        add_check("draft-decodable", "pass", "Draft and final-pass evidence decode correctly.")
    except (RenderError, ReviewError) as exc:
        duration = float(render["actualDuration"])
        video_present = audio_present = False
        add_check(
            "draft-decodable",
            "fail",
            str(exc),
            severity="error",
            recommendation="Rerender the draft before review.",
        )
    streams_present = video_present and audio_present
    add_check(
        "streams-present",
        "pass" if streams_present else "fail",
        "Draft contains video and audio streams."
        if streams_present
        else "Draft is missing a required video or audio stream.",
        severity=None if streams_present else "error",
        recommendation="Rerender with both required streams.",
    )
    expected = float(render["expectedDuration"])
    tolerance = max(0.15, 2 / float(render["fps"]))
    delta = abs(duration - expected)
    duration_valid = delta <= tolerance
    add_check(
        "duration-valid",
        "pass" if duration_valid else "fail",
        f"Draft duration delta is {delta:.3f}s (tolerance {tolerance:.3f}s).",
        severity=None if duration_valid else "error",
        recommendation="Rerender from the authoritative timeline.",
    )

    try:
        validate_asset_readiness(context)
        missing = [
            item
            for item in cast(list[dict[str, Any]], documents["manifest"]["requests"])
            if item["status"] == "missing"
        ]
        if missing:
            add_check(
                "assets-valid",
                "warning",
                f"{len(missing)} optional asset request(s) are unresolved.",
                severity="warning",
                recommendation="Accept the graphic/speaker fallback or request another asset search.",
            )
        else:
            add_check(
                "assets-valid", "pass", "All resolved assets and licensing evidence are valid."
            )
    except AssetError as exc:
        add_check(
            "assets-valid",
            "fail",
            str(exc),
            severity="error",
            recommendation="Re-resolve invalid or mandatory assets.",
        )

    after_audio = cast(dict[str, Any], audio_document["after"])
    speech_present = bool(audio_document["speechPresent"])
    target_lufs = float(audio_document["targetLufs"])
    actual_lufs = float(after_audio["integratedLufs"])
    target_peak = float(audio_document["targetTruePeakDb"])
    actual_peak = float(after_audio["truePeakDb"])
    add_check(
        "voice-present",
        "pass" if speech_present else "fail",
        "Timed speech is present in the mastered output."
        if speech_present
        else "No timed speech is present.",
        severity=None if speech_present else "error",
        recommendation="Restore or retranscribe the voice track.",
    )
    loudness_valid = abs(actual_lufs - target_lufs) <= 1.5
    add_check(
        "loudness-valid",
        "pass" if loudness_valid else "fail",
        f"Integrated loudness is {actual_lufs:.1f} LUFS for a {target_lufs:.1f} LUFS target.",
        severity=None if loudness_valid else "error",
        recommendation="Rerun speech mastering.",
    )
    peak_valid = actual_peak <= target_peak + 0.5
    add_check(
        "true-peak-valid",
        "pass" if peak_valid else "fail",
        f"True peak is {actual_peak:.1f} dBFS for a {target_peak:.1f} dBFS ceiling.",
        severity=None if peak_valid else "error",
        recommendation="Rerun limiting before review.",
    )
    longest_silence = _longest_silence(context, draft) if audio_present else duration
    if longest_silence >= 4.0:
        add_check(
            "silence-valid",
            "warning",
            f"Output contains a {longest_silence:.2f}s silent span.",
            severity="warning",
            recommendation="Confirm that the long silence is intentional.",
        )
    else:
        add_check("silence-valid", "pass", "No unexpected long silent output span was detected.")

    global_audio = cast(dict[str, Any], plan["globalAudio"])
    music_used = global_audio["musicAssetId"] is not None
    ducking = bool(global_audio["duckingEnabled"])
    music_safe = not music_used or (ducking and float(global_audio["musicGainDb"]) <= -12)
    add_check(
        "music-balance",
        "pass" if music_safe else "warning",
        "Music is absent or conservatively ducked below speech."
        if music_safe
        else "Music gain/ducking may mask speech.",
        severity=None if music_safe else "warning",
        recommendation="Enable ducking and keep music at least 12 dB below voice.",
    )
    sfx = [
        effect
        for scene in cast(list[dict[str, Any]], plan["scenes"])
        for effect in cast(list[dict[str, Any]], scene["sfx"])
    ]
    loud_sfx = [effect for effect in sfx if float(effect["gainDb"]) > -6]
    add_check(
        "sfx-balance",
        "pass" if not loud_sfx else "warning",
        "SFX gains remain below the voice-priority ceiling."
        if not loud_sfx
        else f"{len(loud_sfx)} SFX event(s) may be too loud.",
        severity=None if not loud_sfx else "warning",
        recommendation="Lower SFX gain below -6 dB.",
    )

    review_dir = context.project_dir / "review"
    before_frame = review_dir / "color-before.jpg"
    after_frame = review_dir / "color-after.jpg"
    frame_time = duration / 2
    _extract_frame(context, before_source, before_frame, frame_time)
    _extract_frame(context, after_source, after_frame, frame_time)
    previews = _stage_asset_previews(context, documents["manifest"])
    add_check(
        "review-evidence", "pass", "Local before/after frames and asset previews were generated."
    )

    blocking = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    status = "blocked" if blocking else "passed"
    report = {
        "version": 1,
        "projectId": project_id,
        "createdAt": _now(),
        "status": status,
        "recommendation": "fix-blocking-findings" if blocking else "approve-or-revise",
        "artifacts": {
            "draftPath": _relative(context, draft),
            "draftSha256": sha256_file(draft),
            "beforeFramePath": _relative(context, before_frame),
            "beforeFrameSha256": sha256_file(before_frame),
            "afterFramePath": _relative(context, after_frame),
            "afterFrameSha256": sha256_file(after_frame),
        },
        "duration": {
            "expected": expected,
            "actual": duration,
            "tolerance": tolerance,
            "delta": delta,
        },
        "audio": {
            "speechPresent": speech_present,
            "targetLufs": target_lufs,
            "actualLufs": actual_lufs,
            "targetTruePeakDb": target_peak,
            "actualTruePeakDb": actual_peak,
            "longestSilenceSeconds": longest_silence,
            "musicDuckingEnabled": ducking if music_used else False,
        },
        "counts": {
            "checks": len(checks),
            "passed": sum(item["status"] == "pass" for item in checks),
            "warnings": warnings,
            "blocking": blocking,
        },
        "checks": checks,
        "findings": findings,
    }
    report_path = review_dir / "qc-report.json"
    write_validated_json_atomic(context.repository_root, report_path, "qc-report", report)
    html_path = review_dir / "index.html"
    _atomic_text(html_path, _html_page(context, documents, report, previews))
    package_path = review_dir / "review-package.json"
    package = {
        "version": 1,
        "projectId": project_id,
        "createdAt": _now(),
        "htmlPath": _relative(context, html_path),
        "htmlSha256": sha256_file(html_path),
        "draftPath": _relative(context, draft),
        "draftSha256": sha256_file(draft),
        "qcReportPath": _relative(context, report_path),
        "qcReportSha256": sha256_file(report_path),
        "beforeFramePath": _relative(context, before_frame),
        "beforeFrameSha256": sha256_file(before_frame),
        "afterFramePath": _relative(context, after_frame),
        "afterFrameSha256": sha256_file(after_frame),
        "assetPreviews": previews,
        "readOnly": True,
        "remoteResources": False,
    }
    write_validated_json_atomic(context.repository_root, package_path, "review-package", package)
    artifacts = [
        _relative(context, report_path),
        _relative(context, html_path),
        _relative(context, package_path),
        _relative(context, before_frame),
        _relative(context, after_frame),
        *[cast(str, item["path"]) for item in previews],
    ]
    if blocking:
        raise QualityControlBlocked(f"QC found {blocking} blocking issue(s). See {report_path}.")
    return artifacts


def validate_qc_outputs(context: ProjectContext) -> None:
    try:
        report = read_validated_json(
            context.repository_root, context.project_dir / "review" / "qc-report.json", "qc-report"
        )
        package = read_validated_json(
            context.repository_root,
            context.project_dir / "review" / "review-package.json",
            "review-package",
        )
        if (
            report["projectId"] != context.project["projectId"]
            or package["projectId"] != context.project["projectId"]
        ):
            raise ReviewError("Review artifacts belong to another project.")
        for path_key, hash_key in (
            ("htmlPath", "htmlSha256"),
            ("draftPath", "draftSha256"),
            ("qcReportPath", "qcReportSha256"),
            ("beforeFramePath", "beforeFrameSha256"),
            ("afterFramePath", "afterFrameSha256"),
        ):
            path = resolve_inside(context.project_dir, cast(str, package[path_key]))
            if not path.is_file() or sha256_file(path) != package[hash_key]:
                raise ReviewError(f"Review artifact is missing or changed: {package[path_key]}")
        for preview in cast(list[dict[str, Any]], package["assetPreviews"]):
            path = resolve_inside(context.project_dir, cast(str, preview["path"]))
            if not path.is_file() or sha256_file(path) != preview["sha256"]:
                raise ReviewError(
                    f"Review asset preview is missing or changed: {preview['assetId']}"
                )
    except (PersistenceError, UnsafePathError) as exc:
        raise ReviewError(f"Review artifact is missing or invalid: {exc}") from exc
    if report["status"] != "passed" or int(cast(dict[str, Any], report["counts"])["blocking"]) != 0:
        raise ReviewError("QC report contains blocking findings.")
    checks = cast(list[dict[str, Any]], report["checks"])
    findings = cast(list[dict[str, Any]], report["findings"])
    counts = cast(dict[str, Any], report["counts"])
    expected_checks = {
        "plan-valid",
        "timeline-valid",
        "captions-monotonic",
        "captions-safe-zone",
        "draft-decodable",
        "streams-present",
        "duration-valid",
        "assets-valid",
        "voice-present",
        "loudness-valid",
        "true-peak-valid",
        "silence-valid",
        "music-balance",
        "sfx-balance",
        "review-evidence",
    }
    if {item["id"] for item in checks} != expected_checks or len(checks) != len(expected_checks):
        raise ReviewError("QC report does not contain exactly one result for every required check.")
    expected_counts = {
        "checks": len(checks),
        "passed": sum(item["status"] == "pass" for item in checks),
        "warnings": sum(item["severity"] == "warning" for item in findings),
        "blocking": sum(item["severity"] == "error" for item in findings),
    }
    if counts != expected_counts:
        raise ReviewError("QC report counts do not match its checks and findings.")
    html_path = resolve_inside(context.project_dir, cast(str, package["htmlPath"]))
    try:
        page = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewError(f"Could not read review page: {exc}") from exc
    if "<script" in page.casefold() or _REMOTE_RESOURCE.search(page):
        raise ReviewError("Review page contains executable or remote resources.")
    report_artifacts = cast(dict[str, Any], report["artifacts"])
    for path_key, hash_key in (
        ("draftPath", "draftSha256"),
        ("beforeFramePath", "beforeFrameSha256"),
        ("afterFramePath", "afterFrameSha256"),
    ):
        if (
            package[path_key] != report_artifacts[path_key]
            or package[hash_key] != report_artifacts[hash_key]
        ):
            raise ReviewError("QC report and review package evidence do not match.")


def prepare_review_checkpoint(context: ProjectContext) -> list[str]:
    validate_qc_outputs(context)
    return ["review/index.html", "review/qc-report.json", "review/review-package.json"]


def write_approval_decision(context: ProjectContext, note: str | None = None) -> list[str]:
    validate_qc_outputs(context)
    report_path = context.project_dir / "review" / "qc-report.json"
    decision_path = context.project_dir / "review" / "decision.json"
    decision = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "action": "approved",
        "note": note,
        "qcReportPath": _relative(context, report_path),
        "qcReportSha256": sha256_file(report_path),
        "revisionPath": None,
        "revisionSha256": None,
        "invalidateFrom": None,
    }
    write_validated_json_atomic(context.repository_root, decision_path, "review-decision", decision)
    return [_relative(context, decision_path)]


def validate_review_decision(context: ProjectContext, *, expected_action: str) -> None:
    try:
        decision = read_validated_json(
            context.repository_root,
            context.project_dir / "review" / "decision.json",
            "review-decision",
        )
        report_path = resolve_inside(context.project_dir, cast(str, decision["qcReportPath"]))
    except (PersistenceError, UnsafePathError) as exc:
        raise ReviewError(f"Review decision is missing or invalid: {exc}") from exc
    if (
        decision["projectId"] != context.project["projectId"]
        or decision["action"] != expected_action
        or not report_path.is_file()
        or sha256_file(report_path) != decision["qcReportSha256"]
    ):
        raise ReviewError("Review decision is project-mismatched, stale, or changed.")
    if expected_action == "approved":
        validate_qc_outputs(context)
        if any(
            decision[key] is not None
            for key in ("revisionPath", "revisionSha256", "invalidateFrom")
        ):
            raise ReviewError("Approval decision contains revision fields.")
        return
    if (
        decision["revisionPath"] is None
        or decision["revisionSha256"] is None
        or decision["invalidateFrom"] != "plan_ready"
    ):
        raise ReviewError("Revision decision is missing typed revision evidence.")
    try:
        revision_path = resolve_inside(context.project_dir, cast(str, decision["revisionPath"]))
    except UnsafePathError as exc:
        raise ReviewError(f"Revision decision path is unsafe: {exc}") from exc
    if not revision_path.is_file() or sha256_file(revision_path) != decision["revisionSha256"]:
        raise ReviewError("Revision evidence is missing or changed.")


def apply_review_revision(
    context: ProjectContext, revision_relative: str, note: str | None = None
) -> list[str]:
    validate_qc_outputs(context)
    try:
        revision_path = resolve_inside(context.project_dir, revision_relative)
    except UnsafePathError as exc:
        raise ReviewError(f"Revision path is unsafe: {exc}") from exc
    try:
        revision = read_validated_json(context.repository_root, revision_path, "plan-revision")
    except PersistenceError as exc:
        raise ReviewError(f"Revision document is invalid: {exc}") from exc
    try:
        apply_revision_document(context, revision)
    except PlanningError as exc:
        raise ReviewError(f"Revision cannot be applied: {exc}") from exc
    saved_revision = context.project_dir / "review" / "requested-revision.json"
    write_validated_json_atomic(context.repository_root, saved_revision, "plan-revision", revision)
    report_path = context.project_dir / "review" / "qc-report.json"
    decision_path = context.project_dir / "review" / "decision.json"
    decision = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": _now(),
        "action": "revision-requested",
        "note": note,
        "qcReportPath": _relative(context, report_path),
        "qcReportSha256": sha256_file(report_path),
        "revisionPath": _relative(context, saved_revision),
        "revisionSha256": sha256_file(saved_revision),
        "invalidateFrom": "plan_ready",
    }
    write_validated_json_atomic(context.repository_root, decision_path, "review-decision", decision)
    return [
        _relative(context, decision_path),
        _relative(context, saved_revision),
        "planning/edit-plan.json",
    ]
