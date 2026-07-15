# CutMachine - Master Build Prompt for Claude Code or Codex

Read these files completely before making changes:

1. `MASTER_DOCUMENTATION.md`
2. `BUILD_SPEC.md`
3. `AGENTS.md`
4. `CLAUDE.md`
5. `DECISIONS.md`
6. `docs/status.md`, if it exists

`MASTER_DOCUMENTATION.md` is the authoritative product and architecture specification when an earlier document conflicts with it.

## Mission

Build CutMachine as a local-first, mostly automated AI video editing system for Urdu speech mixed with English technical terms. A normal run must take a raw video from `inbox/` to an automatically rendered draft, pause once for human review, then create a verified final MP4.

## Non-negotiable architecture

- Python owns orchestration, state, media analysis, transcription, asset retrieval, validation, and reports.
- FFmpeg/FFprobe own technical media processing and verification.
- Claude Cowork owns editorial reasoning and writes validated JSON only.
- Remotion owns visual composition, captions, layouts, B-roll, graphics, transitions, and timed audio.
- The original media is immutable.
- Python and Remotion communicate only through versioned JSON and files on disk.
- The core workflow must operate without paid APIs and remain usable with all optional APIs disabled.
- API adapters must be optional, cached, rate-limited, and have local fallbacks.
- Never execute imported code, shell text, or arbitrary paths from an edit plan.

## Working method

1. Determine the current active phase from `docs/status.md`; create it if missing.
2. Inspect the repository before designing new abstractions.
3. Write or update `docs/implementation-plan.md` with the active phase, exact tasks, risks, and acceptance tests.
4. Make reasonable defaults and record them in `DECISIONS.md`. Ask no question unless implementation is genuinely blocked.
5. Implement only the active phase.
6. Add unit and integration tests with the implementation.
7. Run formatting, linting, type checking, Python tests, and relevant render/media checks.
8. Do not state that a feature works unless a relevant command or test was actually run.
9. Update `docs/status.md`, `DECISIONS.md`, and user documentation.
10. Do not begin a later phase until current acceptance criteria pass.

## Priority order

1. Environment doctor and safe project scaffold.
2. One-command orchestrator and resumable state machine.
3. Ingest, proxy, audio, contact sheet, and media metadata.
4. Local Faster-Whisper transcription with immutable word IDs.
5. Roman Urdu normalization with glossary, local fallback, and optional free provider.
6. Safe cut detection and source/output timestamp mapping.
7. Cowork plan schema, prompt, validation, and revision workflow.
8. Remotion MVP and synchronized captions.
9. Local asset library, optional stock/SFX adapters, caching, licensing, and ranking.
10. Draft render, static review report, and automated QC.
11. Technical audio/color finishing and final render.
12. Advanced design, face tracking, and learning features.

## Safety and quality rules

- Reject absolute and traversal paths.
- Validate every external JSON boundary with Pydantic or Zod/JSON Schema.
- Preserve word IDs, start times, and end times.
- Do not silently remove uncertain speech.
- Do not make the pipeline fail because optional B-roll is missing.
- Do not apply cinematic color treatment to screenshots or screen recordings by default.
- Use conservative effect density.
- Prefer reusable components over per-video generated code.
- Keep Windows 11, WSL2, Linux, Unicode, and long-path behavior in mind.
- Use safe subprocess argument arrays, never shell string concatenation.
- Keep API keys out of Git and logs.

## Required end-of-phase report

At the end of each phase, provide:

1. Phase completed or current status.
2. Files created or modified.
3. Commands executed.
4. Tests passed.
5. Tests failed.
6. Items requiring local verification.
7. Known risks or debt.
8. Exact next phase, without starting it.
