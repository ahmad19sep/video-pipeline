import json
from pathlib import Path

from cutmachine import cli
from cutmachine.orchestrator import OrchestratorResult


def test_cli_run_and_status_json(
    repository: Path,
    source_video: Path,
    capsys: object,
    phase2_workers: None,
) -> None:
    assert cli.main(["run", str(source_video), "--root", str(repository), "--json"]) == 0
    run_output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    assert run_output["workflowState"] == "awaiting_review"
    project_dir = run_output["projectDir"]
    assert cli.main(["status", project_dir, "--root", str(repository), "--json"]) == 0
    status_output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert status_output["nextStage"] == "approved"


def test_cli_reports_missing_source(repository: Path, capsys: object, phase2_workers: None) -> None:
    result = cli.main(["run", "missing.mp4", "--root", str(repository)])

    assert result == 1
    assert "does not exist" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_cli_routes_explicit_phase9_review_decisions(
    repository: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def result(state: str, next_stage: str) -> OrchestratorResult:
        return OrchestratorResult(
            project_id="prj_demo",
            project_dir=repository / "workspace" / "demo",
            workflow_state=state,
            run_status="active",
            next_stage=next_stage,
            message="review decision recorded",
        )

    def approve(
        _root: Path,
        _project: Path,
        note: str | None,
        feedback: str | None,
    ) -> OrchestratorResult:
        calls.append(("approve", note, feedback))
        return result("completed", "none")

    def revise(
        _root: Path,
        _project: Path,
        revision: str,
        note: str | None,
        feedback: str | None,
    ) -> OrchestratorResult:
        calls.append((revision, note, feedback))
        return result("revision_requested", "plan_ready")

    monkeypatch.setattr(cli, "approve_project", approve)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "request_project_revision", revise)  # type: ignore[attr-defined]

    assert (
        cli.main(
            [
                "approve",
                "demo",
                "--root",
                str(repository),
                "--note",
                "ready",
                "--feedback",
                "planning/feedback.json",
            ]
        )
        == 0
    )
    capsys.readouterr()  # type: ignore[attr-defined]
    assert (
        cli.main(
            [
                "request-revision",
                "demo",
                "planning/revision.json",
                "--root",
                str(repository),
                "--note",
                "change",
                "--feedback",
                "planning/rejected.json",
            ]
        )
        == 0
    )
    capsys.readouterr()  # type: ignore[attr-defined]

    assert calls == [
        ("approve", "ready", "planning/feedback.json"),
        ("planning/revision.json", "change", "planning/rejected.json"),
    ]
