# Architecture Decisions

## 2026-07-15 - ADR-0001: Python package layout

Use a `src/` Python package with a thin root `cutmachine.py` entry point. Phase 0 exposes only the doctor command; Phase 1 will expand the dispatcher with orchestration and resumable state.

## 2026-07-15 - ADR-0002: Doctor severity

Python 3.11+, Node 20+, FFmpeg, FFprobe, writable workspace, and minimum free disk are core checks. Git, an active virtual environment, Faster-Whisper, CUDA, optional API keys, and installed Remotion dependencies are warnings during Phase 0. Missing optional capabilities must never prevent the local base workflow.

## 2026-07-15 - ADR-0003: Layered configuration

Configuration merges repository defaults, a named style profile, an optional project file, and `CUTMACHINE__SECTION__KEY` environment overrides. Secrets are never included in configuration snapshots or doctor output.

## 2026-07-15 - ADR-0004: Compatibility target

Support Python 3.11+ and Node 20+ on Windows 11, WSL2, and Linux. Use `pathlib`, UTF-8 JSON/YAML, and subprocess argument arrays for portable behavior.

## 2026-07-15 - ADR-0005: Remotion Phase 0 boundary

Pin Remotion to the version produced by the official blank scaffold and provide only static 9:16 and 16:9 smoke compositions. Upgrade ESLint within its major version to clear the scaffold's low-severity audit findings. Timeline-driven media, captions, and graphics remain Phase 6 work.

## 2026-07-15 - ADR-0006: Documentation custody

Keep byte-equivalent normalized UTF-8 copies of the supplied authoritative Markdown, Cowork skill, and build prompt inside the repository. The DOCX and PDF remain external formatted reading copies and are not runtime dependencies.

## 2026-07-15 - ADR-0007: Phase 1 run boundary

During Phase 1, `run` creates and validates a project, then stops at the `validated` state. It must not fabricate ingest, transcript, plan, or render artifacts. Later phases register the workers that advance beyond this boundary.

## 2026-07-15 - ADR-0008: State durability

Persist project and state JSON with write-to-temp plus `os.replace`, and serialize state mutations under an exclusive per-project lock. Persist only project-relative artifact paths; user-supplied CLI source paths may be absolute because they are explicit local inputs.

## 2026-07-15 - ADR-0009: Review is a branch, not a mandatory stage

Keep `revision_requested` as a workflow state and history event rather than a mandatory linear processing stage. A user may approve directly after `awaiting_review`; when revisions are requested, invalidate only the earliest affected dependency and its downstream stages.

## 2026-07-15 - ADR-0010: Windows lock liveness

Use a read-only `tasklist` query to check lock-owner liveness on Windows. Retain `os.kill(pid, 0)` only on POSIX because that probe is not safely portable to Windows process semantics.

## 2026-07-15 - ADR-0011: Phase 2 media outputs

Preserve a PCM audio extraction as `audio/original.wav`, create a separate mono 16 kHz `audio/source.wav` for transcription, and create an H.264/AAC proxy whose longest dimension is at most 1280 pixels. All generated media uses temporary sibling outputs followed by atomic replacement.

## 2026-07-15 - ADR-0012: Transcription fallback

Select Faster-Whisper settings from editing mode and detected hardware, but retry once with a smaller CPU int8 model when GPU initialization, memory, or inference fails. Record the requested and effective settings plus fallback reason in transcript provenance.

## 2026-07-15 - ADR-0013: Persisted transcript revalidation

Treat a resumed raw transcript as an untrusted file boundary even though CutMachine originally generated it. Revalidate project ownership, finite and monotonic word and segment timestamps, stable sequential IDs, segment membership, and word containment before skipping transcription. Empty model tokens do not consume immutable IDs; only overlaps of at most 50 milliseconds are repaired conservatively.

## 2026-07-15 - ADR-0014: One-to-one Roman Urdu normalization

Write Roman Urdu into a separate versioned transcript and retain the Phase 2 raw transcript unchanged. Every normalized word preserves its raw text, ID, segment membership, source, and timestamps. Technical glossary matches take precedence, followed by the local lexicon, already-Roman preservation, and deterministic character transliteration. Ambiguous results keep conservative confidence and appear in a normalization report.

## 2026-07-15 - ADR-0015: Optional refinement boundary

