# CutMachine Build Status

- Active phase: Post-v2 local editor controls and owned B-roll workflow
- Status: Complete (CLI surface); optional loopback browser UI remains future work
- Phase started: 2026-07-16
- Editor controls CLI completed: 2026-07-16
- Timestamped transcript cues completed: 2026-07-16
- Post-v2 hardening completed: 2026-07-16
- Phase 12 completed: 2026-07-16
- Phase 11 completed: 2026-07-16
- Completed phases: Phase 0 - Repository and doctor; Phase 1 - Orchestrator and project state; Phase 2 - Ingest and transcription; Phase 3 - Transcript normalization; Phase 4 - Timeline automation; Phase 5 - Cowork planning contract; Phase 6 - Remotion MVP; Phase 7 - Asset system; Phase 8 - Technical finishing; Phase 9 - Review and QC; Phase 10 - Advanced design system; Phase 11 - Learning and optimization; Phase 12 - Viral social design expansion; Post-v2 production enrichment; Post-v2 timestamped transcript cues
- Blocking environment finding: None

## Local-editor acceptance

- Provide an optional loopback-only UI without weakening the immutable static review package: deferred - the domain layer (ADR-0053) ships behind `editor-apply`, `add-broll`, and `cowork-request` CLI commands (ADR-0054); a browser surface may later call the same orchestrator functions.
- Let the creator add a supported source video, select mode, and watch background pipeline status: pass via `run --mode` and `status`.
- Let the creator turn captions on/off and choose an allowlisted caption preset without changing transcript words, IDs, or timing: pass via `editor-apply`.
- Offer B-roll modes for local-first automatic search, graphics-only fallback, validated Cowork handoff, and explicit owned-file selection: pass via `editor-apply` `brollMode` and typed pins.
- Accept owned B-roll uploads only with bounded size, allowlisted extensions, license confirmation, safe names, media probing, hashing, and typed scene pins: pass via `add-broll` and the controlled upload directory.
- Apply only validated plan operations and project-bound asset pins, then rerender through normal QC to `awaiting_review`: pass via `apply_project_editor_settings`.
- Test the UI/API, schema boundaries, Remotion behavior, pipeline regression suite, and representative local browser interactions: schema, domain, loader, staging, and pipeline regression tests pass; browser-interaction testing moves to the future UI work.

## Timestamped-transcript completion

- Accept strict Markdown-style `M:SS–M:SS` and final `M:SS–End` cue headers in a project-relative UTF-8 `.txt` manual transcript.
- Exclude cue headers from captions, preserve every supplied spoken token exactly, and align words deterministically only inside their authoritative cue bounds.
- Resolve `End` to the validated media duration and reject malformed, empty, reversed, overlapping, non-monotonic, or out-of-duration cues.
- Hash-bind and reparse the timestamped source during resume validation so changed cue text or timing cannot be accepted silently.
- Imported the user's timestamped script into project `t`, preserved the ASR snapshot, and rerendered to `awaiting_review`.
- Verified 283/283 exact supplied tokens, 16/16 exact cue ranges, zero captioned headers, and `timestamped-script-cues` provenance.
- Verified 15 creative scenes, 15 graphics, 15 camera moves, 12 B-roll queries, 11 SFX cues, H.264/AAC portrait output, and 15/15 QC checks with zero blockers.
- Inspected fresh opening, quotation, and privacy-warning frames; focused transcription tests, formatting, lint, and strict typing passed.

## Post-v2 hardening (ADR-0045 through ADR-0048)

- Deterministic bounded SFX placement engine feeding the existing tiered asset search
- Roman Urdu transcription tuning: glossary hotwords, hallucination-silence guard, stronger per-mode models, word-initial "w" and digit transliteration, ~190-word high-frequency lexicon
- Typed `set-scene-graphic`/`remove-scene-graphic` revision operations for runtime catalog graphics (for example PriceComparison "$1" vs "$100") through Cowork
- Attention-pacing camera engine (hook punch-in, alternating slow zooms) with per-mode motion curves in Remotion, plus the `teal-orange` grade preset
- Hash-bound project-relative manual Roman Urdu transcript import with immutable ASR snapshot, exact-token preservation, deterministic speech-span alignment, and automatic downstream rerender

