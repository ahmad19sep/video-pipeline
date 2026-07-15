from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from cutmachine import orchestrator
from cutmachine.assets import prepare_assets
from cutmachine.editorial import analyze_project, generate_timeline
from cutmachine.normalization import normalize_project
from cutmachine.orchestrator import run_new_project
from cutmachine.persistence import read_validated_json, write_validated_json_atomic
from cutmachine.planning import generate_plan
from cutmachine.project import ProjectContext, open_project, sha256_file
from cutmachine.rendering import preprocess_project, render_draft
from cutmachine.review import (
    QualityControlBlocked,
    ReviewError,
    apply_review_revision,
    run_quality_control,
    validate_qc_outputs,
    validate_review_decision,
    write_approval_decision,
)
from cutmachine.transcription import transcribe_project


@dataclass
class FakeWord:
    start: float
    end: float
    word: str
    probability: float = 0.99


@dataclass
class FakeSegment:
    start: float = 0.1
    end: float = 1.0
    text: str = "AI useful"
    words: tuple[FakeWord, ...] = (
        FakeWord(0.1, 0.5, "AI"),
        FakeWord(0.6, 1.0, "useful"),
    )


@dataclass
class FakeInfo:
    language: str = "ur"
    duration: float = 2.0


class FakeModel:
    def transcribe(self, audio: object, **kwargs: object) -> tuple[list[FakeSegment], FakeInfo]:
        del audio, kwargs
        return [FakeSegment()], FakeInfo()


@pytest.fixture
def finished_context(ingested_context: ProjectContext) -> Iterator[ProjectContext]:
    transcribe_project(
        ingested_context,
        model_factory=lambda _settings: FakeModel(),
        gpu_memory_mb=0,
    )
    normalize_project(ingested_context)
    analyze_project(ingested_context)
    generate_timeline(ingested_context)
    generate_plan(ingested_context)
    prepare_assets(ingested_context)
    preprocess_project(ingested_context)
    remotion_root = Path(__file__).resolve().parents[1] / "remotion"
    public_project = (
        remotion_root / "public" / "cutmachine" / str(ingested_context.project["projectId"])
    )
    try:
        render_draft(ingested_context, remotion_root=remotion_root)
        yield ingested_context
    finally:
        shutil.rmtree(public_project, ignore_errors=True)


def test_phase9_generates_safe_review_and_blocks_regressed_voice(
    finished_context: ProjectContext,
) -> None:
    preserved = [
        finished_context.project_dir / finished_context.project["source"]["storedPath"],
        finished_context.project_dir / "transcript" / "transcript.raw.json",
        finished_context.project_dir / "transcript" / "transcript.roman.json",
        finished_context.project_dir / "transcript" / "transcript.remapped.json",
        finished_context.project_dir / "timeline" / "source-timeline.json",
        finished_context.project_dir / "planning" / "edit-plan.json",
    ]
    hashes = {path: sha256_file(path) for path in preserved}
    finished_context.project["source"]["originalName"] = (
        '<img src="https://attacker.invalid/x" onerror="alert(1)">'
    )

    artifacts = run_quality_control(finished_context)
    validate_qc_outputs(finished_context)
    report = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "review" / "qc-report.json",
        "qc-report",
    )
    package = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "review" / "review-package.json",
        "review-package",
    )
    page = (finished_context.project_dir / "review" / "index.html").read_text(encoding="utf-8")

    assert report["status"] == "passed"
    assert report["counts"]["blocking"] == 0
    assert len(report["checks"]) == 15
    assert package["readOnly"] is True
    assert package["remoteResources"] is False
    assert "review/index.html" in artifacts
    assert all(
        section in page
        for section in (
            'id="draft"',
            'id="scenes"',
            'id="transcript-warnings"',
            'id="uncertain-cuts"',
            'id="assets"',
            'id="color"',
            'id="audio"',
            'id="qc"',
            'id="action"',
        )
    )
    assert "&lt;img" in page
    assert not re.search(r"(?:src|href)=[\"']https?://", page, re.IGNORECASE)
    assert "<script" not in page.casefold()
    assert all(sha256_file(path) == digest for path, digest in hashes.items())

    decision_artifacts = write_approval_decision(finished_context, "Ready to publish.")
    decision = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "review" / "decision.json",
        "review-decision",
    )
    assert decision_artifacts == ["review/decision.json"]
    assert decision["action"] == "approved"
    assert decision["revisionPath"] is None
    validate_review_decision(finished_context, expected_action="approved")

    audio_path = finished_context.project_dir / "analysis" / "audio-mastering.json"
    audio = read_validated_json(finished_context.repository_root, audio_path, "audio-mastering")
    audio["speechPresent"] = False
    audio["after"]["integratedLufs"] = -30.0
    audio["after"]["truePeakDb"] = 1.0
    write_validated_json_atomic(
        finished_context.repository_root, audio_path, "audio-mastering", audio
    )
    with pytest.raises(QualityControlBlocked, match="blocking issue"):
        run_quality_control(finished_context)
    blocked = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "review" / "qc-report.json",
        "qc-report",
    )
    assert blocked["status"] == "blocked"
    blocked_checks = {item["checkId"] for item in blocked["findings"]}
    assert {"voice-present", "loudness-valid", "true-peak-valid"} <= blocked_checks
    assert (finished_context.project_dir / "review" / "index.html").is_file()
    with pytest.raises(ReviewError, match="blocking"):
        validate_qc_outputs(finished_context)