Keep refinement disabled by default and require both project and current network settings to allow it. A configured adapter receives only bounded word objects without timestamps or the full transcript. It must use HTTPS and return the exact ordered IDs with one display per input word. Malformed or unavailable responses retry at most the configured bound and then retain the local result; technical glossary and already-preserved tokens are never sent for refinement.

## 2026-07-15 - ADR-0016: Corroborated automatic silence cuts

Treat transcript word gaps and FFmpeg silence detection as separate evidence. A gap becomes an automatic cut only when FFmpeg corroborates at least 80 percent of it, it exceeds the configured automatic threshold, contains no timed word, and leaves configured speech padding. Uncorroborated and short gaps remain review-only; a project with no timed speech is retained intact.

## 2026-07-15 - ADR-0017: Repetitions require later creative agreement

Phase 4 records nearby high-similarity segment pairs but never removes them automatically. The authoritative policy requires semantic confirmation from Cowork, which is unavailable until Phase 5, so every repetition candidate remains reversible and review-only.

## 2026-07-15 - ADR-0018: Piecewise source-to-output mapping

Represent editing as ordered keep ranges plus reversible cut records over the immutable source. Generate a piecewise-linear time map and a separate remapped transcript that retains original IDs and source timestamps. If a final model timestamp slightly exceeds media duration, preserve that source value and clamp only the derived output endpoint to the actual timeline duration.

## 2026-07-15 - ADR-0019: Offline baseline creative plan

Always generate a complete conservative edit plan locally before optional Cowork changes. The baseline uses the validated proxy, authoritative remapped caption words, one scene per kept timeline range, static speaker framing, no unresolved assets, and a bounded HookTitle when the opening range is long enough. This keeps the core pipeline functional without a network planner.

## 2026-07-15 - ADR-0020: Cross-document planning validation

JSON Schema validation is necessary but not sufficient for creative plans. Revalidate project and timeline versions, proxy identity, exact caption timing/content, gap-free scene coverage, timeline references, catalog component props, graphic and B-roll offsets, and asset readiness against authoritative project artifacts. Reject all non-null asset IDs until an asset manifest exists.

## 2026-07-15 - ADR-0021: Typed revisions instead of arbitrary JSON paths

Accept revisions only as allowlisted operations for caption emphasis, caption preset, scene camera, scene layout, and B-roll query. Never accept JSON Patch paths, executable fields, arbitrary filenames, or code. Apply operations to a copy, preserve unrelated content, validate the complete result, and replace the plan atomically only after it passes.

## 2026-07-15 - ADR-0022: Direct-proxy piecewise Remotion timeline

Render each authoritative keep range as its own premounted media sequence. Convert second-based boundaries with one rounded frame rule, apply source trims in frames, and derive total composition length with a ceiling. Video and its source audio remain together in each sequence, preventing a visual cut from drifting away from continuous audio.

## 2026-07-15 - ADR-0023: Duration-preserving draft effects

Keep camera moves, catalog graphics, captions, and transitions inside the existing scene timeline. Transitions are visual overlays rather than timeline-overlapping transition series, so they cannot shorten the authoritative output duration. Optional B-roll, SFX, and music references degrade to the speaker composition when unresolved.

## 2026-07-15 - ADR-0024: Local atomic Remotion bridge

Invoke the repository-pinned Remotion CLI directly with a subprocess argument array, bounded concurrency, timeout, and captured logs. Stage only derived project-scoped public media paths, write the draft to a temporary sibling, atomically replace `review/draft.mp4`, and accept completion only after FFprobe verifies streams, dimensions, codecs, and duration.

## 2026-07-15 - ADR-0025: Preserve the creative plan during asset resolution

Keep `planning/edit-plan.json` as the immutable Phase 5 creative decision record. Phase 7 writes `planning/resolved-edit-plan.json` with concrete manifest IDs and validates that captions, video, timeline references, scene timing, graphics, camera, color, and transitions remain unchanged. Rendering consumes the resolved copy only after manifest validation.

## 2026-07-15 - ADR-0026: Earliest qualifying asset tier

Resolve owned local media before a valid content-addressed cache entry and consult an optional provider only when no earlier tier meets the configured relevance threshold. An existing scene graphic precedes a provider search. Within a tier, rank from persisted query, orientation, duration, resolution, quality, license, and reuse scores, then use candidate ID as the deterministic tie-breaker.

