from pathlib import Path

import pytest

from cutmachine.orchestrator import rerun_from, run_new_project
from cutmachine.project import open_project
from cutmachine.state import STAGES, ProjectState, StateTransitionError


def test_out_of_order_start_is_rejected() -> None:
    state = ProjectState.initialize("project_one")

    with pytest.raises(StateTransitionError, match="next actionable stage is validated"):
        state.start("ingested")


def test_stage_must_run_before_completion() -> None:
    state = ProjectState.initialize("project_one")

    with pytest.raises(StateTransitionError, match="must be running"):
        state.complete("validated")


def test_interrupted_stage_is_recovered() -> None:
    state = ProjectState.initialize("project_one")
    state.start("validated")

    assert state.recover_interrupted()
    assert state.stage("validated").status == "pending"
    assert state.next_actionable() == "validated"
    assert state.run_status == "active"


def test_failure_is_recoverable() -> None:
    state = ProjectState.initialize("project_one")
    state.start("validated")
    state.fail("validated", "fixture failure")

    assert state.workflow_state == "failed"
    assert state.failed_stage == "validated"
    assert state.recover_interrupted()
    assert state.workflow_state == "created"


def test_invalidation_preserves_upstream_and_clears_downstream() -> None:
    state = ProjectState.initialize("project_one")
    state.start("validated")
    state.complete("validated", ["project.json"])
    state.start("ingested")
    state.complete("ingested", ["analysis/media-info.json"])

    state.invalidate_from("ingested")

    assert state.stage("validated").status == "completed"
    assert state.stage("ingested").status == "invalidated"
    assert state.stage("transcribed").status == "invalidated"
    assert state.stage("ingested").artifacts == []
    assert state.next_actionable() == "ingested"


def test_created_stage_cannot_be_invalidated() -> None:
    state = ProjectState.initialize("project_one")

    with pytest.raises(StateTransitionError, match="cannot be invalidated"):
        state.invalidate_from("created")


def test_rerun_validated_executes_phase1_validation(
    repository: Path, source_video: Path, phase2_workers: None
) -> None:
    created = run_new_project(repository, source_video, "balanced")
    result = rerun_from(repository, created.project_dir, "validated")
    state = open_project(repository, created.project_dir).state_store.load()

    assert result.workflow_state == "awaiting_review"
    assert state.stage("validated").attempts == 2
    assert state.stage("ingested").status == "completed"
    assert state.stage("ingested").attempts == 2


def test_approval_path_does_not_require_a_revision() -> None:
    state = ProjectState.initialize("project_one")
    for name in STAGES[1 : STAGES.index("awaiting_review") + 1]:
        state.start(name)
        state.complete(name)

    assert state.next_actionable() == "approved"


def test_revision_request_invalidates_selected_dependency() -> None:
    state = ProjectState.initialize("project_one")
    for name in STAGES[1 : STAGES.index("awaiting_review") + 1]:
        state.start(name)
        state.complete(name)

    state.request_revision("plan_ready", "Change the title treatment.")

    assert state.workflow_state == "revision_requested"
    assert state.next_actionable() == "plan_ready"
    assert state.stage("timeline_ready").status == "completed"
    assert state.stage("plan_ready").status == "invalidated"
