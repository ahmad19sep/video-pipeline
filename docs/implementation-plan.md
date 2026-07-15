# Phase 11 Implementation Plan

## Scope

Add a local, auditable learning loop from explicit review decisions while preserving the single human checkpoint, immutable media/timing evidence, deterministic fallbacks, and reproducible rendering. Track accepted/rejected decisions, preferred assets, approved caption corrections, bounded style tuning, and measured performance improvements. The system must not infer approval from silence, mutate source artifacts, execute learned code, publish content, or require paid/network services.

## Tasks

1. Define versioned local schemas for decision history, asset preferences, caption corrections, style tuning, and performance measurements.
2. Accept learning events only from explicit, current, project-bound approval or revision decisions whose referenced artifacts and hashes revalidate.
3. Store append-only accepted/rejected decision records with stable IDs, timestamps, project provenance, decision scope, and before/after evidence.
4. Record asset preference signals from explicit acceptance/rejection without changing licensing, attribution, hash, source, or project evidence.
5. Incorporate bounded preference scores into deterministic asset ranking after relevance and license gates, with stable tie-breaking and no automatic provider expansion.
6. Add an approved caption-correction dictionary containing heard text, preferred display, bounded context terms, provenance, and approval time.
7. Apply caption corrections before optional refinement while preserving the exact ordered immutable word IDs and source/remapped timestamps.
8. Keep protected technical glossary terms authoritative and reject corrections that merge, split, reorder, delete, or retime words.
9. Derive bounded per-mode style-tuning suggestions from accepted/rejected structured decisions; require explicit activation and retain default profiles as fallbacks.
10. Restrict learned style values to the existing component, transition, effect-budget, color, screen-treatment, and safe-zone allowlists.
11. Add deterministic cache reuse and stage timing measurements without skipping hash/schema revalidation or changing output semantics.
12. Surface learning provenance, active preferences/corrections, style overrides, cache hits, and timing summaries in project/review evidence.
13. Add migration, corruption, duplicate-event, stale-project, unsafe-path, tampered-evidence, deterministic-ranking, timing-preservation, offline, and graceful-fallback tests.
14. Run formatting, linting, strict typing, Python tests, doctor, Remotion checks/bundle, representative end-to-end inspection, duration/codec validation, and dependency audit.

## Risks

- Feedback may be ambiguous; only explicit structured decisions may become learning events.
- Preference feedback can overpower semantic relevance or licensing unless ranking weights and order remain bounded.
- Caption corrections can corrupt technical terms or timing unless the one-to-one immutable-word contract is revalidated.
- Style tuning can drift toward excessive effects unless all learned values remain inside existing mode budgets.
- Cache optimization can reuse stale artifacts unless every hit is schema-, project-, dependency-, and hash-bound.
- Cross-project history can leak private content unless records contain only the minimal approved structured context.

## Acceptance tests

- Only explicit current review outcomes produce schema-valid append-only learning events; stale, duplicated, tampered, or malformed events are rejected.
- Accepted/rejected asset signals affect ranking deterministically but never bypass relevance, ownership/license, attribution, orientation, or quality gates.
- Approved caption corrections are reused by bounded context and preserve exact word IDs, ordering, raw text, source timestamps, and remapped timestamps.
- Protected technical terms remain authoritative, and uncertain or conflicting corrections fall back to the existing deterministic normalizer.
- Style tuning stays within known presets, component/transition allowlists, safe zones, color bounds, and per-mode effect budgets, with defaults available at all times.
- Learning records contain no raw media, full transcript, secrets, executable fields, absolute paths, or traversal paths.
- Cache hits revalidate dependencies and hashes, produce byte-equivalent artifacts where required, and fall back safely after corruption.
- Performance reports use monotonic stage timings and demonstrate improvement without weakening validation or changing observable output contracts.
- A clean offline project can run through draft, QC, explicit review, learning update, and a future reuse path without paid services.
- Existing Phase 9 review/approval and Phase 10 design behavior plus all immutable source, transcript, and timeline evidence remain unchanged.
- Formatting, linting, strict types, Python tests, doctor, Remotion checks/bundle, representative render inspection, duration/codec checks, and NPM audit pass.

## Phase boundary

Phase 11 is the final planned roadmap phase. Do not add publishing, autonomous approval, arbitrary learned execution, or paid-service requirements.
