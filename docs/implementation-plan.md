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
