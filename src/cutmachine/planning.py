"""Validated local edit planning, Cowork import, and typed revision boundaries."""

from __future__ import annotations

import copy
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.config import load_config
from cutmachine.pacing import plan_scene_cameras
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_json,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext
from cutmachine.schemas import validate_document
from cutmachine.sfx import plan_scene_sfx


class PlanningError(RuntimeError):
    """Raised when an edit plan or revision crosses an invalid boundary."""


_DANGEROUS_PROP_NAMES = {
    "code",
    "command",
    "css",
    "executable",
    "html",
    "javascript",
    "jsx",
    "path",
    "python",
    "script",
    "shell",
    "tsx",
    "url",
}


def _load_catalog(root: Path) -> dict[str, Any]:
    try:
        catalog = read_validated_json(
            root, root / "config" / "component-catalog.json", "component-catalog"
        )
    except PersistenceError as exc:
        raise PlanningError(f"Component catalog is invalid: {exc}") from exc
    names: set[str] = set()
    for component in cast(list[dict[str, Any]], catalog["components"]):
        name = cast(str, component["name"])
        if name in names:
            raise PlanningError(f"Component catalog contains duplicate name {name!r}.")
        names.add(name)
        allowed = cast(dict[str, str], component["allowedProps"])
        required = cast(list[str], component["requiredProps"])
        if not set(required).issubset(allowed):
            raise PlanningError(f"Component {name} requires undeclared props.")
        if any(key.casefold() in _DANGEROUS_PROP_NAMES for key in allowed):
            raise PlanningError(f"Component {name} declares an unsafe prop name.")
    return catalog


def _finite_document(value: object, path: str = "<root>") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise PlanningError(f"Plan contains a non-finite number at {path}.")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_document(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite_document(item, f"{path}/{index}")


def _validate_prop_value(value: object, expected: str, label: str) -> None:
    valid = False
    if expected == "string":
        valid = isinstance(value, str) and bool(value.strip())
    elif expected == "number":
        valid = isinstance(value, int | float) and not isinstance(value, bool)
    elif expected == "boolean":
        valid = isinstance(value, bool)
    elif expected == "string-array":
        valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
    if not valid:
        raise PlanningError(f"Component prop {label} must have type {expected}.")


def _load_authoritative_inputs(
    context: ProjectContext,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        timeline = read_validated_json(
            context.repository_root,
            context.project_dir / "timeline" / "source-timeline.json",
            "timeline",
        )
        transcript = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.remapped.json",
            "remapped-transcript",
        )
        media_info = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "media-info.json",
            "media-info",
        )
    except PersistenceError as exc:
        raise PlanningError(f"Planning inputs are invalid: {exc}") from exc
    catalog = _load_catalog(context.repository_root)
    return timeline, transcript, media_info, catalog


def _baseline_dimensions(media_info: dict[str, Any], config: dict[str, Any]) -> tuple[int, int]:
    video = cast(dict[str, Any], media_info["video"])
    render = cast(dict[str, Any], config["render"])
    short = min(int(render["final_width"]), int(render["final_height"]))
    long = max(int(render["final_width"]), int(render["final_height"]))
    return (short, long) if int(video["height"]) >= int(video["width"]) else (long, short)


