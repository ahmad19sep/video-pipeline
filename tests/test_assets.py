from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from cutmachine.assets import (
    AssetError,
    PexelsAdapter,
    build_asset_requests,
    index_local_assets,
    load_asset_cache,
    local_candidates,
    rank_candidates,
)
from cutmachine.schemas import validate_document


def _request() -> dict[str, Any]:
    return {
        "id": "request_000001",
        "kind": "broll",
        "query": "student using AI laptop",
        "sceneId": "scene_000001",
        "orientation": "landscape",
        "targetDuration": 2.0,
        "optional": True,
    }


def test_asset_requests_reject_private_or_non_english_queries() -> None:
    plan = {
        "projectId": "prj_test",
        "video": {"width": 1920, "height": 1080, "durationInSeconds": 10},
        "globalAudio": {"musicAssetId": None, "musicQuery": None},
        "scenes": [
            {
                "id": "scene_000001",
                "start": 0,
                "end": 10,
                "broll": {"assetId": None, "query": "طالب علم"},
                "sfx": [],
            }
        ],
    }

    with pytest.raises(AssetError, match="short English visual phrase"):
        build_asset_requests(plan)


def test_deterministic_ranking_prefers_earliest_tier_then_candidate_id() -> None:
    request = _request()
    base = {
        "requestId": request["id"],
        "tier": "local",
        "provider": "local",
        "providerId": "broll/student-ai.mp4",
        "type": "video",
        "localPath": "broll/student-ai.mp4",
        "downloadUrl": None,
        "sourcePage": None,
        "creator": None,
        "license": "owned",
        "attributionRequired": False,
        "tags": ["student", "using", "ai", "laptop"],
        "duration": 2.0,
        "width": 1280,
        "height": 720,
        "orientation": "landscape",
        "watermark": False,
        "usageCount": 0,
    }
    later_id = {**base, "id": "candidate_z"}
    earlier_id = {**base, "id": "candidate_a"}
    provider = {
        **base,
        "id": "candidate_provider",
        "tier": "provider",
        "provider": "pexels",
        "providerId": "99",
        "downloadUrl": "https://cdn.example/video.mp4",
        "sourcePage": "https://www.pexels.com/video/99",
        "license": "Pexels License",
    }

    selected, evidence = rank_candidates(
        request, [later_id, provider, earlier_id], minimum_score=0.35
    )

    assert selected is not None
    assert selected["id"] == "candidate_a"
    assert evidence["tier"] == "local"
    assert evidence["scores"]["query"] == 1.0


def test_ranking_rejects_watermarks_and_unknown_licenses() -> None:
    request = _request()
    candidate = {
        "id": "candidate_bad",
        "requestId": request["id"],
        "tier": "local",
        "provider": "local",
        "providerId": "bad.mp4",
        "type": "video",
        "localPath": "bad.mp4",
        "downloadUrl": None,
        "sourcePage": None,
        "creator": None,
        "license": "unknown",
        "attributionRequired": False,
        "tags": ["student", "laptop"],
        "duration": 2.0,
        "width": 1280,
        "height": 720,
        "orientation": "landscape",
        "watermark": True,
        "usageCount": 0,
    }

    selected, evidence = rank_candidates(request, [candidate], minimum_score=0)

    assert selected is None
    assert evidence["status"] == "missing"


def test_ranking_moves_to_cache_when_local_candidates_are_irrelevant() -> None:
    request = _request()
    base = {
        "requestId": request["id"],
        "provider": "local",
        "providerId": "abstract.mp4",
        "type": "video",
        "downloadUrl": None,
        "sourcePage": None,
        "creator": None,
        "license": "owned",
        "attributionRequired": False,
        "duration": 2,
        "width": 1280,
        "height": 720,
        "orientation": "landscape",
        "watermark": False,
        "usageCount": 0,
    }
    local = {
        **base,
        "id": "candidate_local",
        "tier": "local",
        "localPath": "broll/abstract.mp4",
        "tags": ["abstract"],
    }
    cached = {
        **base,
        "id": "candidate_cache",
        "tier": "cache",
        "provider": "pexels",
        "providerId": "42",
        "localPath": ".cache/assets/objects/video.mp4",
        "sourcePage": "https://www.pexels.com/video/42",
        "license": "Pexels License",
        "tags": ["student", "using", "ai", "laptop"],
    }

    selected, evidence = rank_candidates(request, [local, cached], minimum_score=0.8)

    assert selected is not None and selected["id"] == "candidate_cache"
    assert evidence["tier"] == "cache"


