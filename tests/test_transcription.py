from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cutmachine.config import load_config
from cutmachine.project import ProjectContext
from cutmachine.transcription import (
    ModelSettings,
    TranscriptError,
    import_manual_transcript,
    select_model_settings,
    transcribe_project,
    validate_transcript_outputs,
)


@dataclass
class FakeWord:
    start: float
    end: float
    word: str
    probability: float = 0.9


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str
    words: list[FakeWord]


@dataclass
class FakeInfo:
    language: str = "ur"
    duration: float = 2.0


class FakeModel:
    def __init__(self, segments: list[FakeSegment]) -> None:
        self.segments = segments
        self.kwargs: dict[str, object] = {}

    def transcribe(self, audio: object, **kwargs: object) -> tuple[list[FakeSegment], FakeInfo]:
        assert not isinstance(audio, str)
        self.kwargs = kwargs
        return self.segments, FakeInfo()


def _segments() -> list[FakeSegment]:
    return [
        FakeSegment(
            0.1,
            1.2,
            "AI bohat useful hai",
            [
                FakeWord(0.1, 0.3, "AI", 0.99),
                FakeWord(0.31, 0.55, "bohat", 0.92),
                FakeWord(0.56, 0.85, "useful", 0.95),
                FakeWord(0.86, 1.1, "hai", 0.91),
            ],
        )
    ]


def test_hardware_policy_is_bounded(repository: Path) -> None:
    config = load_config(repository, style="balanced")

    assert select_model_settings(config, "fast", None) == ModelSettings("small", "cpu", "int8")
    assert select_model_settings(config, "balanced", 8192) == ModelSettings(
        "medium", "cuda", "float16"
    )
    assert select_model_settings(config, "energetic", 4096) == ModelSettings(
        "medium", "cuda", "float16"
    )
    assert select_model_settings(config, "cinematic", 2048) == ModelSettings(
        "large-v3", "cpu", "int8"
    )


def test_fake_transcription_writes_stable_monotonic_ids(
    ingested_context: ProjectContext,
) -> None:
    model = FakeModel(_segments())

    artifacts = transcribe_project(
        ingested_context,
        model_factory=lambda _settings: model,
        gpu_memory_mb=0,
    )
    validate_transcript_outputs(ingested_context)
    document = json.loads((ingested_context.project_dir / artifacts[0]).read_text(encoding="utf-8"))

    assert [word["id"] for word in document["words"]] == [
        "word_000001",
        "word_000002",
        "word_000003",
        "word_000004",
    ]
    assert document["segments"][0]["wordIds"] == [word["id"] for word in document["words"]]
    assert model.kwargs["word_timestamps"] is True
    assert model.kwargs["vad_filter"] is True
    assert "ChatGPT" in str(model.kwargs["initial_prompt"])


def test_small_word_overlap_is_repaired(ingested_context: ProjectContext) -> None:
    segments = [
        FakeSegment(
            0.1,
            0.9,
            "do lafz",
            [FakeWord(0.1, 0.5, "do"), FakeWord(0.48, 0.8, "lafz")],
        )
    ]

    transcribe_project(
        ingested_context,
        model_factory=lambda _settings: FakeModel(segments),
        gpu_memory_mb=0,
    )
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.raw.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["words"][1]["start"] == 0.5


def test_large_word_overlap_is_rejected(ingested_context: ProjectContext) -> None:
    segments = [
        FakeSegment(
            0.1,
            0.9,
            "bad timing",
            [FakeWord(0.1, 0.6, "bad"), FakeWord(0.2, 0.8, "timing")],
        )
    ]

    with pytest.raises(TranscriptError, match="overlaps the previous word"):
        transcribe_project(
            ingested_context,
            model_factory=lambda _settings: FakeModel(segments),
            gpu_memory_mb=0,
        )


def test_empty_words_are_skipped_without_consuming_ids(
    ingested_context: ProjectContext,
) -> None:
    segments = [
        FakeSegment(
            0.1,
            0.9,
            "one word",
            [FakeWord(0.1, 0.2, "  "), FakeWord(0.3, 0.6, "word")],
        )
    ]

    transcribe_project(
        ingested_context,
        model_factory=lambda _settings: FakeModel(segments),
        gpu_memory_mb=0,
    )
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.raw.json").read_text(
            encoding="utf-8"
        )
    )

    assert [word["id"] for word in document["words"]] == ["word_000001"]
    assert document["words"][0]["raw"] == "word"


def test_reversed_word_timestamps_are_rejected(ingested_context: ProjectContext) -> None:
    segments = [FakeSegment(0.1, 0.9, "bad", [FakeWord(0.7, 0.2, "bad")])]

    with pytest.raises(TranscriptError, match="non-positive duration"):
        transcribe_project(
            ingested_context,
            model_factory=lambda _settings: FakeModel(segments),
            gpu_memory_mb=0,
        )


def test_zero_length_word_timestamp_gets_minimal_deterministic_duration(
    ingested_context: ProjectContext,
) -> None:
    segments = [
        FakeSegment(
            0.1,
            0.9,
            "har giz nahi",
            [
                FakeWord(0.1, 0.3, "har"),
                FakeWord(0.3, 0.3, "giz"),
                FakeWord(0.31, 0.6, "nahi"),
            ],
        )
    ]

    transcribe_project(
        ingested_context,
        model_factory=lambda _settings: FakeModel(segments),
        gpu_memory_mb=0,
    )
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.raw.json").read_text(
            encoding="utf-8"
        )
    )

    assert document["words"][1]["start"] == 0.3
    assert document["words"][1]["end"] == 0.301
    validate_transcript_outputs(ingested_context)


