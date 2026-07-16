from pathlib import Path

import pytest

from cutmachine.schemas import load_schema, validate_document

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name",
    [
        "project",
        "state",
        "media-info",
        "transcript",
        "normalized-transcript",
        "normalization-report",
        "silence-candidates",
        "repetition-candidates",
        "timeline",
        "time-map",
        "remapped-transcript",
        "component-catalog",
        "planning-input",
        "plan-revision",
        "edit-plan",
        "asset-manifest",
        "asset-index",
        "asset-requests",
        "asset-candidates",
        "asset-ranking",
        "asset-cache",
        "asset-pins",
        "editor-settings",
        "cowork-editor-request",
        "preprocess-record",
        "render-input",
        "draft-render",
        "scene-classification",
        "reframe-analysis",
        "color-analysis",
        "audio-mastering",
        "technical-finish",
        "final-pass",
        "qc-report",
        "render-report",
        "review-decision",
        "review-package",
    ],
)
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    schema = load_schema(ROOT, name)
    assert schema["$schema"].endswith("2020-12/schema")
    assert "cutmachine.local" in schema["$id"]


def test_edit_plan_rejects_absolute_source_path() -> None:
    invalid = {
        "version": 2,
        "projectId": "demo",
        "timelineVersion": 1,
        "style": {
            "preset": "modern-ai",
            "intensity": "balanced",
            "captionPreset": "roman-word-highlight",
            "transitionDensity": "low",
            "visualChangeTargetSeconds": 4.5,
        },
        "video": {
            "source": "C:\\private\\raw.mp4",
            "fps": 30,
            "width": 1080,
            "height": 1920,
            "durationInSeconds": 10,
        },
        "captions": {
            "enabled": True,
            "language": "roman-urdu",
            "safeZone": "shorts-default",
            "maxLines": 2,
            "wordsPerPage": {"min": 2, "max": 5},
            "words": [],
        },
        "globalAudio": {
            "voiceGainDb": 0,
            "musicAssetId": None,
            "musicGainDb": -24,
            "duckingEnabled": True,
            "targetLufs": -14,
            "truePeakDb": -1,
        },
        "globalColor": {
            "enabled": True,
            "preset": "natural-clean",
            "intensity": 0.5,
            "lutAssetId": None,
        },
        "scenes": [],
        "provenance": {
            "createdBy": "test",
            "createdAt": "2026-07-15T12:00:00Z",
            "componentCatalogVersion": 1,
        },
    }

    errors = validate_document(ROOT, "edit-plan", invalid)

    assert any("source" in error for error in errors)
