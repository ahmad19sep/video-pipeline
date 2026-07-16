"""Deterministic local-first creative beat planning.

Source timeline ranges describe media cuts.  They are intentionally not used
as the creative scene cadence: a continuous talking-head take may still need
camera resets, graphic cutaways, and asset opportunities every few seconds.
This module derives those visual beats only from validated output timestamps
and caption text.  It never changes the source timeline or caption objects.
"""

from __future__ import annotations

import math
import re
from typing import Any, cast

_QUESTION = {"kya", "kaisa", "kaisi", "kaise", "kyun", "why", "how"}
_WARNING = {
    "ehtiyaat",
    "khudkushi",
    "personal",
    "privacy",
    "sensitive",
    "stress",
    "suicide",
}
_AI = {"ai", "chatgpt", "openai"}
_LEGAL = {"case", "court", "lawsuit", "legal"}
_RELATIONSHIP = {"boyfriend", "cheating", "relationship"}
_DEVELOPER = {"coder", "coding", "developer", "programmer"}
_DATA = {"companies", "company", "data", "save", "systems"}
_HUMAN = {"human", "insan", "trust"}


def _tokens(words: list[dict[str, Any]]) -> set[str]:
    return set(
        re.findall(
            r"[a-z0-9]+",
            " ".join(cast(str, word["text"]) for word in words).casefold(),
        )
    )


def _snippet(words: list[dict[str, Any]], limit: int = 10) -> str:
    value = " ".join(cast(str, word["text"]) for word in words[:limit]).strip()
    return value[:500].strip()


