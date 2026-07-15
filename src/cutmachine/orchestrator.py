"""Phase-aware CutMachine project orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cutmachine.assets import AssetError, prepare_assets, validate_asset_readiness
from cutmachine.editorial import (
    EditorialError,
    analyze_project,
    generate_timeline,
    validate_analysis_outputs,
    validate_timeline_outputs,
)
from cutmachine.locking import ProjectLock
from cutmachine.media import MediaError, ingest_project, validate_ingest_outputs
from cutmachine.normalization import (
    NormalizationError,
    normalize_project,
    validate_normalized_outputs,
)
from cutmachine.planning import PlanningError, generate_plan, validate_plan_outputs
from cutmachine.project import (
    ProjectContext,
    create_project,
    open_project,
    verify_project,
)
from cutmachine.rendering import (
    RenderError,
    preprocess_project,
    render_draft,
    validate_draft_outputs,
    validate_preprocess_outputs,
)
from cutmachine.review import (
    ReviewError,
    apply_review_revision,
    prepare_review_checkpoint,
    run_quality_control,
    validate_qc_outputs,
    validate_review_decision,
    write_approval_decision,
)
from cutmachine.state import ProjectState
from cutmachine.transcription import (
    TranscriptError,
    transcribe_project,
    validate_transcript_outputs,
)


@dataclass(frozen=True)
class OrchestratorResult:
    project_id: str
    project_dir: Path
    workflow_state: str
    run_status: str
    next_stage: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "projectDir": str(self.project_dir),
            "workflowState": self.workflow_state,
            "runStatus": self.run_status,
            "nextStage": self.next_stage,
            "message": self.message,
        }

    def to_text(self) -> str:
        next_stage = self.next_stage or "none"
        return "\n".join(
            (
                f"Project: {self.project_id}",
                f"Workspace: {self.project_dir}",
                f"State: {self.workflow_state} ({self.run_status})",
                f"Next stage: {next_stage}",
                self.message,
            )
        )


def _result(context: ProjectContext, state: ProjectState, message: str) -> OrchestratorResult:
    return OrchestratorResult(
        project_id=state.project_id,
        project_dir=context.project_dir,
        workflow_state=state.workflow_state,
        run_status=state.run_status,
        next_stage=state.next_actionable(),
        message=message,
    )


def _execute_stage(
    context: ProjectContext,
    state: ProjectState,
    name: str,
    worker: Any,
) -> ProjectState:
    store = context.state_store
    state.start(name)
    store.save(state)
    try:
        artifacts = worker()
    except Exception as exc:
        state.fail(name, str(exc))
        store.save(state)
        raise
    state.complete(name, artifacts)
    store.save(state)
    return state


def _validate_project_stage(context: ProjectContext) -> list[str]:
    verify_project(context)
    source_path = str(context.project["source"]["storedPath"])
    return ["project.json", source_path]


def _run_registered_stages(
    context: ProjectContext,
    state: ProjectState,
    *,
    stop_after: str | None = None,
) -> ProjectState:
    while True:
        next_stage = state.next_actionable()
        if next_stage == "validated":
            state = _execute_stage(
                context,
                state,
                "validated",
                lambda: _validate_project_stage(context),
            )
        elif next_stage == "ingested":
            state = _execute_stage(
                context,
                state,
                "ingested",
                lambda: ingest_project(context),
            )
        elif next_stage == "transcribed":
            state = _execute_stage(
                context,
                state,
                "transcribed",
                lambda: transcribe_project(context),
            )
        elif next_stage == "normalized":
            state = _execute_stage(
                context,
                state,
                "normalized",
                lambda: normalize_project(context),
            )
        elif next_stage == "analyzed":
            state = _execute_stage(
                context,
                state,
                "analyzed",
                lambda: analyze_project(context),
            )
        elif next_stage == "timeline_ready":
            state = _execute_stage(
                context,
                state,
                "timeline_ready",
                lambda: generate_timeline(context),
            )
        elif next_stage == "plan_ready":
            state = _execute_stage(
                context,
                state,
                "plan_ready",
                lambda: generate_plan(context),
            )
        elif next_stage == "assets_ready":
            state = _execute_stage(
                context,
                state,
                "assets_ready",
                lambda: prepare_assets(context),
            )
        elif next_stage == "preprocessed":
            state = _execute_stage(
                context,
                state,
                "preprocessed",
                lambda: preprocess_project(context),
            )
        elif next_stage == "draft_rendered":
            state = _execute_stage(
                context,
                state,
                "draft_rendered",
                lambda: render_draft(context),
            )
        elif next_stage == "qc_passed":
            state = _execute_stage(
                context,
                state,
                "qc_passed",
                lambda: run_quality_control(context),
            )
        elif next_stage == "awaiting_review":
            state = _execute_stage(
                context,
                state,
                "awaiting_review",
                lambda: prepare_review_checkpoint(context),
            )
        else:
            return state
        if next_stage == stop_after:
            return state


def _verify_completed_phase9(context: ProjectContext, state: ProjectState) -> ProjectState:
    store = context.state_store
    if state.stage("ingested").status == "completed":
        try:
            validate_ingest_outputs(context)
        except MediaError:
            state.invalidate_from("ingested")
            store.save(state)
            return state
    if state.stage("transcribed").status == "completed":
        try:
            validate_transcript_outputs(context)
        except TranscriptError:
            state.invalidate_from("transcribed")
            store.save(state)
            return state
    if state.stage("normalized").status == "completed":
        try:
            validate_normalized_outputs(context)
        except NormalizationError:
            state.invalidate_from("normalized")
            store.save(state)
            return state
    if state.stage("analyzed").status == "completed":
        try:
            validate_analysis_outputs(context)
        except EditorialError:
            state.invalidate_from("analyzed")
            store.save(state)
            return state
    if state.stage("timeline_ready").status == "completed":
        try:
            validate_timeline_outputs(context)
        except EditorialError:
            state.invalidate_from("timeline_ready")
            store.save(state)
            return state
    if state.stage("plan_ready").status == "completed":
        try:
            validate_plan_outputs(context)
        except PlanningError:
            state.invalidate_from("plan_ready")
            store.save(state)
            return state
    if state.stage("assets_ready").status == "completed":
        try:
            validate_asset_readiness(context)
        except AssetError:
            state.invalidate_from("assets_ready")
            store.save(state)
            return state
    if state.stage("preprocessed").status == "completed":
        try:
            validate_preprocess_outputs(context)
        except RenderError:
            state.invalidate_from("preprocessed")
            store.save(state)
            return state
    if state.stage("draft_rendered").status == "completed":
        try:
            validate_draft_outputs(context)
        except RenderError:
            state.invalidate_from("draft_rendered")
            store.save(state)
            return state
    if state.stage("qc_passed").status == "completed":
        try:
            validate_qc_outputs(context)
        except ReviewError:
            state.invalidate_from("qc_passed")
            store.save(state)
            return state
    if state.stage("awaiting_review").status == "completed":
        try:
            prepare_review_checkpoint(context)
        except ReviewError:
            state.invalidate_from("awaiting_review")
            store.save(state)
            return state
    if state.stage("approved").status == "completed":
        try:
            validate_review_decision(context, expected_action="approved")
        except ReviewError:
            state.invalidate_from("approved")
            store.save(state)
    return state


def run_new_project(
    repository_root: Path,
    source: Path,
    mode: str,
) -> OrchestratorResult:
    context = create_project(repository_root, source, mode)
    with ProjectLock(context.project_dir):
        state = context.state_store.load()
        state = _run_registered_stages(context, state)
    return _result(
        context,
        state,
        "Phase 9 boundary reached. Review the local QC package, then approve or request revisions.",
    )


def resume_project(repository_root: Path, project: Path) -> OrchestratorResult:
    context = open_project(repository_root, project)
    with ProjectLock(context.project_dir):
        verify_project(context)
        state = context.state_store.load()
        if state.recover_interrupted():
            context.state_store.save(state)
        state = _verify_completed_phase9(context, state)
        state = _run_registered_stages(context, state)
    return _result(
        context,
        state,
        "Resume verification passed. Phase 9 QC and review artifacts are valid.",
    )


def project_status(repository_root: Path, project: Path) -> OrchestratorResult:
    context = open_project(repository_root, project)
    state = context.state_store.load()
    return _result(context, state, "Project state loaded successfully.")


def rerun_from(repository_root: Path, project: Path, stage: str) -> OrchestratorResult:
    context = open_project(repository_root, project)
    with ProjectLock(context.project_dir):
        verify_project(context)
        state = context.state_store.load()
        state.recover_interrupted()
        state.invalidate_from(stage)
        context.state_store.save(state)
        state = _run_registered_stages(context, state)
    return _result(
        context,
        state,
        f"Invalidated {stage} and all downstream stages.",
    )


def approve_project(
    repository_root: Path, project: Path, note: str | None = None
) -> OrchestratorResult:
    context = open_project(repository_root, project)
    with ProjectLock(context.project_dir):
        verify_project(context)
        state = context.state_store.load()
        state = _verify_completed_phase9(context, state)
        if state.stage("awaiting_review").status != "completed":
            raise ReviewError("Project is not awaiting a valid review decision.")
        state = _execute_stage(
            context,
            state,
            "approved",
            lambda: write_approval_decision(context, note),
        )
    return _result(
        context,
        state,
        "Approval recorded. Final delivery rendering remains a later phase.",
    )


def request_project_revision(
    repository_root: Path,
    project: Path,
    revision_relative: str,
    note: str | None = None,
) -> OrchestratorResult:
    context = open_project(repository_root, project)
    with ProjectLock(context.project_dir):
        verify_project(context)
        state = context.state_store.load()
        state = _verify_completed_phase9(context, state)
        if state.stage("awaiting_review").status != "completed":
            raise ReviewError("Project is not awaiting a valid review decision.")
        apply_review_revision(context, revision_relative, note)
        state.request_revision("plan_ready", note or "Structured review revision requested.")
        context.state_store.save(state)
    return _result(
        context,
        state,
        "Structured revision applied; plan_ready and downstream stages were invalidated.",
    )


def run_internal_stage(repository_root: Path, project: Path, stage: str) -> OrchestratorResult:
    if stage not in {
        "ingested",
        "transcribed",
        "normalized",
        "analyzed",
        "timeline_ready",
        "plan_ready",
        "assets_ready",
        "preprocessed",
        "draft_rendered",
        "qc_passed",
        "awaiting_review",
    }:
        raise ValueError(f"No internal worker is registered for stage: {stage}")
    context = open_project(repository_root, project)
    with ProjectLock(context.project_dir):
        verify_project(context)
        state = context.state_store.load()
        state.recover_interrupted()
        target = state.stage(stage)
        if target.status == "completed":
            state.invalidate_from(stage)
            context.state_store.save(state)
        state = _run_registered_stages(context, state, stop_after=stage)
    return _result(context, state, f"Internal {stage} worker completed.")
