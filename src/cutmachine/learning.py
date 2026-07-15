"""Explicit, local, hash-bound learning and performance evidence."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cutmachine.locking import ProjectLock
from cutmachine.paths import UnsafePathError, resolve_inside
from cutmachine.persistence import (
    PersistenceError,
    read_json,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext, sha256_file


class LearningError(RuntimeError):
    """Raised when feedback or stored learning evidence is unsafe or stale."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _learning_root(repository_root: Path) -> Path:
    return repository_root / "workspace" / ".learning"


def _repo_relative(repository_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repository_root.resolve()).as_posix()


def _digest(entries: list[tuple[str, str]]) -> str:
    payload = "\n".join(f"{name}:{digest}" for name, digest in sorted(entries))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _core(value: str) -> str:
    start = 0
    end = len(value)
    while start < end and unicodedata.category(value[start])[0] in {"P", "S"}:
        start += 1
    while end > start and unicodedata.category(value[end - 1])[0] in {"P", "S"}:
        end -= 1
    return value[start:end]


def _glossary(repository_root: Path) -> dict[str, str]:
    try:
        document = read_json(repository_root / "config" / "technical-glossary.json")
    except PersistenceError as exc:
        raise LearningError(f"Technical glossary is unavailable: {exc}") from exc
    terms = document.get("terms")
    aliases = document.get("aliases", {})
    if document.get("version") != 1 or not isinstance(terms, list) or not isinstance(aliases, dict):
        raise LearningError("Technical glossary is invalid.")
    canonical = {term.casefold(): term for term in terms if isinstance(term, str) and term.strip()}
    for alias, target in aliases.items():
        if isinstance(alias, str) and isinstance(target, str) and target in canonical.values():
            canonical[alias.casefold()] = target
    return canonical


def _validated_events(repository_root: Path, *, strict: bool) -> tuple[list[dict[str, Any]], str]:
    events_dir = _learning_root(repository_root) / "events"
    if not events_dir.is_dir():
        return [], _digest([])
    events: list[dict[str, Any]] = []
    hashes: list[tuple[str, str]] = []
    for path in sorted(events_dir.glob("event_*.json"), key=lambda item: item.name):
        try:
            event = read_validated_json(repository_root, path, "learning-event")
            if path.stem != event["eventId"]:
                raise LearningError("Learning event filename and ID do not match.")
            for path_key, hash_key in (
                ("decisionSnapshotPath", "decisionSha256"),
                ("qcSnapshotPath", "qcSha256"),
            ):
                snapshot = resolve_inside(repository_root, cast(str, event[path_key]))
                if not snapshot.is_file() or sha256_file(snapshot) != event[hash_key]:
                    raise LearningError(
                        f"Learning event snapshot is missing or changed: {path_key}"
                    )
            feedback_path = event["feedbackSnapshotPath"]
            feedback_hash = event["feedbackSha256"]
            if (feedback_path is None) != (feedback_hash is None):
                raise LearningError("Learning feedback snapshot evidence is inconsistent.")
            if feedback_path is not None:
                snapshot = resolve_inside(repository_root, cast(str, feedback_path))
                if not snapshot.is_file() or sha256_file(snapshot) != feedback_hash:
                    raise LearningError("Learning feedback snapshot is missing or changed.")
            event_hash = sha256_file(path)
        except (LearningError, PersistenceError, UnsafePathError) as exc:
            if strict:
                raise LearningError(f"Invalid learning event {path.name}: {exc}") from exc
            return [], _digest([])
        events.append(event)
        hashes.append((path.name, event_hash))
    return events, _digest(hashes)


