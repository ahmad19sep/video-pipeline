"""Conservative editorial analysis and non-destructive timeline generation."""

from __future__ import annotations

import math
import re
import shutil
from datetime import UTC, datetime
from difflib import SequenceMatcher
from itertools import pairwise
from typing import Any, Protocol, cast

from cutmachine.config import load_config
from cutmachine.media import MediaError, run_media_command
from cutmachine.paths import resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext


class EditorialError(RuntimeError):
    """Raised when analysis or timeline data is unsafe or inconsistent."""


class SilenceDetector(Protocol):
    def __call__(
        self, context: ProjectContext, threshold_db: float, minimum_seconds: float
    ) -> list[tuple[float, float]]: ...


_START_PATTERN = re.compile(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)")
_END_PATTERN = re.compile(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)")


def parse_silence_output(output: str, duration: float) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    pending: float | None = None
    for line in output.splitlines():
        start_match = _START_PATTERN.search(line)
        if start_match:
            pending = max(0.0, min(duration, float(start_match.group(1))))
        end_match = _END_PATTERN.search(line)
        if end_match and pending is not None:
            end = max(pending, min(duration, float(end_match.group(1))))
            if end > pending:
                intervals.append((pending, end))
            pending = None
    if pending is not None and duration > pending:
        intervals.append((pending, duration))
    return _merge_intervals(intervals)


def detect_ffmpeg_silence(
    context: ProjectContext, threshold_db: float, minimum_seconds: float
) -> list[tuple[float, float]]:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise EditorialError("ffmpeg is unavailable; run `python cutmachine.py doctor`.")
    audio = resolve_inside(context.project_dir, "audio/original.wav")
    if not audio.is_file():
        raise EditorialError("Preserved audio is missing: audio/original.wav")
    result = run_media_command(
        [
            executable,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(audio),
            "-af",
            f"silencedetect=noise={threshold_db}dB:d={minimum_seconds}",
            "-f",
            "null",
            "-",
        ],
        log_path=context.project_dir / "logs" / "timeline-analysis.jsonl",
        timeout_seconds=600,
    )
    try:
        media_info = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "media-info.json",
            "media-info",
        )
    except PersistenceError as exc:
        raise EditorialError(f"Media metadata is invalid: {exc}") from exc
    duration = float(cast(dict[str, Any], media_info["format"])["durationSeconds"])
    return parse_silence_output(result.stderr, duration)


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise EditorialError("Silence detector returned an invalid interval.")
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(start, 6), round(end, 6)) for start, end in merged]


def _is_corroborated(start: float, end: float, intervals: list[tuple[float, float]]) -> bool:
    duration = end - start
    for silence_start, silence_end in intervals:
        overlap = max(0.0, min(end, silence_end) - max(start, silence_start))
        if duration > 0 and overlap / duration >= 0.8:
            return True
    return False


def _candidate(
    index: int,
    kind: str,
    start: float,
    end: float,
    intervals: list[tuple[float, float]],
    policy: dict[str, float],
) -> dict[str, Any]:
    corroborated = _is_corroborated(start, end, intervals)
    long_enough = end - start >= policy["autoRemoveSeconds"]
    proposed_start = start
    proposed_end = end
    if kind == "leading-silence":
        proposed_end = max(start, end - policy["paddingBefore"])
    elif kind == "trailing-silence":
        proposed_start = min(end, start + policy["paddingAfter"])
    else:
        proposed_start = min(end, start + policy["paddingAfter"])
        proposed_end = max(start, end - policy["paddingBefore"])
    removable = corroborated and long_enough and proposed_end - proposed_start >= 0.05
    return {
        "id": f"silence_{index:06d}",
        "type": kind,
        "sourceStart": round(start, 6),
        "sourceEnd": round(end, 6),
        "duration": round(end - start, 6),
        "confidence": 0.98 if removable else (0.7 if corroborated else 0.45),
        "decision": "remove" if removable else "review",
        "automatic": removable,
        "evidence": {
            "wordGap": True,
            "ffmpegSilence": corroborated,
            "noWordOverlap": True,
        },
        "proposedCutStart": round(proposed_start, 6) if removable else None,
        "proposedCutEnd": round(proposed_end, 6) if removable else None,
    }


