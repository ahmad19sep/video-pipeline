"""Deterministic owned media used when an optional asset service is absent."""

from __future__ import annotations

import json
import math
import os
import struct
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

from cutmachine.paths import resolve_inside

_SAMPLE_RATE = 48_000
_CREATOR = "CutMachine deterministic synthesizer"


def _impact(time: float, progress: float) -> float:
    tone = math.sin(2 * math.pi * (115 - 55 * progress) * time)
    click = math.sin(2 * math.pi * 780 * time) * max(0.0, 1 - progress * 8)
    noise = math.sin(2 * math.pi * 1733 * time + math.sin(time * 997))
    return (tone * 0.62 + click * 0.18 + noise * 0.08) * math.pow(1 - progress, 2.8)


def _whoosh(time: float, progress: float) -> float:
    envelope = math.pow(math.sin(math.pi * progress), 1.4)
    carrier = math.sin(2 * math.pi * (240 + 1900 * progress**2) * time)
    texture = math.sin(2 * math.pi * 3179 * time + math.sin(time * 1103))
    return (carrier * 0.22 + texture * 0.16) * envelope


def _pop(time: float, progress: float) -> float:
    tone = math.sin(2 * math.pi * (760 - 430 * progress) * time)
    overtone = math.sin(2 * math.pi * 1250 * time)
    return (tone * 0.48 + overtone * 0.16) * (1 - progress) ** 4


_SOUNDS: tuple[tuple[str, float, Callable[[float, float], float], list[str]], ...] = (
    ("impact-hit-intro.wav", 0.42, _impact, ["impact", "hit", "intro", "soft"]),
    (
        "whoosh-transition-swish.wav",
        0.48,
        _whoosh,
        ["whoosh", "transition", "swish", "swoosh"],
    ),
    ("pop-click-accent.wav", 0.16, _pop, ["pop", "click", "accent", "subtle"]),
)


def _wav_payload(duration: float, synthesizer: Callable[[float, float], float]) -> bytes:
    frames = max(1, round(duration * _SAMPLE_RATE))
    with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024) as handle:
        with wave.open(handle, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(_SAMPLE_RATE)
            payload = bytearray()
            for index in range(frames):
                progress = index / max(1, frames - 1)
                value = max(-0.8, min(0.8, synthesizer(index / _SAMPLE_RATE, progress)))
                payload.extend(struct.pack("<h", round(value * 32767)))
            output.writeframes(payload)
        handle.seek(0)
        return handle.read()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_bytes(path, payload)


def ensure_builtin_sfx(assets_root: Path) -> list[Path]:
    """Create the fixed owned SFX pack without touching unrelated user media."""
    generated_root = resolve_inside(assets_root, "sfx/cutmachine-generated")
    generated: list[Path] = []
    for name, duration, synthesizer, tags in _SOUNDS:
        destination = resolve_inside(generated_root, name)
        payload = _wav_payload(duration, synthesizer)
        if not destination.is_file() or destination.read_bytes() != payload:
            _atomic_bytes(destination, payload)
        sidecar = destination.with_suffix(destination.suffix + ".asset.json")
        metadata: dict[str, object] = {
            "tags": tags,
            "license": "owned",
            "creator": _CREATOR,
            "attributionRequired": False,
            "colorSpace": None,
        }
        expected = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not sidecar.is_file() or sidecar.read_bytes() != expected:
            _atomic_json(sidecar, metadata)
        generated.append(destination)
    return generated
