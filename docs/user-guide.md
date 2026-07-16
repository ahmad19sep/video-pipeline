# CutMachine User Guide

CutMachine turns a raw Urdu/English talking-head recording into an edited, captioned, graded, SFX-scored vertical video — locally, with one human approval before anything final is produced.

## One-time setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd remotion; npm install; cd ..
python cutmachine.py doctor
```

`doctor` must report ready (Python, Node, FFmpeg/FFprobe, Faster-Whisper). The first run per mode downloads a Whisper model once (`balanced` uses `medium`; `cinematic` uses `large-v3` for maximum Urdu accuracy).

## The normal workflow

**1. Drop your video in `inbox\` and run:**

```powershell
python cutmachine.py run inbox\my-video.mp4 --mode energetic
```

Modes: `fast` (minimal effects), `balanced` (default), `energetic` (viral-social style: punch captions, beats, more effects), `cinematic` (calm, best transcription model).

The pipeline automatically: probes and proxies the media → transcribes Urdu with word timestamps → normalizes to Roman Urdu captions (glossary + lexicon) → cuts corroborated silences → builds a creative plan (scenes, hook title, captions, camera pacing, SFX, B-roll queries, graphics) → resolves assets → applies face-aware reframe, bounded color, and voice mastering → renders a draft → runs 15 QC gates → **stops at `awaiting_review`**.

**2. Open the review page:**

`workspace\<slug>\review\index.html` — preview the draft, scenes, captions, warnings, color before/after, audio, and QC results.

**3. Adjust if needed (all optional, all re-render back to review):**

- Captions on/off, caption style, B-roll mode, pin your own clips:
  ```powershell
  python cutmachine.py editor-apply <slug> planning\editor-request.json
  ```
  where the JSON is e.g. `{"captionsEnabled": true, "captionPreset": "viral-punch", "brollMode": "auto", "pins": []}`.
- Add your own footage as reusable B-roll:
  ```powershell
  python cutmachine.py add-broll <slug> D:\clips\phone-demo.mp4 --tags "phone app demo"
  ```
- Ask Cowork for a creative change in plain language:
  ```powershell
  python cutmachine.py cowork-request <slug> "Show a $1 vs $100 price comparison in the pricing scene"
  ```
  Cowork answers by writing `planning\cowork-editor-revision.json`; apply it with:
  ```powershell
  python cutmachine.py request-revision <slug> planning\cowork-editor-revision.json
  ```
- Fix a wrong transcript with your exact script (plain text, or timestamped with `M:SS–M:SS` headers):
  ```powershell
  python cutmachine.py import-transcript <slug> transcript\manual-script.txt
  ```

**4. Approve to get the final video:**

```powershell
python cutmachine.py approve <slug> --note "Looks good"
```

Approval renders the full-resolution master and verifies it. Your finished video is at:

```
output\<slug>.mp4
```

## Useful extras

- `python cutmachine.py status <slug>` — where a project is and what runs next.
- `python cutmachine.py resume <slug>` — continue after an interruption; everything is resumable and hash-verified.
- `python cutmachine.py rerun <slug> --from <stage>` — deliberately redo a stage and everything after it.
- Your asset library lives in `assets-library\` (`broll`, `images`, `music`, `sfx`) with optional `.asset.json` sidecars declaring `tags` and `license`. CutMachine also generates a small built-in SFX pack (impact/whoosh/pop) so baseline sound design works out of the box.
- Approval and revision decisions optionally carry structured learning feedback (`--feedback review\learning-feedback.json`) that improves asset choice, caption corrections, and style tuning on future projects.

## What CutMachine never does

It never uploads or publishes anything, never approves itself, never modifies your original video or the raw transcript, and never executes content from plans or feedback files. Everything runs locally; the only optional network features (Pexels search, HTTPS caption refinement) are off by default.
