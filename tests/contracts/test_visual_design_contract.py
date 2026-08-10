import json
from pathlib import Path

import jsonschema

from lib.visual_design_contract import validate_visual_design_plan

ROOT = Path(__file__).resolve().parents[2]


def _scene_plan() -> dict:
    return {
        "quality_tier": "hero",
        "video_category": "overview-video",
        "scenes": [
            {"id": "s1"},
            {"id": "s2"},
        ],
    }


def _design(tmp_path: Path) -> dict:
    s1 = tmp_path / "s1-proof.png"
    s2 = tmp_path / "s2-proof.png"
    board = tmp_path / "board.jpg"
    for path in (s1, s2, board):
        path.write_bytes(b"proof")

    def scene(scene_id: str, proof: Path, strategy: list[str]) -> dict:
        return {
            "scene_id": scene_id,
            "visual_concept": f"Directed visual concept for {scene_id}",
            "hero_object": f"Hero object {scene_id}",
            "composition_blueprint": {
                "focal_zone": "upper-right product evidence",
                "negative_space": "left editorial breathing field",
                "foreground": "precise evidence highlight",
                "midground": "product surface",
                "background": "low-contrast atmosphere",
                "evidence_legibility": "proof region readable at 1080p",
            },
            "asset_strategy": strategy,
            "art_assets": [
                {
                    "id": f"{scene_id}-evidence",
                    "kind": strategy[0],
                    "purpose": "Carry the primary product proof",
                    "source_truth": "product_evidence" if strategy[0] == "source_capture" else "derived_from_product",
                }
            ],
            "keyframes": [
                {
                    "moment": "proof",
                    "frame_goal": "Premium paused frame",
                    "focal_subject": f"Hero object {scene_id}",
                    "hierarchy": "hero first, support second, background recessed",
                    "output_path": str(proof),
                    "status": "approved",
                }
            ],
            "motion_blueprint": {
                "primary_action": "Evidence changes state",
                "focus_transfer": "Attention moves from claim to proof",
                "secondary_action": "Camera reframes after the semantic action",
                "transition_handoff": "Proof geometry carries into next scene",
                "settle_state": "Proof holds readable",
            },
        }

    return {
        "version": "1.0",
        "quality_tier": "hero",
        "video_category": "overview-video",
        "visual_identity": {
            "design_thesis": "Editorial product evidence with restrained cinematic depth",
            "surface_system": "One product surface family with restrained edges",
            "typography_system": "Large editorial claims yielding to evidence",
            "light_system": "Local contrast guides focus",
            "depth_system": "Foreground evidence, midground product, quiet atmosphere",
            "signature_device": "Evidence trace used only at key proof beats",
            "restraint_rules": ["No generic browser chrome", "No decorative card stacks"],
        },
        "scene_designs": [
            scene("s1", s1, ["source_capture", "svg_vector"]),
            scene("s2", s2, ["ui_abstraction", "procedural_graphic"]),
        ],
        "keyframe_board": {
            "output_path": str(board),
            "status": "approved",
            "scene_ids": ["s1", "s2"],
        },
    }


def test_visual_design_schema_accepts_complete_plan(tmp_path: Path):
    schema = json.loads((ROOT / "schemas" / "artifacts" / "visual_design_plan.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(_design(tmp_path))


def test_hero_visual_design_requires_real_approved_proof_files(tmp_path: Path):
    plan = _design(tmp_path)
    result = validate_visual_design_plan(
        plan,
        _scene_plan(),
        quality_tier="hero",
        video_category="overview-video",
        require_files=True,
    )
    assert result["valid"] is True
    assert result["approved_proof_keyframes"] == 2


def test_missing_visual_design_plan_blocks_hero():
    result = validate_visual_design_plan(
        None,
        _scene_plan(),
        quality_tier="hero",
        video_category="overview-video",
        require_files=True,
    )
    assert result["valid"] is False
    assert any("visual_design_plan" in issue for issue in result["violations"])


def test_missing_proof_file_blocks_full_render(tmp_path: Path):
    plan = _design(tmp_path)
    Path(plan["scene_designs"][0]["keyframes"][0]["output_path"]).unlink()
    result = validate_visual_design_plan(
        plan,
        _scene_plan(),
        quality_tier="hero",
        video_category="overview-video",
        require_files=True,
    )
    assert result["valid"] is False
    assert any("does not exist" in issue for issue in result["violations"])
