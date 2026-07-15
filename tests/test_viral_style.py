from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

from cutmachine.assets import prepare_assets
from cutmachine.config import load_config
from cutmachine.persistence import read_validated_json
from cutmachine.planning import import_plan_document, validate_plan_document
from cutmachine.project import ProjectContext
from cutmachine.rendering import (
    preprocess_project,
    render_draft,
    validate_draft_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


def _plan(context: ProjectContext) -> dict[str, object]:
    return read_validated_json(
        context.repository_root,
        context.project_dir / "planning" / "edit-plan.json",
        "edit-plan",
    )


def test_phase12_energetic_mode_uses_original_viral_caption_preset() -> None:
    config = load_config(ROOT, style="energetic")
    style = cast(dict[str, object], config["style"])
    assert style["caption_preset"] == "viral-punch"
    assert style["visual_change_target_seconds"] == 2.8


def test_phase12_caption_motion_is_frame_driven_without_css_animation() -> None:
    source = (ROOT / "remotion" / "src" / "Captions.tsx").read_text(encoding="utf-8")
    assert "ViralPunchCaption" in source
    assert "BoxedKeywordCaption" in source
    assert "Easing.bezier" in source
    assert "transition:" not in source
    assert "@keyframes" not in source


def test_phase12_new_caption_presets_preserve_plan_timing(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    captions = cast(dict[str, object], plan["captions"])
    original_words = cast(list[dict[str, object]], captions["words"])
    original_timing = [
        (word["id"], word["text"], word["start"], word["end"]) for word in original_words
    ]
    style = cast(dict[str, object], plan["style"])
    for preset in ("viral-punch", "boxed-keyword"):
        style["captionPreset"] = preset
        validate_plan_document(planned_context, plan)
        assert [
            (word["id"], word["text"], word["start"], word["end"]) for word in original_words
        ] == original_timing


def test_phase12_renders_price_graphic_with_viral_subtitles(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    style = cast(dict[str, object], plan["style"])
    style["preset"] = "viral-social"
    style["captionPreset"] = "viral-punch"
    scenes = cast(list[dict[str, object]], plan["scenes"])
    graphics = cast(list[dict[str, object]], scenes[0]["graphics"])
    graphics[0] = {
        "id": "graphic_000001",
        "component": "PriceComparison",
        "startOffset": 0,
        "endOffset": 1.8,
        "props": {"lowValue": "$1", "highValue": "$10K", "label": "VALUE"},
    }
    import_plan_document(planned_context, plan)
    prepare_assets(planned_context)
    preprocess_project(planned_context)
    remotion_root = ROOT / "remotion"
    public_project = (
        remotion_root / "public" / "cutmachine" / cast(str, planned_context.project["projectId"])
    )
    try:
        artifacts = render_draft(planned_context, remotion_root=remotion_root)
        assert "review/draft.mp4" in artifacts
        validate_draft_outputs(planned_context)
        render_input = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "renders" / "draft-input.json",
            "render-input",
        )
        assert render_input["design"]["stylePreset"] == "viral-social"
        assert render_input["captions"]["preset"] == "viral-punch"
        assert render_input["scenes"][0]["graphics"][0]["component"] == ("PriceComparison")
    finally:
        shutil.rmtree(public_project, ignore_errors=True)
