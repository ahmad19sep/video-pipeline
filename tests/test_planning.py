from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from cutmachine.assets import prepare_assets, validate_asset_readiness
from cutmachine.editorial import build_timeline_documents
from cutmachine.persistence import read_validated_json, write_validated_json_atomic
from cutmachine.planning import (
    PlanningError,
    apply_revision_document,
    generate_plan,
    import_plan_document,
    import_plan_file,
    validate_plan_document,
    validate_plan_outputs,
)
from cutmachine.project import ProjectContext, sha256_file
from cutmachine.rendering import (
    build_render_input,
    preprocess_project,
    render_draft,
    validate_draft_outputs,
    validate_preprocess_outputs,
)


@pytest.fixture
def planned_context(ingested_context: ProjectContext) -> ProjectContext:
    media_info = read_validated_json(
        ingested_context.repository_root,
        ingested_context.project_dir / "analysis" / "media-info.json",
        "media-info",
    )
    duration = float(cast(dict[str, Any], media_info["format"])["durationSeconds"])
    words = [
        {
            "id": "word_000001",
            "segmentId": "segment_000001",
            "start": 0.1,
            "end": 0.5,
            "raw": "AI",
            "display": "AI",
            "language": "ur",
            "confidence": 0.99,
            "source": "faster-whisper",
            "normalizationSource": "technical-glossary",
            "lockedTiming": True,
        },
        {
            "id": "word_000002",
            "segmentId": "segment_000001",
            "start": 0.6,
            "end": 1.0,
            "raw": "useful",
            "display": "useful",
            "language": "ur",
            "confidence": 0.9,
            "source": "faster-whisper",
            "normalizationSource": "preserved",
            "lockedTiming": True,
        },
    ]
    normalized = {
        "version": 1,
        "projectId": ingested_context.project["projectId"],
        "language": "ur",
        "displayLanguage": "roman-urdu",
        "durationSeconds": duration,
        "segments": [
            {
                "id": "segment_000001",
                "start": 0.1,
                "end": 1.0,
                "text": "AI useful",
                "wordIds": ["word_000001", "word_000002"],
            }
        ],
        "words": words,
        "provenance": {
            "createdAt": "2026-07-15T12:00:00+00:00",
            "rawTranscriptPath": "transcript/transcript.raw.json",
            "glossaryPath": "config/technical-glossary.json",
            "lexiconPath": "config/roman-urdu-lexicon.json",
            "refinement": {
                "enabled": False,
                "attemptedBatches": 0,
                "appliedBatches": 0,
                "failedBatches": 0,
                "provider": None,
            },
            "wordCountPreserved": True,
            "timingPreserved": True,
        },
    }
    write_validated_json_atomic(
        ingested_context.repository_root,
        ingested_context.project_dir / "transcript" / "transcript.roman.json",
        "normalized-transcript",
        normalized,
    )
    silence = {
        "policy": {"paddingBefore": 0.13, "paddingAfter": 0.2},
        "candidates": [],
    }
    timeline, time_map, remapped = build_timeline_documents(normalized, silence)
    for relative, schema, document in (
        ("timeline/source-timeline.json", "timeline", timeline),
        ("timeline/time-map.json", "time-map", time_map),
        ("transcript/transcript.remapped.json", "remapped-transcript", remapped),
    ):
        write_validated_json_atomic(
            ingested_context.repository_root,
            ingested_context.project_dir / relative,
            schema,
            document,
        )
    generate_plan(ingested_context)
    return ingested_context


def _plan(context: ProjectContext) -> dict[str, Any]:
    return read_validated_json(
        context.repository_root,
        context.project_dir / "planning" / "edit-plan.json",
        "edit-plan",
    )


def test_offline_baseline_plan_is_complete_and_valid(planned_context: ProjectContext) -> None:
    validate_plan_outputs(planned_context)
    plan = _plan(planned_context)
    planning_input = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "cowork-input.json",
        "planning-input",
    )

    assert plan["provenance"]["createdBy"] == "cutmachine-local-baseline"
    assert [word["id"] for word in plan["captions"]["words"]] == [
        "word_000001",
        "word_000002",
    ]
    assert plan["captions"]["words"][0]["emphasis"] is True
    assert plan["scenes"][0]["sourceTimelineIds"] == ["keep_000001"]
    assert plan["globalAudio"]["musicAssetId"] is None
    assert planning_input["constraints"]["allowExecutableContent"] is False
    assert all(not Path(path).is_absolute() for path in planning_input["paths"].values())


