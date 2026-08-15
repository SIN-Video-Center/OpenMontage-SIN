import json
from pathlib import Path

from tools.video.video_compose import VideoCompose


ROOT = Path(__file__).resolve().parents[2]


def _load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / "artifacts" / name).read_text())


def test_edit_schema_requires_governed_caption_layout_when_enabled():
    schema = _load_schema("edit_decisions.schema.json")
    subtitles = schema["properties"]["subtitles"]
    props = subtitles["properties"]

    assert props["layout_policy"]["enum"] == [
        "reserved-rail",
        "adaptive-regions",
    ]
    assert props["unicode_normalization"]["const"] == "NFC"
    assert "protected_regions" in props
    assert props["visual_treatment"]["enum"] == [
        "integrated-field", "local-pill", "surface"
    ]
    assert "full_width_background" in props
    enabled_rule = subtitles["allOf"][0]["then"]["required"]
    assert "layout_policy" in enabled_rule
    assert "protected_regions" in enabled_rule
    assert "visual_treatment" in enabled_rule
    assert "full_width_background" in enabled_rule


def test_scene_schema_declares_protected_regions_and_caption_zone():
    schema = _load_schema("scene_plan.schema.json")
    props = schema["properties"]["scenes"]["items"]["properties"]

    assert props["protected_regions"]["minItems"] == 1
    assert props["caption_layout"]["properties"]["preferred_zone"]["enum"] == [
        "top",
        "bottom",
    ]


def test_final_review_schema_records_zero_occlusion_and_unicode_status():
    schema = _load_schema("final_review.schema.json")
    subtitle_check = schema["properties"]["checks"]["properties"]["subtitle_check"]

    for field in (
        "layout_policy_declared",
        "protected_regions_checked",
        "occlusion_free",
        "collision_count",
        "unicode_text_ok",
    ):
        assert field in subtitle_check["required"]


def test_precompose_blocks_german_ascii_display_text():
    scene = {
        "id": "scene-1",
        "type": "animation",
        "description": "Provider frei waehlen",
        "start_seconds": 0,
        "end_seconds": 5,
        "primary_subject": "Provider-Auswahl",
        "visual_state_before": "Drei Optionen sind sichtbar.",
        "visual_action": "Eine Option wird begründet ausgewählt.",
        "visual_state_after": "Die aktive Option ist verifiziert.",
        "motion_class": "procedural_semantic_motion",
        "semantic_purpose": "Zeigt eine kontrollierte Auswahl.",
        "protected_regions": [
            {"id": "main", "x": 0.05, "y": 0.05, "width": 0.9, "height": 0.7}
        ],
        "caption_layout": {"preferred_zone": "bottom"},
    }
    edit = {
        "renderer_family": "bespoke",
        "composition_mode": "atelier",
        "render_runtime": "remotion",
        "subtitles": {
            "enabled": True,
            "language_code": "de-DE",
            "unicode_normalization": "NFC",
            "layout_policy": "reserved-rail",
            "visual_treatment": "integrated-field",
            "full_width_background": False,
            "preferred_zone": "bottom",
            "safe_margin_px": 48,
            "reserved_rail_height_ratio": 1 / 6,
            "protected_regions": [
                {
                    "id": "scene-1-main",
                    "scene_id": "scene-1",
                    "x": 0.05,
                    "y": 0.05,
                    "width": 0.9,
                    "height": 0.7,
                    "start_ms": 0,
                    "end_ms": 5000,
                }
            ],
        },
    }
    plan = {
        "quality_tier": "draft",
        "delivery_kind": "bespoke",
        "motion_expectation": "motion_led",
        "scenes": [scene],
    }

    result = VideoCompose()._pre_compose_validation(
        edit,
        [
            {
                "id": "scene-1",
                "type": "animation",
                "in_seconds": 0,
                "out_seconds": 5,
                "motion_class": "procedural_semantic_motion",
                "visual_state_before": scene["visual_state_before"],
                "visual_action": scene["visual_action"],
                "visual_state_after": scene["visual_state_after"],
                "semantic_purpose": scene["semantic_purpose"],
            }
        ],
        plan,
        "Provider frei waehlen.",
    )

    assert result is not None
    assert result.success is False
    assert "waehlen" in (result.error or "")
    assert "wählen" in (result.error or "")
