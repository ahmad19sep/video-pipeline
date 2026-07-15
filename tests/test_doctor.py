from pathlib import Path

import pytest

from cutmachine import cli
from cutmachine.doctor import CheckResult, DoctorReport, check_command, check_writable


def test_report_failure_controls_ready_state() -> None:
    report = DoctorReport(
        version=1,
        platform="test",
        root=".",
        checks=(CheckResult("ffmpeg", "fail", "missing"),),
    )

    assert report.has_failures
    assert "BLOCKED" in report.to_text()
    assert '"ok": false' in report.to_json()


def test_missing_optional_command_is_warning() -> None:
    result = check_command(
        "definitely-not-a-real-cutmachine-command",
        ("--version",),
        core=False,
        remediation="Install it.",
    )

    assert result.status == "warn"


def test_workspace_writable(tmp_path: Path) -> None:
    assert check_writable(tmp_path).status == "pass"


def test_cli_returns_zero_when_mocked_core_checks_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    report = DoctorReport(
        version=1,
        platform="test",
        root=".",
        checks=(
            CheckResult("Python", "pass", "3.12"),
            CheckResult("Node.js", "pass", "v24"),
            CheckResult("ffmpeg", "pass", "8.1"),
            CheckResult("ffprobe", "pass", "8.1"),
        ),
    )
    monkeypatch.setattr(cli, "run_doctor", lambda _root: report)

    assert cli.main(["doctor", "--json"]) == 0