def _words_in_range(words: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [
        word
        for word in words
        if float(word["end"]) > start + 0.000001 and float(word["start"]) < end - 0.000001
    ]


def _punctuation_weight(text: str) -> float:
    if text.rstrip().endswith((".", "?", "!")):
        return 1.1
    if text.rstrip().endswith((",", ":", ";")):
        return 0.45
    return 0.0


def _split_timeline_segment(
    segment: dict[str, Any],
    words: list[dict[str, Any]],
    target_seconds: float,
) -> list[tuple[float, float]]:
    start = float(segment["outputStart"])
    end = float(segment["outputEnd"])
    minimum = max(2.4, target_seconds * 0.5)
    maximum = max(minimum + 0.5, target_seconds * 1.35)
    ranges: list[tuple[float, float]] = []
    cursor = start
    while end - cursor > maximum:
        low = cursor + minimum
        high = min(end - minimum, cursor + maximum)
        goal = min(high, cursor + target_seconds)
        candidates = [word for word in words if low <= float(word["end"]) <= high]
        if candidates:
            chosen = min(
                candidates,
                key=lambda word: (
                    abs(float(word["end"]) - goal) - _punctuation_weight(cast(str, word["text"])),
                    float(word["end"]),
                ),
            )
            boundary = float(chosen["end"])
        else:
            boundary = goal
        boundary = round(boundary, 6)
        if boundary <= cursor + 0.000001:
            break
        ranges.append((round(cursor, 6), boundary))
        cursor = boundary
    ranges.append((round(cursor, 6), round(end, 6)))
    return ranges


def visual_beat_ranges(
    timeline_segments: list[dict[str, Any]],
    caption_words: list[dict[str, Any]],
    *,
    visual_change_target_seconds: float,
) -> list[dict[str, Any]]:
    """Split retained media into gap-free visual beats at caption boundaries."""
    target = max(4.5, min(7.0, visual_change_target_seconds * 2.0))
    beats: list[dict[str, Any]] = []
    for segment in timeline_segments:
        segment_words = _words_in_range(
            caption_words,
            float(segment["outputStart"]),
            float(segment["outputEnd"]),
        )
        for start, end in _split_timeline_segment(segment, segment_words, target):
            references = [
                cast(str, candidate["id"])
                for candidate in timeline_segments
                if min(end, float(candidate["outputEnd"]))
                > max(start, float(candidate["outputStart"])) + 0.000001
            ]
            beats.append({"start": start, "end": end, "sourceTimelineIds": references})
    return beats


def _steps(words: list[dict[str, Any]]) -> list[str]:
    if not words:
        return []
    size = max(1, math.ceil(min(len(words), 18) / 3))
    values = [
        _snippet(words[index : index + size], limit=size)
        for index in range(0, min(len(words), 18), size)
    ]
    return [value for value in values if value][:3]


def _topic_query(tokens: set[str]) -> str | None:
    if tokens & _DEVELOPER:
        return "software developer coding laptop"
    if tokens & _RELATIONSHIP:
        return "stressed person relationship conflict"
    if tokens & _LEGAL:
        return "court legal documents technology"
    if tokens & (_DATA | _WARNING):
        return "digital privacy cybersecurity data"
    if tokens & _HUMAN:
        return "people having trusted conversation"
    if tokens & _AI:
        return "person using artificial intelligence smartphone"
    return None


def _graphic(
    *,
    scene_index: int,
    scene_words: list[dict[str, Any]],
    scene_duration: float,
    final_scene: bool,
) -> tuple[str, str, dict[str, Any]]:
    tokens = _tokens(scene_words)
    text = _snippet(scene_words, 12) or "Keep watching"
    graphic_id = f"graphic_{scene_index:06d}"
    duration = round(min(scene_duration, 3.2), 6)

    if scene_index == 1:
        return (
            "hook",
            "speaker-with-title",
            {
                "id": graphic_id,
                "component": "HookTitle",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {
                    "title": _snippet(scene_words, 7) or text,
                    "subtitle": _snippet(scene_words[7:], 5) or "Watch till the end",
                },
            },
        )

    if final_scene:
        return (
            "cta",
            "graphic-fullscreen",
            {
                "id": graphic_id,
                "component": "EndCallToAction",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {"text": text},
            },
        )

    numeric = [
        cast(str, word["text"]).strip(".,:;!?()[]{}")
        for word in scene_words
        if any(character.isdigit() for character in cast(str, word["text"]))
    ]
    if len(numeric) >= 2:
        return (
            "proof",
            "graphic-fullscreen",
            {
                "id": graphic_id,
                "component": "TimelineGraphic",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {"items": numeric[:4]},
            },
        )
    if numeric:
        return (
            "proof",
            "graphic-fullscreen",
            {
                "id": graphic_id,
                "component": "StatisticCard",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {"value": numeric[0], "label": text},
            },
        )

    has_question = any("?" in cast(str, word["text"]) for word in scene_words)
    if has_question or (tokens & _QUESTION and scene_index % 3 == 0):
        return (
            "story",
            "graphic-fullscreen",
            {
                "id": graphic_id,
                "component": "QuoteCard",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {"quote": text},
            },
        )

    if tokens & _WARNING:
        privacy = bool(tokens & (_DATA | {"ehtiyaat", "privacy", "sensitive"}))
        return (
            "warning",
            "graphic-fullscreen",
            {
                "id": graphic_id,
                "component": "WarningCard",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {
                    "title": "Sensitive Information" if privacy else "Sensitive Topic",
                    "body": text,
                },
            },
        )

    if tokens & _HUMAN and tokens & _AI:
        return (
            "comparison",
            "graphic-fullscreen",
            {
                "id": graphic_id,
                "component": "ComparisonCard",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {
                    "leftTitle": "Insan",
                    "rightTitle": "AI",
                    "leftItems": ["Trust", "Personal context"],
                    "rightItems": ["Fast response", "Data systems"],
                },
            },
        )

    if tokens & _AI and scene_index % 3 != 0:
        title = "ChatGPT" if "chatgpt" in tokens else "AI Conversation"
        return (
            "demonstration",
            "mobile-demo",
            {
                "id": graphic_id,
                "component": "MobileScreenFrame",
                "startOffset": 0.0,
                "endOffset": duration,
                "props": {"title": title, "steps": _steps(scene_words)},
            },
        )

    accent = next(
        (
            cast(str, word["text"]).strip(".,:;!?()[]{}")
            for word in scene_words
            if cast(str, word["text"]).casefold().strip(".,:;!?()[]{}") in _AI
        ),
        "",
    )
    return (
        "explanation",
        "graphic-fullscreen" if scene_index % 2 == 0 else "speaker-with-title",
        {
            "id": graphic_id,
            "component": "KineticHeadline",
            "startOffset": 0.0,
            "endOffset": duration,
            "props": {
                "eyebrow": "KEY POINT",
                "headline": _snippet(scene_words, 8) or text,
                **({"accent": accent} if accent else {}),
            },
        },
    )


def build_energetic_scenes(
    timeline_segments: list[dict[str, Any]],
    caption_words: list[dict[str, Any]],
    *,
    visual_change_target_seconds: float,
    transition_allowance: int,
) -> list[dict[str, Any]]:
    """Return bounded, typed scenes for the energetic local baseline."""
    beats = visual_beat_ranges(
        timeline_segments,
        caption_words,
        visual_change_target_seconds=visual_change_target_seconds,
    )
    scenes: list[dict[str, Any]] = []
    transition_count = 0
    transition_types = ("zoom", "directional-slide", "blur")
    for index, beat in enumerate(beats, start=1):
        start = float(beat["start"])
        end = float(beat["end"])
        scene_words = _words_in_range(caption_words, start, end)
        purpose, layout, graphic = _graphic(
            scene_index=index,
            scene_words=scene_words,
            scene_duration=end - start,
            final_scene=index == len(beats),
        )
        transition = {"type": "clean-cut", "durationFrames": 0}
        if index < len(beats) and index % 3 == 2 and transition_count < transition_allowance:
            transition = {
                "type": transition_types[transition_count % len(transition_types)],
                "durationFrames": 8,
            }
            transition_count += 1
        query = _topic_query(_tokens(scene_words))
        scenes.append(
            {
                "id": f"scene_{index:06d}",
                "start": beat["start"],
                "end": beat["end"],
                "purpose": purpose,
                "sourceTimelineIds": beat["sourceTimelineIds"],
                "layout": layout,
                "camera": {
                    "mode": "static",
                    "scaleStart": 1.0,
                    "scaleEnd": 1.0,
                    "focus": "face",
                },
                "colorOverride": None,
                "broll": {
                    "mode": "none",
                    "assetId": None,
                    "query": query,
                    "effect": "kenburns-in" if index % 2 else "slow-pan-left",
                    "fit": "cover",
                },
                "graphics": [graphic],
                "sfx": [],
                "transitionOut": transition,
                "screenTreatment": None,
            }
        )
    return scenes
