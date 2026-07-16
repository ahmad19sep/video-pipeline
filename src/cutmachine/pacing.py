"""Deterministic attention-pacing camera engine.

Applies three well-documented editing-psychology principles inside the
existing typed camera contract:

- Salience at the open: the hook scene gets a fast punch-in so the first
  seconds carry a deliberate visual accent alongside the title and SFX.
- Attention reset: viewer attention decays over a static shot, so scenes
  that outlast the style's visual-change target get an imperceptible slow
  zoom — a pattern interrupt that keeps every spoken word intact.
- Habituation avoidance: consecutive zooms alternate direction so the same
  move never repeats back to back.

Every move stays subtle (scale within 1.0-1.06), deterministic, and bounded
by the style profile's ``camera_moves_per_minute`` budget using the exact
allowance formula the plan validator enforces.
"""

from __future__ import annotations

import math
from typing import Any

_STATIC_CAMERA: dict[str, Any] = {
    "mode": "static",
    "scaleStart": 1.0,
    "scaleEnd": 1.0,
    "focus": "face",
}
_PUNCH_SCALE = 1.05
_ZOOM_SCALE = 1.05


def camera_allowance(budgets: dict[str, Any], output_duration: float) -> int:
    """Mirror the plan validator's camera-move allowance exactly."""
    rate = float(budgets["camera_moves_per_minute"])
    if rate <= 0 or output_duration <= 0:
        return 0
    return max(1, math.ceil(rate * output_duration / 60))


def plan_scene_cameras(
    scenes: list[dict[str, Any]],
    *,
    output_duration: float,
    budgets: dict[str, Any],
    visual_change_target_seconds: float,
) -> list[dict[str, Any]]:
    """Return one bounded, deterministic camera decision per scene."""
    cameras: list[dict[str, Any]] = [dict(_STATIC_CAMERA) for _ in scenes]
    budget = camera_allowance(budgets, output_duration)
    if budget == 0:
        return cameras
    candidates: list[tuple[int, float, int]] = []
    for index, scene in enumerate(scenes):
        duration = float(scene["end"]) - float(scene["start"])
        if scene.get("purpose") == "hook":
            candidates.append((0, -duration, index))
        elif duration >= visual_change_target_seconds:
            candidates.append((1, -duration, index))
    accepted = sorted(candidates)[:budget]
    zoom_count = 0
    for _, _, index in sorted(accepted, key=lambda item: item[2]):
        if scenes[index].get("purpose") == "hook":
            cameras[index] = {
                "mode": "punch-in",
                "scaleStart": 1.0,
                "scaleEnd": _PUNCH_SCALE,
                "focus": "face",
            }
            continue
        zoom_in = zoom_count % 2 == 0
        zoom_count += 1
        cameras[index] = {
            "mode": "slow-zoom",
            "scaleStart": 1.0 if zoom_in else _ZOOM_SCALE,
            "scaleEnd": _ZOOM_SCALE if zoom_in else 1.0,
            "focus": "face",
        }
    return cameras