def test_pexels_adapter_sends_only_bounded_query_and_validates_urls() -> None:
    captured: dict[str, Any] = {}

    def transport(url: str, headers: dict[str, str], timeout: int) -> dict[str, Any]:
        captured.update(url=url, headers=headers, timeout=timeout)
        return {
            "videos": [
                {
                    "id": 42,
                    "duration": 4,
                    "url": "https://www.pexels.com/video/42",
                    "user": {"name": "Creator"},
                    "video_files": [
                        {
                            "id": 7,
                            "file_type": "video/mp4",
                            "width": 1280,
                            "height": 720,
                            "link": "https://videos.pexels.com/video.mp4",
                        }
                    ],
                }
            ]
        }

    adapter = PexelsAdapter(
        "secret",
        "https://api.pexels.com/v1/videos/search",
        timeout_seconds=5,
        max_candidates=3,
        transport=transport,
    )
    candidates = adapter.search(_request())

    assert "student+using+AI+laptop" in captured["url"]
    assert "transcript" not in captured["url"]
    assert captured["headers"] == {"Authorization": "secret"}
    assert candidates[0]["provider"] == "pexels"
    assert candidates[0]["license"] == "Pexels License"

    def unsafe(_url: str, _headers: dict[str, str], _timeout: int) -> dict[str, Any]:
        value = transport("", {}, 0)
        value["videos"][0]["video_files"][0]["link"] = "http://unsafe/video.mp4"
        return value

    adapter.transport = unsafe
    with pytest.raises(AssetError, match="unsafe download URL"):
        adapter.search(_request())


def test_empty_local_index_is_valid(repository: Path) -> None:
    shutil.rmtree(
        repository / "assets-library" / "sfx" / "cutmachine-generated",
        ignore_errors=True,
    )
    index = index_local_assets(repository, repository / "assets-library")
    assert index["assets"] == []

    requests = {
        "version": 1,
        "projectId": "prj_test",
        "createdAt": "2026-07-15T12:00:00+00:00",
        "requests": [_request()],
    }
    assert local_candidates(requests, index) == []


def test_index_rejects_unknown_sidecar_fields(repository: Path) -> None:
    lut = repository / "assets-library" / "luts" / "owned.cube"
    lut.write_text("TITLE test\n", encoding="utf-8")
    lut.with_suffix(".cube.asset.json").write_text(
        json.dumps(
            {
                "tags": ["clean"],
                "license": "owned",
                "creator": None,
                "attributionRequired": False,
                "script": "run-me",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssetError, match="unknown fields: script"):
        index_local_assets(repository, repository / "assets-library")


def test_candidate_schema_rejects_traversal_and_remote_script_urls(
    repository: Path,
) -> None:
    request = _request()
    candidate = {
        "id": "candidate_bad",
        "requestId": request["id"],
        "tier": "local",
        "provider": "local",
        "providerId": "bad",
        "type": "video",
        "localPath": "../private.mp4",
        "downloadUrl": "javascript:alert(1)",
        "sourcePage": None,
        "creator": None,
        "license": "owned",
        "attributionRequired": False,
        "tags": ["bad"],
        "duration": 1,
        "width": 1280,
        "height": 720,
        "orientation": "landscape",
        "watermark": False,
        "usageCount": 0,
    }
    document = {
        "version": 1,
        "projectId": "prj_test",
        "createdAt": "2026-07-15T12:00:00+00:00",
        "candidates": [candidate],
    }

    errors = validate_document(repository, "asset-candidates", document)

    assert any("localPath" in error for error in errors)
    assert any("downloadUrl" in error for error in errors)


def test_invalid_cache_path_is_discarded_without_file_access(repository: Path) -> None:
    path = repository / ".cache" / "assets" / "cache.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "updatedAt": "2026-07-15T12:00:00+00:00",
                "entries": [
                    {
                        "key": "a" * 64,
                        "provider": "pexels",
                        "providerId": "42",
                        "objectPath": "../../private.mp4",
                        "sha256": "b" * 64,
                        "sourcePage": "https://www.pexels.com/video/42",
                        "creator": None,
                        "license": "Pexels License",
                        "attributionRequired": True,
                        "type": "video",
                        "tags": ["student"],
                        "duration": 2,
                        "width": 1280,
                        "height": 720,
                        "orientation": "landscape",
                        "cachedAt": "2026-07-15T12:00:00+00:00",
                        "expiresAt": "2099-07-15T12:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_asset_cache(repository)["entries"] == []
