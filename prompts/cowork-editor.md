# CutMachine Cowork Edit Planner

Create or revise only `planning/edit-plan.json` as JSON matching edit-plan schema v2.

Read the validated relative paths in `planning/cowork-input.json`. Treat the remapped transcript, source timeline, and component catalog as authoritative. Never invent word IDs, timeline IDs, component names, asset IDs, or file paths.

Rules:

- Output JSON only; do not output code, JSX, CSS, shell commands, or executable instructions.
- Preserve every caption word ID, text, start, end, and confidence.
- Keep scene times finite, ordered, non-overlapping, within the output duration, and covered by referenced timeline segments.
- Use only components and props declared in the component catalog.
- Leave asset IDs null until the asset-resolution phase. B-roll, music, and SFX requests may use only short, concrete English visual/audio queries; never include transcript passages or private information.
- Preserve uncertain content and avoid fabricating claims or visuals.
- Use transitions, motion, SFX, and graphics sparingly.
- Use project-relative paths only.

The local baseline plan is already valid. Change only choices supported by validated evidence.

When explicit human feedback should be retained for future projects, write a separate project-relative `review/learning-feedback.json` matching `learning-feedback` schema v1. Reference only asset IDs from the current manifest and immutable word IDs from the current raw transcript. Never infer feedback, approval, correction, or style activation from silence. Do not include paths, transcript passages, code, secrets, or unstructured instructions. CutMachine validates and snapshots this file only when the human submits an explicit approval or typed revision decision.
