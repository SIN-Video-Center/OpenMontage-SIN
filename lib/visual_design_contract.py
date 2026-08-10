"""Deterministic visual-design gate for hero and overview productions.

This gate verifies that visual design happened before motion composition. It does
not attempt to judge taste; it checks that every scene has an explicit art/asset
strategy and that representative proof keyframes were actually rendered and
approved as files before a full hero/overview render may start.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_ALLOWED_STRATEGIES = {
    "source_capture",
    "svg_vector",
    "procedural_graphic",
    "vector_diagram",
    "raster_illustration",
    "ui_abstraction",
    "kinetic_typography",
    "3d_render",
    "video_source",
}


def _is_nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def validate_visual_design_plan(
    visual_design_plan: dict[str, Any] | None,
    scene_plan: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    quality_tier: str = "standard",
    video_category: str = "",
    require_files: bool = False,
) -> dict[str, Any]:
    active = str(quality_tier).lower() == "hero" or str(video_category).lower() == "overview-video"
    if not active:
        return {"active": False, "valid": True, "violations": [], "warnings": []}

    violations: list[str] = []
    warnings: list[str] = []
    if not isinstance(visual_design_plan, dict):
        return {
            "active": True,
            "valid": False,
            "violations": [
                "Hero/overview render requires a visual_design_plan produced before motion composition"
            ],
            "warnings": [],
        }

    if isinstance(scene_plan, dict):
        scenes = scene_plan.get("scenes") or []
    else:
        scenes = scene_plan or []
    expected_ids = [str(scene.get("id") or "").strip() for scene in scenes if str(scene.get("id") or "").strip()]

    identity = visual_design_plan.get("visual_identity") or {}
    for field in (
        "design_thesis",
        "surface_system",
        "typography_system",
        "light_system",
        "depth_system",
        "signature_device",
    ):
        if not _is_nonempty(identity.get(field)):
            violations.append(f"visual_identity.{field} is required")
    if not identity.get("restraint_rules"):
        violations.append("visual_identity.restraint_rules must record what the film refuses to do")

    designs = visual_design_plan.get("scene_designs") or []
    by_id = {
        str(item.get("scene_id") or "").strip(): item
        for item in designs
        if isinstance(item, dict) and str(item.get("scene_id") or "").strip()
    }
    missing = [scene_id for scene_id in expected_ids if scene_id not in by_id]
    extra = [scene_id for scene_id in by_id if scene_id not in expected_ids]
    if missing:
        violations.append("visual_design_plan is missing scene designs: " + ", ".join(missing))
    if extra:
        warnings.append("visual_design_plan contains scene designs not present in scene_plan: " + ", ".join(extra))

    proof_paths: list[str] = []
    for scene_id in expected_ids:
        design = by_id.get(scene_id)
        if not design:
            continue
        for field in ("visual_concept", "hero_object"):
            if not _is_nonempty(design.get(field)):
                violations.append(f"{scene_id}: {field} is required")

        composition = design.get("composition_blueprint") or {}
        for field in ("focal_zone", "negative_space", "foreground", "midground", "background", "evidence_legibility"):
            if not _is_nonempty(composition.get(field)):
                violations.append(f"{scene_id}: composition_blueprint.{field} is required")

        strategies = design.get("asset_strategy") or []
        if not strategies:
            violations.append(f"{scene_id}: asset_strategy must choose at least one designed visual medium")
        invalid = [value for value in strategies if value not in _ALLOWED_STRATEGIES]
        if invalid:
            violations.append(f"{scene_id}: unsupported asset_strategy values: {', '.join(invalid)}")
        if strategies == ["source_capture"]:
            warnings.append(
                f"{scene_id}: source_capture is the only asset strategy; verify the scene is art-directed rather than a raw screenshot in a frame"
            )

        art_assets = design.get("art_assets") or []
        if not art_assets:
            violations.append(f"{scene_id}: art_assets must describe the visual material built before motion")
        elif all((asset or {}).get("source_truth") == "decorative" for asset in art_assets if isinstance(asset, dict)):
            violations.append(f"{scene_id}: art_assets are decorative only; at least one asset must carry product/editorial meaning")

        keyframes = design.get("keyframes") or []
        proof = [frame for frame in keyframes if isinstance(frame, dict) and frame.get("moment") == "proof"]
        if not proof:
            violations.append(f"{scene_id}: at least one proof keyframe is required before motion authoring")
            continue
        approved = [frame for frame in proof if frame.get("status") == "approved"]
        if not approved:
            violations.append(f"{scene_id}: proof keyframe must be status='approved' before full render")
        for frame in approved:
            path_value = str(frame.get("output_path") or "").strip()
            if not path_value:
                violations.append(f"{scene_id}: approved proof keyframe has no output_path")
                continue
            proof_paths.append(path_value)
            if require_files and not Path(path_value).expanduser().is_file():
                violations.append(f"{scene_id}: approved proof keyframe file does not exist: {path_value}")

        motion = design.get("motion_blueprint") or {}
        for field in ("primary_action", "focus_transfer", "secondary_action", "transition_handoff", "settle_state"):
            if not _is_nonempty(motion.get(field)):
                violations.append(f"{scene_id}: motion_blueprint.{field} is required")

    board = visual_design_plan.get("keyframe_board") or {}
    if board.get("status") != "approved":
        violations.append("keyframe_board.status must be 'approved' before full hero/overview render")
    board_path = str(board.get("output_path") or "").strip()
    if not board_path:
        violations.append("keyframe_board.output_path is required")
    elif require_files and not Path(board_path).expanduser().is_file():
        violations.append(f"keyframe board file does not exist: {board_path}")
    board_ids = [str(value) for value in (board.get("scene_ids") or [])]
    if expected_ids and set(board_ids) != set(expected_ids):
        violations.append("keyframe_board.scene_ids must cover every scene exactly")

    return {
        "active": True,
        "valid": not violations,
        "violations": list(dict.fromkeys(violations)),
        "warnings": list(dict.fromkeys(warnings)),
        "scene_count": len(expected_ids),
        "approved_proof_keyframes": len(proof_paths),
    }
