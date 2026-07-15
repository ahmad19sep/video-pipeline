from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from cutmachine.assets import prepare_assets, rank_candidates
from cutmachine.config import load_config
from cutmachine.learning import (
    LearningError,
    approved_caption_corrections,
    asset_preference_scores,
    learning_summary,
    record_learning_event,
    validate_learning_store,
    validate_performance_report,
    write_performance_report,
)
from cutmachine.normalization import normalize_project, validate_normalized_outputs
from cutmachine.persistence import read_validated_json, write_validated_json_atomic
from cutmachine.project import ProjectContext, create_project, sha256_file
from cutmachine.rendering import (
    preprocess_project,
    render_final_delivery,
    validate_final_delivery,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_raw(context: ProjectContext) -> None:
    raw_words = [
        ("video", 0.1, 0.3),
        ("rimoshan", 0.31, 0.6),
        ("React", 0.61, 0.9),
    ]
    words = [
        {
            "id": f"word_{index:06d}",
            "segmentId": "segment_000001",
            "start": start,
            "end": end,
            "raw": raw,
            "display": raw,
            "language": "ur",
            "confidence": 0.9,
            "source": "faster-whisper",
            "normalizationSource": "raw-transcript",
            "lockedTiming": True,
        }
        for index, (raw, start, end) in enumerate(raw_words, start=1)
    ]
    document = {
        "version": 1,
        "projectId": context.project["projectId"],
        "language": "ur",
        "durationSeconds": 1.0,
        "segments": [
            {
                "id": "segment_000001",
                "start": 0.1,
                "end": 0.9,
                "text": "video rimoshan React",
                "wordIds": [item["id"] for item in words],
            }
        ],
        "words": words,
        "provenance": {
            "createdAt": "2026-07-16T12:00:00+00:00",
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


def _write_manifest(context: ProjectContext) -> str:
    digest = "a" * 64
    asset_id = "asset_" + digest[:16]
    manifest = {
        "version": 2,
        "projectId": context.project["projectId"],
        "createdAt": "2026-07-16T12:00:00+00:00",
        "assets": [
            {
                "id": asset_id,
                "path": "assets/broll/clip.mp4",
                "type": "video",
                "query": "local video",
                "provider": "local",
                "providerId": "broll/clip.mp4",
                "creator": None,
                "license": "owned",
                "attributionRequired": False,
                "sourcePage": None,
                "retrievedAt": "2026-07-16T12:00:00+00:00",
                "sha256": digest,
                "duration": 2.0,
                "width": 1920,
                "height": 1080,
                "selectedScene": "scene_000001",
                "relevanceScore": 0.9,
            }
        ],
        "requests": [],
    }
    write_validated_json_atomic(
        context.repository_root,
        context.project_dir / "assets" / "manifest.json",
        "asset-manifest",
        manifest,
    )
    return asset_id


def _write_review_decision(context: ProjectContext, action: str = "approved") -> None:
    qc = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": "2026-07-16T12:00:00+00:00",
        "status": "passed",
        "recommendation": "approve-or-revise",
        "artifacts": {
            "draftPath": "review/draft.mp4",
            "draftSha256": "b" * 64,
            "beforeFramePath": "review/color-before.jpg",
            "beforeFrameSha256": "c" * 64,
            "afterFramePath": "review/color-after.jpg",
            "afterFrameSha256": "d" * 64,
        },
        "duration": {"expected": 1.0, "actual": 1.0, "tolerance": 0.15, "delta": 0.0},
        "audio": {
            "speechPresent": True,
            "targetLufs": -14,
            "actualLufs": -14,
            "targetTruePeakDb": -1,
            "actualTruePeakDb": -1,
            "longestSilenceSeconds": 0.1,
            "musicDuckingEnabled": False,
        },
        "counts": {"checks": 1, "passed": 1, "warnings": 0, "blocking": 0},
        "checks": [{"id": "plan-valid", "status": "pass", "message": "valid"}],
        "findings": [],
    }
    qc_path = context.project_dir / "review" / "qc-report.json"
    write_validated_json_atomic(context.repository_root, qc_path, "qc-report", qc)
    revision_requested = action == "revision-requested"
    decision = {
        "version": 1,
        "projectId": context.project["projectId"],
        "createdAt": "2026-07-16T12:01:00+00:00",
        "action": action,
        "note": None,
        "qcReportPath": "review/qc-report.json",
        "qcReportSha256": sha256_file(qc_path),
        "revisionPath": "review/requested-revision.json" if revision_requested else None,
        "revisionSha256": "e" * 64 if revision_requested else None,
        "invalidateFrom": "plan_ready" if revision_requested else None,
    }
    write_validated_json_atomic(
        context.repository_root,
        context.project_dir / "review" / "decision.json",
        "review-decision",
        decision,
    )


def _write_feedback(context: ProjectContext, asset_id: str) -> str:
    feedback = {
        "version": 1,
        "projectId": context.project["projectId"],
        "assetSignals": [{"assetId": asset_id, "preference": "preferred"}],
        "captionCorrections": [
            {
                "wordId": "word_000002",
                "preferred": "Remotion",
                "context": ["video", "react"],
            }
        ],
        "styleSignal": {
            "preference": "preferred",
            "captionPreset": "clean-two-line",
            "transitionDensity": "none",
            "visualChangeTargetSeconds": 6.0,
            "effectBudgetScale": 0.75,
            "activate": True,
        },
    }
    relative = "review/learning-feedback.json"
    write_validated_json_atomic(
        context.repository_root,
        context.project_dir / relative,
        "learning-feedback",
        feedback,
    )
    return relative


def _learning_context(ingested_context: ProjectContext) -> tuple[ProjectContext, str]:
    _write_raw(ingested_context)
    asset_id = _write_manifest(ingested_context)
    _write_review_decision(ingested_context)
    return ingested_context, _write_feedback(ingested_context, asset_id)


def test_phase11_records_hash_bound_event_and_derived_profiles(
    ingested_context: ProjectContext,
) -> None:
    context, feedback = _learning_context(ingested_context)

    artifacts = record_learning_event(
        context,
        expected_review_action="approved",
        feedback_relative=feedback,
    )

    assert len(artifacts) == 4
    validate_learning_store(context.repository_root)
    summary = learning_summary(context.repository_root)
    assert summary == {
        "valid": True,
        "events": 1,
        "assetPreferences": 1,
        "captionCorrections": 1,
        "activeStyleModes": ["fast"],
    }
    assert asset_preference_scores(context.repository_root)[("local", "broll/clip.mp4")] == 1
    assert approved_caption_corrections(context.repository_root)[0]["preferred"] == "Remotion"
    tuned = load_config(context.repository_root, style="fast")
    assert tuned["style"]["caption_preset"] == "clean-two-line"
    assert tuned["style"]["transition_density"] == "none"
    assert tuned["style"]["effect_budgets"]["camera_moves_per_minute"] == 1

    with pytest.raises(LearningError, match="Duplicate learning event"):
        record_learning_event(
            context,
            expected_review_action="approved",
            feedback_relative=feedback,
        )


def test_phase11_profile_tampering_disables_learning_safely(
    ingested_context: ProjectContext,
) -> None:
    context, feedback = _learning_context(ingested_context)
    artifacts = record_learning_event(
        context,
        expected_review_action="approved",
        feedback_relative=feedback,
    )
    event_path = context.repository_root / artifacts[0]
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["mode"] = "balanced"
    event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")

    assert asset_preference_scores(context.repository_root) == {}
    assert learning_summary(context.repository_root)["valid"] is False
    fallback_style = load_config(context.repository_root, style="fast")["style"]
    assert fallback_style["visual_change_target_seconds"] == 7.0
    assert fallback_style["effect_budgets"]["camera_moves_per_minute"] == 2
    with pytest.raises(LearningError, match="stale"):
        validate_learning_store(context.repository_root)


def test_phase11_rejects_unsafe_feedback_and_protected_term_override(
    ingested_context: ProjectContext,
) -> None:
    context, feedback = _learning_context(ingested_context)
    with pytest.raises(LearningError, match="unsafe"):
        record_learning_event(
            context,
            expected_review_action="approved",
            feedback_relative="../feedback.json",
        )

    document = read_validated_json(
        context.repository_root,
        context.project_dir / feedback,
        "learning-feedback",
    )
    document["captionCorrections"][0] = {
        "wordId": "word_000003",
        "preferred": "ArtificialAI",
        "context": [],
    }
    write_validated_json_atomic(
        context.repository_root,
        context.project_dir / feedback,
        "learning-feedback",
        document,
    )
    with pytest.raises(LearningError, match="protected technical term"):
        record_learning_event(
            context,
            expected_review_action="approved",
            feedback_relative=feedback,
        )


def test_phase11_correction_reuse_preserves_word_identity_and_timing(
    ingested_context: ProjectContext,
    real_source_video: Path,
) -> None:
    context, feedback = _learning_context(ingested_context)
    record_learning_event(
        context,
        expected_review_action="approved",
        feedback_relative=feedback,
    )
    future = create_project(context.repository_root, real_source_video, "fast")
    _write_raw(future)
    before = read_validated_json(
        future.repository_root,
        future.project_dir / "transcript" / "transcript.raw.json",
        "transcript",
    )

    normalize_project(future)
    validate_normalized_outputs(future)
    after = read_validated_json(
        future.repository_root,
        future.project_dir / "transcript" / "transcript.roman.json",
        "normalized-transcript",
    )

    corrected = cast(list[dict[str, Any]], after["words"])[1]
    assert corrected["display"] == "Remotion"
    assert corrected["normalizationSource"] == "approved-correction"
    for raw, normalized in zip(before["words"], after["words"], strict=True):
        assert normalized["id"] == raw["id"]
        assert normalized["start"] == raw["start"]
        assert normalized["end"] == raw["end"]


def test_phase11_preferences_only_break_safe_ranking_ties() -> None:
    request = {
        "id": "request_000001",
        "kind": "broll",
        "query": "local video",
        "sceneId": "scene_000001",
        "orientation": "landscape",
        "targetDuration": 2.0,
        "optional": True,
    }
    candidate = {
        "id": "candidate_a",
        "requestId": "request_000001",
        "tier": "local",
        "provider": "local",
        "providerId": "a.mp4",
        "type": "video",
        "localPath": "a.mp4",
        "downloadUrl": None,
        "sourcePage": None,
        "creator": None,
        "license": "owned",
        "attributionRequired": False,
        "tags": ["local", "video"],
        "duration": 2.0,
        "width": 1920,
        "height": 1080,
        "orientation": "landscape",
        "watermark": False,
        "usageCount": 0,
    }
    preferred = copy.deepcopy(candidate)
    preferred["id"] = "candidate_z"
    preferred["providerId"] = "z.mp4"
    selected, evidence = rank_candidates(
        request,
        [candidate, preferred],
        minimum_score=0,
        preference_scores={("local", "z.mp4"): 1.0},
    )
    assert selected is preferred
    assert evidence["scores"]["preference"] == 1

    unsafe = copy.deepcopy(preferred)
    unsafe["license"] = "unknown"
    selected, _evidence = rank_candidates(
        request,
        [unsafe],
        minimum_score=0,
        preference_scores={("local", "z.mp4"): 1.0},
    )
    assert selected is None


def test_phase11_performance_report_is_monotonic_and_cache_explicit(
    ingested_context: ProjectContext,
) -> None:
    artifacts = write_performance_report(
        ingested_context, validated_cache_hits=["validated", "ingested", "validated"]
    )
    validate_performance_report(ingested_context)
    report = read_validated_json(
        ingested_context.repository_root,
        ingested_context.project_dir / artifacts[0],
        "performance-report",
    )
    assert report["validatedCacheHits"] == ["ingested", "validated"]
    assert all(item["durationSeconds"] >= 0 for item in report["stages"])
    assert report["artifactsRevalidated"] is True


def test_phase11_renders_and_validates_final_delivery(
    planned_context: ProjectContext,
) -> None:
    prepare_assets(planned_context)
    preprocess_project(planned_context)
    _write_review_decision(planned_context)
    remotion_root = ROOT / "remotion"
    public_project = (
        remotion_root / "public" / "cutmachine" / cast(str, planned_context.project["projectId"])
    )
    try:
        artifacts = render_final_delivery(planned_context, remotion_root=remotion_root)
        validate_final_delivery(planned_context)
        record = read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / artifacts[-1],
            "delivery-record",
        )
        assert record["width"] == 1920
        assert record["height"] == 1080
        assert (planned_context.repository_root / cast(str, record["deliveryPath"])).is_file()
    finally:
        shutil.rmtree(public_project, ignore_errors=True)
