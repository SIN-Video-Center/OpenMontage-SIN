import json
from pathlib import Path

from tools.video.video_compose import VideoCompose

ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / "artifacts" / name).read_text())


def test_category_registry_activates_only_overview_video():
    registry = json.loads((ROOT / "schemas" / "video_categories.registry.json").read_text())
    assert registry["active_categories"] == ["overview-video"]
    assert registry["categories"]["overview-video"]["status"] == "active"
    assert registry["categories"]["tutorial"]["status"] == "planned"


def test_category_is_supported_across_proposal_scene_edit_and_review_contracts():
    proposal = _schema("proposal_packet.schema.json")
    scene = _schema("scene_plan.schema.json")
    edit = _schema("edit_decisions.schema.json")
    review = _schema("final_review.schema.json")
    assert proposal["properties"]["production_plan"]["properties"]["video_category"]["enum"] == ["overview-video"]
    assert scene["properties"]["video_category"]["enum"] == ["overview-video"]
    assert edit["properties"]["video_category"]["enum"] == ["overview-video"]
    promise = review["properties"]["checks"]["properties"]["promise_preservation"]["properties"]
    assert "video_category_used" in promise
    assert "category_contract_honored" in promise


def test_overview_video_requires_integrated_caption_field_without_full_width_bar():
    edit = {
        "video_category": "overview-video",
        "renderer_family": "bespoke",
        "composition_mode": "atelier",
        "render_runtime": "remotion",
        "subtitles": {
            "enabled": True,
            "language_code": "de-DE",
            "unicode_normalization": "NFC",
            "layout_policy": "reserved-rail",
            "visual_treatment": "surface",
            "full_width_background": True,
            "preferred_zone": "bottom",
            "safe_margin_px": 56,
            "reserved_rail_height_ratio": 0.17,
            "protected_regions": [{
                "id": "scene-main", "scene_id": "scene-1",
                "x": 0.05, "y": 0.05, "width": 0.9, "height": 0.72,
                "start_ms": 0, "end_ms": 5000,
            }],
        },
    }
    scene = {
        "video_category": "overview-video",
        "quality_tier": "hero",
        "delivery_kind": "bespoke",
        "motion_expectation": "motion_led",
        "scenes": [{
            "id": "scene-1", "type": "animation", "description": "Evidence flow",
            "start_seconds": 0, "end_seconds": 5,
            "primary_subject": "Evidence flow", "visual_state_before": "Raw source",
            "visual_action": "Source becomes a traceable claim", "visual_state_after": "Verified claim",
            "motion_class": "procedural_semantic_motion", "semantic_purpose": "Show provenance",
            "keyframe_contract": {
                "focal_subject": "Verified source passage",
                "hierarchy": "Source passage first, claim second, chrome recessed",
                "proof_frame": "Claim is visibly connected to the original passage",
                "still_quality_goal": "premium-keyvisual",
            },
            "focus_path": {
                "entry": "Enter on the claim", "action": "Follow the source link",
                "proof": "Land on the original passage", "exit": "Carry focus into the next evidence beat",
            },
            "motion_hierarchy": {
                "primary": "Source link connects claim to original passage",
                "secondary": "Camera reframes toward the passage",
                "ambient": "Background light remains subordinate",
                "settle": "Passage holds readable after the link resolves",
            },
            "protected_regions": [{"id": "main", "x": 0.05, "y": 0.05, "width": 0.9, "height": 0.72}],
            "caption_layout": {"preferred_zone": "bottom"},
        }],
    }
    result = VideoCompose()._pre_compose_validation(edit, [{
        "id": "scene-1", "type": "animation", "in_seconds": 0, "out_seconds": 5,
        "motion_class": "procedural_semantic_motion",
        "visual_state_before": "Raw source", "visual_action": "Source becomes a traceable claim",
        "visual_state_after": "Verified claim", "semantic_purpose": "Show provenance",
    }], scene, "Quellen werden zu überprüfbaren Aussagen.")
    assert result is not None and result.success is False
    assert "integrated-field" in (result.error or "")
    assert "full-width" in (result.error or "")
