from __future__ import annotations

import json
from typing import Any

import pytest

from cutmachine.normalization import (
    NormalizationError,
    normalize_project,
    validate_normalized_outputs,
)
from cutmachine.persistence import write_validated_json_atomic
from cutmachine.project import ProjectContext


def _write_raw_transcript(
    context: ProjectContext,
    words: list[tuple[str, float, float, float]] | None = None,
) -> None:
    words = words or [
        ("ChatGPT", 0.1, 0.3, 0.99),
        ("بہت", 0.31, 0.55, 0.92),
        ("اچھا", 0.56, 0.85, 0.65),
        ("ہے", 0.86, 1.1, 0.91),
    ]
    word_documents = [
        {
            "id": f"word_{index:06d}",
            "segmentId": "segment_000001",
            "start": start,
            "end": end,
            "raw": raw,
            "display": raw,
            "language": "ur",
            "confidence": confidence,
            "source": "faster-whisper",
            "normalizationSource": "raw-transcript",
            "lockedTiming": True,
        }
        for index, (raw, start, end, confidence) in enumerate(words, start=1)
    ]
    document = {
        "version": 1,
        "projectId": context.project["projectId"],
        "language": "ur",
        "durationSeconds": 2.0,
        "segments": [
            {
                "id": "segment_000001",
                "start": 0.1,
                "end": words[-1][2],
                "text": " ".join(word[0] for word in words),
                "wordIds": [word["id"] for word in word_documents],
            }
        ],
        "words": word_documents,
        "provenance": {
            "createdAt": "2026-07-15T12:00:00+00:00",
            "audioPath": "audio/source.wav",
            "requested": {"model": "tiny", "device": "cpu", "computeType": "int8"},
            "effective": {"model": "tiny", "device": "cpu", "computeType": "int8"},
            "fallbackReason": None,
            "wordTimestamps": True,
            "vadEnabled": True,
        },
    }
    write_validated_json_atomic(
        context.repository_root,
        context.project_dir / "transcript" / "transcript.raw.json",
        "transcript",
        document,
    )


def test_local_normalization_preserves_timing_and_ids(
    ingested_context: ProjectContext,
) -> None:
    _write_raw_transcript(ingested_context)

    artifacts = normalize_project(ingested_context)
    validate_normalized_outputs(ingested_context)
    document = json.loads((ingested_context.project_dir / artifacts[0]).read_text(encoding="utf-8"))
    report = json.loads((ingested_context.project_dir / artifacts[1]).read_text(encoding="utf-8"))

    assert [word["display"] for word in document["words"]] == [
        "ChatGPT",
        "bohat",
        "acha",
        "hai",
    ]
    assert [word["normalizationSource"] for word in document["words"]] == [
        "technical-glossary",
        "local-lexicon",
        "local-lexicon",
        "local-lexicon",
    ]
    assert [word["id"] for word in document["words"]] == [
        "word_000001",
        "word_000002",
        "word_000003",
        "word_000004",
    ]
    assert [word["start"] for word in document["words"]] == [0.1, 0.31, 0.56, 0.86]
    assert report["counts"]["technicalGlossary"] == 1
    assert [word["id"] for word in report["lowConfidenceWords"]] == ["word_000003"]


def test_urls_numbers_roman_tokens_and_glossary_aliases_are_preserved(
    ingested_context: ProjectContext,
) -> None:
    _write_raw_transcript(
        ingested_context,
        [
            ("https://openai.com", 0.1, 0.3, 0.99),
            ("2026", 0.31, 0.5, 0.99),
            ("Roman", 0.51, 0.7, 0.99),
            ("اوپن اے آئی", 0.71, 1.0, 0.99),
        ],
    )

    normalize_project(ingested_context)
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.roman.json").read_text(
            encoding="utf-8"
        )
    )

    assert [word["display"] for word in document["words"]] == [
        "https://openai.com",
        "2026",
        "Roman",
        "OpenAI",
    ]


