from __future__ import annotations

import json
import wave
from pathlib import Path

from cutmachine.builtin_assets import ensure_builtin_sfx
from cutmachine.project import sha256_file


def test_builtin_sfx_are_deterministic_owned_pcm_assets(tmp_path: Path) -> None:
    assets = tmp_path / "assets-library"
    first = ensure_builtin_sfx(assets)
    hashes = {path.name: sha256_file(path) for path in first}
    second = ensure_builtin_sfx(assets)

    assert len(first) == 3
    assert hashes == {path.name: sha256_file(path) for path in second}
    for path in first:
        with wave.open(str(path), "rb") as audio:
            assert audio.getframerate() == 48_000
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getnframes() > 0
        sidecar = json.loads(path.with_suffix(".wav.asset.json").read_text(encoding="utf-8"))
        assert sidecar["license"] == "owned"
        assert sidecar["attributionRequired"] is False
