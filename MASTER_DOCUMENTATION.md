# CutMachine v2.0
## Master Product, Architecture, Automation, and Implementation Documentation

**Project:** Cowork-driven, local-first AI video editor for Urdu/Roman Urdu creators  
**Primary user:** Ahmad - AI educator and short-form/long-form content creator  
**Target environment:** Windows 11 with WSL2 or Linux, Python 3.11+, Node.js 20+  
**Primary output:** Professionally edited 9:16 and 16:9 MP4 videos  
**Operating-cost target:** Near zero; local processing first, free APIs optional  
**Human involvement target:** One review checkpoint after an automatically rendered draft  
**Document status:** Authoritative build and operating specification  

---

# 1. Executive Summary

CutMachine is a local, folder-based, AI-assisted video editing system designed for a creator who speaks Urdu mixed with English technical terminology. It converts raw talking-head footage into a polished video with synchronized Roman Urdu captions, intelligent cuts, B-roll, motion graphics, sound effects, audio mastering, optional color grading, and final rendering.

The system is not intended to reproduce every feature of Premiere Pro, DaVinci Resolve, CapCut, or OpenCut. Its purpose is narrower and more practical: automate the repetitive editing style Ahmad uses every week while preserving human creative control at one meaningful checkpoint.

The central design principle is:

> AI plans the edit; deterministic software executes and validates it.

Claude Cowork is the creative director and workflow operator. Python and FFmpeg handle media analysis and preprocessing. Remotion handles timeline composition, captions, motion graphics, B-roll, transitions, and rendering. Optional local computer-vision models handle face tracking, reframing, and visual analysis. Optional free APIs supply stock footage and sound effects when local assets are insufficient.

The default automated journey is:

```text
Raw video placed in inbox
-> environment and media validation
-> proxy and audio preparation
-> local Urdu transcription with word timestamps
-> Roman Urdu normalization and English-term correction
-> silence, repetition, and mistake analysis
-> source timeline generation
-> Cowork creates a structured creative edit plan
-> local/free asset retrieval and relevance ranking
-> technical audio and color correction
-> Remotion draft render
-> automated quality-control report
-> one human review checkpoint
-> requested revisions, if any
-> final master render and delivery package
```

A user should normally interact with the system through one command or one Cowork instruction, not by manually running every internal script.

---

# 2. Baseline Assessment and Required Expansion

The original CutMachine build specification establishes a strong MVP foundation:

- Local Faster-Whisper transcription.
- Roman Urdu conversion.
- A shared `edit-plan.json` contract.
- Free stock-media and SFX providers.
- Remotion rendering.
- A Cowork skill that runs the process.
- One human review point.

However, a production-quality, mostly automated system also requires the following capabilities, which this document adds:

1. A single top-level orchestrator instead of a collection of disconnected commands.
2. A resumable project state machine.
3. Automatic retry, caching, and recovery from partial failures.
4. A draft render before the human review checkpoint.
5. Automated technical and editorial quality checks.
6. Confidence-based decisions for silence, fillers, repetitions, and transcript corrections.
7. Local asset indexing and relevance ranking before external search.
8. A graphics-first fallback when stock B-roll is irrelevant.
9. Advanced but controlled color, audio, reframing, and motion systems.
10. Separate fast, balanced, energetic, and cinematic editing modes.
11. Strong schema versioning, path security, and provenance tracking.
12. A repeatable learning loop based on accepted and rejected edits.
13. Support for both shorts and long-form videos.
14. A static review package so no full web application is required.
15. Clear operational, testing, troubleshooting, and maintenance documentation.

This master document supersedes any earlier requirement that conflicts with the goal of a safe, resumable, mostly automated workflow.

---

# 3. Product Vision

## 3.1 Primary outcome

Ahmad should be able to record a video, put it in the `inbox/` folder, ask Cowork to edit it, review one automatically generated draft, and receive a final export without manually operating a traditional editing timeline.

## 3.2 Content profiles

CutMachine must support these common content types:

- AI news and updates.
- Tool demonstrations.
- Educational explainers.
- Coding and automation tutorials.
- Productivity and personal-development videos.
- Talking-head shorts.
- Screen-recording-led tutorials.
- Long-form YouTube videos.

## 3.3 Success metrics

The project is successful when:

- At least 80 percent of repetitive editing work is automated.
- Normal videos need only one human review checkpoint.
- Roman Urdu captions remain synchronized after cuts.
- English product names and technical terms are preserved.
- The system produces a usable draft even when all external APIs are unavailable.
- Every edit is non-destructive and reproducible.
- Re-running the pipeline does not redo completed work unnecessarily.
- A failed step can resume without restarting the entire project.
- Final output passes automated media validation.
- The resulting style is consistent across videos.

## 3.4 Non-goals for the first stable release

Do not prioritize:

- A full free-form multi-track editing interface.
- Multi-user collaboration.
- Cloud rendering.
- Subscription billing.
- Mobile applications.
- Automatic publishing.
- AI voice cloning or TTS.
- Fully autonomous deletion of uncertain spoken content.
- Exact copying of Pinterest, Instagram, or YouTube designs.

---

# 4. Core Principles

## 4.1 Local first

Raw media, transcripts, edit plans, assets, and renders remain on the user’s machine by default.

## 4.2 Optional network use

External APIs are adapters, not foundational dependencies. The pipeline must still render a complete video with local captions, graphics, and assets when APIs are disabled.

## 4.3 Structured AI output

Cowork may choose creative direction, but it must write validated JSON. It must never inject arbitrary JavaScript, JSX, Python, CSS, or shell commands into the edit plan.

## 4.4 Deterministic rendering

The same source files, edit plan, configuration, and software versions should produce the same timeline and substantially identical output.

## 4.5 Non-destructive editing

The original media is immutable. Cuts are represented as source ranges. Color, audio, crop, and effects are represented as parameters.

## 4.6 Confidence-aware automation

High-confidence technical decisions can be automatic. Uncertain creative or destructive decisions must be retained, softened, or flagged for review.

## 4.7 Quality over effect density

World-class editing does not mean adding an effect to every sentence. It means strong pacing, clarity, sound, typography, relevant visuals, good color, and deliberate emphasis.

## 4.8 Graceful degradation

Missing API keys, unavailable assets, absent GPU support, or optional model failures should reduce enhancement quality, not prevent a base render.

---

# 5. User Experience

## 5.1 Normal one-command workflow

The primary command is:

```bash
python cutmachine.py run inbox/my-video.mp4 --mode balanced
```

Equivalent Cowork instruction:

```text
Edit the newest video in the inbox using CutMachine balanced mode.
```

The orchestrator performs all steps through draft generation. Cowork then presents:

- Draft video path.
- Review report path.
- Transcript warnings.
- Proposed destructive cuts.
- Missing or weak assets.
- Color and audio summary.
- Quality-control findings.

The user responds with either:

