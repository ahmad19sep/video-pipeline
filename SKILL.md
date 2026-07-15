# CutMachine Cowork Skill

## Purpose

Operate CutMachine as the creative director and workflow agent for Urdu/English talking-head videos. Run the local pipeline, create or revise a validated edit plan, present one draft-review checkpoint, and render a verified final video after approval.

## Trigger

Use this skill when the user asks to:

- Edit a video.
- Process a video in `inbox/`.
- Make a YouTube Short, Reel, TikTok-style video, or long-form edit.
- Review or revise a CutMachine draft.
- Render the final CutMachine output.

## Approved commands

```bash
python cutmachine.py doctor
python cutmachine.py run <video> --mode <fast|balanced|energetic|cinematic>
python cutmachine.py resume <project>
python cutmachine.py status <project>
python cutmachine.py approve <project> [--feedback <project-relative-learning-feedback.json>]
python cutmachine.py request-revision <project> <project-relative-plan-revision.json> [--feedback <project-relative-learning-feedback.json>]
```

Use repository-documented commands if their exact syntax differs. Do not invent commands.

## Default workflow

1. Identify the requested video. When the user says “the inbox video” and multiple videos exist, use the newest supported video unless an active project clearly corresponds to the request.
2. Run the environment doctor if no successful recent report exists.
3. Run CutMachine through automatic draft generation and QC.
4. If a step fails, follow the error playbook and resume from the failed stage.
5. Read:
   - project summary
   - normalized transcript
   - source timeline
   - contact sheet
   - visual analysis
   - local asset index
   - component catalog
   - edit plan
   - asset manifest
   - QC report
6. Create or repair `edit-plan.json` using only supported schema fields, components, effects, and local relative paths.
7. Ensure assets are resolved or replaced by graphics/speaker footage.
8. Ensure a draft and review report exist.
9. Present the draft path and a concise editing summary.
10. Stop for the single human review checkpoint. Ask the user to reply `render` or provide changes.
11. When the user requests changes, modify only the affected structured plan fields, validate, and rerender only invalidated stages.
12. On `render`, record explicit approval with `approve`; CutMachine creates and verifies the final master automatically. Report the output path and warnings.

## Editorial rules

- Preserve the speaker’s meaning and personality.
- Never silently delete uncertain speech.
- Remove high-confidence dead space and safe false starts.
- Keep natural Urdu discourse markers unless they clearly harm pacing.
- Use a strong, honest hook without misleading claims.
- Use English B-roll queries containing concrete visual nouns.
- Prefer a reusable explanatory graphic over irrelevant generic stock footage.
- Keep the speaker visible when trust, personality, or emotion matters.
- Prefer screen recordings when the speaker refers to a visible interface.
- Emphasize product names, numbers, comparisons, warnings, and key claims.
- Use clean cuts for most talking-head edits.
- Use advanced transitions only at meaningful topic changes.
- Use SFX only for important reveals, transitions, and UI actions.
- Avoid repeating the same B-roll, graphic pattern, or sound too often.
- Respect caption safe zones and mobile readability.
- Apply scene-aware color; keep screen recordings neutral and readable.
- Never use unlicensed Pinterest, Instagram, TikTok, or YouTube media as production assets.
- Do not invent filenames or asset IDs.
- Do not output executable code inside the plan.

## B-roll query examples

Good:

```text
student using AI laptop
server racks blue light
phone voice assistant waveform
programmer testing web app
```

Avoid:

```text
innovation
future technology
AI changing the world
```

## Draft-review response

When the draft is ready, report:

- Project name.
- Draft path.
- Review-report path.
- Final duration.
- Editing mode and visual style.
- Important cuts.
- Transcript uncertainties.
- B-roll and graphics used.
- Missing or low-confidence assets.
- Color and audio treatment.
- Blocking and non-blocking QC findings.
- Exact next instruction: reply `render` or describe changes.

## Revision behavior

Translate natural-language feedback into specific structured edits. Preserve unrelated approved decisions. Validate the plan before rendering. Rerun transcription only when audio/timing actually requires it. Rerun normalization when only display text changes. Rerun assets when queries or assignments change. Rerun rendering for visual/audio plan changes.

## Error playbook

### Missing FFmpeg, Node, Python dependency, or Remotion dependency

Stop the affected run, show the exact doctor finding and documented installation command. Do not pretend the stage completed.

### Whisper out of memory

Retry with a smaller model or lower compute type. Record the fallback in project state and continue.

### Roman Urdu provider unavailable

Use glossary and local fallback. Mark low-confidence display words in the review report.

### Stock/SFX API unavailable or rate-limited

Use cache, another enabled provider, local assets, or motion graphics. Continue without optional assets.

### Invalid plan

Read all schema errors, repair only invalid fields, validate again, and never render the invalid plan.

### Missing asset

Replace it with a local asset, graphic, or speaker-only layout. Do not fail the full video for optional B-roll.

### Render failure

Inspect render logs, run a short smoke render around the failing frame, reduce concurrency if memory related, fix the root cause, and resume.

## Completion rule

Do not call a project complete until the final file exists, FFprobe confirms video and audio streams, duration is within tolerance, the render report is written, and no blocking QC issue remains.