def test_phase6_prepares_validated_local_render_input(
    planned_context: ProjectContext,
) -> None:
    preserved_paths = [
        planned_context.project_dir / planned_context.project["source"]["storedPath"],
        planned_context.project_dir / "media" / "proxy.mp4",
        planned_context.project_dir / "transcript" / "transcript.roman.json",
        planned_context.project_dir / "timeline" / "source-timeline.json",
    ]
    preserved_hashes = {path: sha256_file(path) for path in preserved_paths}
    artifacts = prepare_assets(planned_context)
    assert "assets/manifest.json" in artifacts
    assert "planning/resolved-edit-plan.json" in artifacts
    validate_asset_readiness(planned_context)
    preprocess_artifacts = preprocess_project(planned_context)
    assert "analysis/preprocess-record.json" in preprocess_artifacts
    assert "media/technical-proxy.mp4" in preprocess_artifacts
    validate_preprocess_outputs(planned_context)
    audio_mastering = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "analysis" / "audio-mastering.json",
        "audio-mastering",
    )
    technical_finish = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "analysis" / "technical-finish.json",
        "technical-finish",
    )
    assert abs(audio_mastering["after"]["integratedLufs"] + 14) <= 1
    assert audio_mastering["after"]["truePeakDb"] <= -1
    assert technical_finish["videoCodec"] == "h264"
    assert technical_finish["audioCodec"] == "aac"
    assert {path: sha256_file(path) for path in preserved_paths} == preserved_hashes

    input_path = build_render_input(planned_context)
    render_input = read_validated_json(planned_context.repository_root, input_path, "render-input")

    assert render_input["video"]["width"] == 960
    assert render_input["video"]["height"] == 540
    assert render_input["timelineSegments"][0]["id"] == "keep_000001"
    assert render_input["captions"]["words"][0]["id"] == "word_000001"
    assert render_input["assets"]
    assert all(path.endswith(".wav") for path in render_input["assets"].values())
    assert render_input["scenes"][0]["sfx"]
    staged = planned_context.repository_root / "remotion" / "public" / render_input["videoSrc"]
    assert (
        staged.read_bytes()
        == (planned_context.project_dir / "media" / "technical-proxy.mp4").read_bytes()
    )


def test_phase7_resolves_owned_broll_music_and_sfx_into_render_input(
    planned_context: ProjectContext,
) -> None:
    library = planned_context.repository_root / "assets-library"
    broll = library / "broll" / "student-ai-laptop.mp4"
    music = library / "music" / "calm-technology.wav"
    sfx = library / "sfx" / "soft-impact.wav"
    shutil.copy2(planned_context.project_dir / "media" / "proxy.mp4", broll)
    shutil.copy2(planned_context.project_dir / "audio" / "original.wav", music)
    shutil.copy2(planned_context.project_dir / "audio" / "source.wav", sfx)
    for path, tags in (
        (broll, ["student", "using", "ai", "laptop"]),
        (music, ["calm", "technology", "music"]),
        (sfx, ["soft", "impact"]),
    ):
        path.with_suffix(path.suffix + ".asset.json").write_text(
            json.dumps(
                {
                    "tags": tags,
                    "license": "owned",
                    "creator": "CutMachine test",
                    "attributionRequired": False,
                }
            ),
            encoding="utf-8",
        )
    plan = _plan(planned_context)
    plan["scenes"][0]["broll"]["query"] = "student using AI laptop"
    plan["scenes"][0]["sfx"] = [
        {
            "assetId": None,
            "query": "soft impact",
            "offset": 0.2,
            "gainDb": -12,
        }
    ]
    plan["globalAudio"]["musicQuery"] = "calm technology music"
    import_plan_document(planned_context, plan)

    prepare_assets(planned_context)
    validate_asset_readiness(planned_context)
    manifest = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "assets" / "manifest.json",
        "asset-manifest",
    )
    resolved = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "resolved-edit-plan.json",
        "edit-plan",
    )
    index = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "asset-index.json",
        "asset-index",
    )
    preprocess_project(planned_context)
    input_path = build_render_input(planned_context)
    render_input = read_validated_json(planned_context.repository_root, input_path, "render-input")

    assert len(manifest["assets"]) == 3
    assert all(
        (planned_context.repository_root / item["previewPath"]).is_file()
        for item in index["assets"]
    )
    assert {item["status"] for item in manifest["requests"]} == {"resolved"}
    assert resolved["scenes"][0]["broll"]["assetId"] in render_input["assets"]
    assert resolved["scenes"][0]["sfx"][0]["assetId"] in render_input["assets"]
    assert resolved["globalAudio"]["musicAssetId"] in render_input["assets"]
    assert render_input["globalAudio"]["duckingEnabled"] is True
    assert render_input["captions"]["enabled"] is True
    assert all(item["license"] == "owned" for item in manifest["assets"])

    actual_remotion = Path(__file__).resolve().parents[1] / "remotion"
    public_project = (
        actual_remotion / "public" / "cutmachine" / cast(str, planned_context.project["projectId"])
    )
    try:
        render_draft(planned_context, remotion_root=actual_remotion)
        validate_draft_outputs(planned_context)
    finally:
        shutil.rmtree(public_project, ignore_errors=True)