```text
render
```

or a natural-language change request such as:

```text
Remove the B-roll at 18 seconds, make captions smaller, keep my repeated sentence at 32 seconds, and use a cleaner color grade.
```

Cowork updates only the relevant structured plan fields, rerenders the draft if needed, and then produces the final output.

## 5.2 Manual involvement target

The normal manual checkpoint occurs after the draft is already rendered. This is better than asking the user to inspect raw JSON and downloaded files before seeing the result.

The user may optionally inspect or edit:

- `transcript.roman.json`
- `edit-plan.json`
- `review/index.html`
- `assets/`

But none of these should be required for a typical video.

## 5.3 Processing modes

### Fast

Use when speed matters more than maximum polish.

- Smaller transcription model.
- Conservative silence cuts.
- Local assets only unless essential.
- Basic captions.
- Minimal motion graphics.
- Neutral correction.
- Draft-quality render settings.

### Balanced

Default mode.

- Good transcription model chosen from hardware.
- Cowork creative plan.
- Local assets plus optional free API search.
- Word-highlight captions.
- Controlled B-roll and SFX.
- Face-aware crop when available.
- Conservative color and audio finishing.

### Energetic

Designed for high-retention short-form content.

- Faster visual rhythm.
- More text emphasis.
- More frequent but bounded visual changes.
- More B-roll and motion graphics.
- Stronger contrast and sound design.
- No excessive transitions.

### Cinematic

Designed for premium storytelling or long-form segments.

- Slower intentional pacing.
- Advanced scene-aware color grade.
- More atmospheric sound design.
- Smooth camera movement.
- Controlled film texture.
- Fewer, higher-quality visuals.

### Custom

Loads a user-defined style profile.

---

# 6. End-to-End Automated Pipeline

## Stage 0: Environment doctor

Before processing, verify:

- Python version.
- Node.js version.
- FFmpeg and FFprobe.
- Remotion dependencies.
- Python virtual environment.
- Faster-Whisper import.
- Available RAM and VRAM.
- GPU/CUDA availability.
- Disk space.
- Writable workspace.
- Optional API keys.
- Optional model availability.

Missing optional services produce warnings. Missing core tools stop the run with exact installation guidance.

## Stage 1: Project creation

For each video:

1. Create a unique slug.
2. Create a project workspace.
3. Copy the source into the workspace.
4. Calculate a file hash.
5. Write `project.json`.
6. Record source metadata.
7. Initialize processing state.

## Stage 2: Media ingest

Generate:

- `raw.mp4` or the original extension.
- `media-info.json`.
- `proxy.mp4`.
- `audio/source.wav`.
- `contact-sheet.jpg`.
- Representative frames.
- Optional waveform preview.

## Stage 3: Audio preparation

Apply only technical cleanup before transcription:

- Convert to mono 16 kHz WAV.
- Optional gentle denoising.
- High-pass filter for low rumble.
- Avoid aggressive processing that damages words.

Preserve the original extracted audio separately.

## Stage 4: Local transcription

Use Faster-Whisper with:

- Urdu language hint.
- Word-level timestamps.
- VAD.
- A technical glossary prompt.
- Hardware-aware model selection.
- Configurable beam and compute type.

Every word receives an immutable ID.

## Stage 5: Roman Urdu and technical-term normalization

Preferred order:

1. Preserve raw Urdu transcript.
2. Protect known English terms.
3. Apply local lexicon and deterministic replacements.
4. Optionally call a configured free-tier language model for natural Roman Urdu.
5. Validate identical word count and order.
6. Retry malformed batches.
7. Fall back to local conversion or original text.
8. Save confidence and transformation provenance.

Never merge or split timestamped words during transliteration.

## Stage 6: Editorial analysis

Detect:

- Long silence.
- Start/end dead space.
- False starts.
- Nearby repeated phrases.
- Filler candidates.
- Low-confidence transcript spans.
- Topic changes.
- Hook candidates.
- Product names, numbers, and power words.
- Screen-recording or visual-demo references.

Cowork combines transcript meaning with deterministic analysis to create a safe source timeline.

## Stage 7: Timeline generation

Create source-to-output ranges. The original video is never rewritten as the authoritative timeline.

Each cut has:

- Reason.
- Confidence.
- Decision source.
- Automatic/manual status.
- Padding.
- Reversible ID.

## Stage 8: Creative planning

Cowork creates `edit-plan.json` using:

- Transcript.
- Timeline.
- Contact sheet.
- Style profile.
- Local asset index.
- Component catalog.
- Editing rules.
- Platform and duration.

It plans:

- Scene purposes.
- Hook treatment.
- Captions and emphasis.
- B-roll.
- Motion graphics.
- Camera movement.
- Transitions.
- SFX and music.
- Color preset.
- Screen-recording layouts.
- CTA treatment.

## Stage 9: Asset resolution

Resolve assets in this order:

```text
Owned local asset
-> cached prior asset
-> generated Remotion graphic
-> free stock API
-> manually imported asset
-> omit the asset
```

Search results should be downloaded as candidates, not blindly trusted. Candidate ranking may use:

- Query match.
- Duration.
- Orientation.
- Resolution.
- Motion amount.
- Local OpenCLIP text-image similarity, when installed.
- Duplicate detection.
- Watermark or logo rejection.
- License compatibility.

## Stage 10: Technical preprocessing

Depending on the project and style:

- Silence-aware base video generation.
- Audio cleanup.
- Face-aware vertical reframe.
- Stabilization.
- Exposure and white-balance correction.
- Scene-aware denoising.
- Screen-recording preservation.
- Loudness normalization.

## Stage 11: Draft render

Render a draft at lower cost, for example:

- 540x960 for vertical.
- Faster encoding preset.
- Lower bitrate.
- Same timeline and effects.

This draft should accurately represent timing and design, even if final encoding quality is lower.

## Stage 12: Automated QC

Before showing the draft, test:

- Video and audio streams exist.
- Duration matches calculated timeline.
- Captions remain in safe zones.
- No caption groups exceed layout limits.
- No missing mandatory assets.
- No overlay is outside its scene.
- Audio peaks are bounded.
- Voice is not masked by music or SFX.
- Black frames are not introduced unintentionally.
- Freeze frames are intentional.
- B-roll is not stretched beyond acceptable limits.
- File is decodable by FFprobe.

## Stage 13: Human review

Cowork presents a concise review summary and the draft path. This is the only required human checkpoint.

## Stage 14: Final render

After approval:

- Render full resolution.
- Apply final audio mastering.
- Apply final color transform.
- Verify output.
- Generate subtitles.
- Generate thumbnail frame candidates.
- Generate a render report.

---

# 7. System Architecture

## 7.1 High-level components

