"""Local Faster-Whisper transcription with immutable timing identifiers."""

from __future__ import annotations

import importlib
import json
import math
import re
import shutil
import subprocess
import sys
import types
import wave
from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from cutmachine.config import load_config
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext, sha256_file


class TranscriptError(RuntimeError):
    """Raised when transcription fails or produces unsafe timing data."""


@dataclass(frozen=True)
class ModelSettings:
    model: str
    device: str
    compute_type: str

    def to_dict(self) -> dict[str, str]:
        return {
            "model": self.model,
            "device": self.device,
            "computeType": self.compute_type,
        }


@dataclass(frozen=True)
class ManualSection:
    text: str
    tokens: tuple[str, ...]
    start: float | None = None
    end: float | None = None


class WordLike(Protocol):
    @property
    def start(self) -> float: ...

    @property
    def end(self) -> float: ...

    @property
    def word(self) -> str: ...

    @property
    def probability(self) -> float: ...


class SegmentLike(Protocol):
    @property
    def start(self) -> float: ...

    @property
    def end(self) -> float: ...

    @property
    def text(self) -> str: ...

    @property
    def words(self) -> Iterable[WordLike] | None: ...


class InfoLike(Protocol):
    @property
    def language(self) -> str: ...

    @property
    def duration(self) -> float: ...


class WhisperModelLike(Protocol):
    def transcribe(
        self, audio: object, **kwargs: object
    ) -> tuple[Iterable[SegmentLike], InfoLike]: ...


ModelFactory = Callable[[ModelSettings], WhisperModelLike]

_DEGENERATE_WORD_DURATION_SECONDS = 0.001
_MANUAL_PARAGRAPH_GAP_SECONDS = 0.18
_MAX_MANUAL_SCRIPT_BYTES = 1_000_000
_MAX_MANUAL_WORDS = 10_000
_MANUAL_TOKEN_PATTERN = re.compile(r"\S+")
_MANUAL_CUE_PATTERN = re.compile(
    r"^(?:\*\*)?(?P<start>\d{1,3}:[0-5]\d(?:[:][0-5]\d)?)"
    r"\s*[-\u2013\u2014]\s*"
    r"(?P<end>\d{1,3}:[0-5]\d(?:[:][0-5]\d)?|End)(?:\*\*)?$",
    re.IGNORECASE,
)


def detect_gpu_memory_mb() -> int | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    values: list[int] = []
    for line in result.stdout.splitlines():
        try:
            values.append(int(line.strip()))
        except ValueError:
            continue
    return max(values) if values else None


def select_model_settings(
    config: dict[str, Any], mode: str, gpu_memory_mb: int | None
) -> ModelSettings:
    models = cast(dict[str, str], config["transcription"]["models"])
    model = models[mode]
    if gpu_memory_mb is not None and gpu_memory_mb >= 4096:
        return ModelSettings(model=model, device="cuda", compute_type="float16")
    return ModelSettings(model=model, device="cpu", compute_type="int8")


def fallback_settings(config: dict[str, Any]) -> ModelSettings:
    model = cast(str, config["transcription"]["fallback_model"])
    return ModelSettings(model=model, device="cpu", compute_type="int8")


def load_whisper_model(settings: ModelSettings) -> WhisperModelLike:
    try:
        # CutMachine supplies a decoded waveform, so Faster-Whisper never needs PyAV.
        # Avoid loading blocked unsigned PyAV DLLs on locked-down Windows systems.
        sys.modules.setdefault("av", types.ModuleType("av"))
        module = importlib.import_module("faster_whisper")
        model_class = module.WhisperModel
    except (ImportError, AttributeError) as exc:
        raise TranscriptError(
            'Faster-Whisper is not installed. Run `python -m pip install -e ".[dev]"`.'
        ) from exc
    return cast(
        WhisperModelLike,
        model_class(settings.model, device=settings.device, compute_type=settings.compute_type),
    )


def decode_transcription_wav(path: Path) -> object:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            frames = handle.readframes(handle.getnframes())
    except (OSError, wave.Error) as exc:
        raise TranscriptError(f"Could not read transcription WAV: {exc}") from exc
    if channels != 1 or sample_rate != 16000 or sample_width != 2:
        raise TranscriptError("Transcription WAV must be mono, 16 kHz, signed 16-bit PCM.")
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    numpy = importlib.import_module("numpy")
    waveform = numpy.asarray(samples, dtype=numpy.float32) / 32768.0
    return cast(object, waveform)


