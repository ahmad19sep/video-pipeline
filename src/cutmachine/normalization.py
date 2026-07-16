"""Deterministic Roman Urdu normalization with an optional validated refiner."""

from __future__ import annotations

import json
import math
import os
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from cutmachine.config import load_config
from cutmachine.learning import approved_caption_corrections
from cutmachine.paths import UnsafePathError, resolve_inside, validate_relative_path
from cutmachine.persistence import (
    PersistenceError,
    read_validated_json,
    write_validated_json_atomic,
)
from cutmachine.project import ProjectContext


class NormalizationError(RuntimeError):
    """Raised when transcript normalization crosses an invalid boundary."""


class RefinementAdapter(Protocol):
    """A bounded word-for-word optional refinement provider."""

    @property
    def name(self) -> str: ...

    def refine(self, words: list[dict[str, object]]) -> object: ...


class HttpsJsonRefinementAdapter:
    """POST the documented word contract to an explicitly configured HTTPS endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: int,
        api_key: str | None = None,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise NormalizationError(
                "Refinement endpoint must be an HTTPS URL without credentials."
            )
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._name = f"https:{parsed.hostname}"

    @property
    def name(self) -> str:
        return self._name

    def refine(self, words: list[dict[str, object]]) -> object:
        payload = json.dumps({"version": 1, "words": words}, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self._endpoint,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read(1_000_001)
        except (OSError, urllib.error.URLError) as exc:
            raise NormalizationError(f"Refinement request failed: {exc}") from exc
        if len(body) > 1_000_000:
            raise NormalizationError("Refinement response exceeds the 1 MB limit.")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NormalizationError("Refinement endpoint returned invalid UTF-8 JSON.") from exc


AdapterFactory = Callable[[dict[str, Any]], RefinementAdapter]

_URDU_MIN = "\u0600"
_URDU_MAX = "\u06ff"
_TRANSLITERATION = {
    "\u0627": "a",
    "آ": "aa",
    "أ": "a",
    "إ": "i",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ٹ": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ڈ": "d",
    "ذ": "z",
    "ر": "r",
    "ڑ": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ں": "n",
    "و": "o",
    "ؤ": "o",
    "ۓ": "e",
    # Extended Arabic-Indic (Urdu) digits U+06F0-U+06F9.
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
    # Arabic-Indic digits U+0660-U+0669.
    "٠": "0",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
    "\u06c1": "h",
    "\u06be": "h",
    "ۃ": "h",
    "ء": "",
    "ی": "i",
    "ي": "i",
    "ے": "e",
    "ئ": "y",
}


def _read_config_object(root: Path, raw_path: object, label: str) -> tuple[dict[str, Any], str]:
    if not isinstance(raw_path, str):
        raise NormalizationError(f"{label} path must be a repository-relative string.")
    try:
        relative = validate_relative_path(raw_path).as_posix()
        path = resolve_inside(root, relative)
    except UnsafePathError as exc:
        raise NormalizationError(f"Unsafe {label} path: {exc}") from exc
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NormalizationError(f"Could not load {label} at {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise NormalizationError(f"{label} root must be an object: {relative}")
    return cast(dict[str, Any], value), relative


def _load_glossary(root: Path, raw_path: object) -> tuple[dict[str, str], str]:
    value, relative = _read_config_object(root, raw_path, "technical glossary")
    if value.get("version") != 1:
        raise NormalizationError("Technical glossary version must be 1.")
    terms = value.get("terms")
    aliases = value.get("aliases", {})
    if not isinstance(terms, list) or not all(
        isinstance(term, str) and term.strip() for term in terms
    ):
        raise NormalizationError("Technical glossary terms must be non-empty strings.")
    if not isinstance(aliases, dict) or not all(
        isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
        for key, item in aliases.items()
    ):
        raise NormalizationError("Technical glossary aliases must map non-empty strings.")
    canonical = {cast(str, term).casefold(): cast(str, term) for term in terms}
    allowed = set(canonical.values())
    for key, item in cast(dict[str, str], aliases).items():
        if item not in allowed:
            raise NormalizationError(f"Glossary alias {key!r} targets unknown term {item!r}.")
        canonical[key.casefold()] = item
    return canonical, relative


def _load_lexicon(root: Path, raw_path: object) -> tuple[dict[str, str], str]:
    value, relative = _read_config_object(root, raw_path, "Roman Urdu lexicon")
    mappings = value.get("mappings")
    if value.get("version") != 1 or not isinstance(mappings, dict):
        raise NormalizationError("Roman Urdu lexicon must contain version 1 mappings.")
    if not all(
        isinstance(key, str)
        and key.strip()
        and isinstance(item, str)
        and item.strip()
        and "\n" not in item
        for key, item in mappings.items()
    ):
        raise NormalizationError("Roman Urdu mappings must use non-empty single-line strings.")
    folded = {key.casefold(): item for key, item in cast(dict[str, str], mappings).items()}
    return folded, relative


def _is_boundary_character(character: str) -> bool:
    return unicodedata.category(character)[0] in {"P", "S"}


def _split_boundaries(token: str) -> tuple[str, str, str]:
    start = 0
    end = len(token)
    while start < end and _is_boundary_character(token[start]):
        start += 1
    while end > start and _is_boundary_character(token[end - 1]):
        end -= 1
    return token[:start], token[start:end], token[end:]


def _contains_urdu(value: str) -> bool:
    return any(_URDU_MIN <= character <= _URDU_MAX for character in value)


def _transliterate(value: str) -> str:
    pieces: list[str] = []
    for index, character in enumerate(value):
        # Word-initial waw is the consonant "w" (wala, waqt), not the vowel "o".
        if character == "و" and index == 0 and len(value) > 1:
            pieces.append("w")
            continue
        mapped = _TRANSLITERATION.get(character)
        if mapped is not None:
            pieces.append(mapped)
        elif unicodedata.category(character) == "Mn":
            continue
        else:
            pieces.append(character)
    return "".join(pieces)


def _normalize_word(
    raw_word: dict[str, Any],
    glossary: dict[str, str],
    lexicon: dict[str, str],
    corrections: list[dict[str, Any]],
    context: set[str],
) -> dict[str, Any]:
    raw = cast(str, raw_word["raw"])
    prefix, core, suffix = _split_boundaries(raw)
    lookup = core.casefold()
    confidence = float(raw_word["confidence"])
    if lookup in glossary:
        display = f"{prefix}{glossary[lookup]}{suffix}"
        normalization_source = "technical-glossary"
        confidence = min(confidence, 0.98)
    elif approved := sorted(
        (
            item
            for item in corrections
            if _split_boundaries(cast(str, item["heard"]))[1].casefold() == lookup
            and (not item["context"] or context.intersection(cast(list[str], item["context"])))
        ),
        key=lambda item: (
            -len(context.intersection(cast(list[str], item["context"]))),
            -int(item["approvedCount"]),
            cast(str, item["preferred"]).casefold(),
        ),
    ):
        display = f"{prefix}{approved[0]['preferred']}{suffix}"
        normalization_source = "approved-correction"
        confidence = min(confidence, 0.99)
    elif lookup in lexicon:
        display = f"{prefix}{lexicon[lookup]}{suffix}"
        normalization_source = "local-lexicon"
        confidence = min(confidence, 0.95)
    elif not _contains_urdu(core):
        display = raw
        normalization_source = "preserved"
    else:
        converted = _transliterate(core).strip()
        if not converted or _contains_urdu(converted):
            display = raw
            normalization_source = "preserved"
            confidence = min(confidence, 0.5)
        else:
            display = f"{prefix}{converted}{suffix}"
            normalization_source = "deterministic-transliteration"
            confidence = min(confidence, 0.72)
    return {
        **raw_word,
        "display": display,
        "confidence": round(confidence, 6),
        "normalizationSource": normalization_source,
    }


def _default_adapter_factory(config: dict[str, Any]) -> RefinementAdapter:
    endpoint = config.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise NormalizationError("Enabled refinement requires a configured HTTPS endpoint.")
    key_name = config.get("api_key_env")
    if key_name is not None and (not isinstance(key_name, str) or not key_name):
        raise NormalizationError("Refinement api_key_env must be null or a variable name.")
    api_key = os.environ.get(key_name) if isinstance(key_name, str) else None
    return HttpsJsonRefinementAdapter(
        endpoint,
        timeout_seconds=int(config["timeout_seconds"]),
        api_key=api_key,
    )


def _validated_refinement(response: object, expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or set(response) != {"version", "words"}:
        raise NormalizationError("Refinement response must contain only version and words.")
    if response.get("version") != 1 or not isinstance(response.get("words"), list):
        raise NormalizationError("Refinement response must use version 1 and a words array.")
    returned = cast(list[object], response["words"])
    if len(returned) != len(expected):
        raise NormalizationError("Refinement changed the batch word count.")
    results: list[dict[str, Any]] = []
    for source, item in zip(expected, returned, strict=True):
        if not isinstance(item, dict) or set(item) - {"id", "display", "confidence"}:
            raise NormalizationError("Refinement word objects contain unsupported fields.")
        if item.get("id") != source["id"]:
            raise NormalizationError("Refinement changed word order or identifiers.")
        display = item.get("display")
        if not isinstance(display, str) or not display.strip() or "\n" in display:
            raise NormalizationError("Refinement displays must be non-empty single-line strings.")
        confidence_value = item.get("confidence", source["confidence"])
        try:
            confidence = float(cast(str | int | float, confidence_value))
        except (TypeError, ValueError) as exc:
            raise NormalizationError("Refinement confidence must be numeric.") from exc
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise NormalizationError("Refinement confidence must be between zero and one.")
        results.append(
            {
                **source,
                "display": display.strip(),
                "confidence": round(min(float(source["confidence"]), confidence), 6),
                "normalizationSource": "external-refinement",
            }
        )
    return results


def _apply_refinement(
    words: list[dict[str, Any]],
    refinement_config: dict[str, Any],
    adapter: RefinementAdapter,
    *,
    batch_size: int,
    retries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    eligible_indexes = [
        index
        for index, word in enumerate(words)
        if word["normalizationSource"] in {"local-lexicon", "deterministic-transliteration"}
    ]
    output = [dict(word) for word in words]
    attempted = 0
    applied = 0
    failed = 0
    warnings: list[str] = []
    for offset in range(0, len(eligible_indexes), batch_size):
        indexes = eligible_indexes[offset : offset + batch_size]
        batch = [output[index] for index in indexes]
        request_words = [
            {
                "id": word["id"],
                "raw": word["raw"],
                "display": word["display"],
            }
            for word in batch
        ]
        attempted += 1
        last_error: Exception | None = None
        for _attempt in range(retries + 1):
            try:
                refined = _validated_refinement(adapter.refine(request_words), batch)
                for index, word in zip(indexes, refined, strict=True):
                    output[index] = word
                applied += 1
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            failed += 1
            warnings.append(f"Refinement batch {attempted} fell back to local output: {last_error}")
    provenance = {
        "enabled": bool(refinement_config["enabled"]),
        "attemptedBatches": attempted,
        "appliedBatches": applied,
        "failedBatches": failed,
        "provider": adapter.name,
    }
    return output, provenance, warnings


def normalize_project(
    context: ProjectContext,
    *,
    adapter_factory: AdapterFactory = _default_adapter_factory,
) -> list[str]:
    config = load_config(context.repository_root, style=cast(str, context.project["mode"]))
    normalization_config = cast(dict[str, Any], config["normalization"])
    try:
        threshold = float(normalization_config["low_confidence_threshold"])
        batch_size = int(normalization_config["batch_size"])
        refinement_config = cast(dict[str, Any], normalization_config["refinement"])
        retries = int(refinement_config["retries"])
        timeout_seconds = int(refinement_config["timeout_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NormalizationError("Normalization limits are missing or invalid.") from exc
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise NormalizationError("Normalization confidence threshold must be between 0 and 1.")
    if not 1 <= batch_size <= 500:
        raise NormalizationError("Normalization batch size must be between 1 and 500.")
    if not 0 <= retries <= 5:
        raise NormalizationError("Refinement retries must be between 0 and 5.")
    if not 1 <= timeout_seconds <= 120:
        raise NormalizationError("Refinement timeout must be between 1 and 120 seconds.")
    glossary, glossary_path = _load_glossary(
        context.repository_root, normalization_config.get("glossary_path")
    )
    lexicon, lexicon_path = _load_lexicon(
        context.repository_root, normalization_config.get("lexicon_path")
    )
    raw_path = context.project_dir / "transcript" / "transcript.raw.json"
    try:
        raw_document = read_validated_json(context.repository_root, raw_path, "transcript")
    except PersistenceError as exc:
        raise NormalizationError(f"Raw transcript is missing or invalid: {exc}") from exc
    raw_words = cast(list[dict[str, Any]], raw_document["words"])
    corrections = approved_caption_corrections(context.repository_root)
    words = []
    for index, word in enumerate(raw_words):
        context_terms = {
            _split_boundaries(cast(str, raw_words[item]["raw"]))[1].casefold()
            for item in range(max(0, index - 2), min(len(raw_words), index + 3))
            if item != index
        }
        words.append(_normalize_word(word, glossary, lexicon, corrections, context_terms))

    refinement = {
        "enabled": bool(refinement_config["enabled"]),
        "attemptedBatches": 0,
        "appliedBatches": 0,
        "failedBatches": 0,
        "provider": None,
    }
    warnings: list[str] = []
    network_enabled = bool(cast(dict[str, Any], config["network"])["enabled"]) and bool(
        cast(dict[str, Any], context.project["settings"])["networkEnabled"]
    )
    if bool(refinement_config["enabled"]) and network_enabled:
        adapter = adapter_factory(refinement_config)
        words, refinement, warnings = _apply_refinement(
            words,
            refinement_config,
            adapter,
            batch_size=batch_size,
            retries=retries,
        )
    elif bool(refinement_config["enabled"]):
        warnings.append("Refinement was configured but network use is disabled; used local output.")

    word_by_id = {cast(str, word["id"]): word for word in words}
    segments: list[dict[str, Any]] = []
    for segment in cast(list[dict[str, Any]], raw_document["segments"]):
        word_ids = cast(list[str], segment["wordIds"])
        text = " ".join(cast(str, word_by_id[word_id]["display"]) for word_id in word_ids)
        segments.append({**segment, "text": text or segment["text"]})

    created_at = datetime.now(UTC).isoformat()
    document: dict[str, Any] = {
        "version": 1,
        "projectId": raw_document["projectId"],
        "language": raw_document["language"],
        "displayLanguage": "roman-urdu",
        "durationSeconds": raw_document["durationSeconds"],
        "segments": segments,
        "words": words,
        "provenance": {
            "createdAt": created_at,
            "rawTranscriptPath": "transcript/transcript.raw.json",
            "glossaryPath": glossary_path,
            "lexiconPath": lexicon_path,
            "refinement": refinement,
            "wordCountPreserved": True,
            "timingPreserved": True,
        },
    }
    output_path = context.project_dir / "transcript" / "transcript.roman.json"
    write_validated_json_atomic(
        context.repository_root, output_path, "normalized-transcript", document
    )

    counts = Counter(cast(str, word["normalizationSource"]) for word in words)
    low_confidence = [
        {
            "id": word["id"],
            "raw": word["raw"],
            "display": word["display"],
            "confidence": word["confidence"],
        }
        for word in words
        if float(word["confidence"]) < threshold
    ]
    report = {
        "version": 1,
        "projectId": context.project["projectId"],
        "generatedAt": created_at,
        "lowConfidenceThreshold": threshold,
        "counts": {
            "words": len(words),
            "preserved": counts["preserved"],
            "technicalGlossary": counts["technical-glossary"],
            "approvedCorrections": counts["approved-correction"],
            "localLexicon": counts["local-lexicon"],
            "transliterated": counts["deterministic-transliteration"],
            "externallyRefined": counts["external-refinement"],
        },
        "lowConfidenceWords": low_confidence,
        "warnings": warnings,
    }
    report_path = context.project_dir / "analysis" / "transcript-normalization-report.json"
    write_validated_json_atomic(
        context.repository_root, report_path, "normalization-report", report
    )
    validate_normalized_outputs(context)
    return [
        output_path.relative_to(context.project_dir).as_posix(),
        report_path.relative_to(context.project_dir).as_posix(),
    ]


def validate_normalized_outputs(context: ProjectContext) -> None:
    raw_path = context.project_dir / "transcript" / "transcript.raw.json"
    normalized_path = context.project_dir / "transcript" / "transcript.roman.json"
    report_path = context.project_dir / "analysis" / "transcript-normalization-report.json"
    try:
        raw = read_validated_json(context.repository_root, raw_path, "transcript")
        normalized = read_validated_json(
            context.repository_root, normalized_path, "normalized-transcript"
        )
        report = read_validated_json(context.repository_root, report_path, "normalization-report")
    except PersistenceError as exc:
        raise NormalizationError(f"Normalized transcript artifacts are invalid: {exc}") from exc
    if (
        normalized["projectId"] != context.project["projectId"]
        or report["projectId"] != context.project["projectId"]
    ):
        raise NormalizationError("Normalized transcript artifacts belong to another project.")
    if normalized["durationSeconds"] != raw["durationSeconds"]:
        raise NormalizationError("Normalization changed transcript duration.")
    raw_segments = cast(list[dict[str, Any]], raw["segments"])
    normalized_segments = cast(list[dict[str, Any]], normalized["segments"])
    raw_words = cast(list[dict[str, Any]], raw["words"])
    normalized_words = cast(list[dict[str, Any]], normalized["words"])
    if len(raw_segments) != len(normalized_segments) or len(raw_words) != len(normalized_words):
        raise NormalizationError("Normalization changed segment or word count.")
    for raw_segment, normalized_segment in zip(raw_segments, normalized_segments, strict=True):
        for field in ("id", "start", "end", "wordIds"):
            if normalized_segment[field] != raw_segment[field]:
                raise NormalizationError(f"Normalization changed segment {field}.")
    for raw_word, normalized_word in zip(raw_words, normalized_words, strict=True):
        for field in ("id", "segmentId", "start", "end", "raw", "source", "lockedTiming"):
            if normalized_word[field] != raw_word[field]:
                raise NormalizationError(
                    f"Normalization changed immutable word field {field} at {raw_word['id']}."
                )
    counts = Counter(cast(str, word["normalizationSource"]) for word in normalized_words)
    expected_counts = {
        "words": len(normalized_words),
        "preserved": counts["preserved"],
        "technicalGlossary": counts["technical-glossary"],
        "approvedCorrections": counts["approved-correction"],
        "localLexicon": counts["local-lexicon"],
        "transliterated": counts["deterministic-transliteration"],
        "externallyRefined": counts["external-refinement"],
    }
    if report["counts"] != expected_counts:
        raise NormalizationError("Normalization report counts do not match the transcript.")
    threshold = float(report["lowConfidenceThreshold"])
    expected_low_confidence = [
        {
            "id": word["id"],
            "raw": word["raw"],
            "display": word["display"],
            "confidence": word["confidence"],
        }
        for word in normalized_words
        if float(word["confidence"]) < threshold
    ]
    if report["lowConfidenceWords"] != expected_low_confidence:
        raise NormalizationError("Normalization report confidence findings are stale or invalid.")