## 2026-07-15 - ADR-0027: Opt-in private provider boundary

Keep Pexels disabled by default and require project permission, current network permission, explicit provider enablement, and an environment-sourced key. Send only a validated short ASCII visual query. Require HTTPS search, source, and download URLs; bound response/download sizes and timeouts; probe downloaded media; and persist provider, creator, license, attribution, source page, hash, and cache expiry evidence.

## 2026-07-16 - ADR-0028: Technical finishing owns the preprocessing boundary

Use the existing `preprocessed` stage for Phase 8's deterministic FFmpeg technical proxy and evidence rather than adding a parallel state. Rendering consumes only the hash-validated technical proxy. Original source, proxy, transcript, timeline, and creative plan remain immutable.

## 2026-07-16 - ADR-0029: Optional face evidence with a deterministic neutral fallback

Accept face observations only through an injected local detector boundary, filter them by confidence, and smooth their normalized centers. When no detector or confident face is available, use a fixed bounded center crop. Preserve full neutral framing whenever a screen, mobile UI, uncertain scene, or matching aspect ratio makes cropping unsafe.

## 2026-07-16 - ADR-0030: Conservative allowlisted grade and speech master

Derive bounded color decisions from sampled FFmpeg signal statistics and construct all filters internally. Apply LUTs only when a locally indexed file has a verified hash, supported license, declared Rec.709/sRGB space, safe relative path, and intensity no greater than 0.5. Master voice with a fixed high-pass, gentle EQ/compression, loudness normalization, and true-peak limiter, then persist and revalidate before/after metrics. When enabled, Remotion lowers music by 6 dB around captioned speech with a deterministic 150 ms recovery envelope.

## 2026-07-16 - ADR-0031: Finalize Remotion drafts without another lossy encode

After Remotion encodes the composed draft, run a separate atomic FFmpeg stream-copy pass with fast-start metadata. Persist the final hash, duration, and codecs and re-probe them on resume. This provides a deterministic final FFmpeg boundary while avoiding an unnecessary second generation loss.

## 2026-07-16 - ADR-0032: Blocking QC still produces review evidence

Run every deterministic quality gate and generate the static review package before raising a blocking QC error. The `qc_passed` stage completes only when there are no error-severity findings, but a failed run still leaves an actionable schema-valid report and local HTML page for diagnosis.

## 2026-07-16 - ADR-0033: Static review is local, read-only, and hash-bound

Generate one escaped HTML file with no scripts or remote resources and only local relative media references. Persist hashes for the draft, QC report, HTML, before/after frames, and staged asset previews, then revalidate them on resume. Provider source URLs may appear only as escaped text, never as fetched page resources.

## 2026-07-16 - ADR-0034: QC separates deterministic blockers from heuristic warnings

Block on invalid plans/timelines, unsafe caption zones, undecodable or stream-missing output, duration drift, missing voice, loudness deviation, and excessive true peak. Treat conservative caption-width estimates, optional missing assets, long silence, music masking, and loud SFX as visible warnings because those checks can require human editorial context.

## 2026-07-16 - ADR-0035: Human review decisions are explicit typed state transitions

Normal orchestration stops at `awaiting_review` and never approves automatically. Approval requires a current zero-blocker QC package and writes an atomic project-bound decision. Revisions must use the existing allowlisted plan-revision schema from a safe project-relative path; they preserve timeline/transcript evidence and invalidate only `plan_ready` and downstream stages.

## 2026-07-16 - ADR-0036: Version the advanced visual boundary as allowlisted data

Move edit plans, render inputs, and the component catalog to version 2 together. Keep every caption, component, transition, color preset, screen treatment, and prop inside strict schemas plus cross-document validation; never accept JSX, CSS, JavaScript, commands, arbitrary executable fields, or unvalidated paths from Cowork plans.

## 2026-07-16 - ADR-0037: Preserve duration with bounded visual overlays

Implement advanced transitions as visual overlays within authoritative scene time instead of overlapping timeline sequences. Enforce style-profile budgets for transitions, camera moves, fullscreen B-roll, animated text, and impact SFX, keep clean cuts dominant, and render screen scenes with neutral color plus bounded local-only treatments.