```text
Claude Cowork
  - workflow operator
  - editorial reasoning
  - edit-plan authoring
  - revision handling

Python Orchestrator
  - state machine
  - retries and caching
  - command execution
  - project lifecycle
  - report generation

Python Media Workers
  - transcription
  - timeline analysis
  - Roman Urdu processing
  - asset retrieval
  - visual analysis

FFmpeg / FFprobe
  - ingest
  - proxy
  - audio extraction
  - cuts
  - crop/reframe preprocessing
  - color and audio finishing
  - output validation

Remotion
  - captions
  - motion graphics
  - scene composition
  - B-roll
  - transitions
  - SFX and music placement
  - draft and final rendering

Optional Local Models
  - OpenCLIP asset ranking
  - MediaPipe face tracking
  - Ollama planning fallback
  - segmentation/background isolation

Optional Free APIs
  - stock footage/images
  - sound effects
  - Roman Urdu refinement
```

## 7.2 Boundaries

Python and Remotion communicate only through versioned JSON and files on disk.

Cowork communicates with the system through:

- Approved CLI commands.
- Project files.
- Validated JSON.

External APIs never receive the raw video or entire private transcript. Stock providers receive only short visual search queries.

---

# 8. Recommended Repository Structure

```text
cutmachine/
├── README.md
├── MASTER_DOCUMENTATION.md
├── BUILD_SPEC.md
├── AGENTS.md
├── CLAUDE.md
├── SKILL.md
├── DECISIONS.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── cutmachine.py
│
├── config/
│   ├── defaults.yaml
│   ├── styles/
│   │   ├── fast.yaml
│   │   ├── balanced.yaml
│   │   ├── energetic.yaml
│   │   └── cinematic.yaml
│   ├── technical-glossary.json
│   ├── roman-urdu-lexicon.json
│   ├── filler-words.json
│   └── component-catalog.json
│
├── inbox/
├── output/
├── workspace/
│   ├── .cache/
│   └── {video-slug}/
│       ├── project.json
│       ├── state.json
│       ├── logs/
│       ├── input/
│       │   └── raw.mp4
│       ├── media/
│       │   ├── proxy.mp4
│       │   ├── base.mp4
│       │   ├── color-master.mp4
│       │   └── frames/
│       ├── audio/
│       │   ├── source.wav
│       │   ├── cleaned.wav
│       │   └── mastered.wav
│       ├── transcript/
│       │   ├── transcript.raw.json
│       │   ├── transcript.roman.json
│       │   ├── transcript.remapped.json
│       │   └── captions.srt
│       ├── analysis/
│       │   ├── media-info.json
│       │   ├── contact-sheet.jpg
│       │   ├── silence-candidates.json
│       │   ├── repetition-candidates.json
│       │   ├── visual-analysis.json
│       │   └── qc-analysis.json
│       ├── timeline/
│       │   ├── source-timeline.json
│       │   └── time-map.json
│       ├── planning/
│       │   ├── edit-plan.json
│       │   ├── asset-requests.json
│       │   └── editor-notes.md
│       ├── assets/
│       │   ├── broll/
│       │   ├── sfx/
│       │   ├── music/
│       │   ├── images/
│       │   ├── luts/
│       │   └── manifest.json
│       ├── review/
│       │   ├── draft.mp4
│       │   ├── index.html
│       │   └── summary.json
│       └── renders/
│           ├── final.mp4
│           ├── final.srt
│           └── render-report.json
│
├── scripts/
│   ├── doctor.py
│   ├── ingest.py
│   ├── transcribe.py
│   ├── normalize_transcript.py
│   ├── analyze_timeline.py
│   ├── preprocess.py
│   ├── analyze_visuals.py
│   ├── fetch_assets.py
│   ├── rank_assets.py
│   ├── build_review.py
│   ├── quality_check.py
│   ├── finalize.py
│   └── utils/
│
├── schemas/
│   ├── project.schema.json
│   ├── transcript.schema.json
│   ├── timeline.schema.json
│   ├── edit-plan.schema.json
│   ├── asset-manifest.schema.json
│   └── render-report.schema.json
│
├── remotion/
│   ├── package.json
│   ├── remotion.config.ts
│   ├── public/
│   └── src/
│       ├── Root.tsx
│       ├── compositions/
│       │   ├── ShortVideo.tsx
│       │   └── LongVideo.tsx
│       ├── engine/
│       ├── components/
│       │   ├── captions/
│       │   ├── graphics/
│       │   ├── broll/
│       │   ├── layouts/
│       │   ├── camera/
│       │   ├── transitions/
│       │   ├── audio/
│       │   └── branding/
│       └── styles/
│
├── assets-library/
│   ├── broll/
│   ├── sfx/
│   ├── music/
│   ├── images/
│   ├── logos/
│   ├── luts/
│   ├── references/
│   └── index.json
│
├── prompts/
│   ├── cowork-editor.md
│   ├── transcript-normalizer.md
│   ├── edit-plan-reviser.md
│   └── qc-reviewer.md
│
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── render/
│   └── end-to-end/
│
└── docs/
    ├── installation-windows.md
    ├── architecture.md
    ├── workflow.md
    ├── schemas.md
    ├── style-system.md
    ├── operations-runbook.md
    ├── troubleshooting.md
    └── roadmap.md
```

---

# 9. Project State Machine

The orchestrator must track progress in `state.json`.

## 9.1 States

```text
created
validated
ingested
transcribed
normalized
analyzed
timeline_ready
plan_ready
assets_ready
preprocessed
draft_rendered
qc_passed
awaiting_review
revision_requested
approved
final_rendered
completed
failed
cancelled
```

## 9.2 State rules

- A state advances only after outputs are validated.
- A failed state records the failed step and error.
- `--resume` continues from the last valid state.
- `--from <stage>` intentionally invalidates downstream outputs.
- Changes to the transcript invalidate timeline, plan, draft, and final render.
- Changes only to SFX invalidate draft and final render, not transcription.
- A source file hash change creates a new project or requires explicit reset.

## 9.3 Example commands

```bash
python cutmachine.py run inbox/video.mp4 --mode balanced
python cutmachine.py resume workspace/video-slug
python cutmachine.py status workspace/video-slug
python cutmachine.py rerun workspace/video-slug --from assets
python cutmachine.py render workspace/video-slug --quality final
python cutmachine.py clean workspace/video-slug --keep-final
```

---

# 10. Data Contracts

## 10.1 Project file

`project.json` records identity and configuration.

```json
{
  "version": 1,
  "projectId": "prj_20260714_ai_news_a13f",
  "slug": "ai-news-2026-07-14",
  "createdAt": "2026-07-14T22:00:00+05:00",
  "sourceHash": "sha256:...",
  "videoType": "short",
  "platform": "youtube-shorts",
  "mode": "balanced",
  "language": "ur",
  "captionLanguage": "roman-urdu",
  "resolution": {"width": 1080, "height": 1920},
  "fps": 30,
  "styleProfile": "modern-ai",
  "networkEnabled": true
}
```

