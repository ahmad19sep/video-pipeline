from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from cutmachine import orchestrator
from cutmachine.orchestrator import resume_project, run_new_project
from cutmachine.project import ProjectContext, open_project
from cutmachine.rendering import RenderError
from cutmachine.review import ReviewError
from cutmachine.state import STAGES
from cutmachine.transcription import ModelSettings, transcribe_project


@dataclass
class FakeWord:
    start: float = 0.1
    end: float = 0.5
    word: str = "AI"
    probability: float = 0.99


@dataclass
class FakeSegment:
    start: float = 0.1
    end: float = 0.5
    text: str = "AI"
    words: tuple[FakeWord, ...] = (FakeWord(),)


@dataclass
class FakeInfo:
    language: str = "ur"
    duration: float = 2.0


class FakeModel:
    def transcribe(self, audio: object, **kwargs: object) -> tuple[list[FakeSegment], FakeInfo]:
        del audio, kwargs
        return [FakeSegment()], FakeInfo()


def _install_fake_transcriber(monkeypatch: pytest.MonkeyPatch) -> None:
    def worker(context: ProjectContext) -> list[str]:
        return transcribe_project(
            context,
            model_factory=lambda _settings: FakeModel(),
            gpu_memory_mb=0,
        )

    monkeypatch.setattr(orchestrator, "transcribe_project", worker)

    def render(context: ProjectContext) -> list[str]:
        output = context.project_dir / "review" / "draft.mp4"
        output.write_bytes(b"phase-six-draft")
        final_pass = context.project_dir / "renders" / "final-pass.json"
        final_pass.write_text("{}", encoding="utf-8")
        return ["review/draft.mp4", "renders/final-pass.json"]

    def preprocess(context: ProjectContext) -> list[str]:
        artifacts = [
            "analysis/preprocess-record.json",
            "analysis/scene-classification.json",
            "media/technical-proxy.mp4",
        ]
        for relative in artifacts:
            path = context.project_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"phase-eight-technical")
        return artifacts

    def validate_preprocess(context: ProjectContext) -> None:
        for relative in (
            "analysis/preprocess-record.json",
            "analysis/scene-classification.json",
            "media/technical-proxy.mp4",
        ):
            if not (context.project_dir / relative).is_file():
                raise RenderError("Technical preprocessing artifact is missing.")

    def validate_render(context: ProjectContext) -> None:
        if (
            not (context.project_dir / "review" / "draft.mp4").is_file()
            or not (context.project_dir / "renders" / "final-pass.json").is_file()
        ):
            raise RenderError("Draft render is missing.")

    def qc(context: ProjectContext) -> list[str]:
        artifacts = [
            "review/qc-report.json",
            "review/index.html",
            "review/review-package.json",
        ]
        for relative in artifacts:
            path = context.project_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"phase-nine-review")
        return artifacts

    def validate_qc(context: ProjectContext) -> None:
        for relative in (
            "review/qc-report.json",
            "review/index.html",
            "review/review-package.json",
        ):
            if not (context.project_dir / relative).is_file():
                raise ReviewError("Review artifact is missing.")

    monkeypatch.setattr(orchestrator, "preprocess_project", preprocess)
    monkeypatch.setattr(orchestrator, "validate_preprocess_outputs", validate_preprocess)
    monkeypatch.setattr(orchestrator, "render_draft", render)
    monkeypatch.setattr(orchestrator, "validate_draft_outputs", validate_render)
    monkeypatch.setattr(orchestrator, "run_quality_control", qc)
    monkeypatch.setattr(orchestrator, "prepare_review_checkpoint", qc)
    monkeypatch.setattr(orchestrator, "validate_qc_outputs", validate_qc)


def test_phase9_orchestrator_stops_at_review_checkpoint(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)

    result = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, result.project_dir)
    state = context.state_store.load()

    assert result.workflow_state == "awaiting_review"
    assert result.next_stage == "approved"
    assert state.stage("ingested").status == "completed"
    assert state.stage("transcribed").status == "completed"
    assert state.stage("normalized").status == "completed"
    assert state.stage("analyzed").status == "completed"
    assert state.stage("timeline_ready").status == "completed"
    assert state.stage("plan_ready").status == "completed"
    assert state.stage("assets_ready").status == "completed"
    assert state.stage("preprocessed").status == "completed"
    assert state.stage("draft_rendered").status == "completed"
    assert state.stage("qc_passed").status == "completed"
    assert state.stage("awaiting_review").status == "completed"
    assert (context.project_dir / "analysis" / "media-info.json").is_file()
    assert (context.project_dir / "transcript" / "transcript.raw.json").is_file()
    assert (context.project_dir / "transcript" / "transcript.roman.json").is_file()
    assert (context.project_dir / "timeline" / "source-timeline.json").is_file()
    assert (context.project_dir / "planning" / "edit-plan.json").is_file()


