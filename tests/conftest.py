import shutil
import subprocess
from pathlib import Path
from shutil import copytree
from typing import Any, cast

import pytest

from cutmachine import orchestrator
from cutmachine.editorial import build_timeline_documents
from cutmachine.media import ingest_project
from cutmachine.persistence import read_validated_json, write_validated_json_atomic
from cutmachine.planning import generate_plan
from cutmachine.project import ProjectContext, create_project


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    source_root = Path(__file__).resolve().parents[1]
    copytree(source_root / "config", tmp_path / "config")
    copytree(source_root / "schemas", tmp_path / "schemas")
    copytree(source_root / "assets-library", tmp_path / "assets-library")
    (tmp_path / "workspace").mkdir()
    return tmp_path


@pytest.fixture
def source_video(tmp_path: Path) -> Path:
    path = tmp_path / "My AI Video.mp4"
    path.write_bytes(b"cutmachine-phase-one-fixture\x00\x01\x02")
    return path


@pytest.fixture
def phase2_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        orchestrator,
        "ingest_project",
        lambda _context: ["analysis/media-info.json", "audio/source.wav"],
    )
    monkeypatch.setattr(
        orchestrator,
        "transcribe_project",
        lambda _context: ["transcript/transcript.raw.json"],
    )
    monkeypatch.setattr(
        orchestrator,
        "normalize_project",
        lambda _context: [
            "transcript/transcript.roman.json",
            "analysis/transcript-normalization-report.json",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_project",
        lambda _context: [
            "analysis/silence-candidates.json",
            "analysis/repetition-candidates.json",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "generate_timeline",
        lambda _context: [
            "timeline/source-timeline.json",
            "timeline/time-map.json",
            "transcript/transcript.remapped.json",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "generate_plan",
        lambda _context: [
            "planning/edit-plan.json",
            "planning/component-catalog.json",
            "planning/cowork-input.json",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "prepare_assets",
        lambda _context: ["assets/manifest.json"],
    )
    monkeypatch.setattr(
        orchestrator,
        "preprocess_project",
        lambda _context: ["analysis/preprocess-record.json"],
    )
    monkeypatch.setattr(
        orchestrator,
        "render_draft",
        lambda _context: [
            "renders/draft-input.json",
            "review/draft.mp4",
            "renders/draft-render.json",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "run_quality_control",
        lambda _context: [
            "review/qc-report.json",
            "review/index.html",
            "review/review-package.json",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "prepare_review_checkpoint",
        lambda _context: ["review/index.html", "review/qc-report.json"],
    )
    monkeypatch.setattr(orchestrator, "validate_ingest_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_transcript_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_normalized_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_analysis_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_timeline_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_plan_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_asset_readiness", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_preprocess_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_draft_outputs", lambda _context: None)
    monkeypatch.setattr(orchestrator, "validate_qc_outputs", lambda _context: None)


def generate_real_video(path: Path, *, audio: bool = True, video: bool = True) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        pytest.fail("FFmpeg is required for Phase 2 integration tests.")
    command = [executable, "-hide_banner", "-loglevel", "error"]
    if video:
        command.extend(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2"])
    if audio:
        command.extend(["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest"])
    if video:
        command.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if audio:
        command.extend(["-c:a", "aac"])
    command.extend(["-y", str(path)])
    subprocess.run(command, check=True, capture_output=True, timeout=30)


@pytest.fixture
def real_source_video(tmp_path: Path) -> Path:
    path = tmp_path / "phase-two.mp4"
    generate_real_video(path)
    return path


@pytest.fixture
def ingested_context(repository: Path, real_source_video: Path) -> ProjectContext:
    context = create_project(repository, real_source_video, "fast")
    ingest_project(context)
    return context


@pytest.fixture
def planned_context(ingested_context: ProjectContext) -> ProjectContext:
    media_info = read_validated_json(
        ingested_context.repository_root,
        ingested_context.project_dir / "analysis" / "media-info.json",
        "media-info",
    )
    duration = float(cast(dict[str, Any], media_info["format"])["durationSeconds"])
    words = [
        {
            "id": "word_000001",
            "segmentId": "segment_000001",
            "start": 0.1,
            "end": 0.5,
            "raw": "AI",
            "display": "AI",
            "language": "ur",
            "confidence": 0.99,
            "source": "faster-whisper",
            "normalizationSource": "technical-glossary",
            "lockedTiming": True,
        },
        {
            "id": "word_000002",
            "segmentId": "segment_000001",
            "start": 0.6,
            "end": 1.0,
            "raw": "useful",
            "display": "useful",
            "language": "ur",
            "confidence": 0.9,
            "source": "faster-whisper",
            "normalizationSource": "preserved",
            "lockedTiming": True,
        },
    ]
    normalized = {
        "version": 1,
        "projectId": ingested_context.project["projectId"],
        "language": "ur",
        "displayLanguage": "roman-urdu",
        "durationSeconds": duration,
        "segments": [
            {
                "id": "segment_000001",
                "start": 0.1,
                "end": 1.0,
                "text": "AI useful",
                "wordIds": ["word_000001", "word_000002"],
            }
        ],
        "words": words,
        "provenance": {
            "createdAt": "2026-07-15T12:00:00+00:00",
            "rawTranscriptPath": "transcript/transcript.raw.json",
            "glossaryPath": "config/technical-glossary.json",
            "lexiconPath": "config/roman-urdu-lexicon.json",
            "refinement": {
                "enabled": False,
                "attemptedBatches": 0,
                "appliedBatches": 0,
                "failedBatches": 0,
                "provider": None,
            },
            "wordCountPreserved": True,
            "timingPreserved": True,
        },
    }
    write_validated_json_atomic(
        ingested_context.repository_root,
        ingested_context.project_dir / "transcript" / "transcript.roman.json",
        "normalized-transcript",
        normalized,
    )
    silence = {"policy": {"paddingBefore": 0.13, "paddingAfter": 0.2}, "candidates": []}
    timeline, time_map, remapped = build_timeline_documents(normalized, silence)
    for relative, schema, document in (
        ("timeline/source-timeline.json", "timeline", timeline),
        ("timeline/time-map.json", "time-map", time_map),
        ("transcript/transcript.remapped.json", "remapped-transcript", remapped),
    ):
        write_validated_json_atomic(
            ingested_context.repository_root,
            ingested_context.project_dir / relative,
            schema,
            document,
        )
    generate_plan(ingested_context)
    return ingested_context