## 10.2 Transcript word

```json
{
  "id": "word_000042",
  "segmentId": "transcript_seg_004",
  "start": 12.44,
  "end": 12.93,
  "raw": "چیٹ جی پی ٹی",
  "display": "ChatGPT",
  "language": "ur",
  "confidence": 0.96,
  "source": "faster-whisper",
  "normalizationSource": "technical-glossary",
  "lockedTiming": true
}
```

## 10.3 Source timeline

```json
{
  "version": 1,
  "projectId": "prj_20260714_ai_news_a13f",
  "segments": [
    {
      "id": "keep_001",
      "sourceStart": 0.32,
      "sourceEnd": 6.84,
      "outputStart": 0,
      "outputEnd": 6.52,
      "reason": "speech",
      "decision": "keep"
    }
  ],
  "cuts": [
    {
      "id": "cut_001",
      "sourceStart": 6.84,
      "sourceEnd": 8.12,
      "type": "long_silence",
      "confidence": 0.98,
      "decision": "remove",
      "decidedBy": "automatic-rule"
    }
  ]
}
```

## 10.4 Edit plan v2

The edit plan is the main creative contract.

```json
{
  "version": 2,
  "projectId": "prj_20260714_ai_news_a13f",
  "timelineVersion": 1,
  "style": {
    "preset": "modern-ai",
    "intensity": "balanced",
    "captionPreset": "roman-word-highlight",
    "transitionDensity": "low",
    "visualChangeTargetSeconds": 4.5
  },
  "video": {
    "source": "media/base.mp4",
    "fps": 30,
    "width": 1080,
    "height": 1920,
    "durationInSeconds": 58.4
  },
  "captions": {
    "language": "roman-urdu",
    "safeZone": "shorts-default",
    "maxLines": 2,
    "wordsPerPage": {"min": 2, "max": 5},
    "words": []
  },
  "globalAudio": {
    "voiceGainDb": 0,
    "musicAssetId": null,
    "musicGainDb": -24,
    "duckingEnabled": true,
    "targetLufs": -14,
    "truePeakDb": -1
  },
  "globalColor": {
    "enabled": true,
    "preset": "natural-clean",
    "intensity": 0.65,
    "lutAssetId": null
  },
  "scenes": [
    {
      "id": "scene_001",
      "start": 0,
      "end": 5.8,
      "purpose": "hook",
      "sourceTimelineIds": ["keep_001"],
      "layout": "speaker-fullscreen",
      "camera": {
        "mode": "punch-in",
        "scaleStart": 1,
        "scaleEnd": 1.1,
        "focus": "face"
      },
      "colorOverride": null,
      "broll": {
        "mode": "none",
        "assetId": null,
        "query": null,
        "effect": "static",
        "fit": "cover"
      },
      "graphics": [
        {
          "id": "graphic_001",
          "component": "HookTitle",
          "startOffset": 0.15,
          "endOffset": 2.2,
          "props": {
            "text": "AI editing ab automate ho sakti hai",
            "emphasis": ["AI", "automate"]
          }
        }
      ],
      "sfx": [
        {
          "assetId": "sfx_impact_soft_01",
          "offset": 0.15,
          "gainDb": -12
        }
      ],
      "transitionOut": {
        "type": "clean-cut",
        "durationFrames": 0
      }
    }
  ],
  "provenance": {
    "createdBy": "claude-cowork",
    "createdAt": "2026-07-14T22:10:00+05:00",
    "componentCatalogVersion": 1
  }
}
```

## 10.5 Security rules for plans

The plan must not contain:

- Absolute paths.
- `..` path traversal.
- Executable code.
- Shell commands.
- Remote script URLs.
- Unknown component names.
- Unknown effect names.
- Unvalidated component props.

## 10.6 Asset manifest

Every external asset must record:

- Local asset ID.
- Local path.
- Type.
- Search query.
- Source provider.
- Creator.
- License.
- Attribution requirement.
- Source page identifier.
- Download time.
- File hash.
- Duration and dimensions.
- Selected scene.
- Relevance score.

## 10.7 Render report

The final report includes:

- Project and plan versions.
- Software versions.
- Render start/end.
- Resolution, FPS, codec, duration, and size.
- Audio loudness result.
- Missing optional assets.
- QC warnings.
- Source and plan hashes.

---

# 11. Transcription and Roman Urdu Strategy

## 11.1 Spoken-language reality

The creator speaks Urdu, often mixed with English product names and technical phrases. Roman Urdu is primarily the desired caption representation, not necessarily the acoustic language presented to the speech model.

## 11.2 Hardware-aware model selection

The doctor command should select a model based on available memory and configuration. Do not hardcode one model as universally correct.

Suggested policy:

- High-memory GPU: quality model.
- Moderate GPU: balanced model.
- CPU with sufficient RAM: medium/small quantized model.
- Low-memory machine: fast model plus later correction.

The chosen model and compute type must be logged.

## 11.3 Technical glossary

Maintain a user-editable glossary containing:

- Product names.
- Company names.
- Model names.
- Programming languages.
- Frameworks.
- Common AI terminology.
- Ahmad’s frequently used phrases.

Use it in transcription prompts and post-processing.

## 11.4 Roman Urdu conversion contract

For each input word, the converter must return exactly one output word object with the same ID and timestamps.

Allowed:

- Change display spelling.
- Preserve English word.
- Add punctuation metadata.

Not allowed:

- Merge words.
- Split a word into multiple timed tokens.
- Reorder words.
- Change timestamps.
- Delete a word silently.

## 11.5 Confidence and correction

Low-confidence words should be highlighted in the review report. Cowork may correct obvious technical terms. Uncertain semantic words should remain conservative rather than being confidently rewritten.

## 11.6 Learning dictionary

When the user corrects a word, store a reusable mapping with context:

```json
{
  "heard": "ریموسن",
  "preferred": "Remotion",
  "context": ["video", "editing", "React"],
  "approvedAt": "2026-07-14"
}
```

Future runs should prefer approved mappings.

---

# 12. Cut and Pacing Automation

## 12.1 Silence detection

Use a combination of:

- Word gaps.
- VAD output.
- FFmpeg silence detection.
- Configurable padding.

Do not rely on a single dB threshold.

## 12.2 Automatic cut policy

Automatically remove only:

- Leading/trailing dead space above threshold.
- Long silence with no overlapping word timing.
- Very high-confidence non-speech spans.

## 12.3 Repetition policy

A repeated phrase may be removed automatically only when:

- Text similarity is very high.
- It occurs within a short window.
- The second attempt is more complete.
- Audio timing suggests a restart.
- Cowork agrees that meaning is preserved.

Otherwise, flag it for review and keep it in the draft.

## 12.4 Filler policy

Words such as “acha,” “matlab,” “to,” or “basically” may be natural discourse markers. Do not delete them solely because they appear in a filler list.

