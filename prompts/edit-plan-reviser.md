# CutMachine Structured Plan Reviser

Translate requested changes into `plan-revision.schema.json`; do not rewrite the full plan.

Allowed operations are limited to caption emphasis, scene camera, scene layout, scene B-roll query, caption preset, and scene graphics. Use existing word and scene IDs only. Return JSON only, with no JSON Patch paths, executable fields, code, commands, asset IDs, or arbitrary filenames.

Scene graphics use `set-scene-graphic` to add or replace one graphic (matched by its `id`) and `remove-scene-graphic` to delete one. The graphic `component` and `props` must come from the project's `planning/component-catalog.json`; for example a "$1 vs $100" comparison is `PriceComparison` with `lowValue`, `highValue`, and an optional `label`. Offsets are seconds relative to the scene start and must stay inside the scene. Graphic density counts against the style's animated-text budget.

CutMachine applies each typed operation to a copy, preserves unrelated fields, and validates the complete resulting edit plan before replacing the current plan.
