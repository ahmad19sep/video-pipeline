from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from cutmachine.assets import prepare_assets
from cutmachine.persistence import read_validated_json
from cutmachine.planning import PlanningError, import_plan_document, validate_plan_document
from cutmachine.project import ProjectContext, sha256_file
from cutmachine.rendering import (
    build_render_input,
    preprocess_project,
    render_draft,
    validate_draft_outputs,
)
from cutmachine.schemas import validate_document

ROOT = Path(__file__).resolve().parents[1]

GRAPHIC_PROPS: dict[str, dict[str, Any]] = {
    "HookTitle": {"title": "A useful hook", "subtitle": "Optional context"},
    "DefinitionCard": {"term": "AI", "definition": "A local definition"},
    "LowerThird": {"name": "Speaker", "role": "Editor"},
    "EndCallToAction": {"text": "Try the next step"},
    "StepCard": {"step": 1, "title": "Open the tool", "body": "Work locally"},
    "ComparisonCard": {
        "leftTitle": "Before",
        "rightTitle": "After",
        "leftItems": ["Manual"],
        "rightItems": ["Repeatable"],
    },
    "ToolLogoRow": {"tools": ["FFmpeg", "Remotion"]},
    "BrowserWindow": {
        "title": "Local browser",
        "address": "local.app",
        "steps": ["Open", "Review"],
    },
    "MobileScreenFrame": {"title": "Mobile view", "steps": ["Tap", "Confirm"]},
    "QuoteCard": {"quote": "Keep the source immutable", "attribution": "CutMachine"},
    "StatisticCard": {"value": "100%", "label": "Local", "source": "Render input"},
    "WarningCard": {"title": "Check the boundary", "body": "Reject unsafe paths"},
    "QuestionCard": {"question": "What should happen next?"},
    "TimelineGraphic": {"items": ["Ingest", "Plan", "Render"]},
    "FeatureList": {"title": "Features", "items": ["Typed", "Deterministic"]},
    "ProgressIndicator": {"label": "Phase", "value": 80},
    "PictureInPicture": {"label": "Speaker"},
    "FullscreenBroll": {"label": "Evidence"},
    "SplitScreen": {"leftLabel": "Speaker", "rightLabel": "Demo"},
}


def _render_document(component: str = "HookTitle") -> dict[str, Any]:
    return {
        "version": 2,
        "projectId": "preview",
        "videoSrc": "cutmachine/preview/proxy.mp4",
        "video": {"fps": 30, "width": 540, "height": 960, "durationInSeconds": 1},
        "timelineSegments": [
            {
                "id": "keep_000001",
                "sourceStart": 0,
                "sourceEnd": 1,
                "outputStart": 0,
                "outputEnd": 1,
            }
        ],
        "captions": {
            "preset": "roman-word-highlight",
            "language": "roman-urdu",
            "safeZone": "shorts-default",
            "maxLines": 2,
            "wordsPerPage": {"min": 2, "max": 5},
            "words": [],
        },
        "scenes": [
            {
                "id": "scene_000001",
                "start": 0,
                "end": 1,
                "layout": "graphic-fullscreen",
                "camera": {
                    "mode": "static",
                    "scaleStart": 1,
                    "scaleEnd": 1,
                    "focus": "center",
                },
                "broll": {
                    "mode": "none",
                    "assetId": None,
                    "effect": "static",
                    "fit": "cover",
                },
                "graphics": [
                    {
                        "id": "graphic_000001",
                        "component": component,
                        "startOffset": 0,
                        "endOffset": 1,
                        "props": GRAPHIC_PROPS.get(component, {}),
                    }
                ],
                "sfx": [],
                "transitionOut": {"type": "clean-cut", "durationFrames": 0},
                "screenTreatment": None,
            }
        ],
        "globalAudio": {
            "voiceGainDb": 0,
            "musicAssetId": None,
            "musicGainDb": -24,
            "duckingEnabled": True,
        },
        "design": {
            "stylePreset": "minimal-professional",
            "colorPreset": "natural-clean",
            "colorIntensity": 0.5,
            "font": {
                "family": "Noto Naskh Arabic",
                "path": None,
                "sha256": None,
                "license": None,
                "fallback": "Arial, sans-serif",
            },
        },
        "assets": {},
    }


