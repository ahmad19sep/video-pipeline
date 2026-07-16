from __future__ import annotations

from typing import Any

from cutmachine.sfx import plan_scene_sfx, sfx_allowance


def _scene(
    index: int,
    start: float,
    end: float,
    *,
    purpose: str = "explanation",
    graphic_offsets: tuple[float, ...] = (),
    transition: tuple[str, int] = ("clean-cut", 0),
) -> dict[str, Any]:
    return {
        "id": f"scene_{index:06d}",
        "start": start,
        "end": end,
        "purpose": purpose,
        "graphics": [
            {"id": f"graphic_{index:06d}_{i}", "startOffset": offset, "endOffset": offset + 1.0}
            for i, offset in enumerate(graphic_offsets)
        ],
        "sfx": [],
        "transitionOut": {"type": transition[0], "durationFrames": transition[1]},
    }


def _word(start: float, *, emphasis: bool = True) -> dict[str, Any]:
    return {"start": start, "end": start + 0.3, "emphasis": emphasis}


def _budgets(rate: float) -> dict[str, Any]:
    return {"impact_sfx_per_minute": rate}


def test_allowance_matches_plan_validator_formula() -> None:
    assert sfx_allowance(_budgets(4), 10.0) == 1
    assert sfx_allowance(_budgets(4), 60.0) == 4
    assert sfx_allowance(_budgets(4), 61.0) == 5
    assert sfx_allowance(_budgets(0), 300.0) == 0
    assert sfx_allowance(_budgets(4), 0.0) == 0


def test_zero_budget_places_nothing() -> None:
    scenes = [_scene(1, 0.0, 10.0, purpose="hook", graphic_offsets=(0.0,))]
    placements = plan_scene_sfx(
        scenes, [_word(3.0)], fps=30.0, output_duration=10.0, budgets=_budgets(0)
    )
    assert placements == [[]]


def test_hook_scene_gets_impact_under_first_graphic() -> None:
    scenes = [
        _scene(1, 0.0, 5.0, purpose="hook", graphic_offsets=(0.0,)),
        _scene(2, 5.0, 10.0),
    ]
    placements = plan_scene_sfx(scenes, [], fps=30.0, output_duration=10.0, budgets=_budgets(8))
    assert placements[0] == [
        {"assetId": None, "query": "impact hit intro", "offset": 0.0, "gainDb": -10.0}
    ]
    assert placements[1] == []


def test_transition_whoosh_lands_before_scene_end() -> None:
    scenes = [
        _scene(1, 0.0, 5.0, transition=("crossfade", 15)),
        _scene(2, 5.0, 10.0),
    ]
    placements = plan_scene_sfx(scenes, [], fps=30.0, output_duration=10.0, budgets=_budgets(8))
    assert placements[0] == [
        {"assetId": None, "query": "whoosh transition swish", "offset": 4.5, "gainDb": -12.0}
    ]


def test_emphasis_pops_respect_lead_in_tail_and_spacing() -> None:
    scenes = [_scene(1, 0.0, 60.0, purpose="hook", graphic_offsets=(0.0,))]
    words = [
        _word(0.5),  # inside the lead-in window
        _word(1.2),  # too close to the hook impact at 0.0
        _word(4.0),
        _word(4.8),  # too close to the accepted pop at 4.0
        _word(59.8),  # inside the tail window
        _word(20.0, emphasis=False),
    ]
    placements = plan_scene_sfx(scenes, words, fps=30.0, output_duration=60.0, budgets=_budgets(8))
    offsets = [item["offset"] for item in placements[0]]
    assert offsets == [0.0, 4.0]
    assert placements[0][1]["query"] == "pop click accent"
    assert placements[0][1]["gainDb"] == -16.0


def test_budget_truncates_lower_priority_candidates() -> None:
    scenes = [_scene(1, 0.0, 60.0, purpose="hook", graphic_offsets=(0.0,))]
    words = [_word(float(start)) for start in range(5, 55, 5)]
    placements = plan_scene_sfx(scenes, words, fps=30.0, output_duration=60.0, budgets=_budgets(3))
    assert len(placements[0]) == 3
    assert placements[0][0]["query"] == "impact hit intro"
    assert [item["offset"] for item in placements[0]] == [0.0, 5.0, 10.0]


def test_placements_are_deterministic_and_schema_bounded() -> None:
    scenes = [
        _scene(1, 0.0, 8.0, purpose="hook", graphic_offsets=(0.0,), transition=("zoom", 12)),
        _scene(2, 8.0, 20.0, transition=("crossfade", 15)),
        _scene(3, 20.0, 30.0),
    ]
    words = [_word(2.0), _word(9.5), _word(25.0)]
    first = plan_scene_sfx(scenes, words, fps=30.0, output_duration=30.0, budgets=_budgets(8))
    second = plan_scene_sfx(scenes, words, fps=30.0, output_duration=30.0, budgets=_budgets(8))
    assert first == second
    entries = [item for placement in first for item in placement]
    assert entries
    for entry in entries:
        assert entry["assetId"] is None
        assert 1 <= len(entry["query"]) <= 80
        assert all(32 <= ord(character) <= 126 for character in entry["query"])
        assert entry["offset"] >= 0
        assert -60 <= entry["gainDb"] <= -6
