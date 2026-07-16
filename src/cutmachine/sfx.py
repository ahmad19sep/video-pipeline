"""Deterministic bounded SFX placement engine.

Places sound-effect entries into baseline edit-plan scenes from three
evidence-backed cues, in priority order: a hook impact under the opening
title graphic, a whoosh under each visual transition, and subtle accents on
emphasized caption words. Every entry carries only a search query; the
existing tiered asset search resolves it against the local SFX library, and
unresolved entries stay optional so asset-free projects render unchanged.

The total count never exceeds the style profile's ``impact_sfx_per_minute``
budget (the same allowance formula the plan validator enforces), gains stay
below the QC voice-priority ceiling, and identical inputs always produce
identical placements.
"""

from __future__ import annotations

import math
from typing import Any, cast

_HOOK_QUERY = "impact hit intro"
_HOOK_GAIN_DB = -10.0
_TRANSITION_QUERY = "whoosh transition swish"
_TRANSITION_GAIN_DB = -12.0
_EMPHASIS_QUERY = "pop click accent"
_EMPHASIS_GAIN_DB = -16.0

_MIN_GLOBAL_SPACING_SECONDS = 1.5
_EMPHASIS_LEAD_IN_SECONDS = 1.0
_EMPHASIS_TAIL_SECONDS = 0.4


def sfx_allowance(budgets: dict[str, Any], output_duration: float) -> int:
    """Mirror the plan validator's impact-SFX allowance exactly."""
    rate = float(budgets["impact_sfx_per_minute"])
    if rate <= 0 or output_duration <= 0:
        return 0
    return max(1, math.ceil(rate * output_duration / 60))


def _entry(query: str, offset: float, gain_db: float) -> dict[str, Any]:
    return {
        "assetId": None,
        "query": query,
        "offset": round(max(0.0, offset), 6),
        "gainDb": gain_db,
    }


def _hook_candidates(
    scenes: list[dict[str, Any]],
) -> list[tuple[int, float, int, dict[str, Any]]]:
    candidates: list[tuple[int, float, int, dict[str, Any]]] = []
    for index, scene in enumerate(scenes):
        graphics = cast(list[dict[str, Any]], scene["graphics"])
        if scene.get("purpose") != "hook" or not graphics:
            continue
        offset = min(float(graphic["startOffset"]) for graphic in graphics)
        time = float(scene["start"]) + offset
        candidates.append((0, time, index, _entry(_HOOK_QUERY, offset, _HOOK_GAIN_DB)))
    return candidates


def _transition_candidates(
    scenes: list[dict[str, Any]], fps: float
) -> list[tuple[int, float, int, dict[str, Any]]]:
    candidates: list[tuple[int, float, int, dict[str, Any]]] = []
    if fps <= 0:
        return candidates
    for index, scene in enumerate(scenes):
        transition = cast(dict[str, Any], scene["transitionOut"])
        frames = int(transition["durationFrames"])
        if transition["type"] == "clean-cut" or frames <= 0:
            continue
        duration = float(scene["end"]) - float(scene["start"])
        offset = max(0.0, duration - frames / fps)
        time = float(scene["start"]) + offset
        candidates.append((1, time, index, _entry(_TRANSITION_QUERY, offset, _TRANSITION_GAIN_DB)))
    return candidates


def _emphasis_candidates(
    scenes: list[dict[str, Any]], caption_words: list[dict[str, Any]]
) -> list[tuple[int, float, int, dict[str, Any]]]:
    candidates: list[tuple[int, float, int, dict[str, Any]]] = []
    for word in caption_words:
        if not bool(word["emphasis"]):
            continue
        time = float(word["start"])
        for index, scene in enumerate(scenes):
            start = float(scene["start"])
            end = float(scene["end"])
            if not (start <= time < end):
                continue
            offset = time - start
            if offset >= _EMPHASIS_LEAD_IN_SECONDS and end - time >= _EMPHASIS_TAIL_SECONDS:
                candidates.append(
                    (2, time, index, _entry(_EMPHASIS_QUERY, offset, _EMPHASIS_GAIN_DB))
                )
            break
    return candidates


def plan_scene_sfx(
    scenes: list[dict[str, Any]],
    caption_words: list[dict[str, Any]],
    *,
    fps: float,
    output_duration: float,
    budgets: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    """Return one bounded, deterministic SFX list per scene."""
    placements: list[list[dict[str, Any]]] = [[] for _ in scenes]
    budget = sfx_allowance(budgets, output_duration)
    if budget == 0:
        return placements
    candidates = [
        *_hook_candidates(scenes),
        *_transition_candidates(scenes, fps),
        *_emphasis_candidates(scenes, caption_words),
    ]
    accepted_times: list[float] = []
    for _, time, scene_index, entry in sorted(candidates, key=lambda item: (item[0], item[1])):
        if len(accepted_times) >= budget:
            break
        if any(abs(time - other) < _MIN_GLOBAL_SPACING_SECONDS for other in accepted_times):
            continue
        accepted_times.append(time)
        placements[scene_index].append(entry)
    for items in placements:
        items.sort(key=lambda item: float(item["offset"]))
    return placements
