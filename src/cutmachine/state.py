"""Resumable CutMachine workflow state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.persistence import read_validated_json, write_validated_json_atomic

STAGES = (
    "created",
    "validated",
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
    "approved",
    "final_rendered",
    "completed",
)

STAGE_STATUSES = {"pending", "running", "completed", "failed", "invalidated"}


class StateTransitionError(RuntimeError):
    """Raised when a workflow transition violates stage ordering."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class StageRecord:
    name: str
    status: str = "pending"
    attempts: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "attempts": self.attempts,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "error": self.error,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> StageRecord:
        return cls(
            name=cast(str, value["name"]),
            status=cast(str, value["status"]),
            attempts=cast(int, value["attempts"]),
            started_at=cast(str | None, value["startedAt"]),
            completed_at=cast(str | None, value["completedAt"]),
            error=cast(str | None, value["error"]),
            artifacts=cast(list[str], value["artifacts"]),
        )


@dataclass
class ProjectState:
    project_id: str
    workflow_state: str
    run_status: str
    updated_at: str
    stages: list[StageRecord]
    history: list[dict[str, Any]]
    failed_stage: str | None = None

    @classmethod
    def initialize(cls, project_id: str) -> ProjectState:
        now = utc_now()
        stages = [StageRecord(name=name) for name in STAGES]
        stages[0].status = "completed"
        stages[0].attempts = 1
        stages[0].started_at = now
        stages[0].completed_at = now
        return cls(
            project_id=project_id,
            workflow_state="created",
            run_status="active",
            updated_at=now,
            stages=stages,
            history=[{"at": now, "action": "initialized", "stage": "created", "detail": None}],
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProjectState:
        raw_stages = cast(list[dict[str, Any]], value["stages"])
        stages = [StageRecord.from_dict(item) for item in raw_stages]
        if tuple(stage.name for stage in stages) != STAGES:
            raise StateTransitionError("State stage order does not match this CutMachine version.")
        if any(stage.status not in STAGE_STATUSES for stage in stages):
            raise StateTransitionError("State contains an unknown stage status.")
        return cls(
            project_id=cast(str, value["projectId"]),
            workflow_state=cast(str, value["workflowState"]),
            run_status=cast(str, value["runStatus"]),
            updated_at=cast(str, value["updatedAt"]),
            stages=stages,
            history=cast(list[dict[str, Any]], value["history"]),
            failed_stage=cast(str | None, value.get("failedStage")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "projectId": self.project_id,
            "workflowState": self.workflow_state,
            "runStatus": self.run_status,
            "failedStage": self.failed_stage,
            "updatedAt": self.updated_at,
            "stages": [stage.to_dict() for stage in self.stages],
            "history": self.history,
        }

    def stage(self, name: str) -> StageRecord:
        try:
            return self.stages[STAGES.index(name)]
        except ValueError as exc:
            raise StateTransitionError(f"Unknown stage: {name}") from exc

    def next_actionable(self) -> str | None:
        for stage in self.stages:
            if stage.status != "completed":
                return stage.name
        return None

    def _last_completed(self) -> str:
        completed = "created"
        for stage in self.stages:
            if stage.status != "completed":
                break
            completed = stage.name
        return completed

    def _event(self, action: str, stage: str, detail: str | None = None) -> None:
        now = utc_now()
        self.updated_at = now
        self.history.append({"at": now, "action": action, "stage": stage, "detail": detail})

    def start(self, name: str) -> None:
        if self.run_status in {"cancelled", "completed"}:
            raise StateTransitionError(
                f"Cannot start a stage while run status is {self.run_status}."
            )
        expected = self.next_actionable()
        if name != expected:
            raise StateTransitionError(f"Cannot start {name}; next actionable stage is {expected}.")
        stage = self.stage(name)
        if stage.status not in {"pending", "failed", "invalidated"}:
            raise StateTransitionError(f"Stage {name} cannot start from status {stage.status}.")
        now = utc_now()
        stage.status = "running"
        stage.attempts += 1
        stage.started_at = now
        stage.completed_at = None
        stage.error = None
        stage.artifacts = []
        self.run_status = "active"
        self.failed_stage = None
        self._event("started", name)

    def complete(self, name: str, artifacts: list[str] | None = None) -> None:
        stage = self.stage(name)
        if stage.status != "running":
            raise StateTransitionError(f"Stage {name} must be running before completion.")
        stage.status = "completed"
        stage.completed_at = utc_now()
        stage.error = None
        stage.artifacts = list(artifacts or [])
        self.workflow_state = name
        if name == STAGES[-1]:
            self.run_status = "completed"
        self._event("completed", name)

    def fail(self, name: str, error: str) -> None:
        stage = self.stage(name)
        if stage.status != "running":
            raise StateTransitionError(f"Stage {name} must be running before failure.")
        stage.status = "failed"
        stage.error = error
        stage.completed_at = None
        self.workflow_state = "failed"
        self.run_status = "failed"
        self.failed_stage = name
        self._event("failed", name, error)

    def recover_interrupted(self) -> bool:
        recovered = False
        for stage in self.stages:
            if stage.status in {"running", "failed"}:
                previous = stage.status
                stage.status = "pending"
                stage.started_at = None
                stage.completed_at = None
                stage.error = None
                stage.artifacts = []
                self._event("recovered", stage.name, f"recovered from {previous}")
                recovered = True
        if recovered:
            self.workflow_state = self._last_completed()
            self.run_status = "active"
            self.failed_stage = None
        return recovered

    def invalidate_from(self, name: str) -> None:
        if name == "created":
            raise StateTransitionError(
                "The created stage cannot be invalidated; create a new project."
            )
        try:
            index = STAGES.index(name)
        except ValueError as exc:
            raise StateTransitionError(f"Unknown stage: {name}") from exc
        for stage in self.stages[index:]:
            stage.status = "invalidated"
            stage.started_at = None
            stage.completed_at = None
            stage.error = None
            stage.artifacts = []
        self.workflow_state = self._last_completed()
        self.run_status = "active"
        self.failed_stage = None
        self._event("invalidated", name, "invalidated this stage and all downstream stages")

    def request_revision(self, from_stage: str, detail: str) -> None:
        if self.stage("awaiting_review").status != "completed":
            raise StateTransitionError(
                "A revision can be requested only after the draft review stage."
            )
        self.invalidate_from(from_stage)
        self.workflow_state = "revision_requested"
        self._event("revision_requested", from_stage, detail)


class StateStore:
    def __init__(self, repository_root: Path, project_dir: Path) -> None:
        self.repository_root = repository_root
        self.path = project_dir / "state.json"

    def load(self) -> ProjectState:
        value = read_validated_json(self.repository_root, self.path, "state")
        return ProjectState.from_dict(value)

    def save(self, state: ProjectState) -> None:
        write_validated_json_atomic(
            self.repository_root,
            self.path,
            "state",
            state.to_dict(),
        )