def build_analysis_documents(
    project_id: str,
    duration: float,
    words: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    ffmpeg_intervals: list[tuple[float, float]],
    silence_config: dict[str, Any],
    repetition_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not math.isfinite(duration) or duration <= 0:
        raise EditorialError("Source duration must be finite and positive.")
    policy = {
        "thresholdDb": float(silence_config["threshold_db"]),
        "minimumSeconds": float(silence_config["minimum_seconds"]),
        "autoRemoveSeconds": float(silence_config["auto_remove_seconds"]),
        "paddingBefore": float(silence_config["padding_before"]),
        "paddingAfter": float(silence_config["padding_after"]),
    }
    if (
        not all(math.isfinite(value) for value in policy.values())
        or policy["minimumSeconds"] <= 0
        or policy["autoRemoveSeconds"] < policy["minimumSeconds"]
        or policy["paddingBefore"] < 0
        or policy["paddingAfter"] < 0
    ):
        raise EditorialError("Silence policy values are invalid.")
    intervals = _merge_intervals(ffmpeg_intervals)
    if any(end > duration + 0.001 for _, end in intervals):
        raise EditorialError("FFmpeg silence interval exceeds source duration.")
    gaps: list[tuple[str, float, float]] = []
    if words:
        first_start = float(words[0]["start"])
        if first_start >= policy["minimumSeconds"]:
            gaps.append(("leading-silence", 0.0, first_start))
        for previous, following in pairwise(words):
            start = float(previous["end"])
            end = float(following["start"])
            if end - start >= policy["minimumSeconds"]:
                gaps.append(("internal-silence", start, end))
        last_end = float(words[-1]["end"])
        if duration - last_end >= policy["minimumSeconds"]:
            gaps.append(("trailing-silence", last_end, duration))
    else:
        gaps.append(("no-speech", 0.0, duration))
    candidates: list[dict[str, Any]] = []
    for index, (kind, start, end) in enumerate(gaps, start=1):
        if kind == "no-speech":
            candidates.append(
                {
                    "id": f"silence_{index:06d}",
                    "type": kind,
                    "sourceStart": 0.0,
                    "sourceEnd": round(duration, 6),
                    "duration": round(duration, 6),
                    "confidence": 0.5,
                    "decision": "keep",
                    "automatic": False,
                    "evidence": {
                        "wordGap": True,
                        "ffmpegSilence": _is_corroborated(0.0, duration, intervals),
                        "noWordOverlap": True,
                    },
                    "proposedCutStart": None,
                    "proposedCutEnd": None,
                }
            )
        else:
            candidates.append(_candidate(index, kind, start, end, intervals, policy))

    similarity_threshold = float(repetition_config["similarity_threshold"])
    nearby_seconds = float(repetition_config["nearby_seconds"])
    if (
        not math.isfinite(similarity_threshold)
        or not math.isfinite(nearby_seconds)
        or not 0 <= similarity_threshold <= 1
        or nearby_seconds <= 0
    ):
        raise EditorialError("Repetition policy values are invalid.")
    repetitions: list[dict[str, Any]] = []
    for first, second in pairwise(segments):
        gap = float(second["start"]) - float(first["end"])
        if gap > nearby_seconds:
            continue
        first_text = " ".join(cast(str, first["text"]).casefold().split())
        second_text = " ".join(cast(str, second["text"]).casefold().split())
        if not first_text or not second_text:
            continue
        similarity = SequenceMatcher(None, first_text, second_text).ratio()
        if similarity >= similarity_threshold:
            repetitions.append(
                {
                    "id": f"repetition_{len(repetitions) + 1:06d}",
                    "firstSegmentId": first["id"],
                    "secondSegmentId": second["id"],
                    "sourceStart": first["start"],
                    "sourceEnd": second["end"],
                    "similarity": round(similarity, 6),
                    "decision": "review",
                    "automatic": False,
                    "reason": "possible-nearby-repetition",
                }
            )
    generated_at = datetime.now(UTC).isoformat()
    silence_document = {
        "version": 1,
        "projectId": project_id,
        "generatedAt": generated_at,
        "sourceDuration": duration,
        "policy": policy,
        "ffmpegIntervals": [{"start": start, "end": end} for start, end in intervals],
        "candidates": candidates,
    }
    repetition_document = {
        "version": 1,
        "projectId": project_id,
        "generatedAt": generated_at,
        "policy": {
            "similarityThreshold": similarity_threshold,
            "nearbySeconds": nearby_seconds,
            "automaticRemovalEnabled": False,
        },
        "candidates": repetitions,
    }
    return silence_document, repetition_document


def analyze_project(
    context: ProjectContext,
    *,
    silence_detector: SilenceDetector = detect_ffmpeg_silence,
) -> list[str]:
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    try:
        normalized = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.roman.json",
            "normalized-transcript",
        )
    except PersistenceError as exc:
        raise EditorialError(f"Normalized transcript is invalid: {exc}") from exc
    silence_config = cast(dict[str, Any], config["silence"])
    repetition_config = cast(dict[str, Any], config["repetition"])
    threshold = float(silence_config["threshold_db"])
    minimum = float(silence_config["minimum_seconds"])
    try:
        intervals = silence_detector(context, threshold, minimum)
    except MediaError as exc:
        raise EditorialError(f"FFmpeg silence analysis failed: {exc}") from exc
    silence, repetitions = build_analysis_documents(
        cast(str, context.project["projectId"]),
        float(normalized["durationSeconds"]),
        cast(list[dict[str, Any]], normalized["words"]),
        cast(list[dict[str, Any]], normalized["segments"]),
        intervals,
        silence_config,
        repetition_config,
    )
    silence_path = context.project_dir / "analysis" / "silence-candidates.json"
    repetition_path = context.project_dir / "analysis" / "repetition-candidates.json"
    write_validated_json_atomic(
        context.repository_root, silence_path, "silence-candidates", silence
    )
    write_validated_json_atomic(
        context.repository_root, repetition_path, "repetition-candidates", repetitions
    )
    validate_analysis_outputs(context)
    return [
        silence_path.relative_to(context.project_dir).as_posix(),
        repetition_path.relative_to(context.project_dir).as_posix(),
    ]


