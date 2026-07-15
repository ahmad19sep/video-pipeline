# Phase 10 Implementation Plan

## Scope

Expand the validated Remotion design system while preserving the Phase 9 review and approval boundary. Add the complete reusable component catalog, caption variants, controlled advanced transitions, readable screen-recording treatments, and cinematic style presets. Subject isolation, background replacement, arbitrary executable effects, and learning behavior remain out of scope.

## Tasks

1. Version the expanded component catalog and render-input contract without accepting arbitrary JSX, CSS, JavaScript, commands, or file paths.
2. Centralize typography, font sizes, weights, spacing, radii, shadows, accent colors, timing, caption placement, and platform safe zones in typed design tokens.
3. Implement `CleanTwoLineCaption`, `HookCaption`, `DefinitionCaption`, `QuestionCaption`, and `UrduScriptCaption` alongside the existing Roman word highlight.
4. Preserve remapped timing and English technical terms across Roman Urdu and Urdu-script caption components, with punctuation-safe paging and bounded two-line layout.
5. Add `StepCard`, `ComparisonCard`, `ToolLogoRow`, `BrowserWindow`, `MobileScreenFrame`, `QuoteCard`, `StatisticCard`, `WarningCard`, `QuestionCard`, `TimelineGraphic`, `FeatureList`, `ProgressIndicator`, `PictureInPicture`, `FullscreenBroll`, and `SplitScreen`.
6. Define strict prop schemas and deterministic fallback rendering for every catalog component.
7. Add blur, zoom, and mask-reveal transitions while keeping clean cuts dominant and preserving authoritative duration.
8. Enforce per-style effect budgets for transition, camera, fullscreen B-roll, animated-text, and impact-SFX density.
9. Add browser/phone framing, cursor highlight, click ripple, interface-region zoom, step labels, and explicit bounded sensitive-region blur for screen recordings.
10. Keep screen UI legible, neutral in color, inside safe zones, and unobscured by captions or dense graphics.
11. Implement `cinematic-warm`, `cinematic-cool`, `documentary`, and `low-light-recovery` presentation presets using existing bounded technical color evidence and licensed LUT rules.
12. Extend Cowork plan validation so only known components, presets, transitions, and typed screen-treatment props can reach Remotion.
13. Add representative portrait, landscape, screen-demo, Urdu-caption, component-catalog, transition-budget, overflow, path-safety, and graceful-fallback renders.
14. Run formatting, linting, strict typing, Python tests, doctor, Remotion checks/bundle, representative still/video inspection, duration/codec validation, and dependency audit.

## Risks

- A larger catalog increases the chance of inconsistent spacing and typography unless all components consume shared tokens.
- Urdu shaping, punctuation, and mixed English terms require font and layout verification at realistic sizes.
- Transition and motion density can reduce clarity; style budgets must be validated before rendering.
- Screen treatments can obscure small UI text or sensitive regions if coordinates are unbounded.
- Cinematic presets must not override Phase 8 screen neutrality, color limits, or LUT licensing.
- Phase 10 must not add arbitrary code execution, final delivery packaging, publishing, or Phase 11 preference learning.

## Acceptance tests

- Every required catalog component has a typed schema, deterministic render path, and safe fallback.
- All required caption styles preserve word timing, technical terms, safe zones, and configured line limits in portrait and landscape outputs.
- Urdu script and mixed Urdu/English captions render with an approved local font and no clipping or corrupted shaping.
- Blur, zoom, and mask transitions preserve total duration and remain within configured effect budgets.
- Screen recordings remain readable with bounded local-only framing, highlights, ripples, zooms, labels, and sensitive-region blur.
- Unknown components, props, presets, transitions, executable fields, and unsafe paths are rejected before rendering.
- Cinematic and documentary presets stay within Phase 8 color/LUT bounds and never grade screen recordings aggressively.
- Missing optional fonts/assets/treatments degrade to a valid base composition instead of failing the draft.
- Existing Phase 9 QC/review/approval behavior and all immutable transcript/timeline evidence remain unchanged.
- Formatting, linting, strict types, Python tests, doctor, Remotion checks/bundle, representative render inspection, duration/codec checks, and NPM audit pass.

## Phase boundary

Phase 11 (learning and optimization) must not start in this implementation.
