import copy

from lib.premium_visual_contract import validate_premium_scene_plan
from tools.video.video_compose import VideoCompose


def _scene(scene_id: str = "s1", focal: str = "source citation") -> dict:
    return {
        "id": scene_id,
        "type": "animation",
        "description": "Trace the claim to its source",
        "start_seconds": 0,
        "end_seconds": 5,
        "primary_subject": focal,
        "visual_state_before": "Claim is visible",
        "visual_action": "Citation connects the claim to the source passage",
        "visual_state_after": "Source passage is the proof state",
        "motion_class": "procedural_semantic_motion",
        "semantic_purpose": "Show provenance",
        "keyframe_contract": {
            "focal_subject": focal,
            "hierarchy": "Citation first, answer second, chrome recessed",
            "proof_frame": "Source passage is visibly connected to the claim",
            "still_quality_goal": "premium-keyvisual",
        },
        "focus_path": {
            "entry": "Enter on the claim",
            "action": "Follow the citation link",
            "proof": "Land on the source passage",
            "exit": "Carry the passage edge into the next beat",
        },
        "motion_hierarchy": {
            "primary": "Citation travels from claim to source passage",
            "secondary": "Camera reframes toward the source",
            "ambient": "Background luminance breathes below focal priority",
            "settle": "Source passage holds readable for 18 frames",
        },
        "hero_moment": True,
    }


def test_standard_work_does_not_require_premium_contract():
    result = validate_premium_scene_plan([{"id": "draft"}], quality_tier="standard")
    assert result["active"] is False
    assert result["valid"] is True


def test_hero_work_blocks_missing_frame_focus_and_motion_contracts():
    scene = _scene()
    scene.pop("keyframe_contract")
    scene.pop("focus_path")
    scene.pop("motion_hierarchy")
    result = validate_premium_scene_plan([scene], quality_tier="hero")
    assert result["active"] is True
    assert result["valid"] is False
    joined = " | ".join(result["violations"])
    assert "keyframe_contract" in joined
    assert "focus_path" in joined
    assert "motion_hierarchy" in joined


def test_overview_premium_scene_contract_passes_when_complete():
    result = validate_premium_scene_plan([_scene()], video_category="overview-video")
    assert result["valid"] is True
    assert result["scene_count"] == 1
    assert result["hero_moment_count"] == 1


def test_ambient_only_primary_motion_is_not_premium_authorship():
    scene = _scene()
    scene["motion_hierarchy"]["primary"] = "camera drift"
    result = validate_premium_scene_plan([scene], quality_tier="hero")
    assert result["valid"] is False
    assert any("ambient/camera-only" in issue for issue in result["violations"])


def test_repeated_keyframe_focal_subject_is_blocking():
    a = _scene("s1", "same product window")
    b = copy.deepcopy(_scene("s2", "same product window"))
    b["start_seconds"] = 5
    b["end_seconds"] = 10
    result = validate_premium_scene_plan([a, b], quality_tier="hero")
    assert result["valid"] is False
    assert any("focal-subject repetition" in issue for issue in result["violations"])


def test_video_compose_blocks_hero_before_render_when_premium_contract_is_missing():
    scene = _scene()
    scene.pop("focus_path")
    edit = {
        "renderer_family": "bespoke",
        "render_runtime": "remotion",
        "composition_mode": "atelier",
        "video_category": "overview-video",
        "subtitles": {"enabled": False},
    }
    cut = {
        "id": "s1",
        "type": "animation",
        "in_seconds": 0,
        "out_seconds": 5,
        "motion_class": "procedural_semantic_motion",
        "primary_subject": "source citation",
        "visual_state_before": "Claim is visible",
        "visual_action": "Citation connects the claim to the source passage",
        "visual_state_after": "Source passage is the proof state",
        "semantic_purpose": "Show provenance",
    }
    result = VideoCompose()._pre_compose_validation(
        edit,
        [cut],
        {
            "quality_tier": "hero",
            "video_category": "overview-video",
            "scenes": [scene],
        },
        "The claim remains connected to its source.",
    )
    assert result is not None and result.success is False
    assert "Premium visual contract violation" in (result.error or "")
    assert "focus_path" in (result.error or "")