def test_manual_roman_transcript_preserves_exact_words_and_source_hash(
    ingested_context: ProjectContext,
) -> None:
    script = ingested_context.project_dir / "transcript" / "manual-script.txt"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "Us raat ChatGPT se baat hui.\n\nThank you for watching.",
        encoding="utf-8",
    )

    artifacts = import_manual_transcript(ingested_context, "transcript/manual-script.txt")
    validate_transcript_outputs(ingested_context)
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.raw.json").read_text(
            encoding="utf-8"
        )
    )

    assert artifacts == [
        "transcript/transcript.raw.json",
        "transcript/manual-script.txt",
    ]
    assert [word["raw"] for word in document["words"]] == [
        "Us",
        "raat",
        "ChatGPT",
        "se",
        "baat",
        "hui.",
        "Thank",
        "you",
        "for",
        "watching.",
    ]
    assert {word["source"] for word in document["words"]} == {"manual-script"}
    assert document["segments"][0]["text"] == "Us raat ChatGPT se baat hui."
    assert document["segments"][1]["text"] == "Thank you for watching."
    assert document["provenance"]["alignmentMethod"] == "weighted-script-duration"

    script.write_text("changed", encoding="utf-8")
    with pytest.raises(TranscriptError, match="changed after import"):
        validate_transcript_outputs(ingested_context)


def test_timestamped_manual_transcript_uses_cues_without_captioning_headers(
    ingested_context: ProjectContext,
) -> None:
    script = ingested_context.project_dir / "transcript" / "timestamped-script.txt"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "**0:00\u20130:01**\nUs raat ChatGPT se baat hui.\n\n"
        "**0:01\u2013End**\nThank you for watching.",
        encoding="utf-8",
    )

    import_manual_transcript(ingested_context, "transcript/timestamped-script.txt")
    validate_transcript_outputs(ingested_context)
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.raw.json").read_text(
            encoding="utf-8"
        )
    )

    assert [word["raw"] for word in document["words"]] == [
        "Us",
        "raat",
        "ChatGPT",
        "se",
        "baat",
        "hui.",
        "Thank",
        "you",
        "for",
        "watching.",
    ]
    assert document["segments"][0]["start"] == 0
    assert document["segments"][0]["end"] == 1
    assert document["segments"][1]["start"] == 1
    assert document["segments"][1]["end"] == document["durationSeconds"]
    assert document["provenance"]["alignmentMethod"] == "timestamped-script-cues"
    assert all("**" not in word["raw"] for word in document["words"])


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "**0:00\u20130:02**\nFirst cue.\n**0:01\u2013End**\nSecond cue.",
            "overlap",
        ),
        ("**0:01\u20130:00**\nReverse cue.", "positive duration"),
        ("**0:00\u20130:03**\nToo long.", "exceeds media duration"),
        (
            "**0:00\u2013End**\nNot final.\n**0:01\u20130:02**\nLater cue.",
            "End is allowed only",
        ),
        ("**0:00\u20130:01**\n**0:01\u2013End**\nMissing first cue.", "empty cue"),
        ("Text before cue.\n**0:00\u2013End**\nLater cue.", "must begin with a cue"),
        ("**0:00 to End**\nMalformed cue.", "Malformed"),
    ],
)
def test_timestamped_manual_transcript_rejects_invalid_cues(
    ingested_context: ProjectContext, text: str, message: str
) -> None:
    script = ingested_context.project_dir / "transcript" / "invalid-timestamped.txt"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(text, encoding="utf-8")

    with pytest.raises(TranscriptError, match=message):
        import_manual_transcript(ingested_context, "transcript/invalid-timestamped.txt")


def test_timestamped_manual_transcript_rejects_persisted_cue_tampering(
    ingested_context: ProjectContext,
) -> None:
    script = ingested_context.project_dir / "transcript" / "timestamped-script.txt"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("**0:00\u2013End**\nExact supplied words.", encoding="utf-8")
    import_manual_transcript(ingested_context, "transcript/timestamped-script.txt")
    raw = ingested_context.project_dir / "transcript" / "transcript.raw.json"
    document = json.loads(raw.read_text(encoding="utf-8"))
    document["segments"][0]["start"] = 0.1
    raw.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(TranscriptError, match="cue timing changed"):
        validate_transcript_outputs(ingested_context)


def test_manual_transcript_rejects_unsafe_path(ingested_context: ProjectContext) -> None:
    with pytest.raises(TranscriptError, match="Unsafe manual transcript path"):
        import_manual_transcript(ingested_context, "../manual-script.txt")


def test_validation_rejects_non_finite_persisted_segment(
    ingested_context: ProjectContext,
) -> None:
    transcribe_project(
        ingested_context,
        model_factory=lambda _settings: FakeModel(_segments()),
        gpu_memory_mb=0,
    )
    path = ingested_context.project_dir / "transcript" / "transcript.raw.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["segments"][0]["start"] = float("nan")
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(TranscriptError, match="invalid timestamps"):
        validate_transcript_outputs(ingested_context)


def test_gpu_failure_uses_cpu_fallback(ingested_context: ProjectContext) -> None:
    requested: list[ModelSettings] = []

    def factory(settings: ModelSettings) -> FakeModel:
        requested.append(settings)
        if settings.device == "cuda":
            raise RuntimeError("CUDA runtime unavailable")
        return FakeModel(_segments())

    transcribe_project(ingested_context, model_factory=factory, gpu_memory_mb=8192)
    document: dict[str, Any] = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.raw.json").read_text(
            encoding="utf-8"
        )
    )

    assert [settings.device for settings in requested] == ["cuda", "cpu"]
    assert document["provenance"]["effective"] == {
        "model": "tiny",
        "device": "cpu",
        "computeType": "int8",
    }
    assert "CUDA runtime unavailable" in document["provenance"]["fallbackReason"]