def _plan(context: ProjectContext) -> dict[str, Any]:
    return read_validated_json(
        context.repository_root,
        context.project_dir / "planning" / "edit-plan.json",
        "edit-plan",
    )


def test_phase10_catalog_has_typed_deterministic_paths() -> None:
    catalog = json.loads((ROOT / "config" / "component-catalog.json").read_text(encoding="utf-8"))
    assert catalog["version"] == 2
    assert {component["name"] for component in catalog["components"]} == set(GRAPHIC_PROPS)
    graphics_source = (ROOT / "remotion" / "src" / "Graphics.tsx").read_text(encoding="utf-8")
    for component, props in GRAPHIC_PROPS.items():
        document = _render_document(component)
        document["scenes"][0]["graphics"][0]["props"] = props
        assert validate_document(ROOT, "render-input", document) == []
        assert f'case "{component}"' in graphics_source

    captions_source = (ROOT / "remotion" / "src" / "Captions.tsx").read_text(encoding="utf-8")
    for component in (
        "RomanWordHighlightCaption",
        "CleanTwoLineCaption",
        "HookCaption",
        "DefinitionCaption",
        "QuestionCaption",
        "UrduScriptCaption",
    ):
        assert component in captions_source


def test_phase10_studio_preview_does_not_require_placeholder_media() -> None:
    composition_source = (ROOT / "remotion" / "src" / "Composition.tsx").read_text(encoding="utf-8")
    root_source = (ROOT / "remotion" / "src" / "Root.tsx").read_text(encoding="utf-8")
    assert 'input.projectId === "preview"' in composition_source
    assert 'input.videoSrc === "cutmachine/preview/proxy.mp4"' in composition_source
    assert "studioPreview ?" not in composition_source
    assert "if (studioPreview) return <PreviewBackdrop />" in composition_source
    assert 'component: "HookTitle"' in root_source


def test_phase10_render_contract_rejects_unknown_props_components_and_paths() -> None:
    unknown = _render_document("InventedWidget")
    assert any("graphic" in error for error in validate_document(ROOT, "render-input", unknown))

    unsupported = _render_document()
    unsupported["scenes"][0]["graphics"][0]["props"]["script"] = "run()"
    assert validate_document(ROOT, "render-input", unsupported)

    unsafe = _render_document()
    unsafe["videoSrc"] = "../private/raw.mp4"
    assert any("videoSrc" in error for error in validate_document(ROOT, "render-input", unsafe))