def validate_analysis_outputs(context: ProjectContext) -> None:
    try:
        normalized = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.roman.json",
            "normalized-transcript",
        )
        silence = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "silence-candidates.json",
            "silence-candidates",
        )
        repetitions = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "repetition-candidates.json",
            "repetition-candidates",
        )
    except PersistenceError as exc:
        raise EditorialError(f"Editorial analysis artifacts are invalid: {exc}") from exc
    project_id = context.project["projectId"]
    duration = float(normalized["durationSeconds"])
    if silence["projectId"] != project_id or repetitions["projectId"] != project_id:
        raise EditorialError("Editorial analysis artifacts belong to another project.")
    if float(silence["sourceDuration"]) != duration:
        raise EditorialError("Silence analysis source duration is stale.")
    for collection_name, collection in (
        ("FFmpeg silence", silence["ffmpegIntervals"]),
        ("silence candidate", silence["candidates"]),
        ("repetition candidate", repetitions["candidates"]),
    ):
        previous_start = -1.0
        previous_end = -1.0
        for item in cast(list[dict[str, Any]], collection):
            start_value = item["sourceStart"] if "sourceStart" in item else item["start"]
            end_value = item["sourceEnd"] if "sourceEnd" in item else item["end"]
            start = float(start_value)
            end = float(end_value)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0
                or end <= start
                or end > duration + 0.001
            ):
                raise EditorialError(f"{collection_name} range is invalid.")
            if start < previous_start:
                raise EditorialError(f"{collection_name} ranges are not ordered.")
            if collection_name != "repetition candidate" and start < previous_end:
                raise EditorialError(f"{collection_name} ranges overlap.")
            previous_start = start
            previous_end = end
    for candidate in cast(list[dict[str, Any]], silence["candidates"]):
        removable = candidate["decision"] == "remove" and candidate["automatic"] is True
        proposed_start = candidate["proposedCutStart"]
        proposed_end = candidate["proposedCutEnd"]
        if removable:
            if not candidate["evidence"]["ffmpegSilence"]:
                raise EditorialError("Automatic silence cut lacks corroborating evidence.")
            if proposed_start is None or proposed_end is None:
                raise EditorialError("Automatic silence cut is missing proposed boundaries.")
            start = float(proposed_start)
            end = float(proposed_end)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < float(candidate["sourceStart"])
                or end > float(candidate["sourceEnd"])
                or end <= start
            ):
                raise EditorialError("Automatic silence cut has invalid proposed boundaries.")
        elif proposed_start is not None or proposed_end is not None:
            raise EditorialError("Non-removal silence candidate cannot propose a cut.")


