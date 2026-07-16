from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cutmachine.project import ProjectContext, sha256_file
from cutmachine.technical import (
    TechnicalError,
    build_audio_mastering_filter,
    build_reframe_analysis,
    choose_color_adjustments,
    classify_scenes,
    resolve_lut,
)


def test_audio_mastering_limiter_preserves_true_peak_headroom() -> None:
    audio_filter = build_audio_mastering_filter(-14.0, -1.0)

    assert "loudnorm=I=-14.0:TP=-1.0" in audio_filter
    assert "alimiter=limit=0.891251:level=false" in audio_filter
    assert audio_filter.endswith("aresample=48000")


def _config() -> dict[str, Any]:
    return {
        "project": {"assets_root": "assets-library"},
        "technical": {
            "face_confidence": 0.6,
            "face_smoothing": 0.25,
            "max_digital_zoom": 1.2,
            "headroom": 0.12,
            "lut": {
                "enabled": False,
                "path": None,
                "intensity": 0.35,
                "color_space": None,
            },
        },
    }


def _plan(*, layout: str = "speaker-fullscreen", portrait: bool = True) -> dict[str, Any]:
    return {
        "video": {"width": 1080 if portrait else 1920, "height": 1920 if portrait else 1080},
        "scenes": [
            {
                "id": "scene_000001",
                "start": 0,
                "end": 2,
                "layout": layout,
                "purpose": "explanation",
                "broll": {"assetId": None, "query": None},
            }
        ],
    }


def _metrics(luma: float = 110) -> dict[str, Any]:
    return {
        "lumaAverage": luma,
        "lumaLow": 35,
        "lumaHigh": 190,
        "chromaU": 128,
        "chromaV": 128,
        "saturationAverage": 50,
        "clippedShadows": False,
        "clippedHighlights": False,
    }


def test_scene_classification_preserves_screen_recording_neutrally() -> None:
    classified = classify_scenes("prj_test", _plan(layout="browser-demo"), _metrics())
    scene = classified["scenes"][0]

    assert scene["classification"] == "screen-recording"
    assert scene["confidence"] == 0.98
    assert scene["preserveNeutral"] is True


def test_low_light_talking_head_is_classified_from_bounded_metrics() -> None:
    classified = classify_scenes("prj_test", _plan(), _metrics(45))
    assert classified["scenes"][0]["classification"] == "low-light"
    assert "lumaAverage=45.00" in classified["scenes"][0]["evidence"]


def test_face_reframe_smooths_jitter_and_stays_inside_source() -> None:
    plan = _plan()
    classifications = classify_scenes("prj_test", plan, _metrics())
    observations = [
        {"time": 0.2, "centerX": 0.2, "centerY": 0.4, "confidence": 0.9},
        {"time": 0.6, "centerX": 0.8, "centerY": 0.42, "confidence": 0.95},
        {"time": 1.0, "centerX": 0.3, "centerY": 0.41, "confidence": 0.92},
    ]

    reframe = build_reframe_analysis(
        "prj_test",
        plan,
        1280,
        720,
        classifications,
        observations,
        _config(),
    )

    assert reframe["mode"] == "face-aware"
    assert reframe["detector"] == "injected-local"
    assert reframe["samples"][1]["centerX"] == pytest.approx(0.35)
    crop = reframe["crop"]
    assert crop["x"] + crop["width"] <= crop["sourceWidth"]
    assert crop["y"] + crop["height"] <= crop["sourceHeight"]
    assert crop["width"] % 2 == crop["height"] % 2 == 0


def test_no_face_uses_deterministic_center_crop() -> None:
    plan = _plan()
    classifications = classify_scenes("prj_test", plan, _metrics())
    reframe = build_reframe_analysis("prj_test", plan, 1280, 720, classifications, [], _config())

    assert reframe["mode"] == "center-fallback"
    assert reframe["crop"]["centerX"] == 0.5
    assert reframe["fallbackReason"].startswith("No confident")


def test_screen_recording_disables_crop_and_color() -> None:
    plan = _plan(layout="browser-demo")
    classifications = classify_scenes("prj_test", plan, _metrics())
    reframe = build_reframe_analysis("prj_test", plan, 1280, 720, classifications, [], _config())
    adjustments = choose_color_adjustments(
        _metrics(40), preserve_neutral=True, enabled=True, sharpen=0.2
    )

    assert reframe["mode"] == "neutral"
    assert reframe["crop"]["width"] == 1280
    assert adjustments == {
        "enabled": False,
        "reason": "Neutral/disabled color path selected; no correction applied.",
        "brightness": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
        "temperature": 0.0,
        "sharpen": 0.0,
    }


@pytest.mark.parametrize(
    ("metrics", "field", "bound"),
    [
        ({**_metrics(), "lumaAverage": 20}, "brightness", 0.1),
        ({**_metrics(), "lumaAverage": 220}, "brightness", -0.1),
        ({**_metrics(), "chromaU": 255, "chromaV": 0}, "temperature", -0.08),
    ],
)
def test_color_adjustments_remain_conservative(
    metrics: dict[str, Any], field: str, bound: float
) -> None:
    adjustments = choose_color_adjustments(
        metrics, preserve_neutral=False, enabled=True, sharpen=0.8
    )

    assert abs(float(adjustments[field])) <= abs(bound)
    assert adjustments["sharpen"] == 0.5


def test_lut_requires_safe_indexed_license_color_space_and_bounded_intensity(
    repository: Path,
) -> None:
    lut = repository / "assets-library" / "luts" / "clean.cube"
    lut.write_text("TITLE clean\nLUT_3D_SIZE 2\n", encoding="utf-8")
    context = ProjectContext(
        repository,
        repository / "workspace" / "fake",
        {"projectId": "prj_test", "mode": "balanced"},
    )
    index = {
        "assets": [
            {
                "path": "luts/clean.cube",
                "type": "lut",
                "license": "owned",
                "colorSpace": "rec709",
                "sha256": sha256_file(lut),
            }
        ]
    }
    config = _config()
    config["technical"]["lut"] = {
        "enabled": True,
        "path": "luts/clean.cube",
        "intensity": 0.35,
        "color_space": None,
    }

    selected = resolve_lut(context, index, config, preserve_neutral=False)

    assert selected["enabled"] is True
    assert selected["intensity"] == 0.35
    assert selected["colorSpace"] == "rec709"

    config["technical"]["lut"]["intensity"] = 0.8
    with pytest.raises(TechnicalError, match="intensity"):
        resolve_lut(context, index, config, preserve_neutral=False)
    config["technical"]["lut"]["intensity"] = 0.35
    config["technical"]["lut"]["path"] = "../private.cube"
    with pytest.raises(TechnicalError, match="unsafe"):
        resolve_lut(context, index, config, preserve_neutral=False)