def test_phase10_urdu_script_requires_text_and_preserves_technical_terms(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    plan["style"]["captionPreset"] = "urdu-script"
    plan["captions"]["language"] = "urdu-script"
    plan["captions"]["words"][0]["scriptText"] = "AI"
    plan["captions"]["words"][1]["scriptText"] = "مفید"
    validate_plan_document(planned_context, plan)

    plan["captions"]["words"][0]["scriptText"] = "اے آئی"
    with pytest.raises(PlanningError, match="protected technical term"):
        validate_plan_document(planned_context, plan)


def test_phase10_screen_treatments_are_bounded_and_neutral(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    scene = plan["scenes"][0]
    scene["layout"] = "browser-demo"
    scene["screenTreatment"] = {
        "frame": "browser",
        "cursor": {"x": 0.4, "y": 0.4},
        "clicks": [{"offset": 0.4, "x": 0.4, "y": 0.4}],
        "zoom": {"startOffset": 0.2, "endOffset": 1.5, "x": 0.5, "y": 0.45, "scale": 1.3},
        "labels": [{"offset": 0.3, "text": "Choose this", "x": 0.45, "y": 0.3}],
        "sensitiveRegions": [{"x": 0.7, "y": 0.1, "width": 0.2, "height": 0.1, "blur": 12}],
    }
    validate_plan_document(planned_context, plan)

    invalid_region = copy.deepcopy(plan)
    invalid_region["scenes"][0]["screenTreatment"]["sensitiveRegions"][0]["width"] = 0.5
    with pytest.raises(PlanningError, match="Sensitive blur region"):
        validate_plan_document(planned_context, invalid_region)

    aggressive = copy.deepcopy(plan)
    aggressive["scenes"][0]["colorOverride"] = {
        "enabled": True,
        "preset": "cinematic-warm",
        "intensity": 0.5,
        "lutAssetId": None,
    }
    with pytest.raises(PlanningError, match="neutral color"):
        validate_plan_document(planned_context, aggressive)


def test_phase10_style_budgets_keep_clean_cuts_dominant(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    first = plan["scenes"][0]
    first["end"] = 1
    first["graphics"][0]["endOffset"] = 1
    second = copy.deepcopy(first)
    second["id"] = "scene_000002"
    second["start"] = 1
    second["end"] = 2
    second["graphics"] = []
    first["transitionOut"] = {"type": "blur", "durationFrames": 8}
    second["transitionOut"] = {"type": "clean-cut", "durationFrames": 0}
    plan["scenes"] = [first, second]
    with pytest.raises(PlanningError, match="Transition density"):
        validate_plan_document(planned_context, plan)

    plan = _plan(planned_context)
    plan["scenes"][0]["broll"]["mode"] = "fullscreen"
    with pytest.raises(PlanningError, match="Fullscreen B-roll"):
        validate_plan_document(planned_context, plan)


def test_phase10_missing_bundled_font_falls_back(
    planned_context: ProjectContext,
    tmp_path: Path,
) -> None:
    prepare_assets(planned_context)
    preprocess_project(planned_context)
    isolated_remotion = tmp_path / "remotion-without-font"
    (isolated_remotion / "public").mkdir(parents=True)
    input_path = build_render_input(planned_context, remotion_root=isolated_remotion)
    render_input = read_validated_json(planned_context.repository_root, input_path, "render-input")
    assert render_input["design"]["font"] == {
        "family": "Noto Naskh Arabic",
        "path": None,
        "sha256": None,
        "license": None,
        "fallback": "Arial, sans-serif",
    }


def test_phase10_renders_urdu_screen_treatment(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    plan["style"]["captionPreset"] = "urdu-script"
    plan["captions"]["language"] = "urdu-script"
    plan["captions"]["words"][0]["scriptText"] = "AI"
    plan["captions"]["words"][1]["scriptText"] = "مفید"
    scene = plan["scenes"][0]
    scene["layout"] = "browser-demo"
    scene["graphics"][0] = {
        "id": "graphic_000001",
        "component": "BrowserWindow",
        "startOffset": 0,
        "endOffset": 1.8,
        "props": {
            "title": "Local workflow",
            "address": "local.app",
            "steps": ["Open", "Review"],
        },
    }
    scene["screenTreatment"] = {
        "frame": "browser",
        "cursor": {"x": 0.45, "y": 0.45},
        "clicks": [{"offset": 0.5, "x": 0.45, "y": 0.45}],
        "zoom": {"startOffset": 0.3, "endOffset": 1.5, "x": 0.5, "y": 0.45, "scale": 1.25},
        "labels": [{"offset": 0.2, "text": "Review", "x": 0.5, "y": 0.3}],
        "sensitiveRegions": [{"x": 0.72, "y": 0.12, "width": 0.18, "height": 0.1, "blur": 10}],
    }
    plan["globalColor"]["preset"] = "cinematic-warm"
    import_plan_document(planned_context, plan)
    prepare_assets(planned_context)
    preprocess_project(planned_context)
    actual_remotion = ROOT / "remotion"
    public_project = (
        actual_remotion / "public" / "cutmachine" / cast(str, planned_context.project["projectId"])
    )
    try:
        artifacts = render_draft(planned_context, remotion_root=actual_remotion)
        assert "review/draft.mp4" in artifacts
        validate_draft_outputs(planned_context)
        render_input = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "renders" / "draft-input.json",
            "render-input",
        )
        assert render_input["version"] == 2
        assert render_input["captions"]["preset"] == "urdu-script"
        assert render_input["scenes"][0]["screenTreatment"]["frame"] == "browser"
        font_path = actual_remotion / "public" / cast(str, render_input["design"]["font"]["path"])
        assert font_path.is_file()
        assert sha256_file(font_path) == render_input["design"]["font"]["sha256"]
    finally:
        shutil.rmtree(public_project, ignore_errors=True)
