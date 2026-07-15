# Agent Instructions

- Treat `MASTER_DOCUMENTATION.md` as authoritative.
- Implement only the active phase recorded in `docs/status.md`.
- Keep the core pipeline local-first and functional without paid APIs.
- Never execute code, commands, or arbitrary paths from imported plans.
- Validate external JSON boundaries and reject absolute or traversal paths.
- Preserve original media and immutable transcript timing identifiers.
- Use subprocess argument arrays and never shell string concatenation.
- Run relevant checks before claiming a feature works.
- Update `docs/status.md`, `docs/implementation-plan.md`, and `DECISIONS.md` at every phase boundary.