def test_explicit_owned_broll_pin_overrides_automatic_ranking(
    planned_context: ProjectContext,
) -> None:
    library = planned_context.repository_root / "assets-library"
    broll = library / "broll" / "creator-choice.mp4"
    shutil.copy2(planned_context.project_dir / "media" / "proxy.mp4", broll)
    broll.with_suffix(broll.suffix + ".asset.json").write_text(
        json.dumps(
            {
                "tags": ["unrelated", "creator", "choice"],
                "license": "owned",
                "creator": "CutMachine test",
                "attributionRequired": False,
            }
        ),
        encoding="utf-8",
    )
    plan = _plan(planned_context)
    plan["scenes"][0]["broll"]["query"] = "student using AI laptop"
    import_plan_document(planned_context, plan)
    local_id = f"local_{sha256_file(broll)[:16]}"
    write_validated_json_atomic(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "asset-pins.json",
        "asset-pins",
        {
            "version": 1,
            "projectId": planned_context.project["projectId"],
            "pins": [{"sceneId": "scene_000001", "localAssetId": local_id}],
        },
    )

    prepare_assets(planned_context)
    validate_asset_readiness(planned_context)
    resolved = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "resolved-edit-plan.json",
        "edit-plan",
    )
    ranking = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "asset-ranking.json",
        "asset-ranking",
    )

    assert resolved["scenes"][0]["broll"]["assetId"] == f"asset_{sha256_file(broll)[:16]}"
    assert ranking["selections"][0]["totalScore"] == 1
    assert "explicit validated creator-owned" in ranking["selections"][0]["reason"]