def build_baseline_plan(
    context: ProjectContext,
    timeline: dict[str, Any],
    transcript: dict[str, Any],
    media_info: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    mode = cast(str, context.project["mode"])
    style = cast(dict[str, Any], config["style"])
    captions_config = cast(dict[str, Any], config["captions"])
    render_config = cast(dict[str, Any], config["render"])
    quality = cast(dict[str, Any], config["quality"])
    width, height = _baseline_dimensions(media_info, config)
    words = cast(list[dict[str, Any]], transcript["words"])
    caption_words = [
        {
            "id": word["id"],
            "text": word["display"],
            "start": word["start"],
            "end": word["end"],
            "emphasis": word["normalizationSource"] == "technical-glossary"
            or cast(str, word["display"]).isupper()
            or any(character.isdigit() for character in cast(str, word["display"])),
            "confidence": word["confidence"],
        }
        for word in words
    ]
    title = " ".join(cast(str, word["text"]) for word in caption_words[:6]).strip()
    scenes: list[dict[str, Any]] = []
    timeline_segments = cast(list[dict[str, Any]], timeline["segments"])
    for index, segment in enumerate(timeline_segments, start=1):
        start = float(segment["outputStart"])
        end = float(segment["outputEnd"])
        duration = end - start
        graphics: list[dict[str, Any]] = []
        if index == 1 and title and duration >= 0.5:
            graphics.append(
                {
                    "id": "graphic_000001",
                    "component": "HookTitle",
                    "startOffset": 0.0,
                    "endOffset": round(min(duration, 2.5), 6),
                    "props": {"title": title[:500]},
                }
            )
        scenes.append(
            {
                "id": f"scene_{index:06d}",
                "start": segment["outputStart"],
                "end": segment["outputEnd"],
                "purpose": "hook" if index == 1 else "explanation",
                "sourceTimelineIds": [segment["id"]],
                "layout": "speaker-with-title" if graphics else "speaker-fullscreen",
                "camera": {
                    "mode": "static",
                    "scaleStart": 1.0,
                    "scaleEnd": 1.0,
                    "focus": "face",
                },
                "colorOverride": None,
                "broll": {
                    "mode": "none",
                    "assetId": None,
                    "query": None,
                    "effect": "static",
                    "fit": "cover",
                },
                "graphics": graphics,
                "sfx": [],
                "transitionOut": {"type": "clean-cut", "durationFrames": 0},
                "screenTreatment": None,
            }
        )
    sfx_placements = plan_scene_sfx(
        scenes,
        caption_words,
        fps=float(render_config["fps"]),
        output_duration=float(timeline["outputDuration"]),
        budgets=cast(dict[str, Any], style["effect_budgets"]),
    )
    cameras = plan_scene_cameras(
        scenes,
        output_duration=float(timeline["outputDuration"]),
        budgets=cast(dict[str, Any], style["effect_budgets"]),
        visual_change_target_seconds=float(style["visual_change_target_seconds"]),
    )
    for scene, placement, camera in zip(scenes, sfx_placements, cameras, strict=True):
        scene["sfx"] = placement
        scene["camera"] = camera
    style_preset = (
        "documentary"
        if mode == "cinematic"
        else (
            "minimal-professional"
            if mode == "fast"
            else ("viral-social" if mode == "energetic" else "modern-ai")
        )
    )
    artifacts = cast(dict[str, Any], media_info["artifacts"])
    return {
        "version": 2,
        "projectId": context.project["projectId"],
        "timelineVersion": timeline["version"],
        "style": {
            "preset": style_preset,
            "intensity": mode,
            "captionPreset": style["caption_preset"],
            "transitionDensity": style["transition_density"],
            "visualChangeTargetSeconds": style["visual_change_target_seconds"],
        },
        "video": {
            "source": artifacts["proxy"],
            "fps": render_config["fps"],
            "width": width,
            "height": height,
            "durationInSeconds": timeline["outputDuration"],
        },
        "captions": {
            "language": context.project["settings"]["captionLanguage"],
            "safeZone": "shorts-default" if height >= width else "youtube-longform",
            "maxLines": captions_config["max_lines"],
            "wordsPerPage": {
                "min": captions_config["min_words_per_page"],
                "max": captions_config["max_words_per_page"],
            },
            "words": caption_words,
        },
        "globalAudio": {
            "voiceGainDb": 0,
            "musicAssetId": None,
            "musicQuery": None,
            "musicGainDb": -24,
            "duckingEnabled": True,
            "targetLufs": quality["target_lufs"],
            "truePeakDb": quality["true_peak_db"],
        },
        "globalColor": {
            "enabled": True,
            "preset": "natural-clean",
            "intensity": 0.5,
            "lutAssetId": None,
        },
        "scenes": scenes,
        "provenance": {
            "createdBy": "cutmachine-local-baseline",
            "createdAt": datetime.now(UTC).isoformat(),
            "componentCatalogVersion": catalog["version"],
        },
    }


def _catalog_by_name(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        cast(str, component["name"]): component
        for component in cast(list[dict[str, Any]], catalog["components"])
    }


def validate_plan_document(
    context: ProjectContext,
    plan: dict[str, Any],
    *,
    timeline: dict[str, Any] | None = None,
    transcript: dict[str, Any] | None = None,
    media_info: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
) -> None:
    _finite_document(plan)
    errors = validate_document(context.repository_root, "edit-plan", plan)
    if errors:
        raise PlanningError("Invalid edit plan:\n" + "\n".join(f"- {item}" for item in errors))
    if timeline is None or transcript is None or media_info is None or catalog is None:
        timeline, transcript, media_info, catalog = _load_authoritative_inputs(context)
    project_id = context.project["projectId"]
    if plan["projectId"] != project_id:
        raise PlanningError("Edit plan belongs to another project.")
    if plan["timelineVersion"] != timeline["version"]:
        raise PlanningError("Edit plan timeline version is stale.")
    output_duration = float(timeline["outputDuration"])
    if abs(float(plan["video"]["durationInSeconds"]) - output_duration) > 0.00001:
        raise PlanningError("Edit plan duration does not match the timeline.")
    proxy_path = cast(dict[str, Any], media_info["artifacts"])["proxy"]
    if plan["video"]["source"] != proxy_path:
        raise PlanningError("Edit plan video source is not the validated project proxy.")
    try:
        proxy = resolve_inside(context.project_dir, cast(str, proxy_path))
    except UnsafePathError as exc:
        raise PlanningError(f"Edit plan video source path is unsafe: {exc}") from exc
    if not proxy.is_file() or proxy.stat().st_size == 0:
        raise PlanningError("Validated project proxy is missing or empty.")
    expected_words = cast(list[dict[str, Any]], transcript["words"])
    planned_words = cast(list[dict[str, Any]], plan["captions"]["words"])
    if len(expected_words) != len(planned_words):
        raise PlanningError("Edit plan caption word count differs from the transcript.")
    for expected, planned in zip(expected_words, planned_words, strict=True):
        for planned_field, source_field in (
            ("id", "id"),
            ("text", "display"),
            ("start", "start"),
            ("end", "end"),
            ("confidence", "confidence"),
        ):
            if planned[planned_field] != expected[source_field]:
                raise PlanningError(
                    f"Caption word {expected['id']} changed authoritative field {planned_field}."
                )
    words_per_page = cast(dict[str, Any], plan["captions"]["wordsPerPage"])
    if int(words_per_page["min"]) > int(words_per_page["max"]):
        raise PlanningError("Caption words-per-page minimum exceeds maximum.")
    caption_preset = cast(str, plan["style"]["captionPreset"])
    caption_language = cast(str, plan["captions"]["language"])
    if (caption_preset == "urdu-script") != (caption_language == "urdu-script"):
        raise PlanningError("Urdu-script captions require both the Urdu preset and language.")
    if caption_preset == "urdu-script":
        for expected, planned in zip(expected_words, planned_words, strict=True):
            script_text = planned.get("scriptText")
            if not isinstance(script_text, str) or not script_text.strip():
                raise PlanningError(f"Urdu caption word {expected['id']} is missing scriptText.")
            source_text = cast(str, expected["display"])
            protected = source_text.isupper() or any(
                character.isdigit() for character in source_text
            )
            if protected and script_text != source_text:
                raise PlanningError(
                    f"Urdu caption word {expected['id']} changed a protected technical term."
                )
    if float(plan["globalColor"]["intensity"]) > 0.5:
        raise PlanningError("Creative color intensity exceeds the conservative Phase 10 limit.")

    timeline_segments = {
        cast(str, segment["id"]): segment
        for segment in cast(list[dict[str, Any]], timeline["segments"])
    }
    component_map = _catalog_by_name(catalog)
    if plan["provenance"]["componentCatalogVersion"] != catalog["version"]:
        raise PlanningError("Edit plan component catalog version is stale.")
    if any(
        value is not None
        for value in (
            plan["globalAudio"]["musicAssetId"],
            plan["globalColor"]["lutAssetId"],
        )
    ):
        raise PlanningError("Asset IDs are not valid before asset resolution.")
    scenes = cast(list[dict[str, Any]], plan["scenes"])
    scene_ids: set[str] = set()
    graphic_ids: set[str] = set()
    cursor = 0.0
    transition_count = 0
    camera_count = 0
    graphic_count = 0
    sfx_count = 0
    fullscreen_broll_seconds = 0.0
    for scene in scenes:
        scene_id = cast(str, scene["id"])
        if scene_id in scene_ids:
            raise PlanningError(f"Duplicate scene ID: {scene_id}")
        scene_ids.add(scene_id)
        start = float(scene["start"])
        end = float(scene["end"])
        if start < cursor - 0.00001 or abs(start - cursor) > 0.00001 or end <= start:
            raise PlanningError("Edit plan scenes must be ordered, non-overlapping, and gap-free.")
        if end > output_duration + 0.00001:
            raise PlanningError(f"Scene {scene_id} exceeds timeline duration.")
        references = cast(list[str], scene["sourceTimelineIds"])
        try:
            referenced = [timeline_segments[item] for item in references]
        except KeyError as exc:
            raise PlanningError(f"Scene {scene_id} references an unknown timeline ID.") from exc
        referenced.sort(key=lambda item: float(item["outputStart"]))
        coverage_cursor = start
        for segment in referenced:
            segment_start = max(start, float(segment["outputStart"]))
            segment_end = min(end, float(segment["outputEnd"]))
            if segment_end <= segment_start or segment_start > coverage_cursor + 0.00001:
                raise PlanningError(f"Scene {scene_id} timeline references do not cover its range.")
            coverage_cursor = max(coverage_cursor, segment_end)
        if coverage_cursor < end - 0.00001:
            raise PlanningError(f"Scene {scene_id} timeline references do not cover its range.")
        scene_duration = end - start
        transition = cast(dict[str, Any], scene["transitionOut"])
        transition_type = cast(str, transition["type"])
        transition_frames = int(transition["durationFrames"])
        if (transition_type == "clean-cut") != (transition_frames == 0):
            raise PlanningError(
                "Clean cuts require zero frames and visual transitions require a duration."
            )
        if transition_type != "clean-cut":
            if scene is scenes[-1]:
                raise PlanningError("The final scene cannot transition to a missing next scene.")
            transition_count += 1
        camera = cast(dict[str, Any], scene["camera"])
        if camera["mode"] != "static":
            camera_count += 1
        broll = cast(dict[str, Any], scene["broll"])
        if broll["mode"] == "fullscreen":
            fullscreen_broll_seconds += scene_duration
        sfx = cast(list[dict[str, Any]], scene["sfx"])
        sfx_count += len(sfx)
        if broll["assetId"] is not None or any(item["assetId"] is not None for item in sfx):
            raise PlanningError("Scene asset IDs are invalid before asset resolution.")
        has_start_offset = "startOffset" in broll
        has_end_offset = "endOffset" in broll
        if has_start_offset != has_end_offset:
            raise PlanningError("B-roll offsets must be provided together.")
        if has_start_offset and (
            float(broll["startOffset"]) < 0
            or float(broll["endOffset"]) <= float(broll["startOffset"])
            or float(broll["endOffset"]) > scene_duration + 0.00001
        ):
            raise PlanningError(f"Scene {scene_id} has invalid B-roll offsets.")
        for graphic in cast(list[dict[str, Any]], scene["graphics"]):
            graphic_count += 1
            graphic_id = cast(str, graphic["id"])
            if graphic_id in graphic_ids:
                raise PlanningError(f"Duplicate graphic ID: {graphic_id}")
            graphic_ids.add(graphic_id)
            component_name = cast(str, graphic["component"])
            component = component_map.get(component_name)
            if component is None:
                raise PlanningError(f"Unknown graphic component: {component_name}")
            if (
                float(graphic["endOffset"]) <= float(graphic["startOffset"])
                or float(graphic["endOffset"]) > scene_duration + 0.00001
            ):
                raise PlanningError(f"Graphic {graphic_id} exceeds scene bounds.")
            props = cast(dict[str, object], graphic["props"])
            allowed = cast(dict[str, str], component["allowedProps"])
            required = set(cast(list[str], component["requiredProps"]))
            if not required.issubset(props):
                raise PlanningError(f"Graphic {graphic_id} is missing required component props.")
            for key, value in props.items():
                if key.casefold() in _DANGEROUS_PROP_NAMES or key not in allowed:
                    raise PlanningError(f"Graphic {graphic_id} contains unsupported prop {key!r}.")
                _validate_prop_value(value, allowed[key], f"{component_name}.{key}")
        treatment = cast(dict[str, Any] | None, scene.get("screenTreatment"))
        screen_layout = scene["layout"] in {"browser-demo", "mobile-demo"}
        if treatment is not None and not screen_layout:
            raise PlanningError("Screen treatment is allowed only on browser/mobile demo scenes.")
        if treatment is not None:
            expected_frame = "browser" if scene["layout"] == "browser-demo" else "phone"
            if treatment["frame"] != expected_frame:
                raise PlanningError("Screen treatment frame does not match the scene layout.")
            for event in [
                *cast(list[dict[str, Any]], treatment["clicks"]),
                *cast(list[dict[str, Any]], treatment["labels"]),
            ]:
                if float(event["offset"]) >= scene_duration:
                    raise PlanningError("Screen treatment event exceeds scene bounds.")
            zoom = cast(dict[str, Any] | None, treatment["zoom"])
            if zoom is not None and (
                float(zoom["endOffset"]) <= float(zoom["startOffset"])
                or float(zoom["endOffset"]) > scene_duration
            ):
                raise PlanningError("Screen treatment zoom exceeds scene bounds.")
            for region in cast(list[dict[str, Any]], treatment["sensitiveRegions"]):
                if (
                    float(region["x"]) + float(region["width"]) > 1
                    or float(region["y"]) + float(region["height"]) > 1
                ):
                    raise PlanningError("Sensitive blur region exceeds normalized screen bounds.")
        color_override = cast(dict[str, Any] | None, scene["colorOverride"])
        if (
            screen_layout
            and color_override is not None
            and color_override["preset"]
            not in {
                "off",
                "natural-clean",
            }
        ):
            raise PlanningError("Screen scenes permit only neutral color overrides.")
        cursor = end
    if abs(cursor - output_duration) > 0.00001:
        raise PlanningError("Edit plan scenes do not cover the full timeline.")
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    budgets = cast(dict[str, Any], cast(dict[str, Any], config["style"])["effect_budgets"])
    minutes = output_duration / 60

    def allowance(key: str, *, minimum: int) -> int:
        rate = float(budgets[key])
        return max(minimum if rate > 0 else 0, math.ceil(rate * minutes))

    if transition_count > allowance("transitions_per_minute", minimum=1):
        raise PlanningError("Transition density exceeds the selected style budget.")
    if camera_count > allowance("camera_moves_per_minute", minimum=1):
        raise PlanningError("Camera-move density exceeds the selected style budget.")
    if graphic_count > allowance("animated_text_per_minute", minimum=1):
        raise PlanningError("Animated-text density exceeds the selected style budget.")
    if sfx_count > allowance("impact_sfx_per_minute", minimum=1):
        raise PlanningError("SFX density exceeds the selected style budget.")
    if fullscreen_broll_seconds / output_duration > float(budgets["fullscreen_broll_ratio"]):
        raise PlanningError("Fullscreen B-roll exceeds the selected style budget.")


def _planning_input(context: ProjectContext) -> dict[str, Any]:
    return {
        "version": 1,
        "projectId": context.project["projectId"],
        "mode": context.project["mode"],
        "paths": {
            "transcript": "transcript/transcript.remapped.json",
            "timeline": "timeline/source-timeline.json",
            "contactSheet": "analysis/contact-sheet.jpg",
            "componentCatalog": "planning/component-catalog.json",
            "editPlan": "planning/edit-plan.json",
        },
        "constraints": {
            "jsonOnly": True,
            "localFirst": True,
            "preserveWordTiming": True,
            "allowExecutableContent": False,
            "allowUnknownComponents": False,
        },
    }


def generate_plan(context: ProjectContext) -> list[str]:
    timeline, transcript, media_info, catalog = _load_authoritative_inputs(context)
    plan = build_baseline_plan(context, timeline, transcript, media_info, catalog)
    validate_plan_document(
        context,
        plan,
        timeline=timeline,
        transcript=transcript,
        media_info=media_info,
        catalog=catalog,
    )
    plan_path = context.project_dir / "planning" / "edit-plan.json"
    catalog_path = context.project_dir / "planning" / "component-catalog.json"
    input_path = context.project_dir / "planning" / "cowork-input.json"
    write_validated_json_atomic(context.repository_root, plan_path, "edit-plan", plan)
    write_validated_json_atomic(context.repository_root, catalog_path, "component-catalog", catalog)
    write_validated_json_atomic(
        context.repository_root, input_path, "planning-input", _planning_input(context)
    )
    validate_plan_outputs(context)
    return [
        plan_path.relative_to(context.project_dir).as_posix(),
        catalog_path.relative_to(context.project_dir).as_posix(),
        input_path.relative_to(context.project_dir).as_posix(),
    ]


def validate_plan_outputs(context: ProjectContext) -> None:
    try:
        plan = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "edit-plan.json",
            "edit-plan",
        )
        catalog_copy = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "component-catalog.json",
            "component-catalog",
        )
        planning_input = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "cowork-input.json",
            "planning-input",
        )
    except PersistenceError as exc:
        raise PlanningError(f"Planning artifacts are invalid: {exc}") from exc
    catalog = _load_catalog(context.repository_root)
    if catalog_copy != catalog:
        raise PlanningError("Project component catalog snapshot is stale or modified.")
    expected_input = _planning_input(context)
    if planning_input != expected_input:
        raise PlanningError("Cowork planning input is stale or contains unapproved paths.")
    for relative in cast(dict[str, str], planning_input["paths"]).values():
        try:
            artifact = resolve_inside(context.project_dir, relative)
        except UnsafePathError as exc:
            raise PlanningError(f"Cowork planning path is unsafe: {exc}") from exc
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise PlanningError(f"Cowork planning artifact is missing: {relative}")
    validate_plan_document(context, plan, catalog=catalog)


