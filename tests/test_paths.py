from pathlib import Path

import pytest

from cutmachine.paths import UnsafePathError, resolve_inside, validate_relative_path


@pytest.mark.parametrize(
    "raw",
    ["C:\\video.mp4", "D:/video.mp4", "/tmp/video.mp4", "\\server\\share", "~/video.mp4"],
)
def test_absolute_paths_are_rejected(raw: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_relative_path(raw)


@pytest.mark.parametrize("raw", ["../video.mp4", "media/../../video.mp4", "media\\..\\video.mp4"])
def test_traversal_is_rejected(raw: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_relative_path(raw)


def test_safe_path_resolves_inside_root(tmp_path: Path) -> None:
    assert resolve_inside(tmp_path, "media/base.mp4") == tmp_path / "media" / "base.mp4"
