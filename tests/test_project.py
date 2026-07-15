from pathlib import Path
from typing import Any, cast

import pytest

from cutmachine import orchestrator
from cutmachine.orchestrator import (
    approve_project,
    request_project_revision,
    resume_project,
    run_new_project,
)
from cutmachine.project import ProjectError, open_project, sha256_file, slugify


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("My AI Video", "my-ai-video"),
        ("  spaces & symbols! ", "spaces-symbols"),
        ("CON", "video-con"),
        ("اردو", "video"),
    ],
)
def test_slugify_is_portable(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_run_creates_immutable_validated_project(
    repository: Path, source_video: Path, phase2_workers: None
) -> None:
    result = run_new_project(repository, source_video, "balanced")
    context = open_project(repository, result.project_dir)
    source = cast(dict[str, Any], context.project["source"])
    stored = result.project_dir / cast(str, source["storedPath"])
    state = context.state_store.load()

    assert stored.read_bytes() == source_video.read_bytes()
    assert source["sha256"] == sha256_file(stored)
    assert context.project["sourceHash"] == f"sha256:{source['sha256']}"
    assert state.workflow_state == "awaiting_review"
    assert state.next_actionable() == "approved"
    assert result.next_stage == "approved"


def test_repeated_run_never_overwrites_prior_project(
    repository: Path, source_video: Path, phase2_workers: None
) -> None:
    first = run_new_project(repository, source_video, "fast")
    second = run_new_project(repository, source_video, "fast")

    assert first.project_dir != second.project_dir
    assert first.project_dir.name == "my-ai-video"
    assert second.project_dir.name == "my-ai-video-2"
    assert (first.project_dir / "project.json").is_file()


def test_resume_is_idempotent_at_phase_boundary(
    repository: Path, source_video: Path, phase2_workers: None
) -> None:
    created = run_new_project(repository, source_video, "balanced")
    resumed = resume_project(repository, created.project_dir)

    assert resumed.workflow_state == "awaiting_review"
    assert resumed.next_stage == "approved"


def test_resume_rejects_source_copy_tampering(
    repository: Path, source_video: Path, phase2_workers: None
) -> None:
    created = run_new_project(repository, source_video, "balanced")
    context = open_project(repository, created.project_dir)
    source = cast(dict[str, Any], context.project["source"])
    stored = created.project_dir / cast(str, source["storedPath"])
    stored.write_bytes(b"tampered")

    with pytest.raises(ProjectError, match=r"source size changed|hash mismatch"):
        resume_project(repository, created.project_dir)


def test_phase9_approval_is_explicit_and_project_bound(
    repository: Path,
    source_video: Path,
    phase2_workers: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = run_new_project(repository, source_video, "balanced")
    monkeypatch.setattr(
        orchestrator,
        "write_approval_decision",
        lambda context, _note: [
            (context.project_dir / "review" / "decision.json")
            .relative_to(context.project_dir)
            .as_posix()
        ],
    )

    approved = approve_project(repository, created.project_dir, "Reviewed the local QC package.")
    state = open_project(repository, created.project_dir).state_store.load()

    assert approved.workflow_state == "approved"
    assert approved.next_stage == "final_rendered"
    assert state.stage("approved").status == "completed"


def test_phase9_revision_invalidates_plan_and_downstream_only(
    repository: Path,
    source_video: Path,
    phase2_workers: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = run_new_project(repository, source_video, "balanced")
    monkeypatch.setattr(
        orchestrator,
        "apply_review_revision",
        lambda _context, _path, _note: ["review/decision.json"],
    )

    revised = request_project_revision(
        repository,
        created.project_dir,
        "planning/revision.json",
        "Change caption emphasis.",
    )
    state = open_project(repository, created.project_dir).state_store.load()

    assert revised.workflow_state == "revision_requested"
    assert revised.next_stage == "plan_ready"
    assert state.stage("timeline_ready").status == "completed"
    assert state.stage("plan_ready").status == "invalidated"
    assert state.stage("awaiting_review").status == "invalidated"


def test_project_path_must_stay_inside_workspace(repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-project"
    outside.mkdir()

    with pytest.raises(ProjectError, match="inside the workspace"):
        open_project(repository, outside)


def test_unsupported_media_is_rejected(
    repository: Path, tmp_path: Path, phase2_workers: None
) -> None:
    source = tmp_path / "unsafe.exe"
    source.write_bytes(b"not media")

    with pytest.raises(ProjectError, match="Unsupported source extension"):
        run_new_project(repository, source, "balanced")


def test_configured_workspace_root_is_respected(
    repository: Path, source_video: Path, phase2_workers: None
) -> None:
    defaults = repository / "config" / "defaults.yaml"
    content = defaults.read_text(encoding="utf-8").replace(
        "workspace_root: workspace", "workspace_root: custom-workspace"
    )
    defaults.write_text(content, encoding="utf-8")

    result = run_new_project(repository, source_video, "balanced")
    context = open_project(repository, result.project_dir)

    assert result.project_dir.parent.name == "custom-workspace"
    assert context.project["projectId"] == result.project_id
