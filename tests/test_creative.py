from __future__ import annotations

from itertools import pairwise

from cutmachine.creative import build_energetic_scenes, visual_beat_ranges


def _words(duration: int = 24) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    vocabulary = [
        "ChatGPT",
        "se",
        "baat",
        "kar",
        "rahi",
        "thi.",
        "programmer",
        "AI",
        "personal",
        "data",
        "share",
        "karein.",
    ]
    for index in range(duration * 2):
        start = index * 0.5
        values.append(
            {
                "id": f"word_{index + 1:06d}",
                "text": vocabulary[index % len(vocabulary)],
                "start": start,
                "end": start + 0.4,
                "confidence": 1.0,
                "emphasis": index % 7 == 0,
            }
        )
    return values


def test_visual_beats_split_one_continuous_keep_without_changing_coverage() -> None:
    timeline = [
        {
            "id": "keep_000001",
            "outputStart": 0.0,
            "outputEnd": 24.0,
        }
    ]
    words = _words()

    beats = visual_beat_ranges(
        timeline,
        words,
        visual_change_target_seconds=2.8,
    )

    assert len(beats) >= 4
    assert beats[0]["start"] == 0.0
    assert beats[-1]["end"] == 24.0
    assert all(before["end"] == after["start"] for before, after in pairwise(beats))
    assert all(beat["sourceTimelineIds"] == ["keep_000001"] for beat in beats)
    word_ends = {word["end"] for word in words}
    assert all(beat["end"] in word_ends for beat in beats[:-1])


def test_energetic_scenes_add_graphics_broll_queries_and_bounded_transitions() -> None:
    timeline = [
        {
            "id": "keep_000001",
            "outputStart": 0.0,
            "outputEnd": 24.0,
        }
    ]
    scenes = build_energetic_scenes(
        timeline,
        _words(),
        visual_change_target_seconds=2.8,
        transition_allowance=2,
    )

    assert len(scenes) >= 4
    assert all(len(scene["graphics"]) == 1 for scene in scenes)
    assert scenes[0]["graphics"][0]["component"] == "HookTitle"
    assert scenes[-1]["graphics"][0]["component"] == "EndCallToAction"
    assert any(scene["broll"]["query"] for scene in scenes)
    assert sum(scene["transitionOut"]["type"] != "clean-cut" for scene in scenes) <= 2
    assert all(scene["sourceTimelineIds"] == ["keep_000001"] for scene in scenes)
