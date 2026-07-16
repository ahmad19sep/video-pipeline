from __future__ import annotations

from typing import Any

from cutmachine.pacing import camera_allowance, plan_scene_cameras


def _scene(index: int, start: float, end: float, *, purpose: str = "explanation") -> dict[str, Any]:
    return {"id": f"scene_{index:06d}", "start": start, "end": end, "purpose": purpose}


def _budgets(rate: float) -> dict[str, Any]:
    return {"camera_moves_per_minute": rate}


def test_allowance_matches_plan_validator_formula() -> None:
    assert camera_allowance(_budgets(6), 10.0) == 1
    assert camera_allowance(_budgets(6), 60.0) == 6
    assert camera_allowance(_budgets(0), 300.0) == 0


def test_zero_budget_keeps_every_scene_static() -> None:
    scenes = [_scene(1, 0.0, 30.0, purpose="hook"), _scene(2, 30.0, 60.0)]
    cameras = plan_scene_cameras(
        scenes, output_duration=60.0, budgets=_budgets(0), visual_change_target_seconds=4.5
    )
    assert all(camera["mode"] == "static" for camera in cameras)


def test_hook_scene_gets_priority_punch_in() -> None:
    scenes = [_scene(1, 0.0, 3.0, purpose="hook"), _scene(2, 3.0, 10.0)]
    cameras = plan_scene_cameras(
        scenes, output_duration=10.0, budgets=_budgets(6), visual_change_target_seconds=4.5
    )
    assert cameras[0] == {
        "mode": "punch-in",
        "scaleStart": 1.0,
        "scaleEnd": 1.05,
        "focus": "face",
    }


def test_long_scenes_get_alternating_slow_zooms_within_budget() -> None:
    scenes = [
        _scene(1, 0.0, 2.0, purpose="hook"),
        _scene(2, 2.0, 12.0),
        _scene(3, 12.0, 14.0),
        _scene(4, 14.0, 26.0),
        _scene(5, 26.0, 40.0),
    ]
    cameras = plan_scene_cameras(
        scenes, output_duration=40.0, budgets=_budgets(6), visual_change_target_seconds=4.5
    )
    assert cameras[0]["mode"] == "punch-in"
    assert cameras[2]["mode"] == "static"
    zooms = [camera for camera in cameras if camera["mode"] == "slow-zoom"]
    assert len(zooms) == 3
    assert zooms[0]["scaleStart"] == 1.0 and zooms[0]["scaleEnd"] == 1.05
    assert zooms[1]["scaleStart"] == 1.05 and zooms[1]["scaleEnd"] == 1.0
    assert zooms[2]["scaleStart"] == 1.0 and zooms[2]["scaleEnd"] == 1.05


def test_budget_truncates_to_longest_scenes_first() -> None:
    scenes = [
        _scene(1, 0.0, 10.0),
        _scene(2, 10.0, 30.0),
        _scene(3, 30.0, 36.0),
    ]
    cameras = plan_scene_cameras(
        scenes, output_duration=36.0, budgets=_budgets(1), visual_change_target_seconds=4.5
    )
    assert [camera["mode"] for camera in cameras] == ["static", "slow-zoom", "static"]


def test_decisions_are_deterministic_and_bounded() -> None:
    scenes = [
        _scene(1, 0.0, 5.0, purpose="hook"),
        _scene(2, 5.0, 20.0),
        _scene(3, 20.0, 32.0),
    ]
    first = plan_scene_cameras(
        scenes, output_duration=32.0, budgets=_budgets(6), visual_change_target_seconds=4.5
    )
    second = plan_scene_cameras(
        scenes, output_duration=32.0, budgets=_budgets(6), visual_change_target_seconds=4.5
    )
    assert first == second
    for camera in first:
        assert camera["mode"] in {"static", "punch-in", "slow-zoom"}
        assert 1.0 <= camera["scaleStart"] <= 1.06
        assert 1.0 <= camera["scaleEnd"] <= 1.06
        assert camera["focus"] == "face"