def _resolved_feedback(
    context: ProjectContext, feedback_relative: str | None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if feedback_relative is None:
        return None, [], []
    try:
        feedback_path = resolve_inside(context.project_dir, feedback_relative)
    except UnsafePathError as exc:
        raise LearningError(f"Learning feedback path is unsafe: {exc}") from exc
    if feedback_path.suffix.casefold() != ".json" or not feedback_path.is_file():
        raise LearningError("Learning feedback must be an existing project-relative JSON file.")
    if feedback_path.stat().st_size > 1_000_000:
        raise LearningError("Learning feedback exceeds the 1 MB limit.")
    try:
        feedback = read_validated_json(context.repository_root, feedback_path, "learning-feedback")
    except PersistenceError as exc:
        raise LearningError(f"Learning feedback is invalid: {exc}") from exc
    if feedback["projectId"] != context.project["projectId"]:
        raise LearningError("Learning feedback belongs to another project.")

    asset_signals = cast(list[dict[str, Any]], feedback["assetSignals"])
    asset_ids = [cast(str, item["assetId"]) for item in asset_signals]
    if len(asset_ids) != len(set(asset_ids)):
        raise LearningError("Learning feedback repeats an asset ID.")
    try:
        manifest = read_validated_json(
            context.repository_root,
            context.project_dir / "assets" / "manifest.json",
            "asset-manifest",
        )
    except PersistenceError as exc:
        raise LearningError(f"Asset feedback cannot be resolved: {exc}") from exc
    assets = {
        cast(str, item["id"]): item for item in cast(list[dict[str, Any]], manifest["assets"])
    }
    resolved_assets: list[dict[str, Any]] = []
    for signal in asset_signals:
        asset = assets.get(cast(str, signal["assetId"]))
        if asset is None:
            raise LearningError("Learning feedback references an unknown asset ID.")
        resolved_assets.append(
            {
                "provider": asset["provider"],
                "providerId": asset["providerId"],
                "sha256": asset["sha256"],
                "preference": signal["preference"],
            }
        )

    corrections = cast(list[dict[str, Any]], feedback["captionCorrections"])
    word_ids = [cast(str, item["wordId"]) for item in corrections]
    if len(word_ids) != len(set(word_ids)):
        raise LearningError("Learning feedback repeats a caption word ID.")
    try:
        transcript = read_validated_json(
            context.repository_root,
            context.project_dir / "transcript" / "transcript.raw.json",
            "transcript",
        )
    except PersistenceError as exc:
        raise LearningError(f"Caption feedback cannot be resolved: {exc}") from exc
    words = cast(list[dict[str, Any]], transcript["words"])
    word_indexes = {cast(str, word["id"]): index for index, word in enumerate(words)}
    glossary = _glossary(context.repository_root)
    resolved_corrections: list[dict[str, Any]] = []
    for correction in corrections:
        index = word_indexes.get(cast(str, correction["wordId"]))
        if index is None:
            raise LearningError("Learning feedback references an unknown caption word ID.")
        heard = cast(str, words[index]["raw"])
        preferred = cast(str, correction["preferred"]).strip()
        lookup = _core(heard).casefold()
        if lookup in glossary and preferred != glossary[lookup]:
            raise LearningError("A caption correction cannot override a protected technical term.")
        nearby = [
            _core(cast(str, words[item]["raw"])).casefold()
            for item in range(max(0, index - 2), min(len(words), index + 3))
            if item != index and _core(cast(str, words[item]["raw"]))
        ]
        supplied = [cast(str, item).casefold() for item in correction["context"]]
        context_terms = list(dict.fromkeys([*supplied, *nearby]))[:8]
        resolved_corrections.append(
            {"heard": heard, "preferred": preferred, "context": context_terms}
        )
    return feedback, resolved_assets, resolved_corrections


def _write_snapshot(
    repository_root: Path,
    path: Path,
    schema: str,
    document: dict[str, Any],
) -> tuple[str, str]:
    write_validated_json_atomic(repository_root, path, schema, document)
    return _repo_relative(repository_root, path), sha256_file(path)


def _profiles(
    events: list[dict[str, Any]], source_digest: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    updated_at = _now()
    asset_values: dict[tuple[str, str, str], dict[str, Any]] = {}
    correction_values: dict[tuple[str, str], dict[str, Any]] = {}
    modes = ("fast", "balanced", "energetic", "cinematic")
    style_values: dict[str, dict[str, Any]] = {
        mode: {
            "mode": mode,
            "active": False,
            "captionPreset": None,
            "transitionDensity": None,
            "visualChangeTargetSeconds": None,
            "effectBudgetScale": None,
            "preferredSignals": 0,
            "rejectedSignals": 0,
        }
        for mode in modes
    }
    for event in sorted(events, key=lambda item: (cast(str, item["createdAt"]), item["eventId"])):
        for asset_signal in cast(list[dict[str, Any]], event["assetSignals"]):
            asset_key = (
                cast(str, asset_signal["provider"]),
                cast(str, asset_signal["providerId"]),
                cast(str, asset_signal["sha256"]),
            )
            value = asset_values.setdefault(
                asset_key,
                {
                    "id": "assetpref_"
                    + hashlib.sha256("|".join(asset_key).encode()).hexdigest()[:16],
                    "provider": asset_key[0],
                    "providerId": asset_key[1],
                    "sha256": asset_key[2],
                    "preferredCount": 0,
                    "rejectedCount": 0,
                    "score": 0.0,
                },
            )
            count_key = (
                "preferredCount" if asset_signal["preference"] == "preferred" else "rejectedCount"
            )
            value[count_key] += 1
        for correction in cast(list[dict[str, Any]], event["captionCorrections"]):
            correction_key = (
                cast(str, correction["heard"]).casefold(),
                cast(str, correction["preferred"]).casefold(),
            )
            value = correction_values.setdefault(
                correction_key,
                {
                    "id": "correction_"
                    + hashlib.sha256("|".join(correction_key).encode()).hexdigest()[:16],
                    "heard": correction["heard"],
                    "preferred": correction["preferred"],
                    "context": [],
                    "approvedCount": 0,
                    "lastApprovedAt": event["createdAt"],
                },
            )
            value["context"] = sorted(
                set(cast(list[str], value["context"])) | set(cast(list[str], correction["context"]))
            )[:8]
            value["approvedCount"] += 1
            value["lastApprovedAt"] = event["createdAt"]
        style_signal = cast(dict[str, Any] | None, event["styleSignal"])
        if style_signal is not None:
            profile = style_values[cast(str, event["mode"])]
            if style_signal["preference"] == "preferred":
                profile["preferredSignals"] += 1
                for field in (
                    "captionPreset",
                    "transitionDensity",
                    "visualChangeTargetSeconds",
                    "effectBudgetScale",
                ):
                    if style_signal[field] is not None:
                        profile[field] = style_signal[field]
                profile["active"] = bool(style_signal["activate"])
            else:
                profile["rejectedSignals"] += 1
                profile["active"] = False
    for value in asset_values.values():
        preferred = int(value["preferredCount"])
        rejected = int(value["rejectedCount"])
        value["score"] = round((preferred - rejected) / max(1, preferred + rejected), 6)
    common = {
        "version": 1,
        "updatedAt": updated_at,
        "sourceEventDigest": source_digest,
        "eventCount": len(events),
    }
    assets = {
        **common,
        "preferences": sorted(asset_values.values(), key=lambda item: cast(str, item["id"])),
    }
    corrections = {
        **common,
        "corrections": sorted(correction_values.values(), key=lambda item: cast(str, item["id"])),
    }
    styles = {**common, "profiles": [style_values[mode] for mode in modes]}
    return assets, corrections, styles


def _refresh_profiles(repository_root: Path) -> list[str]:
    events, source_digest = _validated_events(repository_root, strict=True)
    assets, corrections, styles = _profiles(events, source_digest)
    root = _learning_root(repository_root)
    outputs = (
        (root / "asset-preferences.json", "asset-preferences", assets),
        (root / "caption-corrections.json", "caption-corrections", corrections),
        (root / "style-tuning.json", "style-tuning", styles),
    )
    for path, schema, document in outputs:
        write_validated_json_atomic(repository_root, path, schema, document)
    return [_repo_relative(repository_root, path) for path, _schema, _document in outputs]


def record_learning_event(
    context: ProjectContext,
    *,
    expected_review_action: str,
    feedback_relative: str | None = None,
) -> list[str]:
    try:
        decision = read_validated_json(
            context.repository_root,
            context.project_dir / "review" / "decision.json",
            "review-decision",
        )
        qc = read_validated_json(
            context.repository_root,
            context.project_dir / "review" / "qc-report.json",
            "qc-report",
        )
    except PersistenceError as exc:
        raise LearningError(f"Current review evidence is missing or invalid: {exc}") from exc
    decision_path = context.project_dir / "review" / "decision.json"
    qc_path = context.project_dir / "review" / "qc-report.json"
    if (
        decision["projectId"] != context.project["projectId"]
        or qc["projectId"] != context.project["projectId"]
        or decision["action"] != expected_review_action
        or sha256_file(qc_path) != decision["qcReportSha256"]
    ):
        raise LearningError("Review evidence is project-mismatched, stale, or changed.")
    feedback, asset_signals, corrections = _resolved_feedback(context, feedback_relative)
    decision_hash = sha256_file(decision_path)
    feedback_payload = (
        json.dumps(feedback, sort_keys=True, ensure_ascii=False) if feedback is not None else "none"
    )
    event_seed = (
        f"{context.project['projectId']}|{decision_hash}|"
        f"{expected_review_action}|{feedback_payload}"
    )
    event_id = "event_" + hashlib.sha256(event_seed.encode("utf-8")).hexdigest()[:16]
    root = _learning_root(context.repository_root)
    snapshot_dir = root / "snapshots" / event_id
    event_path = root / "events" / f"{event_id}.json"
    with ProjectLock(root):
        if event_path.exists():
            raise LearningError(f"Duplicate learning event rejected: {event_id}")
        decision_relative, decision_snapshot_hash = _write_snapshot(
            context.repository_root,
            snapshot_dir / "decision.json",
            "review-decision",
            decision,
        )
        qc_relative, qc_snapshot_hash = _write_snapshot(
            context.repository_root, snapshot_dir / "qc-report.json", "qc-report", qc
        )
        feedback_relative_snapshot: str | None = None
        feedback_snapshot_hash: str | None = None
        if feedback is not None:
            feedback_relative_snapshot, feedback_snapshot_hash = _write_snapshot(
                context.repository_root,
                snapshot_dir / "feedback.json",
                "learning-feedback",
                feedback,
            )
        event = {
            "version": 1,
            "eventId": event_id,
            "projectId": context.project["projectId"],
            "createdAt": _now(),
            "action": "accepted" if expected_review_action == "approved" else "rejected",
            "reviewAction": expected_review_action,
            "mode": context.project["mode"],
            "projectSourceHash": context.project["sourceHash"],
            "decisionSnapshotPath": decision_relative,
            "decisionSha256": decision_snapshot_hash,
            "qcSnapshotPath": qc_relative,
            "qcSha256": qc_snapshot_hash,
            "feedbackSnapshotPath": feedback_relative_snapshot,
            "feedbackSha256": feedback_snapshot_hash,
            "assetSignals": asset_signals,
            "captionCorrections": corrections,
            "styleSignal": feedback["styleSignal"] if feedback is not None else None,
        }
        write_validated_json_atomic(context.repository_root, event_path, "learning-event", event)
        profiles = _refresh_profiles(context.repository_root)
    return [_repo_relative(context.repository_root, event_path), *profiles]


def _valid_profile(repository_root: Path, name: str, filename: str) -> dict[str, Any] | None:
    try:
        profile = read_validated_json(
            repository_root, _learning_root(repository_root) / filename, name
        )
        events, source_digest = _validated_events(repository_root, strict=False)
    except PersistenceError:
        return None
    if profile["sourceEventDigest"] != source_digest or profile["eventCount"] != len(events):
        return None
    return profile


def asset_preference_scores(repository_root: Path) -> dict[tuple[str, str], float]:
    profile = _valid_profile(repository_root, "asset-preferences", "asset-preferences.json")
    if profile is None:
        return {}
    return {
        (cast(str, item["provider"]), cast(str, item["providerId"])): float(item["score"])
        for item in cast(list[dict[str, Any]], profile["preferences"])
    }


def approved_caption_corrections(repository_root: Path) -> list[dict[str, Any]]:
    profile = _valid_profile(repository_root, "caption-corrections", "caption-corrections.json")
    return [] if profile is None else cast(list[dict[str, Any]], profile["corrections"])


def active_style_tuning(repository_root: Path, mode: str) -> dict[str, Any] | None:
    profile = _valid_profile(repository_root, "style-tuning", "style-tuning.json")
    if profile is None:
        return None
    return next(
        (
            item
            for item in cast(list[dict[str, Any]], profile["profiles"])
            if item["mode"] == mode and item["active"] is True
        ),
        None,
    )


def learning_summary(repository_root: Path) -> dict[str, Any]:
    assets = _valid_profile(repository_root, "asset-preferences", "asset-preferences.json")
    corrections = _valid_profile(repository_root, "caption-corrections", "caption-corrections.json")
    styles = _valid_profile(repository_root, "style-tuning", "style-tuning.json")
    valid = assets is not None and corrections is not None and styles is not None
    return {
        "valid": valid,
        "events": int(assets["eventCount"]) if assets is not None else 0,
        "assetPreferences": len(cast(list[Any], assets["preferences"])) if assets else 0,
        "captionCorrections": (
            len(cast(list[Any], corrections["corrections"])) if corrections else 0
        ),
        "activeStyleModes": (
            [
                cast(str, item["mode"])
                for item in cast(list[dict[str, Any]], styles["profiles"])
                if item["active"]
            ]
            if styles
            else []
        ),
    }


def validate_learning_store(repository_root: Path) -> None:
    events, source_digest = _validated_events(repository_root, strict=True)
    for name, filename in (
        ("asset-preferences", "asset-preferences.json"),
        ("caption-corrections", "caption-corrections.json"),
        ("style-tuning", "style-tuning.json"),
    ):
        path = _learning_root(repository_root) / filename
        if not path.is_file() and not events:
            continue
        try:
            profile = read_validated_json(repository_root, path, name)
        except PersistenceError as exc:
            raise LearningError(f"Learning profile is invalid: {filename}: {exc}") from exc
        if profile["sourceEventDigest"] != source_digest or profile["eventCount"] != len(events):
            raise LearningError(f"Learning profile is stale: {filename}")


def write_performance_report(
    context: ProjectContext, *, validated_cache_hits: list[str] | None = None
) -> list[str]:
    state = context.state_store.load()
    stages: list[dict[str, Any]] = []
    for stage in state.stages:
        duration = 0.0
        if stage.started_at is not None and stage.completed_at is not None:
            try:
                start = datetime.fromisoformat(stage.started_at)
                end = datetime.fromisoformat(stage.completed_at)
                duration = max(0.0, (end - start).total_seconds())
            except ValueError as exc:
                raise LearningError(f"Stage {stage.name} has invalid timing evidence.") from exc
        stages.append(
            {
                "name": stage.name,
                "attempts": stage.attempts,
                "durationSeconds": round(duration, 6),
            }
        )
    total = round(sum(float(item["durationSeconds"]) for item in stages), 6)
    prior: list[float] = []
    workspace = context.repository_root / "workspace"
    for path in workspace.glob("*/analysis/performance-report.json"):
        if path.parent.parent == context.project_dir:
            continue
        try:
            report = read_validated_json(context.repository_root, path, "performance-report")
        except PersistenceError:
            continue
        if report["mode"] == context.project["mode"]:
            prior.append(float(report["totalDurationSeconds"]))
    median = round(statistics.median(prior), 6) if prior else None
    improvement = (
        round((median - total) / median * 100, 6)
        if median is not None and median > 0 and math.isfinite(median)
        else None
    )
    report = {
        "version": 1,
        "projectId": context.project["projectId"],
        "generatedAt": _now(),
        "mode": context.project["mode"],
        "stages": stages,
        "totalDurationSeconds": total,
        "priorMedianSeconds": median,
        "improvementPercent": improvement,
        "validatedCacheHits": sorted(set(validated_cache_hits or [])),
        "artifactsRevalidated": True,
    }
    path = context.project_dir / "analysis" / "performance-report.json"
    write_validated_json_atomic(context.repository_root, path, "performance-report", report)
    return [path.relative_to(context.project_dir).as_posix()]


def validate_performance_report(context: ProjectContext) -> None:
    try:
        report = read_validated_json(
            context.repository_root,
            context.project_dir / "analysis" / "performance-report.json",
            "performance-report",
        )
    except PersistenceError as exc:
        raise LearningError(f"Performance report is missing or invalid: {exc}") from exc
    if report["projectId"] != context.project["projectId"]:
        raise LearningError("Performance report belongs to another project.")
    durations = [float(item["durationSeconds"]) for item in report["stages"]]
    if abs(sum(durations) - float(report["totalDurationSeconds"])) > 0.001:
        raise LearningError("Performance report stage timings do not match its total.")