def test_phase7_provider_download_is_cached_and_corruption_degrades_cleanly(
    planned_context: ProjectContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(planned_context)
    plan["scenes"][0]["graphics"] = []
    plan["scenes"][0]["layout"] = "speaker-fullscreen"
    plan["scenes"][0]["broll"]["query"] = "student using AI laptop"
    import_plan_document(planned_context, plan)
    planned_context.project["settings"]["networkEnabled"] = True
    monkeypatch.setenv("CUTMACHINE__NETWORK__ENABLED", "true")
    monkeypatch.setenv("CUTMACHINE__ASSETS__PEXELS__ENABLED", "true")
    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    searches: list[str] = []

    def search(url: str, _headers: dict[str, str], _timeout: int) -> dict[str, Any]:
        searches.append(url)
        return {
            "videos": [
                {
                    "id": 42,
                    "duration": 2,
                    "url": "https://www.pexels.com/video/42",
                    "user": {"name": "Creator"},
                    "video_files": [
                        {
                            "id": 7,
                            "file_type": "video/mp4",
                            "width": 320,
                            "height": 240,
                            "link": "https://videos.pexels.com/video.mp4",
                        }
                    ],
                }
            ]
        }

    payload = (planned_context.project_dir / "media" / "proxy.mp4").read_bytes()

    def download(
        _url: str, _headers: dict[str, str], _timeout: int, _maximum: int
    ) -> tuple[bytes, str]:
        return payload, "video/mp4"

    prepare_assets(
        planned_context,
        pexels_transport=search,
        download_transport=download,
    )
    first = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "assets" / "manifest.json",
        "asset-manifest",
    )
    first_provider = next(item for item in first["assets"] if item["provider"] == "pexels")
    assert searches and first_provider["provider"] == "pexels"

    monkeypatch.setenv("CUTMACHINE__ASSETS__PEXELS__ENABLED", "false")
    prepare_assets(planned_context, pexels_transport=lambda *_args: pytest.fail("network used"))
    cached = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "assets" / "manifest.json",
        "asset-manifest",
    )
    assert len(searches) == 1
    cached_provider = next(item for item in cached["assets"] if item["provider"] == "pexels")
    assert cached_provider["sha256"] == first_provider["sha256"]

    cache = read_validated_json(
        planned_context.repository_root,
        planned_context.repository_root / ".cache" / "assets" / "cache.json",
        "asset-cache",
    )
    (planned_context.repository_root / cache["entries"][0]["objectPath"]).unlink()
    prepare_assets(planned_context)
    degraded = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "assets" / "manifest.json",
        "asset-manifest",
    )
    assert not any(item["provider"] == "pexels" for item in degraded["assets"])
    assert degraded["requests"][0]["status"] == "missing"


def test_phase8_applies_validated_owned_lut_below_full_strength(
    planned_context: ProjectContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lut = planned_context.repository_root / "assets-library" / "luts" / "identity.cube"
    lut.write_text(
        "\n".join(
            (
                "TITLE identity",
                "LUT_3D_SIZE 2",
                "DOMAIN_MIN 0 0 0",
                "DOMAIN_MAX 1 1 1",
                "0 0 0",
                "1 0 0",
                "0 1 0",
                "1 1 0",
                "0 0 1",
                "1 0 1",
                "0 1 1",
                "1 1 1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    lut.with_suffix(".cube.asset.json").write_text(
        json.dumps(
            {
                "tags": ["identity", "clean"],
                "license": "owned",
                "creator": "CutMachine test",
                "attributionRequired": False,
                "colorSpace": "rec709",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CUTMACHINE__TECHNICAL__LUT__ENABLED", "true")
    monkeypatch.setenv("CUTMACHINE__TECHNICAL__LUT__PATH", "luts/identity.cube")
    monkeypatch.setenv("CUTMACHINE__TECHNICAL__LUT__INTENSITY", "0.35")

    prepare_assets(planned_context)
    preprocess_project(planned_context)
    color = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "analysis" / "color-analysis.json",
        "color-analysis",
    )
    finish = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "analysis" / "technical-finish.json",
        "technical-finish",
    )

    assert color["lut"]["enabled"] is True
    assert color["lut"]["intensity"] == 0.35
    assert color["lut"]["colorSpace"] == "rec709"
    assert "licensed-lut" in finish["operations"]


@pytest.mark.parametrize("portrait", [False, True])
def test_phase6_renders_decodable_horizontal_and_vertical_drafts(
    planned_context: ProjectContext,
    portrait: bool,
) -> None:
    if portrait:
        media_path = planned_context.project_dir / "analysis" / "media-info.json"
        media_info = read_validated_json(planned_context.repository_root, media_path, "media-info")
        media_info["video"]["width"] = 240
        media_info["video"]["height"] = 320
        write_validated_json_atomic(
            planned_context.repository_root, media_path, "media-info", media_info
        )
        generate_plan(planned_context)
    else:
        normalized = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "transcript" / "transcript.roman.json",
            "normalized-transcript",
        )
        silence = {
            "policy": {"paddingBefore": 0.13, "paddingAfter": 0.2},
            "candidates": [
                {
                    "id": "silence_000001",
                    "type": "internal-silence",
                    "confidence": 1.0,
                    "decision": "remove",
                    "automatic": True,
                    "proposedCutStart": 1.1,
                    "proposedCutEnd": 1.5,
                }
            ],
        }
        timeline, time_map, remapped = build_timeline_documents(normalized, silence)
        for relative, schema, document in (
            ("timeline/source-timeline.json", "timeline", timeline),
            ("timeline/time-map.json", "time-map", time_map),
            ("transcript/transcript.remapped.json", "remapped-transcript", remapped),
        ):
            write_validated_json_atomic(
                planned_context.repository_root,
                planned_context.project_dir / relative,
                schema,
                document,
            )
        generate_plan(planned_context)

    prepare_assets(planned_context)
    preprocess_project(planned_context)
    actual_remotion = Path(__file__).resolve().parents[1] / "remotion"
    public_project = (
        actual_remotion / "public" / "cutmachine" / cast(str, planned_context.project["projectId"])
    )
    try:
        artifacts = render_draft(planned_context, remotion_root=actual_remotion)
        validate_draft_outputs(planned_context)
        record = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "renders" / "draft-render.json",
            "draft-render",
        )
        assert artifacts[1] == "review/draft.mp4"
        assert artifacts[3] == "renders/final-pass.json"
        assert record["videoCodec"] == "h264"
        assert record["audioCodec"] == "aac"
        input_document = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "renders" / "draft-input.json",
            "render-input",
        )
        assert len(input_document["timelineSegments"]) == (1 if portrait else 2)
        final_pass = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "renders" / "final-pass.json",
            "final-pass",
        )
        assert final_pass["operation"] == "stream-copy-faststart"
        assert (record["width"], record["height"]) == ((540, 960) if portrait else (960, 540))
    finally:
        shutil.rmtree(public_project, ignore_errors=True)


