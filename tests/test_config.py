from pathlib import Path
from typing import Any, cast

from cutmachine.config import deep_merge, load_config


def test_deep_merge_does_not_mutate_inputs() -> None:
    base = {"render": {"fps": 30, "width": 540}, "network": {"enabled": True}}
    override = {"render": {"width": 1080}}

    merged = deep_merge(base, override)

    assert merged["render"] == {"fps": 30, "width": 1080}
    assert cast(dict[str, Any], base["render"])["width"] == 540


def test_load_config_applies_style_project_and_environment(tmp_path: Path) -> None:
    config = tmp_path / "config"
    styles = config / "styles"
    styles.mkdir(parents=True)
    (config / "defaults.yaml").write_text(
        "render:\n  fps: 30\nnetwork:\n  enabled: true\n", encoding="utf-8"
    )
    (styles / "balanced.yaml").write_text("render:\n  fps: 25\n", encoding="utf-8")
    project = tmp_path / "project.yaml"
    project.write_text("network:\n  enabled: false\n", encoding="utf-8")

    loaded = load_config(
        tmp_path,
        project_config=project,
        environment={"CUTMACHINE__RENDER__FPS": "60"},
    )

    assert loaded["render"]["fps"] == 60
    assert loaded["network"]["enabled"] is False