## 2026-07-16 - ADR-0038: Bundle the Urdu font and keep preview/fallback paths deterministic

Use the repository-bundled OFL-licensed Noto Naskh Arabic variable font only when its fixed path and hash validate, otherwise continue with the declared local fallback. Missing optional visual inputs must preserve a valid base composition. The exact Remotion Studio preview sentinel renders an internal deterministic backdrop so local preview does not depend on nonexistent placeholder media, while normal project inputs still require validated staged media.

## 2026-07-16 - ADR-0039: Learn only from explicit hash-bound review events

Create an append-only local learning event only alongside an explicit current approval or typed revision decision. Snapshot and hash the project-bound decision, QC report, and optional structured feedback under `workspace/.learning`; reject duplicates, stale ownership, changed evidence, unsafe paths, unknown IDs, and protected glossary overrides. Derived profiles are reproducible caches and are disabled when their source-event digest no longer validates.

## 2026-07-16 - ADR-0040: Keep learned behavior bounded below safety and editorial contracts

Apply asset preference only inside the earliest safe license-compatible tier as a bounded deterministic tie-break. Apply an approved caption correction to one matching immutable word display only, after the technical glossary and without changing raw text, IDs, order, or timestamps. Apply style learning only when explicitly activated and only through existing allowlisted presets and effect-budget reductions; deterministic defaults always remain available.

## 2026-07-16 - ADR-0041: Explicit approval triggers verified final delivery

After the single human approval, render the authoritative plan at its full planned dimensions with the repository-pinned Remotion CLI, run an FFmpeg stream-copy fast-start pass, atomically copy the master to `output/<slug>.mp4`, and persist approval hash, input, media metadata, and output hash in a strict delivery record. Resume accepts completion only after revalidating both workspace and delivery copies, codecs, dimensions, duration, input, and approval evidence.

## 2026-07-16 - ADR-0042: Modern review remains static and read-only

Present the review package as a responsive editor-like local surface with preview, timeline, transcript, asset, color, audio, learning, QC, and action sections. Preserve the Phase 9 security boundary: no scripts, remote resources, arbitrary plan execution, or implicit approval controls.

## 2026-07-16 - ADR-0043: Model observable social-editing principles, not creator identity

Add a post-v2 viral social style pack using original Remotion components derived from observable public patterns: clear premises, reaction-led reframing, clean cuts, sparse high-value labels, word-timed emphasis, phone demonstrations, and compact data graphics. Do not claim knowledge of private After Effects projects or copy handles, branding, promotional wrappers, reference footage, or proprietary assets. Keep every new choice inside typed schemas, local assets, immutable caption timing, safe zones, and existing effect budgets.

## 2026-07-16 - ADR-0044: Treat social typography as timed information hierarchy

Use a heavy local display stack, one yellow emphasis color, black separation, short word-level entrances, and compact boxed-keyword alternatives instead of permanent full-screen decoration. Drive blur, scale, opacity, and movement from Remotion frames only. Keep modern phone and comparison demonstrations as typed local data, and require representative portrait-frame inspection before completing the design phase.

## 2026-07-16 - ADR-0045: Deterministic bounded SFX placement in the baseline plan

Place baseline sound effects only from three evidence-backed cues in fixed priority order: a hook impact under the opening title graphic, a whoosh under each visual transition, and sparse accents on emphasized caption words. Entries carry search queries only; the existing tiered local asset search resolves them, unresolved entries remain optional warnings, and asset-free projects render unchanged. The engine reuses the plan validator's `impact_sfx_per_minute` allowance formula, enforces global minimum spacing, and keeps every gain below the QC voice-priority ceiling.

## 2026-07-16 - ADR-0046: Tune transcription defaults for Roman Urdu speech

Keep decoding pinned to Urdu, but carry the technical glossary as Faster-Whisper hotwords so English technical terms stay biased in every window rather than only the first prompt. Enable the word-timestamp hallucination-silence guard, and raise the per-mode model defaults (small/medium/large-v3) because tiny and small models are materially weaker on Urdu. Extend the deterministic Roman Urdu layer with word-initial waw as "w", Urdu and Arabic-Indic digit mapping, and a curated high-frequency lexicon so common words use standard Roman spellings instead of raw transliteration.