## 12.5 Pacing targets

The style profile defines:

- Maximum silence.
- Minimum shot duration.
- Visual-change target.
- Maximum consecutive speaker-only duration.
- Zoom cooldown.
- Transition density.

Pacing is a target, not a command to cut unnaturally.

---

# 13. Cowork Creative Planning

## 13.1 Cowork role

Cowork acts as:

- Editorial director.
- Story and retention analyst.
- Visual planner.
- Asset-query writer.
- Motion-graphics selector.
- Sound-design planner.
- Revision agent.

It is not the renderer.

## 13.2 Required inputs

Cowork reads:

- Project summary.
- Transcript.
- Timeline.
- Contact sheet.
- Visual-analysis results.
- Style profile.
- Component catalog.
- Asset index.
- Editing rules.

## 13.3 Editorial logic

For each scene, Cowork should determine:

- What the viewer must understand.
- Whether the speaker’s face should remain visible.
- Whether a screen demonstration is more useful than stock footage.
- Whether a motion graphic can explain the concept better.
- Which words deserve emphasis.
- Whether an SFX adds clarity or only noise.
- Whether a transition marks a meaningful topic change.

## 13.4 Hook rules

The first seconds should:

- State or visually imply the payoff.
- Avoid long logos or introductions.
- Use one strong title treatment.
- Preserve a natural opening sentence when strong.
- Avoid misleading claims.

## 13.5 B-roll query rules

Queries must be:

- English.
- Concrete.
- Visual.
- Short.
- Free from abstract wording.

Good:

```text
student using AI laptop
server racks blue light
phone voice assistant waveform
programmer testing web app
```

Weak:

```text
innovation
future technology
AI is changing life
```

## 13.6 Graphics-first rule

When stock footage would be generic or irrelevant, prefer a reusable graphic:

- Comparison card.
- Step card.
- Tool logo row.
- Browser frame.
- Timeline.
- Stat card.
- Definition card.
- Diagram.

## 13.7 Effect budgets

Each style profile defines maximum budgets, such as:

- Whip transitions per minute.
- Impact SFX per minute.
- Fullscreen B-roll percentage.
- Punch-in zoom frequency.
- Animated text density.

These limits prevent AI over-editing.

---

# 14. Asset System

## 14.1 Local library first

Build a curated local library for frequently used topics:

- AI and technology.
- Coding.
- Students and education.
- Productivity.
- Social media.
- Mobile applications.
- Business automation.
- Abstract backgrounds.
- UI sounds.
- Whooshes and impacts.

## 14.2 Indexing

The asset indexer extracts:

- File metadata.
- Duration.
- Dimensions.
- Orientation.
- Thumbnail.
- Audio waveform for SFX.
- Tags.
- License.
- Usage history.

## 14.3 Optional free API adapters

Adapters may include providers for:

- Stock video and images.
- Sound effects.
- Roman Urdu text refinement.

All provider limits, models, and terms must be configurable and verified during setup rather than assumed permanently.

## 14.4 Privacy

Only visual search phrases are sent to stock APIs. Do not send the entire transcript or raw video.

## 14.5 Ranking

Download or inspect several candidates when possible. Rank them by:

- Semantic relevance.
- Orientation.
- Duration.
- Resolution.
- Visual quality.
- Motion suitability.
- Absence of watermarks.
- Prior reuse frequency.

## 14.6 Failure behavior

If no relevant B-roll is available:

1. Use a motion graphic.
2. Keep the speaker visible.
3. Use a subtle camera move.
4. Mark the request as missing.

Never fail the render solely because optional B-roll is unavailable.

## 14.7 Pinterest and social references

Pinterest, Instagram, and YouTube screenshots may be stored in `assets-library/references/` for visual inspiration. Do not download and publish their media as production assets unless usage rights are confirmed.

---

# 15. Remotion Editing and Design System

## 15.1 Responsibility

Remotion handles composition and visual presentation, including:

- Speaker video.
- Captions.
- B-roll.
- Motion graphics.
- Layouts.
- Digital camera moves.
- Transitions.
- SFX and music placement.

## 15.2 Required caption components

- `RomanWordHighlightCaption`
- `CleanTwoLineCaption`
- `HookCaption`
- `DefinitionCaption`
- `QuestionCaption`
- `UrduScriptCaption`

## 15.3 Caption behavior

Captions must:

- Remain synchronized to remapped timestamps.
- Support Roman Urdu and Urdu script.
- Preserve English technical terms.
- Avoid more than two lines by default.
- Avoid platform UI zones.
- Scale within safe limits.
- Highlight active words smoothly.
- Use readable stroke or shadow.
- Support punctuation without timing corruption.

## 15.4 Required graphic components

- `HookTitle`
- `DefinitionCard`
- `StepCard`
- `ComparisonCard`
- `ToolLogoRow`
- `BrowserWindow`
- `MobileScreenFrame`
- `QuoteCard`
- `StatisticCard`
- `WarningCard`
- `QuestionCard`
- `TimelineGraphic`
- `FeatureList`
- `ProgressIndicator`
- `LowerThird`
- `PictureInPicture`
- `FullscreenBroll`
- `SplitScreen`
- `EndCallToAction`

## 15.5 Layout rules

- Keep important text within mobile safe zones.
- Do not cover the speaker’s face without purpose.
- Use screen recordings at readable size.
- Use high contrast.
- Do not place captions over dense on-screen text.
- Keep styles consistent within a video.

## 15.6 Camera moves

Supported modes:

- Static.
- Punch-in.
- Slow zoom.
- Reframe left.
- Reframe right.
- Return to wide.
- Face-follow.

Default maximum digital zoom is conservative. Every movement needs a reason.

## 15.7 Transitions

Initial set:

- Clean cut.
- Crossfade.
- Directional slide.
- Blur transition.
- Zoom transition.
- Mask reveal.

Most talking-head edits use clean cuts.

## 15.8 Reusable design tokens

Store in one style module:

- Typography.
- Font sizes.
- Font weights.
- Spacing.
- Corner radius.
- Shadows.
- Accent colors.
- Animation timing.
- Caption placement.
- Safe zones.

Do not scatter values across components.

---

# 16. Advanced Editing

## 16.1 Face-aware reframing

Optional MediaPipe-based tracking should:

- Find the primary face.
- Smooth landmark movement.
- Preserve headroom.
- Leave space for text.
- Avoid rapid crop motion.
- Fall back to center crop.

## 16.2 Stabilization

Use optional FFmpeg-supported or OpenCV stabilization. Report expected crop and do not apply when it causes excessive zoom.

## 16.3 Speed changes

Allowed uses:

- Slight speed-up during non-critical pauses.
- Screen-recording acceleration.
- Deliberate slow-down for emphasis.
- Freeze frame for a labeled visual point.

Never change the speaker’s voice unnaturally without explicit approval.

## 16.4 Background and subject effects