def _source_to_output(point: float, mappings: list[dict[str, Any]]) -> float:
    for mapping in mappings:
        source_start = float(mapping["sourceStart"])
        source_end = float(mapping["sourceEnd"])
        if source_start - 0.000001 <= point <= source_end + 0.000001:
            return round(float(mapping["outputStart"]) + point - source_start, 6)
        if point < source_start:
            return round(float(mapping["outputStart"]), 6)
    return round(float(mappings[-1]["outputEnd"]), 6)


def build_timeline_documents(
    normalized: dict[str, Any], silence: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    duration = float(normalized["durationSeconds"])
    policy = cast(dict[str, Any], silence["policy"])
    cuts: list[dict[str, Any]] = []
    for candidate in cast(list[dict[str, Any]], silence["candidates"]):
        if candidate["decision"] != "remove" or not candidate["automatic"]:
            continue
        start = float(candidate["proposedCutStart"])
        end = float(candidate["proposedCutEnd"])
        if start < 0 or end <= start or end > duration:
            raise EditorialError("Automatic cut candidate has invalid proposed boundaries.")
        cuts.append(
            {
                "id": f"cut_{len(cuts) + 1:06d}",
                "candidateId": candidate["id"],
                "sourceStart": round(start, 6),
                "sourceEnd": round(end, 6),
                "type": candidate["type"],
                "confidence": candidate["confidence"],
                "decision": "remove",
                "decidedBy": "automatic-rule",
                "automatic": True,
                "padding": {
                    "before": policy["paddingBefore"],
                    "after": policy["paddingAfter"],
                },
            }
        )
    cuts.sort(key=lambda item: float(item["sourceStart"]))
    previous_end = 0.0
    for cut in cuts:
        if float(cut["sourceStart"]) < previous_end:
            raise EditorialError("Automatic cuts overlap.")
        previous_end = float(cut["sourceEnd"])

    keep_ranges: list[tuple[float, float]] = []
    cursor = 0.0
    for cut in cuts:
        start = float(cut["sourceStart"])
        if start > cursor + 0.000001:
            keep_ranges.append((cursor, start))
        cursor = float(cut["sourceEnd"])
    if cursor < duration - 0.000001:
        keep_ranges.append((cursor, duration))
    if not keep_ranges:
        raise EditorialError("Safe-cut policy cannot remove the entire source.")

    segments: list[dict[str, Any]] = []
    output_cursor = 0.0
    for index, (source_start, source_end) in enumerate(keep_ranges, start=1):
        output_end = output_cursor + source_end - source_start
        segments.append(
            {
                "id": f"keep_{index:06d}",
                "sourceStart": round(source_start, 6),
                "sourceEnd": round(source_end, 6),
                "outputStart": round(output_cursor, 6),
                "outputEnd": round(output_end, 6),
                "reason": "retained-source",
                "decision": "keep",
            }
        )
        output_cursor = output_end
    output_duration = round(output_cursor, 6)
    timeline = {
        "version": 1,
        "projectId": normalized["projectId"],
        "sourceDuration": duration,
        "outputDuration": output_duration,
        "segments": segments,
        "cuts": cuts,
    }
    mappings = [
        {
            "timelineSegmentId": segment["id"],
            "sourceStart": segment["sourceStart"],
            "sourceEnd": segment["sourceEnd"],
            "outputStart": segment["outputStart"],
            "outputEnd": segment["outputEnd"],
        }
        for segment in segments
    ]
    time_map = {
        "version": 1,
        "projectId": normalized["projectId"],
        "sourceDuration": duration,
        "outputDuration": output_duration,
        "mappings": mappings,
    }
    remapped_words: list[dict[str, Any]] = []
    for word in cast(list[dict[str, Any]], normalized["words"]):
        source_start = float(word["start"])
        source_end = float(word["end"])
        effective_source_end = min(source_end, duration)
        matching = [
            mapping
            for mapping in mappings
            if float(mapping["sourceStart"]) <= source_start + 0.000001
            and float(mapping["sourceEnd"]) >= effective_source_end - 0.000001
        ]
        if len(matching) != 1:
            raise EditorialError(f"Automatic cut intersects transcript word {word['id']}.")
        mapping = matching[0]
        remapped_words.append(
            {
                **word,
                "sourceStart": word["start"],
                "sourceEnd": word["end"],
                "start": round(
                    float(mapping["outputStart"]) + source_start - float(mapping["sourceStart"]),
                    6,
                ),
                "end": round(
                    float(mapping["outputStart"])
                    + effective_source_end
                    - float(mapping["sourceStart"]),
                    6,
                ),
            }
        )
    remapped_by_id = {cast(str, word["id"]): word for word in remapped_words}
    remapped_segments: list[dict[str, Any]] = []
    for segment in cast(list[dict[str, Any]], normalized["segments"]):
        ids = cast(list[str], segment["wordIds"])
        if ids:
            output_start = remapped_by_id[ids[0]]["start"]
            output_end = remapped_by_id[ids[-1]]["end"]
        else:
            output_start = _source_to_output(float(segment["start"]), mappings)
            output_end = _source_to_output(float(segment["end"]), mappings)
        remapped_segments.append(
            {
                "id": segment["id"],
                "sourceStart": segment["start"],
                "sourceEnd": segment["end"],
                "start": output_start,
                "end": output_end,
                "text": segment["text"],
                "wordIds": ids,
            }
        )
    remapped = {
        "version": 1,
        "projectId": normalized["projectId"],
        "language": normalized["language"],
        "displayLanguage": normalized["displayLanguage"],
        "sourceDuration": duration,
        "durationSeconds": output_duration,
        "segments": remapped_segments,
        "words": remapped_words,
        "provenance": {
            "sourceTranscriptPath": "transcript/transcript.roman.json",
            "timelinePath": "timeline/source-timeline.json",
            "timeMapPath": "timeline/time-map.json",
            "identifiersPreserved": True,
        },
    }
    return timeline, time_map, remapped


def generate_timeline(context: ProjectContext) -> list[str]:
    try:
        normalized = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.roman.json",
            "normalized-transcript",
        )
        silence = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "silence-candidates.json",
            "silence-candidates",
        )
    except PersistenceError as exc:
        raise EditorialError(f"Timeline inputs are invalid: {exc}") from exc
    timeline, time_map, remapped = build_timeline_documents(normalized, silence)
    outputs = (
        ("timeline/source-timeline.json", "timeline", timeline),
        ("timeline/time-map.json", "time-map", time_map),
        ("transcript/transcript.remapped.json", "remapped-transcript", remapped),
    )
    for relative, schema, document in outputs:
        write_validated_json_atomic(
            context.repository_root,
            context.project_dir / relative,
            schema,
            document,
        )
    validate_timeline_outputs(context)
    return [relative for relative, _schema, _document in outputs]