def test_unknown_component_and_executable_prop_are_rejected(
    planned_context: ProjectContext,
) -> None:
    plan = _plan(planned_context)
    plan["scenes"][0]["graphics"][0]["component"] = "InventedWidget"
    with pytest.raises(PlanningError, match="Unknown graphic component"):
        validate_plan_document(planned_context, plan)

    plan = _plan(planned_context)
    plan["scenes"][0]["graphics"][0]["props"]["script"] = "run-dangerous()"
    with pytest.raises(PlanningError, match="unsupported prop 'script'"):
        validate_plan_document(planned_context, plan)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda plan: plan["video"].update(source="C:/private/raw.mp4"), "Invalid edit plan"),
        (lambda plan: plan.update(projectId="prj_other"), "another project"),
        (
            lambda plan: plan["globalAudio"].update(musicAssetId="asset_unresolved"),
            "Asset IDs are not valid",
        ),
        (lambda plan: plan["scenes"][0].update(end=999.0), "exceeds timeline duration"),
        (
            lambda plan: plan["captions"]["words"][0].update(start=0.2),
            "changed authoritative field start",
        ),
    ],
)
def test_imported_plan_rejects_invalid_cross_references(
    planned_context: ProjectContext,
    mutation: Any,
    message: str,
) -> None:
    plan = _plan(planned_context)
    mutation(plan)

    with pytest.raises(PlanningError, match=message):
        import_plan_document(planned_context, plan)


def test_valid_import_replaces_only_the_plan(planned_context: ProjectContext) -> None:
    plan = _plan(planned_context)
    plan["style"]["captionPreset"] = "clean-two-line"

    artifacts = import_plan_document(planned_context, plan)

    assert artifacts == ["planning/edit-plan.json"]
    assert _plan(planned_context)["style"]["captionPreset"] == "clean-two-line"


def test_import_file_rejects_traversal(planned_context: ProjectContext) -> None:
    with pytest.raises(PlanningError, match="path is unsafe"):
        import_plan_file(planned_context, "../outside.json")