## Production-enrichment completion

- Split a long continuous kept range into deterministic visual beats without changing the source timeline, caption text, caption IDs, or caption timings.
- Give energetic projects multiple bounded camera resets and typed code-native graphic cutaways, including a hook, explanation beats, warning/quote/data treatments when detected, and a closing CTA.
- Emit concrete English B-roll queries for visual beats; when no licensed clip is available, render the typed graphic as the local-first cutaway instead of silently falling back to captions only.
- Generate a small owned local SFX pack deterministically, resolve planned impact/whoosh/pop cues through the existing asset boundary, and keep voice intelligibility dominant.
- Rerender project `t` to `awaiting_review` and verify multiple scenes, graphics, resolved SFX, preserved 310-token manual transcript, zero blocking QC findings, and representative portrait frames.
- Pass Python format/lint/types/tests, Remotion lint/types/build, and a real render smoke check before marking the phase complete.

## Verified 2026-07-16

- Python format: pass
- Python lint: pass
- Python strict type check: pass
- Python tests: pass (212 collected)
- Doctor: ready with Python 3.12.10, Node 24.18.0, FFmpeg/FFprobe 8.1.2, Faster-Whisper 1.2.1, and Remotion dependencies
- Remotion lint and TypeScript: pass
- Remotion production bundle: pass
- NPM audit: pass (0 vulnerabilities)
- Environment warnings: no active virtual environment; no optional API adapters configured
- Real 310-word manual transcript import for project `t`: exact token equality, original ASR snapshot, three inspected portrait caption frames, zero blocking QC errors, and `awaiting_review`: pass
- Real production-enriched project `t`: 15 gap-free scenes, 15 typed graphics, 14 camera moves, 5 transitions, 13 B-roll requests with graphic fallbacks, 10 resolved SFX cues from 3 owned staged assets, exact 310-token/timing-ID preservation, 15/15 QC checks, and representative hook/statistic/phone/quote/timeline/warning/kinetic/CTA frame inspection: pass

## Phase 11 verification

- Versioned feedback, immutable event, preference, correction, style-tuning, performance, and delivery schemas with strict boundaries: pass
- Explicit current review/QC hash binding and append-only accepted/rejected snapshots: pass
- Duplicate, stale, tampered, malformed, cross-project, absolute, and traversal feedback rejection: pass
- Safe-tier bounded asset preference ranking without license or watermark bypass: pass
- Context-aware caption correction reuse with protected glossary priority and immutable word identity/timing: pass
- Explicitly activated per-mode style tuning inside existing presets and effect-budget ceilings: pass
- Corrupt or stale learned-profile fallback to deterministic local defaults: pass
- Validated cache-hit and non-negative stage timing evidence: pass
- Modern responsive local editor HTML with preview, timeline, transcript, assets, color, audio, learning, QC, and action navigation: pass
- Script-free, remote-resource-free, escaped local review security boundary: pass
- Automatic full-resolution render only after explicit approval: pass
- Final workspace/output hash equality plus dimension, duration, H.264 video, AAC audio, and approval evidence validation: pass
- Real review-package generation and real full-resolution Remotion/FFmpeg final-delivery tests: pass
- Browser preview server: pass at `http://127.0.0.1:8765/index.html`; in-app screenshot inspection unavailable because no browser backend was exposed in this session
- Phase boundary: pass; all planned roadmap phases are complete

## Phase 12 verification

- Original `viral-punch` and `boxed-keyword` caption presets with immutable word timing and frame-driven motion: pass
- `viral-social` energetic-mode preset with existing mode compatibility: pass
- Typed `KineticHeadline` and `PriceComparison` graphics with strict bounded props: pass
- Modern phone/search demonstration with validated local strings and staggered frame timing: pass
- Portrait typography hierarchy, spacing, contrast, and caption safe-zone screenshot inspection: pass
- Remotion lint, TypeScript, production bundle, and zero-vulnerability audit: pass
- Real three-second H.264/AAC portrait preview at 540x960 and 30 fps: pass
- Phase boundary: pass; the local-first roadmap is complete through the optional viral social design expansion