Future optional capabilities:

- Background blur.
- Background replacement.
- Subject isolation.
- Text behind subject.
- Depth transitions.

These are not required for the first stable release.

## 16.5 Screen-recording treatment

Support:

- Cursor highlight.
- Click ripple.
- Zoom into interface regions.
- Browser or phone framing.
- Step labels.
- Blur sensitive information.
- Keep UI text readable.

---

# 17. Color Pipeline

## 17.1 Processing order

```text
source
-> scene classification
-> optional denoise
-> exposure and white-balance correction
-> tonal correction
-> skin-aware protection
-> creative grade or LUT
-> sharpening
-> optional vignette/grain
-> final color conversion
```

## 17.2 Technical correction

Analyze representative frames for:

- Luma percentiles.
- Clipped highlights.
- Crushed shadows.
- Strong color cast.
- Saturation extremes.
- Face exposure, when a face is detected.

Use bounded adjustments. The system must not aggressively “fix” footage based on uncertain analysis.

## 17.3 Scene classification

Apply different logic to:

- Talking-head footage.
- Screen recordings.
- Mobile screenshots.
- Stock footage.
- Outdoor scenes.
- Low-light scenes.

Screen recordings should normally remain neutral and should not receive a cinematic LUT.

## 17.4 Presets

Initial presets:

- `off`
- `natural-clean`
- `modern-ai`
- `soft-professional`
- `high-contrast-social`
- `cinematic-warm`
- `cinematic-cool`
- `documentary`
- `low-light-recovery`

## 17.5 LUT support

Support licensed local `.cube` LUT files with:

- Declared color space.
- Adjustable intensity.
- Preview.
- License metadata.

Never apply full-strength LUT by default.

## 17.6 Before/after review

The review report should include representative before/after frame comparisons when grading is enabled.

---

# 18. Audio Pipeline

## 18.1 Voice priority

Speech intelligibility is more important than music or SFX.

## 18.2 Processing chain

Suggested chain:

- Noise reduction when needed.
- High-pass filter.
- Gentle EQ.
- Compression.
- De-essing if available and required.
- Loudness normalization.
- True-peak limiting.

## 18.3 Music

Music is optional. When used:

- Keep it low under speech.
- Duck automatically.
- Fade at scene boundaries.
- Avoid copyright-uncertain tracks.
- Record license and source.

## 18.4 SFX

Use SFX for:

- Important reveals.
- Meaningful transitions.
- UI interactions.
- Title entry.

Do not add an SFX to every text animation.

## 18.5 Audio QC

Check:

- Integrated loudness.
- True peak.
- Long silent output spans.
- Clipping.
- Missing voice.
- Music masking speech.
- SFX that are too loud.

---

# 19. Static Review Package

A full web application is not required. Generate `review/index.html` containing:

- Embedded or linked draft video.
- Scene list.
- Transcript warnings.
- Proposed uncertain cuts.
- Asset thumbnails and sources.
- Missing assets.
- Color before/after images.
- Audio summary.
- QC findings.
- Final recommended action.

The report is read-only. Revisions are communicated naturally to Cowork, which edits structured files.

---

# 20. Automation and Decision Matrix

| Task | Default automation | Human review condition |
|---|---|---|
| Environment validation | Full | Core dependency missing |
| Audio extraction | Full | Failure only |
| Transcription | Full | Low-confidence critical terms |
| Roman Urdu conversion | Full | Ambiguous words shown in report |
| Leading/trailing dead space | Full | None when confidence high |
| Long silence | Full | Borderline durations |
| Repeated sentence removal | Conditional | Review when uncertain |
| Filler removal | Conservative | Usually retained |
| Scene segmentation | Full | User may revise |
| Hook treatment | Cowork automatic | User sees draft |
| B-roll search | Full | Missing or weak relevance |
| B-roll selection | Automatic ranking | User sees draft |
| Motion graphics | Full from templates | User sees draft |
| SFX | Full with density limits | User sees draft |
| Color correction | Full conservative | Before/after shown |
| Creative LUT | Optional | User sees draft |
| Audio mastering | Full | QC failure |
| Draft render | Full | None |
| Final render | After approval | Required approval |

---

# 21. Configuration

Use layered configuration:

1. Hard safety limits.
2. Repository defaults.
3. Style profile.
4. `.env` values.
5. Project settings.
6. CLI overrides.

Example `defaults.yaml`:

```yaml
transcription:
  language: ur
  word_timestamps: true
  vad: true
  preset: balanced

silence:
  threshold_db: -35
  minimum_seconds: 0.55
  auto_remove_seconds: 1.35
  padding_before: 0.13
  padding_after: 0.20

captions:
  language: roman-urdu
  preset: roman-word-highlight
  max_lines: 2
  min_words_per_page: 2
  max_words_per_page: 5

render:
  fps: 30
  draft_width: 540
  draft_height: 960
  final_width: 1080
  final_height: 1920

network:
  enabled: true
  cache_days: 30

quality:
  target_lufs: -14
  true_peak_db: -1
```

---

# 22. Command-Line Interface

## 22.1 Main commands

```bash
python cutmachine.py doctor
python cutmachine.py run <video> [--mode fast|balanced|energetic|cinematic]
python cutmachine.py resume <project>
python cutmachine.py status <project>
python cutmachine.py review <project>
python cutmachine.py revise <project> --plan <file>
python cutmachine.py render <project> --quality draft|final
python cutmachine.py verify <project>
```

## 22.2 Internal commands

```bash
python scripts/ingest.py <video>
python scripts/transcribe.py <project>
python scripts/normalize_transcript.py <project>
python scripts/analyze_timeline.py <project>
python scripts/preprocess.py <project>
python scripts/fetch_assets.py <project>
python scripts/rank_assets.py <project>
python scripts/build_review.py <project>
python scripts/quality_check.py <project>
```

All commands must provide `--help`, timestamped logging, and non-zero exit status on failure.

---

# 23. Cowork Skill Specification

## 23.1 Trigger

Activate when the user asks to:

- Edit a video.
- Process the inbox video.
- Make a short or reel.
- Render a CutMachine project.
- Change a draft.

## 23.2 Default workflow

1. Run doctor if the current environment has not been checked.
2. Identify the requested or newest inbox video.
3. Run the orchestrator through draft and QC.
4. Read project summary, plan, and QC output.
5. Present draft and review summary.
6. Stop for approval or change request.
7. On changes, edit only valid structured fields and rerender affected stages.
8. On approval, run final render and verify.
9. Report final output and warnings.

## 23.3 Cowork editorial rules

- Preserve meaning.
- Never remove uncertain speech silently.
- Use a strong but honest hook.
- Prefer relevant graphics over generic stock footage.
- Keep B-roll queries concrete and visual.
- Avoid repeated use of the same asset.
- Keep transitions sparse.
- Keep captions readable.
- Keep the speaker visible when emotion or trust matters.
- Use SFX selectively.
- Use screen recordings when the speaker discusses a visible interface.
- Never invent filenames.
- Never reference unsupported components.