def _load_glossary(repository_root: Path) -> list[str]:
    path = repository_root / "config" / "technical-glossary.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranscriptError(f"Could not load technical glossary: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("terms"), list):
        raise TranscriptError("Technical glossary must contain a terms array.")
    terms = [item.strip() for item in value["terms"] if isinstance(item, str) and item.strip()]
    return terms


def _finite_timestamp(value: object, label: str) -> float:
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise TranscriptError(f"Invalid {label}: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise TranscriptError(f"Invalid {label}: {value!r}")
    return round(number, 6)


def _manual_clock(value: str) -> float:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes * 60 + seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours * 3600 + minutes * 60 + seconds)
    raise TranscriptError(f"Invalid manual transcript timecode: {value!r}")


def _validate_manual_sections(sections: list[ManualSection]) -> list[ManualSection]:
    word_count = sum(len(section.tokens) for section in sections)
    if word_count == 0:
        raise TranscriptError("Manual transcript does not contain any words.")
    if word_count > _MAX_MANUAL_WORDS:
        raise TranscriptError(f"Manual transcript exceeds the {_MAX_MANUAL_WORDS}-word limit.")
    if any(len(token) > 200 for section in sections for token in section.tokens):
        raise TranscriptError("Manual transcript contains a word longer than 200 characters.")
    return sections


def _plain_manual_sections(text: str) -> list[ManualSection]:
    sections: list[ManualSection] = []
    for line in text.splitlines():
        paragraph = line.strip()
        if not paragraph:
            continue
        tokens = tuple(_MANUAL_TOKEN_PATTERN.findall(paragraph))
        if tokens:
            sections.append(ManualSection(paragraph, tokens))
    return _validate_manual_sections(sections)


def _manual_sections(text: str, duration: float) -> tuple[list[ManualSection], bool]:
    if "\x00" in text:
        raise TranscriptError("Manual transcript contains a null byte.")
    meaningful = [line.strip() for line in text.splitlines() if line.strip()]
    matches = [_MANUAL_CUE_PATTERN.fullmatch(line) for line in meaningful]
    if not any(matches):
        malformed = next(
            (
                line
                for line in meaningful
                if line.startswith("**") and line.endswith("**") and ":" in line
            ),
            None,
        )
        if malformed is not None:
            raise TranscriptError(f"Malformed manual transcript cue header: {malformed!r}")
        return _plain_manual_sections(text), False
    if not matches[0]:
        raise TranscriptError("Timestamped manual transcript must begin with a cue header.")

    sections: list[ManualSection] = []
    current_start: float | None = None
    current_end: float | None = None
    body: list[str] = []

    def finish_section() -> None:
        nonlocal body
        if current_start is None or current_end is None:
            return
        paragraph = " ".join(body).strip()
        tokens = tuple(_MANUAL_TOKEN_PATTERN.findall(paragraph))
        if not tokens:
            raise TranscriptError("Timestamped manual transcript contains an empty cue.")
        sections.append(ManualSection(paragraph, tokens, current_start, current_end))
        body = []

    previous_end = 0.0
    for index, (line, match) in enumerate(zip(meaningful, matches, strict=True)):
        if match is None:
            if line.startswith("**") and line.endswith("**") and ":" in line:
                raise TranscriptError(f"Malformed manual transcript cue header: {line!r}")
            if current_start is None:
                raise TranscriptError(
                    "Timestamped manual transcript has text before its first cue."
                )
            body.append(line)
            continue

        finish_section()
        start = _manual_clock(match.group("start"))
        end_label = match.group("end")
        is_end = end_label.casefold() == "end"
        if is_end and any(matches[index + 1 :]):
            raise TranscriptError("End is allowed only on the final timestamped transcript cue.")
        end = duration if is_end else _manual_clock(end_label)
        if start < previous_end - 0.000001:
            raise TranscriptError(
                "Timestamped manual transcript cues overlap or are non-monotonic."
            )
        if end <= start:
            raise TranscriptError("Timestamped manual transcript cue must have positive duration.")
        if end > duration + 0.000001:
            raise TranscriptError("Timestamped manual transcript cue exceeds media duration.")
        current_start = round(start, 6)
        current_end = round(end, 6)
        previous_end = end
    finish_section()
    return _validate_manual_sections(sections), True


