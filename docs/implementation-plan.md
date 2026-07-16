# Post-v2 Local Editor Controls and Owned B-roll Plan

Status: In progress on 2026-07-16.

## Active scope

Add an optional loopback-only control surface around the existing deterministic pipeline. Keep the immutable static review package read-only, keep Cowork output schema-bound, and expose only bounded creator actions: video intake, caption visibility/preset, B-roll policy, owned B-roll upload/pinning, Cowork request/apply, render, and status.

## Active tasks

1. Add caption visibility to edit-plan, revision, render-input, QC, and Remotion contracts while retaining all caption words and timing.
2. Add a validated project-bound owned B-roll pin document and make explicit pins override automatic ranking without bypassing media, hash, or license checks.
3. Build a localhost UI/API with safe streaming uploads, background jobs, project selection, video preview, status, caption controls, B-roll modes, owned asset selection, and Cowork handoff files.
4. Preserve the static `review/index.html` security/evidence boundary and never execute code or commands from browser or Cowork payloads.
5. Add schema, planning, asset, controller, CLI, Remotion, and browser tests.
6. Verify project `t`, full Python/Remotion checks, and documentation.

## Active acceptance tests

- The server binds only to loopback, requires a per-process mutation token, rejects unsafe paths/extensions/oversized bodies, and serializes jobs.
- Caption off removes only the visual caption layer; transcript words, IDs, timings, and audio ducking evidence remain intact.
- Caption presets remain allowlisted and render deterministically.
- Auto B-roll remains local-first; graphics-only produces no B-roll request; user-pinned owned media wins for its selected scene and remains fully evidenced in the manifest.
- Cowork receives a bounded request file and the UI applies only a valid project-matching typed revision file.
- A UI-triggered change returns the project to `awaiting_review` with passing QC.

---

# Post-v2 Timestamped Transcript Cue Plan

Status: Complete on 2026-07-16.

## Active scope

Extend the authoritative manual transcript boundary to accept user-supplied section timecodes without treating Markdown headers as caption text. Keep exact Roman Urdu/English wording and use the supplied cue ranges as the segment timing authority.

## Active tasks

1. Parse bounded `M:SS–M:SS` and final `M:SS–End` headers with strict mixed-format and chronology validation.
2. Allocate deterministic word timings within each cue while preserving exact tokens, segment text, IDs, and source hashing.
3. Revalidate the timestamped source format and tokens on resume.
4. Add valid, malformed, overlapping, out-of-range, empty-cue, and `End` tests.
5. Import the new user script for project `t`, rerender, inspect cue/visual boundaries, and verify QC.
6. Run formatting, lint, strict typing, Python tests, and relevant integration checks; update the phase record.

## Active acceptance tests

- Cue headers never become transcript words or captions.
- Segment start/end values equal the supplied timecodes; `End` equals validated media duration.
- Word IDs are sequential, timestamps are positive and monotonic, and every word remains inside its cue.
- Plain manual scripts retain the existing weighted full-duration behavior.
- Source tampering and unsafe paths remain rejected.
- Project `t` returns to `awaiting_review` with the user's exact timestamped version.

## Completion record

- Added strict timestamp parsing for Markdown-style minute/hour cues and final `End`, including malformed, mixed, empty, reversed, overlapping, and out-of-duration rejection.
- Cue headers are excluded from words; each exact supplied token receives a positive deterministic interval inside its authoritative cue.
- Source hash, text, token, segment, and cue timing revalidation now protects resume behavior.
- Project `t` contains exactly 283 supplied tokens and 16 exact user ranges; the ASR snapshot remains present.
- The rerender returned to `awaiting_review`, passed 15/15 QC checks, and produced valid 540x960 H.264/AAC media with recurring graphics, camera motion, B-roll queries, and SFX.
- Python formatting, lint, strict typing, all focused transcription tests, exact artifact checks, media probing, and representative frame inspection passed.

---

# Post-v2 Production Enrichment Plan

Status: Complete on 2026-07-16.

## Active scope

Correct the captions-only result produced when an entire talking-head recording is retained as one timeline range. Treat source cuts and creative visual beats as separate concepts, preserve the authoritative manual transcript, and keep enhancement generation local-first.

## Active tasks

1. Segment continuous output into gap-free visual beats at stable word boundaries while retaining authoritative source-timeline references.
2. Assign bounded energetic-mode camera changes and typed catalog graphics across the full video instead of only the opening 2.5 seconds.
3. Derive short ASCII B-roll queries from allowlisted topic cues and preserve a code-native graphic cutaway whenever no licensed asset resolves.
4. Add deterministic owned impact, whoosh, and pop WAV generation before local asset indexing so planned SFX remain audible without paid APIs.
5. Improve full-screen graphic presentation in Remotion with frame-driven motion and opaque local backgrounds; do not add CSS animation or remote runtime media.
6. Add unit, contract, fallback, and representative render tests.
7. Rerun project `t` from planning, inspect representative frames and audio/asset evidence, and return it to the human review checkpoint.
8. Run the required Python and Remotion verification suite and record the phase boundary.