## 23.4 Revision behavior

When the user gives feedback:

- Translate feedback into exact plan changes.
- Preserve unrelated approved decisions.
- Validate the plan.
- Rerun only invalidated stages.
- Produce a new draft when the change is visual or timing-related.

---

# 24. Error Handling and Recovery

## 24.1 Whisper memory failure

- Retry with smaller model or lower compute type.
- Record fallback.
- Do not delete existing valid outputs.

## 24.2 API rate limit or failure

- Use cache.
- Back off.
- Try another configured provider.
- Use local assets or graphics.
- Continue the pipeline.

## 24.3 Invalid Cowork plan

- Show every schema error.
- Ask Cowork to repair the JSON.
- Never render invalid data.

## 24.4 Missing asset

- Replace with a graphic or speaker footage.
- Mark warning.
- Do not fail the full render.

## 24.5 Render failure

- Save logs.
- Run a five-second smoke render around the failing frame.
- Check missing files and invalid durations.
- Retry with lower concurrency if memory related.

## 24.6 Corrupt media

- Report FFprobe failure.
- Offer a normalization/transcode command.
- Preserve original.

## 24.7 Interrupted run

- Read `state.json`.
- Verify completed artifacts.
- Resume from the first incomplete stage.

---

# 25. Security and Privacy

- Keep the local server, if any, bound to localhost.
- Sanitize all filenames.
- Reject absolute imported paths.
- Resolve all paths inside allowed roots.
- Never evaluate imported code.
- Never execute commands from plans.
- Store API keys only in environment variables.
- Never commit `.env` or workspace media.
- Limit allowed media and asset extensions.
- Verify downloaded file MIME and media streams.
- Store source and license metadata.
- Do not upload raw media without explicit opt-in.

---

# 26. Testing Strategy

## 26.1 Unit tests

Test:

- Slug generation.
- Path safety.
- Transcript schema.
- Timestamp monotonicity.
- Roman Urdu word-count preservation.
- Silence merging.
- Source/output time mapping.
- Repetition similarity.
- Edit-plan validation.
- Asset resolution.
- Component prop validation.
- Render-duration calculation.

## 26.2 Integration tests

Test:

1. Ingest fixture video.
2. Extract audio.
3. Load or generate transcript.
4. Normalize transcript.
5. Detect cuts.
6. Generate timeline.
7. Import valid plan.
8. Reject invalid plan.
9. Resolve local assets.
10. Render a short draft.
11. Verify with FFprobe.

## 26.3 Visual regression tests

Capture frames for:

- Roman Urdu captions.
- Urdu-script captions.
- Hook title.
- Comparison card.
- B-roll overlay.
- Fullscreen B-roll.
- Browser frame.
- CTA.

Check overflow, clipping, missing fonts, and safe zones.

## 26.4 End-to-end acceptance test

A clean setup should process a demo project to a valid MP4 without any paid service.

---

# 27. Quality-Control Gates

A project cannot be marked complete unless:

- Plan validates.
- All source timeline ranges are valid.
- Word timestamps are monotonic.
- Caption timing maps correctly after cuts.
- Draft and final output are decodable.
- Output contains video and audio.
- Duration is within tolerance.
- No mandatory asset is missing.
- No captions are outside safe zones.
- Voice remains audible.
- Final report is written.

Warnings may be allowed for optional B-roll, external services, or low-confidence transcript words.

---

# 28. Implementation Roadmap

## Phase 0 - Repository and doctor

Deliver:

- Folder scaffold.
- Configuration system.
- Logging.
- Schemas.
- Environment doctor.
- Remotion scaffold.
- Tests.

## Phase 1 - Orchestrator and project state

Deliver:

- `cutmachine.py`.
- Project creation.
- State machine.
- Resume and invalidation logic.

## Phase 2 - Ingest and transcription

Deliver:

- Media metadata.
- Proxy.
- Contact sheet.
- Faster-Whisper integration.
- Hardware-aware model selection.

## Phase 3 - Transcript normalization

Deliver:

- Technical glossary.
- Roman Urdu conversion.
- Optional free API adapter.
- Local fallback.
- Confidence reporting.

## Phase 4 - Timeline automation

Deliver:

- Silence candidates.
- Repetition candidates.
- Safe cut policy.
- Source-to-output map.
- Caption remapping tests.

## Phase 5 - Cowork planning contract

Deliver:

- Component catalog.
- Edit-plan schema v2.
- Cowork prompt.
- Validation.
- Revision prompt.

## Phase 6 - Remotion MVP

Deliver:

- Speaker base.
- Captions.
- Hook title.
- B-roll overlay/fullscreen.
- Basic camera moves.
- SFX/music.
- Draft render.

## Phase 7 - Asset system

Deliver:

- Local index.
- Free provider adapters.
- Caching.
- Manifest and licensing.
- Candidate ranking.

## Phase 8 - Technical finishing

Deliver:

- Face-aware reframe.
- Audio mastering.
- Conservative color correction.
- Scene classification.
- Final FFmpeg pass.

## Phase 9 - Review and QC

Deliver:

- Static HTML review report.
- Automated QC.
- Before/after frames.
- Draft approval workflow.

## Phase 10 - Advanced design system

Deliver:

- Full component catalog.
- Additional caption styles.
- Advanced transitions.
- Screen-recording treatments.
- Cinematic presets.

## Phase 11 - Learning and optimization

Deliver:

- Accepted/rejected decision history.
- Preferred asset tracking.
- Caption correction dictionary.
- Style tuning.
- Performance improvements.

Each phase must pass its acceptance criteria before the next phase begins.

---

# 29. Definition of Done

CutMachine v2.0 is complete when:

- A raw Urdu/English talking-head video can be processed from the inbox with one top-level command.
- The project can run locally with external APIs disabled.
- Roman Urdu captions retain valid word-level timing.
- The system automatically creates and validates an edit plan.
- Local or optional free assets are resolved with licensing records.
- A professional draft is rendered before review.
- The user has one required approval checkpoint.
- Natural-language change requests can be converted into plan revisions.
- Final rendering includes technical color and audio finishing.
- The final file passes automated validation.
- Processing can resume after interruption.
- All edits are reproducible and non-destructive.
- Both vertical shorts and horizontal long-form compositions are supported.

---

# 30. Operational Runbook

## First setup

1. Install Python, Node.js, FFmpeg, and Git.
2. Create and activate a Python virtual environment.
3. Install Python requirements.
4. Install Remotion dependencies.
5. Copy `.env.example` to `.env` and add optional free API keys.
6. Run `python cutmachine.py doctor`.
7. Add local fonts through documented setup; do not commit font binaries unless licensing permits.
8. Add reusable SFX, music, B-roll, logos, and LUTs to the local library.
9. Run the demo project.