def import_plan_document(context: ProjectContext, document: object) -> list[str]:
    if not isinstance(document, dict):
        raise PlanningError("Imported edit plan root must be a JSON object.")
    plan = cast(dict[str, Any], copy.deepcopy(document))
    validate_plan_document(context, plan)
    path = context.project_dir / "planning" / "edit-plan.json"
    write_validated_json_atomic(context.repository_root, path, "edit-plan", plan)
    validate_plan_outputs(context)
    return [path.relative_to(context.project_dir).as_posix()]


def import_plan_file(context: ProjectContext, relative_path: str) -> list[str]:
    try:
        path = resolve_inside(context.project_dir, relative_path)
    except UnsafePathError as exc:
        raise PlanningError(f"Imported plan path is unsafe: {exc}") from exc
    if path.suffix.casefold() != ".json":
        raise PlanningError("Imported plan must be a JSON file.")
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise PlanningError("Imported plan is missing or exceeds the 2 MB limit.")
    try:
        document = read_json(path)
    except PersistenceError as exc:
        raise PlanningError(f"Imported plan JSON is invalid: {exc}") from exc
    return import_plan_document(context, document)


def apply_revision_document(context: ProjectContext, revision: object) -> list[str]:
    if not isinstance(revision, dict):
        raise PlanningError("Plan revision root must be a JSON object.")
    _finite_document(revision)
    errors = validate_document(context.repository_root, "plan-revision", revision)
    if errors:
        raise PlanningError("Invalid plan revision:\n" + "\n".join(f"- {item}" for item in errors))
    typed_revision = cast(dict[str, Any], revision)
    if typed_revision["projectId"] != context.project["projectId"]:
        raise PlanningError("Plan revision belongs to another project.")
    try:
        current = read_validated_json(
            context.repository_root,
            context.project_dir / "planning" / "edit-plan.json",
            "edit-plan",
        )
    except PersistenceError as exc:
        raise PlanningError(f"Current edit plan is invalid: {exc}") from exc
    updated = copy.deepcopy(current)
    words = {
        cast(str, word["id"]): word
        for word in cast(list[dict[str, Any]], updated["captions"]["words"])
    }
    scenes = {
        cast(str, scene["id"]): scene for scene in cast(list[dict[str, Any]], updated["scenes"])
    }
    for operation in cast(list[dict[str, Any]], typed_revision["operations"]):
        operation_name = operation["op"]
        if operation_name == "set-caption-emphasis":
            target = words.get(cast(str, operation["wordId"]))
            if target is None:
                raise PlanningError("Revision references an unknown caption word ID.")
            target["emphasis"] = operation["emphasis"]
        elif operation_name == "set-caption-preset":
            updated["style"]["captionPreset"] = operation["captionPreset"]
        else:
            scene = scenes.get(cast(str, operation["sceneId"]))
            if scene is None:
                raise PlanningError("Revision references an unknown scene ID.")
            if operation_name == "set-scene-camera":
                scene["camera"] = copy.deepcopy(operation["camera"])
            elif operation_name == "set-scene-layout":
                scene["layout"] = operation["layout"]
            elif operation_name == "set-scene-broll-query":
                scene["broll"]["query"] = operation["query"]
            elif operation_name == "set-scene-graphic":
                graphic = copy.deepcopy(cast(dict[str, Any], operation["graphic"]))
                graphics = cast(list[dict[str, Any]], scene["graphics"])
                for index, existing in enumerate(graphics):
                    if existing["id"] == graphic["id"]:
                        graphics[index] = graphic
                        break
                else:
                    graphics.append(graphic)
            elif operation_name == "remove-scene-graphic":
                graphics = cast(list[dict[str, Any]], scene["graphics"])
                remaining = [item for item in graphics if item["id"] != operation["graphicId"]]
                if len(remaining) == len(graphics):
                    raise PlanningError("Revision references an unknown graphic ID.")
                scene["graphics"] = remaining
            else:
                raise PlanningError(f"Unsupported revision operation: {operation_name}")
    validate_plan_document(context, updated)
    path = context.project_dir / "planning" / "edit-plan.json"
    write_validated_json_atomic(context.repository_root, path, "edit-plan", updated)
    validate_plan_outputs(context)
    return [path.relative_to(context.project_dir).as_posix()]