def _manual_speech_bounds(context: ProjectContext, duration: float) -> tuple[float, float]:
    speech_start = 0.0
    speech_end = duration
    silence_path = context.project_dir / "analysis" / "silence-candidates.json"
    if silence_path.is_file():
        try:
            silence = read_validated_json(
                context.repository_root, silence_path, "silence-candidates"
            )
            intervals = cast(list[dict[str, Any]], silence["ffmpegIntervals"])
            if intervals and float(intervals[0]["start"]) <= 0.05:
                speech_start = float(intervals[0]["end"])
            if intervals and float(intervals[-1]["end"]) >= duration - 0.05:
                speech_end = float(intervals[-1]["start"])
        except (KeyError, TypeError, ValueError, PersistenceError):
            speech_start = 0.0
            speech_end = duration
    if speech_end - speech_start < 1.0:
        raise TranscriptError("Manual transcript has no usable speech-duration boundary.")
    return round(speech_start, 6), round(speech_end, 6)


def _manual_word_weight(token: str) -> float:
    core = "".join(character for character in token if character.isalnum())
    weight = max(1.0, min(12.0, float(len(core))) ** 0.65)
    if token.endswith((".", "?", "!")):
        weight += 1.2
    elif token.endswith((",", ";", ":")):
        weight += 0.45
    return float(weight)


def _build_manual_document(
    context: ProjectContext,
    text: str,
    *,
    script_relative: str,
    script_sha256: str,
) -> dict[str, Any]:
    media_info = read_validated_json(
        context.repository_root,
        context.project_dir / "analysis" / "media-info.json",
        "media-info",
    )
    duration = float(cast(dict[str, Any], media_info["format"])["durationSeconds"])
    manual_sections, timestamped = _manual_sections(text, duration)
    words: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []

    def add_section(
        segment_index: int,
        section: ManualSection,
        start: float,
        end: float,
    ) -> None:
        segment_id = f"segment_{segment_index:06d}"
        available = end - start
        weights = [_manual_word_weight(token) for token in section.tokens]
        if available <= len(weights) * _DEGENERATE_WORD_DURATION_SECONDS:
            raise TranscriptError("Manual transcript cue is too short for its supplied words.")
        total_weight = sum(weights)
        cursor = start
        word_ids: list[str] = []
        for token_index, (token, weight) in enumerate(
            zip(section.tokens, weights, strict=True), start=1
        ):
            word_start = round(cursor, 6)
            cursor += available * weight / total_weight
            is_final_word = token_index == len(section.tokens)
            word_end = end if is_final_word else round(cursor, 6)
            if word_end <= word_start:
                raise TranscriptError("Manual transcript alignment produced invalid timing.")
            word_id = f"word_{len(words) + 1:06d}"
            words.append(
                {
                    "id": word_id,
                    "segmentId": segment_id,
                    "start": word_start,
                    "end": word_end,
                    "raw": token,
                    "display": token,
                    "language": "roman-urdu",
                    "confidence": 1.0,
                    "source": "manual-script",
                    "normalizationSource": "manual-script",
                    "lockedTiming": True,
                }
            )
            word_ids.append(word_id)
        segments.append(
            {
                "id": segment_id,
                "start": round(start, 6),
                "end": round(end, 6),
                "text": section.text,
                "wordIds": word_ids,
            }
        )

    if timestamped:
        for segment_index, section in enumerate(manual_sections, start=1):
            assert section.start is not None and section.end is not None
            add_section(segment_index, section, section.start, section.end)
    else:
        speech_start, speech_end = _manual_speech_bounds(context, duration)
        gap_count = max(0, len(manual_sections) - 1)
        gap_total = gap_count * _MANUAL_PARAGRAPH_GAP_SECONDS
        available = speech_end - speech_start - gap_total
        all_weights = [
            _manual_word_weight(token) for section in manual_sections for token in section.tokens
        ]
        if available <= len(all_weights) * _DEGENERATE_WORD_DURATION_SECONDS:
            raise TranscriptError("Manual transcript is too long for the source duration.")
        total_weight = sum(all_weights)
        cursor = speech_start
        weight_index = 0
        for segment_index, section in enumerate(manual_sections, start=1):
            section_start = cursor
            section_weight = sum(all_weights[weight_index : weight_index + len(section.tokens)])
            section_end = cursor + available * section_weight / total_weight
            if segment_index == len(manual_sections):
                section_end = speech_end
            add_section(
                segment_index,
                section,
                round(section_start, 6),
                round(section_end, 6),
            )
            cursor = section_end + _MANUAL_PARAGRAPH_GAP_SECONDS
            weight_index += len(section.tokens)
    manual_settings = ModelSettings("manual-script", "cpu", "deterministic-alignment")
    return {
        "version": 1,
        "projectId": context.project["projectId"],
        "language": "roman-urdu",
        "durationSeconds": duration,
        "segments": segments,
        "words": words,
        "provenance": {
            "createdAt": datetime.now(UTC).isoformat(),
            "audioPath": "audio/source.wav",
            "requested": manual_settings.to_dict(),
            "effective": manual_settings.to_dict(),
            "fallbackReason": "Authoritative user-supplied Roman Urdu transcript.",
            "wordTimestamps": True,
            "vadEnabled": False,
            "manualScriptPath": script_relative,
            "manualScriptSha256": script_sha256,
            "alignmentMethod": (
                "timestamped-script-cues" if timestamped else "weighted-script-duration"
            ),
        },
    }