@pytest.mark.parametrize("unsafe_path", ["../outside.json", "D:/outside.json"])
def test_unsafe_lexicon_path_is_rejected(
    ingested_context: ProjectContext,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_path: str,
) -> None:
    _write_raw_transcript(ingested_context)
    monkeypatch.setenv("CUTMACHINE__NORMALIZATION__LEXICON_PATH", unsafe_path)

    with pytest.raises(NormalizationError, match="Unsafe Roman Urdu lexicon path"):
        normalize_project(ingested_context)


def test_malformed_lexicon_is_rejected(ingested_context: ProjectContext) -> None:
    _write_raw_transcript(ingested_context)
    path = ingested_context.repository_root / "config" / "roman-urdu-lexicon.json"
    path.write_text('{"version": 1, "mappings": {"ہے": ""}}', encoding="utf-8")

    with pytest.raises(NormalizationError, match="non-empty single-line"):
        normalize_project(ingested_context)


class MalformedAdapter:
    name = "fixture-malformed"

    def __init__(self) -> None:
        self.calls = 0

    def refine(self, words: list[dict[str, object]]) -> object:
        self.calls += 1
        return {"version": 1, "words": [{"id": "wrong", "display": "bad"}]}


class ValidAdapter:
    name = "fixture-valid"

    def refine(self, words: list[dict[str, object]]) -> object:
        return {
            "version": 1,
            "words": [
                {"id": word["id"], "display": f"natural-{word['display']}", "confidence": 0.8}
                for word in words
            ],
        }


def _enable_refinement(context: ProjectContext, monkeypatch: pytest.MonkeyPatch) -> None:
    cast_settings = context.project["settings"]
    assert isinstance(cast_settings, dict)
    cast_settings["networkEnabled"] = True
    monkeypatch.setenv("CUTMACHINE__NETWORK__ENABLED", "true")
    monkeypatch.setenv("CUTMACHINE__NORMALIZATION__REFINEMENT__ENABLED", "true")


def test_malformed_refinement_retries_then_falls_back_locally(
    ingested_context: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw_transcript(ingested_context)
    _enable_refinement(ingested_context, monkeypatch)
    adapter = MalformedAdapter()

    normalize_project(ingested_context, adapter_factory=lambda _config: adapter)
    document: dict[str, Any] = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.roman.json").read_text(
            encoding="utf-8"
        )
    )
    report = json.loads(
        (
            ingested_context.project_dir / "analysis" / "transcript-normalization-report.json"
        ).read_text(encoding="utf-8")
    )

    assert adapter.calls == 3
    assert document["words"][1]["display"] == "bohat"
    assert document["provenance"]["refinement"]["failedBatches"] == 1
    assert len(report["warnings"]) == 1


def test_valid_refinement_cannot_modify_protected_technical_terms(
    ingested_context: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw_transcript(ingested_context)
    _enable_refinement(ingested_context, monkeypatch)

    normalize_project(
        ingested_context,
        adapter_factory=lambda _config: ValidAdapter(),
    )
    document = json.loads(
        (ingested_context.project_dir / "transcript" / "transcript.roman.json").read_text(
            encoding="utf-8"
        )
    )

    assert document["words"][0]["display"] == "ChatGPT"
    assert document["words"][0]["normalizationSource"] == "technical-glossary"
    assert document["words"][1]["display"] == "natural-bohat"
    assert document["words"][1]["normalizationSource"] == "external-refinement"


def test_validation_rejects_timing_mutation(ingested_context: ProjectContext) -> None:
    _write_raw_transcript(ingested_context)
    normalize_project(ingested_context)
    path = ingested_context.project_dir / "transcript" / "transcript.roman.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["words"][0]["start"] = 0.2
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(NormalizationError, match="immutable word field start"):
        validate_normalized_outputs(ingested_context)