## 2026-07-16 - ADR-0047: Typed graphic revisions instead of full plan reimports

Add `set-scene-graphic` (add or replace one graphic matched by ID) and `remove-scene-graphic` to the allowlisted plan-revision operations so Cowork can request a specific runtime graphic - for example a PriceComparison of "$1" versus "$100" - without rewriting the whole plan. Revision graphics carry only catalog components and typed props; the full cross-document plan validation (catalog membership, dangerous-prop rejection, scene bounds, animated-text budget, duplicate IDs) reruns before the plan is replaced.

## 2026-07-16 - ADR-0048: Bounded attention pacing from editing psychology

Encode three evidence-backed editing principles as deterministic, budgeted data rather than free-form effects: salience at the open (a fast punch-in on the hook scene), attention reset (imperceptible alternating slow zooms only on scenes that outlast the style's visual-change target), and habituation avoidance (no repeated identical move back to back). Remotion shapes each camera mode's motion curve (fast-settle punch-ins and reframes, full-scene eased zooms) while scale stays within 1.0-1.06 and the camera budget formula matches the plan validator. Add the intensity-scaled `teal-orange` grade to the existing bounded CSS preset family.

## 2026-07-16 - ADR-0049: Manual transcripts are explicit immutable fallbacks

When Faster-Whisper omits or materially misrecognizes speech, allow the user to import an exact project-relative Roman Urdu text file instead of silently guessing corrections. Preserve the original ASR transcript as a validated snapshot, hash-bind the manual source, keep every supplied token unchanged, and create new sequential locked timing identifiers through deterministic weighted alignment. Invalidate normalization and downstream artifacts only, rerender to `awaiting_review`, and never accept arbitrary, absolute, traversal, oversized, mixed-source, tampered, or post-approval transcript replacement.

## 2026-07-16 - ADR-0050: Creative beats are independent of source cuts

Do not equate one retained source-timeline range with one visual scene. Split long output ranges at deterministic caption-word boundaries into gap-free creative beats, retain every overlapping authoritative timeline ID, and apply camera, graphic, transition, and asset decisions to those beats without changing media cuts or caption identity/timing. This permits attention pacing across a continuous talking-head take while preserving the immutable editorial timeline.

## 2026-07-16 - ADR-0051: Owned generated SFX are the local-first audio floor

Before local asset indexing, deterministically synthesize a small fixed PCM WAV pack for the allowlisted baseline impact, whoosh, and pop queries. Store it under a reserved CutMachine-generated asset-library directory with owned-license sidecars, validate and rank it through the same hash, media-probe, relevance, manifest, and staging boundaries as user assets, and never overwrite unrelated user media. Optional provider SFX may still supersede only according to the existing tier rules; speech remains dominant through bounded negative gains.

## 2026-07-16 - ADR-0052: User cue ranges override inferred manual alignment

When an authoritative manual transcript contains strict timestamp headers, treat each validated range as the segment timing authority, exclude headers from spoken tokens, and distribute exact words deterministically only within that range. Resolve `End` against validated media duration; reject mixed, missing, overlapping, reversed, or out-of-range cues. Preserve the existing whole-speech weighted alignment for plain scripts and hash-bind/reparse either format during resume validation.

## 2026-07-16 - ADR-0053: Interactive controls wrap but do not replace the review boundary

Keep `review/index.html` an immutable, script-free evidence package and add the requested interactive workflow as a separate loopback-only controller. Browser actions translate only into allowlisted caption revisions, validated project-bound B-roll pins, or fixed Cowork handoff files; they never inject code, shell commands, arbitrary paths, or unvalidated plan content. User-pinned owned media may override automatic relevance ranking only after extension, size, probe, hash, license, and local-library validation.

## 2026-07-16 - ADR-0054: Editor controls ship CLI-first

Expose the validated editor workflow through three CLI commands before any browser surface exists: `editor-apply` reads a bounded project-relative JSON settings request (captions on/off, allowlisted caption preset, B-roll mode, owned pins) and rerenders through normal QC; `add-broll` stages an explicit user file through the controlled upload directory into the owned asset library; `cowork-request` writes the fixed Cowork handoff document whose typed revision returns through the existing `request-revision` boundary. A future loopback browser UI may call the same orchestrator functions but adds no new mutation paths.