def test_phase9_revision_is_typed_project_relative_and_non_destructive(
    finished_context: ProjectContext,
) -> None:
    run_quality_control(finished_context)
    plan_path = finished_context.project_dir / "planning" / "edit-plan.json"
    render_input_path = finished_context.project_dir / "renders" / "draft-input.json"
    render_path = finished_context.project_dir / "renders" / "draft-render.json"
    plan_before = read_validated_json(finished_context.repository_root, plan_path, "edit-plan")
    render_input_before = read_validated_json(
        finished_context.repository_root, render_input_path, "render-input"
    )
    render_before = read_validated_json(
        finished_context.repository_root, render_path, "draft-render"
    )
    invalid_plan = json.loads(json.dumps(plan_before))
    invalid_plan["projectId"] = "prj_other"
    invalid_input = json.loads(json.dumps(render_input_before))
    invalid_input["captions"]["safeZone"] = "shorts-default"
    invalid_render = json.loads(json.dumps(render_before))
    invalid_render["expectedDuration"] = 0.25
    for path, schema, document in (
        (plan_path, "edit-plan", invalid_plan),
        (render_input_path, "render-input", invalid_input),
        (render_path, "draft-render", invalid_render),
    ):
        write_validated_json_atomic(finished_context.repository_root, path, schema, document)
    with pytest.raises(QualityControlBlocked):
        run_quality_control(finished_context)
    blocked = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "review" / "qc-report.json",
        "qc-report",
    )
    blocked_checks = {item["checkId"] for item in blocked["findings"]}
    assert {"plan-valid", "captions-safe-zone", "duration-valid"} <= blocked_checks
    for path, schema, document in (
        (plan_path, "edit-plan", plan_before),
        (render_input_path, "render-input", render_input_before),
        (render_path, "draft-render", render_before),
    ):
        write_validated_json_atomic(finished_context.repository_root, path, schema, document)
    run_quality_control(finished_context)

    with pytest.raises(ReviewError, match="unsafe"):
        apply_review_revision(finished_context, "../outside.json")
    with pytest.raises(ReviewError, match="unsafe"):
        apply_review_revision(finished_context, "C:/outside.json")

    revision_path = finished_context.project_dir / "planning" / "review-revision.json"
    revision = {
        "version": 1,
        "projectId": finished_context.project["projectId"],
        "operations": [
            {
                "op": "set-caption-emphasis",
                "wordId": "word_000002",
                "emphasis": True,
            }
        ],
    }
    write_validated_json_atomic(
        finished_context.repository_root,
        revision_path,
        "plan-revision",
        revision,
    )
    raw_hash = sha256_file(finished_context.project_dir / "transcript" / "transcript.raw.json")
    apply_review_revision(
        finished_context,
        "planning/review-revision.json",
        "Emphasize the second word.",
    )
    plan = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "planning" / "edit-plan.json",
        "edit-plan",
    )
    decision = read_validated_json(
        finished_context.repository_root,
        finished_context.project_dir / "review" / "decision.json",
        "review-decision",
    )
    assert plan["captions"]["words"][1]["emphasis"] is True
    assert decision["action"] == "revision-requested"
    assert decision["invalidateFrom"] == "plan_ready"
    assert (
        sha256_file(finished_context.project_dir / "transcript" / "transcript.raw.json") == raw_hash
    )
    parsed = json.loads(
        (finished_context.project_dir / decision["revisionPath"]).read_text(encoding="utf-8")
    )
    assert parsed == revision


def test_phase9_real_orchestrator_reaches_single_review_checkpoint(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def transcribe(context: ProjectContext) -> list[str]:
        return transcribe_project(
            context,
            model_factory=lambda _settings: FakeModel(),
            gpu_memory_mb=0,
        )

    remotion_root = Path(__file__).resolve().parents[1] / "remotion"

    def render(context: ProjectContext) -> list[str]:
        return render_draft(context, remotion_root=remotion_root)

    monkeypatch.setattr(orchestrator, "transcribe_project", transcribe)
    monkeypatch.setattr(orchestrator, "render_draft", render)
    result = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, result.project_dir)
    public_project = remotion_root / "public" / "cutmachine" / str(context.project["projectId"])
    try:
        state = context.state_store.load()
        validate_qc_outputs(context)
        assert result.workflow_state == "awaiting_review"
        assert result.next_stage == "approved"
        assert state.stage("qc_passed").status == "completed"
        assert state.stage("awaiting_review").status == "completed"
        assert (context.project_dir / "review" / "index.html").is_file()
    finally:
        shutil.rmtree(public_project, ignore_errors=True)