def validate_timeline_outputs(context: ProjectContext) -> None:
    try:
        normalized = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.roman.json",
            "normalized-transcript",
        )
        timeline = read_validated_json(
            context.repository_root,
            context.project_dir / "timeline" / "source-timeline.json",
            "timeline",
        )
        time_map = read_validated_json(
            context.repository_root,
            context.project_dir / "timeline" / "time-map.json",
            "time-map",
        )
        remapped = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.remapped.json",
            "remapped-transcript",
        )
    except PersistenceError as exc:
        raise EditorialError(f"Timeline artifacts are invalid: {exc}") from exc
    project_id = context.project["projectId"]
    documents = (timeline, time_map, remapped)
    if any(document["projectId"] != project_id for document in documents):
        raise EditorialError("Timeline artifacts belong to another project.")
    source_duration = float(normalized["durationSeconds"])
    output_duration = float(timeline["outputDuration"])
    if (
        not math.isfinite(source_duration)
        or not math.isfinite(output_duration)
        or source_duration <= 0
        or output_duration <= 0
    ):
        raise EditorialError("Timeline durations must be finite and positive.")
    if (
        float(timeline["sourceDuration"]) != source_duration
        or float(time_map["sourceDuration"]) != source_duration
        or float(remapped["sourceDuration"]) != source_duration
        or float(time_map["outputDuration"]) != output_duration
        or float(remapped["durationSeconds"]) != output_duration
    ):
        raise EditorialError("Timeline artifact durations are inconsistent.")
    segments = cast(list[dict[str, Any]], timeline["segments"])
    cuts = cast(list[dict[str, Any]], timeline["cuts"])
    mappings = cast(list[dict[str, Any]], time_map["mappings"])
    if len(segments) != len(mappings):
        raise EditorialError("Time map does not match timeline segments.")
    output_cursor = 0.0
    previous_source_end = -1.0
    for segment, mapping in zip(segments, mappings, strict=True):
        values = [
            float(segment["sourceStart"]),
            float(segment["sourceEnd"]),
            float(segment["outputStart"]),
            float(segment["outputEnd"]),
        ]
        if (
            not all(math.isfinite(value) for value in values)
            or values[0] < 0
            or values[1] <= values[0]
            or values[1] > source_duration + 0.00001
            or values[3] <= values[2]
        ):
            raise EditorialError("Timeline contains non-finite ranges.")
        if values[0] < previous_source_end or abs(values[2] - output_cursor) > 0.00001:
            raise EditorialError("Timeline mappings are not monotonic.")
        if abs((values[1] - values[0]) - (values[3] - values[2])) > 0.00001:
            raise EditorialError("Timeline mapping duration changed unexpectedly.")
        expected_mapping = {
            "timelineSegmentId": segment["id"],
            "sourceStart": segment["sourceStart"],
            "sourceEnd": segment["sourceEnd"],
            "outputStart": segment["outputStart"],
            "outputEnd": segment["outputEnd"],
        }
        if mapping != expected_mapping:
            raise EditorialError("Time map entry differs from its timeline segment.")
        previous_source_end = values[1]
        output_cursor = values[3]
    if abs(output_cursor - output_duration) > 0.00001:
        raise EditorialError("Timeline output duration does not match its mappings.")
    previous_cut_end = -1.0
    for cut in cuts:
        start = float(cut["sourceStart"])
        end = float(cut["sourceEnd"])
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or end <= start
            or end > source_duration + 0.00001
            or start < previous_cut_end
        ):
            raise EditorialError("Timeline cuts are invalid or overlapping.")
        previous_cut_end = end
    partition = sorted(
        [(float(segment["sourceStart"]), float(segment["sourceEnd"])) for segment in segments]
        + [(float(cut["sourceStart"]), float(cut["sourceEnd"])) for cut in cuts]
    )
    source_cursor = 0.0
    for start, end in partition:
        if abs(start - source_cursor) > 0.00001:
            raise EditorialError("Timeline keep/cut ranges do not partition the source.")
        source_cursor = end
    if abs(source_cursor - source_duration) > 0.00001:
        raise EditorialError("Timeline does not cover the full source duration.")
    normalized_words = cast(list[dict[str, Any]], normalized["words"])
    remapped_words = cast(list[dict[str, Any]], remapped["words"])
    if len(normalized_words) != len(remapped_words):
        raise EditorialError("Caption remapping changed word count.")
    for source_word, output_word in zip(normalized_words, remapped_words, strict=True):
        for field in (
            "id",
            "segmentId",
            "raw",
            "display",
            "language",
            "source",
            "normalizationSource",
            "lockedTiming",
        ):
            if output_word[field] != source_word[field]:
                raise EditorialError(f"Caption remapping changed immutable field {field}.")
        if (
            output_word["sourceStart"] != source_word["start"]
            or output_word["sourceEnd"] != source_word["end"]
        ):
            raise EditorialError("Caption remapping changed source timestamps.")
        expected_start = _source_to_output(float(source_word["start"]), mappings)
        expected_end = _source_to_output(float(source_word["end"]), mappings)
        actual_start = float(output_word["start"])
        actual_end = float(output_word["end"])
        if (
            not math.isfinite(actual_start)
            or not math.isfinite(actual_end)
            or actual_end <= actual_start
            or actual_end > output_duration + 0.00001
            or actual_start != expected_start
            or actual_end != expected_end
        ):
            raise EditorialError("Caption output timestamps do not match the time map.")
