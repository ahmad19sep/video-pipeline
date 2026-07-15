from __future__ import annotations

from typing import Any

import pytest

from cutmachine.editorial import (
    EditorialError,
    build_analysis_documents,
    build_timeline_documents,
    parse_silence_output,
)

SILENCE_CONFIG = {
    "threshold_db": -35,
    "minimum_seconds": 0.55,
    "auto_remove_seconds": 1.35,
    "padding_before": 0.1,
    "padding_after": 0.2,
}
REPETITION_CONFIG = {"similarity_threshold": 0.85, "nearby_seconds": 12.0}


def _word(index: int, start: float, end: float, display: str) -> dict[str, Any]:
    return {
        "id": f"word_{index:06d}",
        "segmentId": f"segment_{index:06d}",
        "start": start,
        "end": end,
        "raw": display,
        "display": display,
        "language": "ur",
        "confidence": 0.9,
        "source": "faster-whisper",
        "normalizationSource": "preserved",
        "lockedTiming": True,
    }


def _normalized(words: list[dict[str, Any]], duration: float = 10.0) -> dict[str, Any]:
    segments = [
        {
            "id": word["segmentId"],
            "start": word["start"],
            "end": word["end"],
            "text": word["display"],
            "wordIds": [word["id"]],
        }
        for word in words
    ]
    return {
        "version": 1,
        "projectId": "prj_editorial",
        "language": "ur",
        "displayLanguage": "roman-urdu",
        "durationSeconds": duration,
        "segments": segments,
        "words": words,
        "provenance": {},
    }


def test_ffmpeg_silence_parser_handles_terminal_interval() -> None:
    output = """
[silencedetect] silence_start: 0
[silencedetect] silence_end: 1.5 | silence_duration: 1.5
[silencedetect] silence_start: 8.2
"""

    assert parse_silence_output(output, 10.0) == [(0.0, 1.5), (8.2, 10.0)]


def test_corroborated_gaps_create_safe_multiple_cuts_and_remap_words() -> None:
    words = [
        _word(1, 2.0, 3.0, "one"),
        _word(2, 5.0, 6.0, "two"),
        _word(3, 8.0, 9.0, "three"),
    ]
    normalized = _normalized(words)
    silence, repetitions = build_analysis_documents(
        "prj_editorial",
        10.0,
        words,
        normalized["segments"],
        [(0.0, 2.0), (3.0, 5.0), (6.0, 8.0), (9.0, 10.0)],
        SILENCE_CONFIG,
        REPETITION_CONFIG,
    )

    assert [candidate["decision"] for candidate in silence["candidates"]] == [
        "remove",
        "remove",
        "remove",
        "review",
    ]
    assert repetitions["candidates"] == []

    timeline, time_map, remapped = build_timeline_documents(normalized, silence)

    assert len(timeline["cuts"]) == 3
    assert timeline["outputDuration"] == pytest.approx(4.7)
    assert [mapping["outputStart"] for mapping in time_map["mappings"]] == [0.0, 1.3, 2.6]
    assert [word["id"] for word in remapped["words"]] == [
        "word_000001",
        "word_000002",
        "word_000003",
    ]
    assert [word["start"] for word in remapped["words"]] == [0.1, 1.4, 2.7]
    assert [word["sourceStart"] for word in remapped["words"]] == [2.0, 5.0, 8.0]


def test_uncorroborated_word_gap_is_review_only() -> None:
    words = [_word(1, 2.0, 3.0, "one")]
    normalized = _normalized(words, 4.0)
    silence, _repetitions = build_analysis_documents(
        "prj_editorial",
        4.0,
        words,
        normalized["segments"],
        [],
        SILENCE_CONFIG,
        REPETITION_CONFIG,
    )

    assert all(candidate["decision"] == "review" for candidate in silence["candidates"])
    timeline, _time_map, _remapped = build_timeline_documents(normalized, silence)
    assert timeline["cuts"] == []
    assert timeline["outputDuration"] == 4.0


def test_empty_transcript_keeps_entire_source() -> None:
    normalized = _normalized([], 0.8)
    silence, _repetitions = build_analysis_documents(
        "prj_editorial",
        0.8,
        [],
        [],
        [(0.0, 0.8)],
        SILENCE_CONFIG,
        REPETITION_CONFIG,
    )

    assert silence["candidates"][0]["type"] == "no-speech"
    assert silence["candidates"][0]["decision"] == "keep"
    timeline, _time_map, remapped = build_timeline_documents(normalized, silence)
    assert timeline["segments"][0]["sourceStart"] == 0.0
    assert timeline["segments"][0]["sourceEnd"] == 0.8
    assert remapped["words"] == []


def test_final_word_overrun_clamps_output_but_preserves_source_timestamp() -> None:
    words = [_word(1, 1.5, 2.1, "ending")]
    normalized = _normalized(words, 2.0)
    silence, _repetitions = build_analysis_documents(
        "prj_editorial",
        2.0,
        words,
        normalized["segments"],
        [],
        SILENCE_CONFIG,
        REPETITION_CONFIG,
    )

    _timeline, _time_map, remapped = build_timeline_documents(normalized, silence)

    assert remapped["words"][0]["sourceEnd"] == 2.1
    assert remapped["words"][0]["end"] == 2.0


def test_nearby_repetition_is_reported_but_never_removed() -> None:
    words = [_word(1, 0.2, 0.8, "same phrase"), _word(2, 1.0, 1.6, "same phrase")]
    normalized = _normalized(words, 2.0)
    silence, repetitions = build_analysis_documents(
        "prj_editorial",
        2.0,
        words,
        normalized["segments"],
        [],
        SILENCE_CONFIG,
        REPETITION_CONFIG,
    )

    assert len(repetitions["candidates"]) == 1
    candidate = repetitions["candidates"][0]
    assert candidate["decision"] == "review"
    assert candidate["automatic"] is False
    timeline, _time_map, _remapped = build_timeline_documents(normalized, silence)
    assert timeline["cuts"] == []


def test_timeline_rejects_cut_that_intersects_a_word() -> None:
    words = [_word(1, 1.0, 2.0, "speech")]
    normalized = _normalized(words, 3.0)
    silence = {
        "policy": {"paddingBefore": 0.1, "paddingAfter": 0.2},
        "candidates": [
            {
                "id": "silence_000001",
                "type": "internal-silence",
                "decision": "remove",
                "automatic": True,
                "proposedCutStart": 1.2,
                "proposedCutEnd": 1.8,
                "confidence": 0.99,
            }
        ],
    }

    with pytest.raises(EditorialError, match="intersects transcript word"):
        build_timeline_documents(normalized, silence)