def test_typed_revision_preserves_unrelated_plan_content(
    planned_context: ProjectContext,
) -> None:
    before = _plan(planned_context)
    revision = {
        "version": 1,
        "projectId": planned_context.project["projectId"],
        "operations": [
            {"op": "set-caption-emphasis", "wordId": "word_000002", "emphasis": True},
            {"op": "set-captions-enabled", "enabled": False},
            {
                "op": "set-scene-camera",
                "sceneId": "scene_000001",
                "camera": {
                    "mode": "slow-zoom",
                    "scaleStart": 1.0,
                    "scaleEnd": 1.1,
                    "focus": "face",
                },
            },
        ],
    }

    apply_revision_document(planned_context, revision)
    after = _plan(planned_context)

    assert after["captions"]["words"][1]["emphasis"] is True
    assert after["captions"]["enabled"] is False
    assert after["scenes"][0]["camera"]["mode"] == "slow-zoom"
    assert after["video"] == before["video"]
    assert after["globalAudio"] == before["globalAudio"]
    assert after["scenes"][0]["graphics"] == before["scenes"][0]["graphics"]


def test_graphic_revision_adds_price_comparison_at_runtime(
    planned_context: ProjectContext,
) -> None:
    revision = {
        "version": 1,
        "projectId": planned_context.project["projectId"],
        "operations": [
            {
                "op": "remove-scene-graphic",
                "sceneId": "scene_000001",
                "graphicId": "graphic_000001",
            },
            {
                "op": "set-scene-graphic",
                "sceneId": "scene_000001",
                "graphic": {
                    "id": "graphic_price_000001",
                    "component": "PriceComparison",
                    "startOffset": 0.0,
                    "endOffset": 0.5,
                    "props": {"lowValue": "$1", "highValue": "$100", "label": "hosting cost"},
                },
            },
        ],
    }

    apply_revision_document(planned_context, revision)
    graphics = _plan(planned_context)["scenes"][0]["graphics"]

    assert [item["id"] for item in graphics] == ["graphic_price_000001"]
    assert graphics[0]["component"] == "PriceComparison"
    assert graphics[0]["props"]["lowValue"] == "$1"
    assert graphics[0]["props"]["highValue"] == "$100"


def test_graphic_revision_rejects_unknown_component_and_graphic(
    planned_context: ProjectContext,
) -> None:
    unknown_component = {
        "version": 1,
        "projectId": planned_context.project["projectId"],
        "operations": [
            {
                "op": "set-scene-graphic",
                "sceneId": "scene_000001",
                "graphic": {
                    "id": "graphic_evil_000001",
                    "component": "EvilComponent",
                    "startOffset": 0.0,
                    "endOffset": 0.5,
                    "props": {"title": "x"},
                },
            }
        ],
    }
    with pytest.raises(PlanningError, match="Unknown graphic component"):
        apply_revision_document(planned_context, unknown_component)

    unknown_graphic = {
        "version": 1,
        "projectId": planned_context.project["projectId"],
        "operations": [
            {"op": "remove-scene-graphic", "sceneId": "scene_000001", "graphicId": "graphic_none"}
        ],
    }
    with pytest.raises(PlanningError, match="unknown graphic ID"):
        apply_revision_document(planned_context, unknown_graphic)


def test_revision_rejects_unknown_word_and_arbitrary_operation(
    planned_context: ProjectContext,
) -> None:
    unknown_word = {
        "version": 1,
        "projectId": planned_context.project["projectId"],
        "operations": [{"op": "set-caption-emphasis", "wordId": "word_999999", "emphasis": True}],
    }
    with pytest.raises(PlanningError, match="unknown caption word"):
        apply_revision_document(planned_context, unknown_word)

    arbitrary = {
        "version": 1,
        "projectId": planned_context.project["projectId"],
        "operations": [{"op": "set-json-path", "path": "/video/source", "value": "bad"}],
    }
    with pytest.raises(PlanningError, match="Invalid plan revision"):
        apply_revision_document(planned_context, arbitrary)


def test_non_finite_import_is_rejected(planned_context: ProjectContext) -> None:
    plan = copy.deepcopy(_plan(planned_context))
    plan["scenes"][0]["start"] = float("nan")

    with pytest.raises(PlanningError, match="non-finite"):
        import_plan_document(planned_context, plan)


def test_prompt_templates_are_json_only_contracts() -> None:
    root = Path(__file__).resolve().parents[1]
    planner = (root / "prompts" / "cowork-editor.md").read_text(encoding="utf-8")
    reviser = (root / "prompts" / "edit-plan-reviser.md").read_text(encoding="utf-8")

    assert "Output JSON only" in planner
    assert "do not rewrite the full plan" in reviser
