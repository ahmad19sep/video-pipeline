from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import generate_real_video

from cutmachine.media import MediaError, ingest_project, probe_media, validate_ingest_outputs
from cutmachine.orchestrator import run_new_project
from cutmachine.project import ProjectContext, create_project, open_project


def test_real_ingest_creates_verified_artifacts(ingested_context: ProjectContext) -> None:
    validate_ingest_outputs(ingested_context)
    media_info = cast(
        dict[str, Any],
        json.loads(
            (ingested_context.project_dir / "analysis" / "media-info.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    artifacts = cast(dict[str, Any], media_info["artifacts"])

    assert media_info["video"]["width"] == 320
    assert media_info["video"]["height"] == 240
    assert len(artifacts["frames"]) == 3
    assert (ingested_context.project_dir / artifacts["contactSheet"]).stat().st_size > 0

    audio_probe = probe_media(
        ingested_context.project_dir / artifacts["transcriptionAudio"],
        log_path=ingested_context.project_dir / "logs" / "test-probe.jsonl",
    )
    audio = next(stream for stream in audio_probe["streams"] if stream["codec_type"] == "audio")
    assert audio["sample_rate"] == "16000"
    assert audio["channels"] == 1

    proxy_probe = probe_media(
        ingested_context.project_dir / artifacts["proxy"],
        log_path=ingested_context.project_dir / "logs" / "test-proxy-probe.jsonl",
    )
    video = next(stream for stream in proxy_probe["streams"] if stream["codec_type"] == "video")
    assert video["width"] == 320
    assert video["height"] == 240


def test_ingest_rejects_corrupt_media(repository: Path, tmp_path: Path) -> None:
    source = tmp_path / "corrupt.mp4"
    source.write_bytes(b"not a media container")
    context = create_project(repository, source, "fast")

    with pytest.raises(MediaError, match="Media command failed"):
        ingest_project(context)


def test_orchestrator_records_corrupt_ingest_failure(repository: Path, tmp_path: Path) -> None:
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"not a media container")

    with pytest.raises(MediaError, match="Media command failed"):
        run_new_project(repository, source, "fast")

    state = open_project(repository, Path("broken")).state_store.load()
    assert state.workflow_state == "failed"
    assert state.failed_stage == "ingested"


def test_ingest_requires_audio_stream(repository: Path, tmp_path: Path) -> None:
    source = tmp_path / "silent-video.mp4"
    generate_real_video(source, audio=False)
    context = create_project(repository, source, "fast")

    with pytest.raises(MediaError, match="no audio stream"):
        ingest_project(context)


def test_ingest_requires_video_stream(repository: Path, tmp_path: Path) -> None:
    source = tmp_path / "audio-only.mp4"
    generate_real_video(source, video=False)
    context = create_project(repository, source, "fast")

    with pytest.raises(MediaError, match="no video stream"):
        ingest_project(context)