def import_manual_transcript(context: ProjectContext, relative_path: str) -> list[str]:
    try:
        script = resolve_inside(context.project_dir, relative_path)
    except UnsafePathError as exc:
        raise TranscriptError(f"Unsafe manual transcript path: {exc}") from exc
    if script.suffix.casefold() != ".txt":
        raise TranscriptError("Manual transcript must be a project-relative .txt file.")
    if not script.is_file():
        raise TranscriptError(f"Manual transcript is missing: {relative_path}")
    if script.stat().st_size > _MAX_MANUAL_SCRIPT_BYTES:
        raise TranscriptError("Manual transcript exceeds the 1 MB size limit.")
    try:
        text = script.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TranscriptError("Manual transcript must be readable UTF-8 text.") from exc
    script_relative = script.relative_to(context.project_dir).as_posix()
    document = _build_manual_document(
        context,
        text,
        script_relative=script_relative,
        script_sha256=sha256_file(script),
    )
    raw_path = context.project_dir / "transcript" / "transcript.raw.json"
    snapshot_path = context.project_dir / "transcript" / "transcript.asr.json"
    if raw_path.is_file() and not snapshot_path.exists():
        existing = read_validated_json(context.repository_root, raw_path, "transcript")
        write_validated_json_atomic(context.repository_root, snapshot_path, "transcript", existing)
    write_validated_json_atomic(context.repository_root, raw_path, "transcript", document)
    artifacts = [raw_path, script]
    if snapshot_path.is_file():
        artifacts.append(snapshot_path)
    return [path.relative_to(context.project_dir).as_posix() for path in artifacts]