def test_resume_rebuilds_only_missing_transcript(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    (context.project_dir / "transcript" / "transcript.raw.json").unlink()

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("ingested").attempts == 1
    assert state.stage("transcribed").attempts == 2
    assert state.stage("normalized").attempts == 2
    assert state.stage("analyzed").attempts == 2
    assert state.stage("timeline_ready").attempts == 2
    assert state.stage("plan_ready").attempts == 2


def test_resume_rebuilds_ingest_and_transcript_when_proxy_is_missing(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    (context.project_dir / "media" / "proxy.mp4").unlink()

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("ingested").attempts == 2
    assert state.stage("transcribed").attempts == 2
    assert state.stage("normalized").attempts == 2
    assert state.stage("analyzed").attempts == 2
    assert state.stage("timeline_ready").attempts == 2
    assert state.stage("plan_ready").attempts == 2
    provenance = state.stage("transcribed").artifacts
    assert provenance == ["transcript/transcript.raw.json"]


def test_resume_rebuilds_only_missing_normalized_transcript(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    (context.project_dir / "transcript" / "transcript.roman.json").unlink()

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("ingested").attempts == 1
    assert state.stage("transcribed").attempts == 1
    assert state.stage("normalized").attempts == 2
    assert state.stage("analyzed").attempts == 2
    assert state.stage("timeline_ready").attempts == 2
    assert state.stage("plan_ready").attempts == 2


def test_resume_rebuilds_only_timing_mutated_normalized_transcript(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    path = context.project_dir / "transcript" / "transcript.roman.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["words"][0]["start"] = 0.2
    path.write_text(json.dumps(document), encoding="utf-8")

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("ingested").attempts == 1
    assert state.stage("transcribed").attempts == 1
    assert state.stage("normalized").attempts == 2
    assert state.stage("analyzed").attempts == 2
    assert state.stage("timeline_ready").attempts == 2
    assert state.stage("plan_ready").attempts == 2


def test_resume_rebuilds_analysis_and_timeline_when_analysis_is_missing(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    (context.project_dir / "analysis" / "silence-candidates.json").unlink()

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("normalized").attempts == 1
    assert state.stage("analyzed").attempts == 2
    assert state.stage("timeline_ready").attempts == 2
    assert state.stage("plan_ready").attempts == 2


def test_resume_rebuilds_only_corrupt_timeline(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    path = context.project_dir / "timeline" / "time-map.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["mappings"][0]["outputStart"] = 0.1
    path.write_text(json.dumps(document), encoding="utf-8")

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("normalized").attempts == 1
    assert state.stage("analyzed").attempts == 1
    assert state.stage("timeline_ready").attempts == 2
    assert state.stage("plan_ready").attempts == 2


def test_resume_rebuilds_only_invalid_edit_plan(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    path = context.project_dir / "planning" / "edit-plan.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["scenes"][0]["graphics"][0]["props"]["script"] = "do-not-run()"
    path.write_text(json.dumps(document), encoding="utf-8")

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("normalized").attempts == 1
    assert state.stage("analyzed").attempts == 1
    assert state.stage("timeline_ready").attempts == 1
    assert state.stage("plan_ready").attempts == 2


@pytest.mark.parametrize(
    ("relative", "stage"),
    [
        ("assets/manifest.json", "assets_ready"),
        ("planning/asset-ranking.json", "assets_ready"),
        ("analysis/preprocess-record.json", "preprocessed"),
        ("analysis/scene-classification.json", "preprocessed"),
        ("review/draft.mp4", "draft_rendered"),
        ("renders/final-pass.json", "draft_rendered"),
        ("review/qc-report.json", "qc_passed"),
        ("review/index.html", "qc_passed"),
        ("review/review-package.json", "qc_passed"),
    ],
)
def test_resume_rebuilds_from_earliest_invalid_phase6_artifact(
    repository: Path,
    real_source_video: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    stage: str,
) -> None:
    _install_fake_transcriber(monkeypatch)
    created = run_new_project(repository, real_source_video, "fast")
    context = open_project(repository, created.project_dir)
    (context.project_dir / relative).unlink()

    resumed = resume_project(repository, created.project_dir)
    state = context.state_store.load()

    assert resumed.workflow_state == "awaiting_review"
    assert state.stage("plan_ready").attempts == 1
    assert state.stage(stage).attempts == 2
    for earlier in (
        "assets_ready",
        "preprocessed",
        "draft_rendered",
        "qc_passed",
        "awaiting_review",
    ):
        expected = 2 if STAGES.index(earlier) >= STAGES.index(stage) else 1
        assert state.stage(earlier).attempts == expected


def test_fake_model_factory_signature_is_stable() -> None:
    settings = ModelSettings("tiny", "cpu", "int8")
    assert settings.to_dict()["computeType"] == "int8"
