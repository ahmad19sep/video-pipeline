"""Command-line entry point for CutMachine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from cutmachine.assets import AssetError
from cutmachine.config import ConfigError
from cutmachine.doctor import DoctorReport, run_doctor
from cutmachine.editorial import EditorialError
from cutmachine.learning import LearningError
from cutmachine.locking import ProjectLockedError
from cutmachine.normalization import NormalizationError
from cutmachine.orchestrator import (
    OrchestratorResult,
    approve_project,
    project_status,
    request_project_revision,
    rerun_from,
    resume_project,
    run_new_project,
)
from cutmachine.persistence import PersistenceError
from cutmachine.planning import PlanningError
from cutmachine.project import MODES, ProjectError
from cutmachine.rendering import RenderError
from cutmachine.review import ReviewError
from cutmachine.state import STAGES, StateTransitionError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cutmachine",
        description="Local-first Urdu/English video editing pipeline.",
    )
    parser.add_argument("--version", action="version", version="CutMachine 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate the local build environment.")
    doctor.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    doctor.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect (default: current directory).",
    )

    run = subparsers.add_parser("run", help="Create a project and run registered stages.")
    run.add_argument("video", type=Path, help="Source video to copy into an immutable project.")
    run.add_argument("--mode", choices=sorted(MODES), default="balanced")
    run.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    run.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")

    resume = subparsers.add_parser("resume", help="Verify and resume an existing project.")
    resume.add_argument("project", type=Path, help="Workspace project path or slug.")
    resume.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    resume.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")

    status = subparsers.add_parser("status", help="Show an existing project's state.")
    status.add_argument("project", type=Path, help="Workspace project path or slug.")
    status.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    status.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")

    rerun = subparsers.add_parser("rerun", help="Invalidate a stage and its dependents.")
    rerun.add_argument("project", type=Path, help="Workspace project path or slug.")
    rerun.add_argument("--from", dest="from_stage", choices=STAGES[1:], required=True)
    rerun.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    rerun.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")

    approve = subparsers.add_parser("approve", help="Approve a QC-passed review package.")
    approve.add_argument("project", type=Path, help="Workspace project path or slug.")
    approve.add_argument("--note", help="Optional approval note.")
    approve.add_argument(
        "--feedback",
        help="Optional project-relative explicit learning-feedback JSON document.",
    )
    approve.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    approve.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")

    revision = subparsers.add_parser(
        "request-revision", help="Apply a project-relative typed revision request."
    )
    revision.add_argument("project", type=Path, help="Workspace project path or slug.")
    revision.add_argument(
        "revision", help="Safe project-relative path to a plan-revision JSON document."
    )
    revision.add_argument("--note", help="Optional human review note.")
    revision.add_argument(
        "--feedback",
        help="Optional project-relative explicit learning-feedback JSON document.",
    )
    revision.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    revision.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    return parser


def _print_report(report: DoctorReport, as_json: bool) -> None:
    print(report.to_json() if as_json else report.to_text())


def _print_result(result: OrchestratorResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.to_text())


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.root.resolve()
        if args.command == "doctor":
            report = run_doctor(root)
            _print_report(report, args.json)
            return 1 if report.has_failures else 0
        if args.command == "run":
            result = run_new_project(root, args.video, args.mode)
            _print_result(result, args.json)
            return 0
        if args.command == "resume":
            result = resume_project(root, args.project)
            _print_result(result, args.json)
            return 0
        if args.command == "status":
            result = project_status(root, args.project)
            _print_result(result, args.json)
            return 0
        if args.command == "rerun":
            result = rerun_from(root, args.project, args.from_stage)
            _print_result(result, args.json)
            return 0
        if args.command == "approve":
            result = approve_project(root, args.project, args.note, args.feedback)
            _print_result(result, args.json)
            return 0
        if args.command == "request-revision":
            result = request_project_revision(
                root, args.project, args.revision, args.note, args.feedback
            )
            _print_result(result, args.json)
            return 0
    except (
        ConfigError,
        AssetError,
        EditorialError,
        PersistenceError,
        ProjectError,
        ProjectLockedError,
        LearningError,
        NormalizationError,
        PlanningError,
        RenderError,
        ReviewError,
        StateTransitionError,
    ) as exc:
        print(f"CutMachine error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("CutMachine interrupted by user.", file=sys.stderr)
        return 130
    return 2