def _build_document(
    context: ProjectContext,
    segments_input: Iterable[SegmentLike],
    info: InfoLike,
    requested: ModelSettings,
    effective: ModelSettings,
    fallback_reason: str | None,
    audio_path: str,
    vad_enabled: bool,
) -> dict[str, Any]:
    media_info = read_validated_json(
        context.repository_root,
        context.project_dir / "analysis" / "media-info.json",
        "media-info",
    )
    duration = float(cast(dict[str, Any], media_info["format"])["durationSeconds"])
    language = (
        info.language.strip() if isinstance(info.language, str) and info.language.strip() else "ur"
    )
    words: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    previous_word_end = 0.0
    previous_segment_start = 0.0

    for segment_index, source_segment in enumerate(segments_input, start=1):
        segment_id = f"segment_{segment_index:06d}"
        segment_start = _finite_timestamp(source_segment.start, "segment start")
        segment_end = _finite_timestamp(source_segment.end, "segment end")
        if segment_end < segment_start:
            raise TranscriptError(f"Segment {segment_id} ends before it starts.")
        if segment_start + 0.05 < previous_segment_start:
            raise TranscriptError(f"Segment {segment_id} is not monotonic.")
        previous_segment_start = max(previous_segment_start, segment_start)
        word_ids: list[str] = []

        for source_word in source_segment.words or ():
            text = source_word.word.strip()
            if not text:
                continue
            start = _finite_timestamp(source_word.start, "word start")
            end = _finite_timestamp(source_word.end, "word end")
            degenerate_timestamp = end == start
            if end < start:
                raise TranscriptError(f"Word {text!r} has a non-positive duration.")
            if start < previous_word_end:
                overlap = previous_word_end - start
                if overlap > 0.05:
                    raise TranscriptError(
                        f"Word {text!r} overlaps the previous word by {overlap:.3f}s."
                    )
                start = previous_word_end
                if end <= start and not degenerate_timestamp:
                    raise TranscriptError(f"Word {text!r} collapses after overlap repair.")
            if end <= start:
                # Faster-Whisper can occasionally emit an otherwise valid token
                # with identical start/end alignment. Preserve the token and its
                # source start while assigning the smallest schema-valid interval.
                end = round(
                    min(duration + 2.0, start + _DEGENERATE_WORD_DURATION_SECONDS),
                    6,
                )
                if end <= start:
                    raise TranscriptError(
                        f"Word {text!r} cannot be repaired inside the source boundary."
                    )
            confidence = min(1.0, max(0.0, float(source_word.probability)))
            word_id = f"word_{len(words) + 1:06d}"
            words.append(
                {
                    "id": word_id,
                    "segmentId": segment_id,
                    "start": start,
                    "end": end,
                    "raw": text,
                    "display": text,
                    "language": language,
                    "confidence": confidence,
                    "source": "faster-whisper",
                    "normalizationSource": "raw-transcript",
                    "lockedTiming": True,
                }
            )
            word_ids.append(word_id)
            previous_word_end = end
            segment_start = min(segment_start, start)
            segment_end = max(segment_end, end)

        segments.append(
            {
                "id": segment_id,
                "start": segment_start,
                "end": segment_end,
                "text": source_segment.text.strip(),
                "wordIds": word_ids,
            }
        )

    if words and float(words[-1]["end"]) > duration + 2.0:
        raise TranscriptError("Transcript extends more than two seconds beyond source duration.")
    return {
        "version": 1,
        "projectId": context.project["projectId"],
        "language": language,
        "durationSeconds": duration,
        "segments": segments,
        "words": words,
        "provenance": {
            "createdAt": datetime.now(UTC).isoformat(),
            "audioPath": audio_path,
            "requested": requested.to_dict(),
            "effective": effective.to_dict(),
            "fallbackReason": fallback_reason,
            "wordTimestamps": True,
            "vadEnabled": vad_enabled,
        },
    }


def transcribe_project(
    context: ProjectContext,
    *,
    model_factory: ModelFactory = load_whisper_model,
    gpu_memory_mb: int | None = None,
) -> list[str]:
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    requested = select_model_settings(
        config,
        cast(str, context.project["mode"]),
        detect_gpu_memory_mb() if gpu_memory_mb is None else gpu_memory_mb,
    )
    fallback = fallback_settings(config)
    audio_relative = "audio/source.wav"
    audio = resolve_inside(context.project_dir, audio_relative)
    if not audio.is_file():
        raise TranscriptError(f"Transcription audio is missing: {audio_relative}")
    glossary = _load_glossary(context.repository_root)
    waveform = decode_transcription_wav(audio)
    transcription_config = cast(dict[str, Any], config["transcription"])
    kwargs: dict[str, object] = {
        "language": cast(str, transcription_config["language"]),
        "word_timestamps": True,
        "vad_filter": bool(transcription_config["vad"]),
        "beam_size": int(transcription_config["beam_size"]),
        # The initial prompt only biases the first window; hotwords keep the
        # technical glossary active in every window of a long recording.
        "initial_prompt": ", ".join(glossary),
        "hotwords": " ".join(glossary) or None,
        "condition_on_previous_text": False,
        "hallucination_silence_threshold": float(
            transcription_config["hallucination_silence_threshold"]
        ),
    }
    effective = requested
    fallback_reason: str | None = None
    try:
        model = model_factory(requested)
        raw_segments, info = model.transcribe(waveform, **kwargs)
        segments = list(raw_segments)
    except Exception as exc:
        if requested == fallback:
            raise TranscriptError(f"Faster-Whisper transcription failed: {exc}") from exc
        fallback_reason = f"{type(exc).__name__}: {exc}"[-1000:]
        effective = fallback
        try:
            model = model_factory(fallback)
            raw_segments, info = model.transcribe(waveform, **kwargs)
            segments = list(raw_segments)
        except Exception as fallback_exc:
            raise TranscriptError(
                f"Faster-Whisper failed with requested and fallback settings: {fallback_exc}"
            ) from fallback_exc

    document = _build_document(
        context,
        segments,
        info,
        requested,
        effective,
        fallback_reason,
        audio_relative,
        bool(transcription_config["vad"]),
    )
    output = context.project_dir / "transcript" / "transcript.raw.json"
    write_validated_json_atomic(
        context.repository_root,
        output,
        "transcript",
        document,
    )
    return [output.relative_to(context.project_dir).as_posix()]