## Normal operation

```bash
python cutmachine.py run inbox/video.mp4 --mode balanced
```

Review:

```text
workspace/<slug>/review/draft.mp4
workspace/<slug>/review/index.html
```

Approve through Cowork:

```text
render
```

Final output:

```text
output/<slug>.mp4
```

## Backup

Back up:

- `config/`
- `assets-library/`
- `DECISIONS.md`
- Approved transcript mappings.
- Project plans worth reusing.

Raw project workspaces may be archived or deleted after final delivery.

---

# 31. Troubleshooting Guide

## Captions are out of sync

- Verify the remapped transcript was generated after timeline changes.
- Run the timing verification preview.
- Check source/output mapping tests.
- Do not reuse a pre-cut transcript on a post-cut video.

## Urdu technical terms are wrong

- Add the term to the glossary.
- Apply a correction mapping.
- Rerun normalization, not transcription, when timing is correct.

## B-roll is irrelevant

- Strengthen query using concrete nouns.
- Prefer a motion graphic.
- Enable local semantic ranking.
- Add the chosen asset to the local library for future use.

## Render is slow

- Use draft resolution.
- Lower Remotion concurrency.
- Use proxy assets for preview.
- Preprocess expensive FFmpeg filters once.
- Avoid decoding large files repeatedly.

## Face crop moves too much

- Increase smoothing.
- Reduce tracking sensitivity.
- Use static center or manual keyframes.

## Color looks unnatural

- Reduce preset intensity.
- Disable LUT.
- Use `natural-clean`.
- Exclude screen recordings.
- Review representative frames.

## Music is too loud

- Reduce music gain.
- Increase ducking.
- Verify loudness after final mastering.

## API key is missing

- Continue with local library and graphics.
- Show a warning rather than failing.

---

# 32. Future Enhancements

After the stable local pipeline:

- Optional local LLM planning with Ollama.
- Optional paid API providers behind explicit opt-in.
- OpenCut, Premiere Pro, or DaVinci timeline export.
- Tauri desktop packaging.
- Automated thumbnail generation.
- Long-form chapter detection.
- Multi-camera support.
- Speaker diarization.
- Automated publishing.
- Creator-style profiles.
- Analytics feedback integration.
- Reinforcement from user-approved edits.

---

# Appendix A - Agent Build Instruction

Use this prompt with Claude Code or Codex:

```text
Read MASTER_DOCUMENTATION.md, BUILD_SPEC.md, AGENTS.md, CLAUDE.md, and docs/status.md completely.

Treat MASTER_DOCUMENTATION.md as the authoritative architecture and product specification when earlier documents conflict.

Implement only the active phase. Before coding, create or update docs/implementation-plan.md with the exact acceptance criteria being addressed. Make reasonable defaults and record them in DECISIONS.md rather than asking questions unless work is truly blocked.

Core rules:
- Local-first and non-destructive.
- The core pipeline must work without paid APIs.
- External APIs are optional adapters with caching and fallbacks.
- Cowork produces validated JSON; it never injects executable code.
- Python and Remotion communicate only through versioned files.
- Preserve transcript IDs and timestamps.
- Run real tests before claiming success.
- Keep Windows and WSL2 compatibility.
- Do not begin a later phase until the current phase passes acceptance criteria.

At the end of the phase:
1. Run formatting, linting, type checking, Python tests, and relevant integration/render tests.
2. List commands executed.
3. List verified passes and failures.
4. List items requiring local verification.
5. Update docs/status.md and DECISIONS.md.
6. Show the files changed.
```

---

# Appendix B - Cowork Editing Prompt

```text
You are the creative director and workflow operator for CutMachine.

Your goal is to turn the selected Urdu/English talking-head video into a polished, high-retention video while preserving meaning and keeping editing natural.

Operate the system through approved CutMachine commands and validated project files. Do not generate arbitrary executable code. Do not invent component names, asset IDs, or filenames.

Workflow:
1. Identify the requested video.
2. Run CutMachine through draft generation and automated QC.
3. Read the transcript, timeline, contact sheet, component catalog, asset index, edit plan, and QC report.
4. Repair any validation or planning issue.
5. Present the draft path and a concise review summary.
6. Stop for one human review checkpoint.
7. Translate user feedback into precise edit-plan changes without altering unrelated approved choices.
8. Validate and rerender affected stages.
9. On approval, render and verify the final master.

Editorial rules:
- Preserve the speaker’s intended meaning.
- Keep uncertain spoken content instead of deleting it.
- Use a strong, honest hook.
- Use visual English B-roll queries with concrete nouns.
- Prefer explanatory motion graphics over generic stock footage.
- Keep the speaker visible when trust, emotion, or personality matters.
- Use screen recordings when the content refers to an interface.
- Mark product names, numbers, and power words for caption emphasis.
- Use transitions and SFX sparingly.
- Avoid repeating the same B-roll or SFX.
- Respect mobile safe zones and caption readability.
- Use scene-aware color; do not grade screen recordings like camera footage.
- Never use unlicensed Pinterest or social-media media as production assets.

When the draft is ready, report:
- Output path.
- Duration.
- Mode and style.
- Important cuts.
- Transcript uncertainties.
- B-roll and graphics summary.
- Missing assets.
- Color and audio treatment.
- QC warnings.
- The exact reply expected: “render” or change instructions.
```

---

# Appendix C - Recommended Acceptance Checklist per Video

```text
[ ] Source file hash recorded
[ ] Media metadata valid
[ ] Transcript word timestamps monotonic
[ ] Roman Urdu word count matches raw transcript
[ ] Technical terms checked
[ ] Source timeline validates
[ ] No uncertain spoken phrase removed silently
[ ] Edit plan validates against schema
[ ] All referenced component names exist
[ ] Asset licenses recorded
[ ] Draft render exists and is decodable
[ ] Captions are inside safe zones
[ ] Voice is clear and louder than music
[ ] B-roll is relevant or replaced with graphics
[ ] Color is natural on face footage
[ ] Screen recordings remain readable
[ ] QC report has no blocking error
[ ] Human approved final render
[ ] Final MP4 and SRT exist
[ ] Final duration matches expected duration
[ ] Render report written
```

---

# Appendix D - Recommended MVP Boundary

The first usable release should include:

- One-command orchestrator.
- State/resume system.
- Local transcription.
- Roman Urdu normalization with local fallback.
- Silence cutting and timestamp remapping.
- Cowork edit-plan generation.
- Captions.
- Hook title.
- B-roll overlay and fullscreen modes.
- Basic graphics.
- Controlled zooms and transitions.
- Local asset library.
- Optional free stock/SFX adapters.
- Draft render.
- Static review report.
- Automated QC.
- Final render.

Advanced segmentation, background replacement, professional-editor export, and local LLM planning should come after this reliable foundation.
