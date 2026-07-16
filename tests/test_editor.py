from __future__ import annotations

import json
import shutil

import pytest

from cutmachine.assets import prepare_assets
from cutmachine.editor import (
    EditorError,
    current_editor_settings,
    load_editor_request,
    prepare_editor_mutation,
    register_owned_broll,
    stage_editor_upload,
    write_cowork_request,
    write_editor_documents,
)
from cutmachine.persistence import read_validated_json
from cutmachine.planning import apply_revision_document
from cutmachine.project import ProjectContext


def test_editor_caption_and_graphics_only_settings_are_typed(
    planned_context: ProjectContext,
) -> None:
    initial = current_editor_settings(planned_context)

    mutation = prepare_editor_mutation(
        planned_context,
        {
            "captionsEnabled": False,
            "captionPreset": "clean-two-line",
            "brollMode": "graphics-only",
            "pins": [],
        },
    )
    assert mutation.invalidate_from == "plan_ready"
    assert mutation.revision is not None
    write_editor_documents(planned_context, mutation)
    apply_revision_document(planned_context, mutation.revision)
    plan = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / "planning" / "edit-plan.json",
        "edit-plan",
    )

    assert initial["captionsEnabled"] is True
    assert plan["captions"]["enabled"] is False
    assert plan["style"]["captionPreset"] == "clean-two-line"
    assert all(scene["broll"]["query"] is None for scene in plan["scenes"])
    assert (
        read_validated_json(
            planned_context.repository_root,
            planned_context.project_dir / "planning" / "asset-pins.json",
            "asset-pins",
        )["pins"]
        == []
    )


def test_editor_rejects_unknown_fields_and_non_manual_pins(
    planned_context: ProjectContext,
) -> None:
    base = {
        "captionsEnabled": True,
        "captionPreset": "roman-word-highlight",
        "brollMode": "auto",
        "pins": [],
    }
    with pytest.raises(EditorError, match="unknown fields"):
        prepare_editor_mutation(planned_context, {**base, "command": "calc.exe"})
    with pytest.raises(EditorError, match="only in manual mode"):
        prepare_editor_mutation(
            planned_context,
            {
                **base,
                "pins": [
                    {
                        "sceneId": "scene_000001",
                        "localAssetId": "local_" + "a" * 16,
                    }
                ],
            },
        )


def test_editor_registers_decodable_owned_broll_and_cowork_handoff(
    planned_context: ProjectContext,
) -> None:
    upload_root = planned_context.repository_root / ".cache" / "editor-uploads"
    upload_root.mkdir(parents=True)
    upload = upload_root / "bounded-upload.mov"
    shutil.copy2(planned_context.project_dir / "media" / "proxy.mp4", upload)

    asset = register_owned_broll(
        planned_context,
        upload,
        "My phone demo.MOV",
        "phone app demo",
    )
    prepare_assets(planned_context)
    artifacts = write_cowork_request(
        planned_context,
        "Use my phone demo for the product scene and keep captions readable.",
    )
    request = read_validated_json(
        planned_context.repository_root,
        planned_context.project_dir / artifacts[0],
        "cowork-editor-request",
    )

    assert asset["id"].startswith("local_")
    assert asset["license"] == "owned"
    assert set(asset["tags"]) >= {"phone", "app", "demo"}
    assert request["constraints"]["allowExecutableContent"] is False
    assert request["outputPath"] == "planning/cowork-editor-revision.json"


def test_editor_rejects_upload_outside_controlled_directory(
    planned_context: ProjectContext,
) -> None:
    with pytest.raises(EditorError, match="outside the controlled"):
        register_owned_broll(
            planned_context,
            planned_context.project_dir / "media" / "proxy.mp4",
            "unsafe.mp4",
            "unsafe",
        )


def test_editor_request_loader_is_path_safe_and_typed(
    planned_context: ProjectContext,
) -> None:
    request_path = planned_context.project_dir / "planning" / "editor-request.json"
    request_path.write_text(
        json.dumps(
            {
                "captionsEnabled": True,
                "captionPreset": "clean-two-line",
                "brollMode": "auto",
                "pins": [],
            }
        ),
        encoding="utf-8",
    )

    payload = load_editor_request(planned_context, "planning/editor-request.json")
    assert payload["captionPreset"] == "clean-two-line"

    with pytest.raises(EditorError, match="unsafe"):
        load_editor_request(planned_context, "../outside.json")
    with pytest.raises(EditorError, match="missing"):
        load_editor_request(planned_context, "planning/does-not-exist.json")
    array_path = planned_context.project_dir / "planning" / "editor-array.json"
    array_path.write_text("[]", encoding="utf-8")
    with pytest.raises(EditorError, match="JSON object"):
        load_editor_request(planned_context, "planning/editor-array.json")


def test_stage_editor_upload_copies_into_controlled_directory(
    planned_context: ProjectContext,
) -> None:
    source = planned_context.project_dir / "media" / "proxy.mp4"
    staged = stage_editor_upload(planned_context.repository_root, source)
    try:
        upload_root = planned_context.repository_root / ".cache" / "editor-uploads"
        assert staged.is_file()
        assert staged.parent == upload_root
        assert staged.read_bytes() == source.read_bytes()
        registered = register_owned_broll(planned_context, staged, source.name, "staging test")
        assert registered["license"] == "owned"
    finally:
        staged.unlink(missing_ok=True)

    with pytest.raises(EditorError, match="does not exist"):
        stage_editor_upload(
            planned_context.repository_root,
            planned_context.project_dir / "media" / "missing.mp4",
        )