def validate_transcript_outputs(context: ProjectContext) -> None:
    path = context.project_dir / "transcript" / "transcript.raw.json"
    try:
        document = read_validated_json(context.repository_root, path, "transcript")
    except PersistenceError as exc:
        raise TranscriptError(f"Raw transcript is missing or invalid: {exc}") from exc
    segments = cast(list[dict[str, Any]], document["segments"])
    words = cast(list[dict[str, Any]], document["words"])
    if document["projectId"] != context.project["projectId"]:
        raise TranscriptError("Raw transcript belongs to a different project.")
    sources = {cast(str, word["source"]) for word in words}
    if len(sources) > 1:
        raise TranscriptError("Raw transcript mixes incompatible word sources.")
    if sources == {"manual-script"}:
        provenance = cast(dict[str, Any], document["provenance"])
        relative = provenance.get("manualScriptPath")
        expected_hash = provenance.get("manualScriptSha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise TranscriptError("Manual transcript provenance is incomplete.")
        try:
            script = resolve_inside(context.project_dir, relative)
        except UnsafePathError as exc:
            raise TranscriptError(f"Manual transcript provenance is unsafe: {exc}") from exc
        if not script.is_file() or sha256_file(script) != expected_hash:
            raise TranscriptError("Manual transcript source changed after import.")
        try:
            manual_sections, timestamped = _manual_sections(
                script.read_text(encoding="utf-8"), float(document["durationSeconds"])
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise TranscriptError("Manual transcript source is unreadable.") from exc
        expected_tokens = [token for section in manual_sections for token in section.tokens]
        if [cast(str, word["raw"]) for word in words] != expected_tokens:
            raise TranscriptError("Manual transcript words do not match the source script.")
        if len(segments) != len(manual_sections):
            raise TranscriptError("Manual transcript segments do not match the source script.")
        for segment, section in zip(segments, manual_sections, strict=True):
            if segment["text"] != section.text:
                raise TranscriptError("Manual transcript segment text changed after import.")
            if timestamped and (
                float(segment["start"]) != section.start or float(segment["end"]) != section.end
            ):
                raise TranscriptError(
                    "Timestamped manual transcript cue timing changed after import."
                )
    word_by_id = {cast(str, word["id"]): word for word in words}
    previous_end = 0.0
    for index, word in enumerate(words, start=1):
        expected_id = f"word_{index:06d}"
        if word["id"] != expected_id:
            raise TranscriptError(f"Transcript word ID sequence is broken at {expected_id}.")
        start = float(word["start"])
        end = float(word["end"])
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise TranscriptError(f"Transcript word {expected_id} has invalid timestamps.")
        if start < previous_end:
            raise TranscriptError(f"Transcript word {expected_id} is not monotonic.")
        previous_end = end
    for index, segment in enumerate(segments, start=1):
        expected_id = f"segment_{index:06d}"
        if segment["id"] != expected_id:
            raise TranscriptError(f"Transcript segment ID sequence is broken at {expected_id}.")
        segment_start = float(segment["start"])
        segment_end = float(segment["end"])
        if (
            not math.isfinite(segment_start)
            or not math.isfinite(segment_end)
            or segment_end < segment_start
        ):
            raise TranscriptError(f"Transcript segment {expected_id} has invalid timestamps.")
        if index > 1 and segment_start < float(segments[index - 2]["start"]):
            raise TranscriptError(f"Transcript segment {expected_id} is not monotonic.")
        for word_id in cast(list[str], segment["wordIds"]):
            referenced_word = word_by_id.get(word_id)
            if referenced_word is None or referenced_word["segmentId"] != expected_id:
                raise TranscriptError(
                    f"Transcript segment {expected_id} has an invalid word reference."
                )
            if (
                float(referenced_word["start"]) < segment_start
                or float(referenced_word["end"]) > segment_end
            ):
                raise TranscriptError(f"Word {word_id} falls outside segment {expected_id}.")