## Active acceptance tests

- A single 80-second timeline keep range produces several ordered, non-overlapping, gap-free creative scenes.
- All 310 supplied Roman Urdu tokens, immutable word IDs, and aligned timings remain byte-for-byte equivalent across the planning rerun.
- Energetic planning produces multiple typed graphics and camera resets while remaining inside configured per-minute budgets.
- Planned SFX queries resolve to hash-verified, owned, project-staged WAV files and appear in `renders/draft-input.json`.
- Missing B-roll never produces a captions-only frame sequence when a typed graphic fallback exists.
- The rerendered draft passes QC and visibly contains more than captions.

## Completion record

- Project `t` now resolves one continuous 79.94-second keep range into 15 gap-free creative scenes without changing the media timeline.
- The draft contains 15 typed graphics, 14 camera moves, five visual transitions, 13 topic-specific B-roll requests with code-native fallbacks, and ten resolved SFX placements from three deterministic owned WAV assets.
- The exact 310 manual transcript tokens, immutable word IDs, and timings remain preserved.
- Representative portrait frames verified centered hook, statistic, mobile, quote, timeline, warning, kinetic-headline, and CTA treatments after one layout correction pass.
- Real project QC passed 15/15 checks with zero warnings and zero blockers; state returned to `awaiting_review`.
- Python formatting, lint, strict typing, all 212 tests, Remotion lint/TypeScript/bundle, and npm audit passed.

---

# Phase 12 Implementation Plan

Status: Complete on 2026-07-16.

## Scope

Add a schema-safe viral social design expansion for portrait explainers and Shorts. Use observable patterns from user-provided references and official public Shorts without claiming access to private After Effects projects or copying creator branding, handles, promotional wrappers, reference footage, or proprietary assets.

## Tasks

1. Add original `viral-punch` and `boxed-keyword` caption presets with deterministic word-timed motion.
2. Add a `viral-social` design preset and make it the energetic-mode baseline while retaining all existing modes and fallbacks.
3. Add typed price/comparison and kinetic-headline graphics for high-value data beats.
4. Upgrade the existing mobile-screen component into a modern search/demo treatment using only validated strings and arrays.
5. Keep one focal message per beat, generous portrait safe zones, limited colors, and short frame-driven entrances.
6. Use clean cuts and reaction/reframe changes as the baseline; effects remain inside existing transition, camera, graphic, and SFX budgets.
7. Update component-catalog and plan/render schemas without accepting arbitrary CSS, code, fonts, colors, URLs, or paths.
8. Add contract, unsafe-input, deterministic-timing, fallback, and representative render tests.
9. Run Python format/lint/types/tests, doctor, Remotion lint/build, real still/video inspection, duration/codec checks, and dependency audit.

## Acceptance tests

- New captions preserve authoritative word IDs, text, order, start/end timing, and safe zones.
- Caption animation is driven only by Remotion frames and explicit interpolation; no CSS animations or transitions are used.
- New graphic props are strict, bounded, typed, and reject unknown values and executable/path fields.
- Energetic mode selects the new design while fast, balanced, and cinematic behavior remains compatible.
- Price labels, phone demos, and kinetic typography have one clear focal point and remain legible at portrait viewing size.
- Missing optional assets preserve a valid speaker/graphic fallback.
- Existing Phase 9 review, Phase 10 design, Phase 11 learning, final delivery, and local-first behavior remain valid.

## Phase boundary

This phase adds design primitives only. It does not add publishing, autonomous approval, paid services, remote runtime assets, creator impersonation, or arbitrary After Effects/project execution.

## Completion record

- Added two typed caption presets, one design preset, two catalogued graphics, and an upgraded phone/search component.
- Preserved caption IDs, wording, order, timestamps, safe zones, local font fallback, and existing effect budgets.
- Verified strict schemas, runtime validation, energetic-mode selection, deterministic frame motion, representative real renders, and existing design behavior.
- Inspected headline, phone-demo, and value-comparison portrait frames at original resolution and corrected word spacing plus preview data wiring from visual evidence.
- Passed Python format, lint, strict types, all 189 tests, environment doctor, Remotion lint/types/build, dependency audit, and H.264/AAC preview metadata checks.

## Post-v2 hardening addendum: authoritative manual transcripts

When local ASR is materially incomplete, accept an explicit project-relative UTF-8 `.txt`
file as the authoritative Roman Urdu transcript. Preserve the original validated ASR JSON,
hash-bind and revalidate the supplied script, keep its tokens unchanged through normalization,
assign deterministic locked timing within FFmpeg-supported speech bounds, invalidate only
normalization and downstream stages, and rerender to the normal human review boundary. This
fallback must reject absolute paths, traversal, non-UTF-8 content, oversized input, mixed word
sources, source tampering, and post-approval replacement.
