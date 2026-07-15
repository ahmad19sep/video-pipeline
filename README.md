# CutMachine

CutMachine is a complete local-first, resumable AI video-editing pipeline for Urdu speech mixed with English technical terms. Python owns orchestration and validation, FFmpeg owns technical media work, and Remotion owns deterministic visual composition. The v2.0 roadmap is complete through final delivery, explicit review learning, and a modern local editor/review surface.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd remotion
npm install
cd ..
```

Install FFmpeg and ensure both `ffmpeg` and `ffprobe` are on `PATH`, then run:

```powershell
python cutmachine.py doctor
```

The doctor exits non-zero when a core dependency is missing. Optional services only produce warnings.

## Phase 1 project commands

Create and validate a project from a source video:

```powershell
python cutmachine.py run inbox\video.mp4 --mode balanced
```

Inspect or resume it using either its workspace slug or path:

```powershell
python cutmachine.py status video
python cutmachine.py resume video
```

Intentionally invalidate a stage and all of its downstream dependents:

```powershell
python cutmachine.py rerun video --from validated
```

A successful run stops at `awaiting_review` with technical finishing, automated QC, and a modern read-only local editor at `review/index.html`. Original source files and transcripts are never modified. Persisted project paths are relative, state writes are atomic, and concurrent project mutations are locked.

Phase 2 creates:

- `analysis/media-info.json` and `analysis/contact-sheet.jpg`
- `media/proxy.mp4` and representative JPEG frames
- `audio/original.wav` and mono 16 kHz `audio/source.wav`
- `transcript/transcript.raw.json` with immutable word IDs and timestamps

Phase 3 additionally creates:

- `transcript/transcript.roman.json` with one normalized display per immutable word
- `analysis/transcript-normalization-report.json` with provenance and low-confidence findings

Normalization works offline using the technical glossary, local lexicon, and deterministic transliteration. Optional HTTPS refinement is disabled by default and must return the same ordered word IDs; malformed responses fall back to local output.

Phase 4 additionally creates:

- `analysis/silence-candidates.json` and `analysis/repetition-candidates.json`
- `timeline/source-timeline.json` with reversible safe cuts
- `timeline/time-map.json` with source-to-output mappings
- `transcript/transcript.remapped.json` with synchronized output timestamps

Automatic cuts require corroborating word-gap and FFmpeg silence evidence. Repetition candidates are retained for later creative review.

Phase 5 additionally creates:

- `planning/edit-plan.json` with a complete local baseline edit
- `planning/component-catalog.json` with the allowed MVP components and props
- `planning/cowork-input.json` with bounded validated artifact paths

Cowork may import only schema-valid JSON using existing IDs and catalog components. Typed revision operations preserve unrelated plan choices and rerun full validation.

Phase 6 additionally creates:

- the initial asset-free `assets/manifest.json` boundary, expanded by Phase 7 resolution
- `analysis/preprocess-record.json` describing direct proxy/timeline preprocessing
- `renders/draft-input.json` with typed Remotion props
- `review/draft.mp4` and `renders/draft-render.json` with verified output metadata

The draft composition renders piecewise speaker video/audio, Roman Urdu word highlights, catalog graphics, bounded camera moves, and duration-preserving transitions. It supports optional validated local B-roll, music, and SFX while retaining a speaker-only fallback.

Phase 7 additionally creates:

- `planning/asset-index.json`, `asset-requests.json`, `asset-candidates.json`, and `asset-ranking.json`
- `planning/resolved-edit-plan.json`, leaving the original creative plan unchanged
- `assets/manifest.json` with source, creator, license, attribution, hash, scene, and relevance evidence
- content-addressed provider cache objects under `.cache/assets/`

Add owned media beneath `assets-library/broll`, `images`, `music`, or `sfx`. An optional adjacent sidecar such as `clip.mp4.asset.json` may declare `tags`, `license`, `creator`, and `attributionRequired`; LUT sidecars also declare `colorSpace`. Unknown fields are rejected. Video/image thumbnails and audio waveforms are cached during indexing.

Pexels video search is disabled by default. To opt in, set `PEXELS_API_KEY`, enable `assets.pexels.enabled`, and keep both project and current network access enabled. Only short validated English visual queries are sent. Asset-free and offline runs continue with graphics or speaker output.

Phase 8 additionally creates:

- `analysis/scene-classification.json` and `reframe-analysis.json` with deterministic framing evidence
- `analysis/color-analysis.json` and `audio-mastering.json` with bounded before/after metrics
- `media/technical-proxy.mp4` and `analysis/technical-finish.json`
- `renders/final-pass.json` for the verified FFmpeg fast-start pass over the Remotion draft

Technical finishing uses a center-crop fallback when no local face detector is supplied, preserves screens and uncertain scenes neutrally, applies bounded color and speech-first mastering, and supports only indexed licensed LUTs with a declared `rec709` or `srgb` color space and intensity at or below 0.5.

Phase 9 additionally creates:

- `review/qc-report.json` with blocking, warning, and passed quality gates
- `review/color-before.jpg` and `review/color-after.jpg`
- `review/index.html`, a local-only read-only review page with the draft, scenes, warnings, assets, technical summaries, and recommended action
- `review/review-package.json` with hashes for every review artifact

Normal runs never approve automatically. After opening `review/index.html`, record the single human checkpoint with either:

```powershell
python cutmachine.py approve video --note "Reviewed and approved"
python cutmachine.py request-revision video planning\revision.json --note "Change caption emphasis"
```

Approval automatically renders and verifies the full-resolution master at `output/<project-slug>.mp4`, then marks the project complete. Revision JSON must use the existing allowlisted `plan-revision` contract and a safe project-relative path. A revision invalidates `plan_ready` and downstream stages while preserving the source timeline and transcript evidence.

Phase 10 adds the versioned visual design system: six caption presets, typed title/information/data/screen/layout components, bundled Urdu typography, responsive safe zones, bounded camera and transition treatments, and conservative color presets. Unsupported components, props, effects, paths, or executable fields are rejected before rendering.

Phase 11 adds an explicit, auditable local learning loop and final delivery:

- immutable hash-bound accepted/rejected review events under `workspace/.learning/`
- bounded asset preference tie-breaking after license and relevance gates
- approved context-aware caption corrections without changing word IDs or timing
- explicitly activated per-mode style tuning that can only reduce effect budgets
- monotonic stage timing and validated cache-hit evidence in `analysis/performance-report.json`
- `renders/final.mp4`, `renders/delivery-record.json`, and the verified `output/<project-slug>.mp4` master

Optional structured feedback is project-relative and validated by `schemas/learning-feedback.schema.json`. Pass it with the same explicit human decision:

```powershell
python cutmachine.py approve video --feedback review\learning-feedback.json
python cutmachine.py request-revision video planning\revision.json --feedback review\learning-feedback.json
```

Learning is never inferred from silence. Invalid, stale, duplicated, tampered, absolute, or traversal-based feedback is rejected; corrupt derived profiles fall back to deterministic defaults.

The first transcription run downloads the selected Faster-Whisper model when it is not cached. CUDA is attempted on suitable hardware; failures retry once with the configured CPU int8 fallback and record the reason.

Stage-specific internal commands are also available:

```powershell
python scripts\ingest.py video
python scripts\transcribe.py video
python scripts\normalize_transcript.py video
python scripts\analyze_timeline.py video
python scripts\plan_edit.py video
python scripts\resolve_assets.py video
python scripts\finish_technical.py video
python scripts\render_draft.py video
python scripts\review_project.py video
```

## Development checks

```powershell
ruff format --check .
ruff check .
mypy
pytest
cd remotion
npm run typecheck
```

See [docs/status.md](docs/status.md) for the active roadmap phase and [docs/implementation-plan.md](docs/implementation-plan.md) for its acceptance tests.
