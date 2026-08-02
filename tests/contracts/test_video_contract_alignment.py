"""Cross-layer contracts for scene vocabulary, timing, routing, and quality gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.delivery_promise import DeliveryPromise, PromiseType  # noqa: E402
from lib.slideshow_risk import score_slideshow_risk  # noqa: E402


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _valid_proposal_plan(**overrides):
    plan = {
        "pipeline": "animated-explainer",
        "stages": [],
        "quality_tier": "standard",
        "delivery_kind": "templated",
        "motion_expectation": "motion_led",
        "renderer_family": "explainer-data",
        "render_runtime": "remotion",
        "composition_mode": "templated",
        "delivery_promise": {
            "promise_type": "data_explainer",
            "motion_required": True,
            "tone_mode": "educational",
            "quality_floor": "presentable",
        },
        "taste_profile": {
            "design_read": "Progressive data explanation",
            "visual_variance": 6,
            "motion_intensity": 6,
            "information_density": 5,
        },
    }
    plan.update(overrides)
    return plan


def _valid_proposal(plan: dict) -> dict:
    return {
        "version": "1.0",
        "concept_options": [
            {
                "id": f"c{i}",
                "title": f"Concept {i}",
                "hook": f"Hook {i}",
                "narrative_structure": structure,
                "visual_approach": f"Approach {i}",
                "target_duration_seconds": 30,
                "why_this_works": "Grounded concept",
            }
            for i, structure in enumerate(
                ["journey", "comparison", "problem_solution"], start=1
            )
        ],
        "selected_concept": {"concept_id": "c1", "rationale": "Best fit"},
        "production_plan": plan,
        "cost_estimate": {
            "total_estimated_usd": 0,
            "line_items": [],
            "budget_verdict": "within_budget",
        },
        "approval": {"status": "approved"},
    }


def _semantic_scene(scene_id: str = "s1") -> dict:
    return {
        "id": scene_id,
        "type": "diagram",
        "description": "A query becomes a vector and activates results.",
        "start_seconds": 0,
        "end_seconds": 5,
        "primary_subject": "query encoder",
        "visual_state_before": "raw query",
        "visual_action": "tokens enter encoder and become a vector",
        "visual_state_after": "ranked neighbours surround the vector",
        "motion_class": "procedural_semantic_motion",
        "semantic_purpose": "show transformation",
    }


def test_registry_matches_scene_and_edl_schemas_and_generated_types():
    registry = _json("schemas/scene_types.registry.json")
    scene_schema = _json("schemas/artifacts/scene_plan.schema.json")
    edl_schema = _json("schemas/artifacts/edit_decisions.schema.json")

    assert scene_schema["properties"]["scenes"]["items"]["properties"]["type"]["enum"] == registry["scene_types"]
    assert edl_schema["$defs"]["cut"]["properties"]["type"]["enum"] == registry["scene_types"]
    assert edl_schema["$defs"]["overlay"]["properties"]["type"]["enum"] == registry["overlay_types"]
    assert scene_schema["properties"]["scenes"]["items"]["properties"]["motion_class"]["enum"] == registry["motion_classes"]
    assert edl_schema["$defs"]["cut"]["properties"]["motion_class"]["enum"] == registry["motion_classes"]

    generated = (ROOT / "remotion-composer/src/generated/sceneTypes.ts").read_text(encoding="utf-8")
    for value in registry["scene_types"] + registry["overlay_types"] + registry["motion_classes"]:
        assert f'"{value}"' in generated


def test_scene_plan_requires_visual_state_change_contract():
    schema = _json("schemas/artifacts/scene_plan.schema.json")
    validator = Draft202012Validator(schema)
    valid = {
        "version": "1.0",
        "quality_tier": "standard",
        "delivery_kind": "templated",
        "motion_expectation": "motion_led",
        "scenes": [_semantic_scene()],
    }
    assert list(validator.iter_errors(valid)) == []

    invalid = json.loads(json.dumps(valid))
    del invalid["scenes"][0]["visual_action"]
    assert list(validator.iter_errors(invalid))


def test_edl_component_props_and_absolute_timeline_validate():
    schema = _json("schemas/artifacts/edit_decisions.schema.json")
    validator = Draft202012Validator(schema)
    artifact = {
        "version": "1.0",
        "renderer_family": "explainer-data",
        "render_runtime": "remotion",
        "composition_mode": "templated",
        "cuts": [
            {
                "id": "hero",
                "source": "",
                "type": "hero_title",
                "in_seconds": 0,
                "out_seconds": 4,
                "text": "Title",
                "heroSubtitle": "Subtitle",
                "motion_class": "procedural_semantic_motion",
                "primary_subject": "title tokens",
                "visual_state_before": "one line",
                "visual_action": "line fragments into tokens",
                "visual_state_after": "tokens enter encoder",
                "semantic_purpose": "introduce transformation",
            },
            {
                "id": "video",
                "source": "clip.mp4",
                "type": "video",
                "in_seconds": 4,
                "out_seconds": 9,
                "source_in_seconds": 2.5,
                "motion_class": "source_motion",
                "primary_subject": "moving vector",
                "visual_state_before": "vector outside index",
                "visual_action": "vector traverses index",
                "visual_state_after": "results activate",
                "semantic_purpose": "show retrieval",
            },
        ],
        "audio": {
            "narration": {"segments": [{"asset_id": "n1", "start_seconds": 0, "end_seconds": 9}]},
            "music": {"asset_id": "m1", "ducking": True},
        },
    }
    assert list(validator.iter_errors(artifact)) == []
    assert artifact["cuts"][1]["in_seconds"] == 4
    assert artifact["cuts"][1]["source_in_seconds"] == 2.5


def test_semantic_motion_label_without_states_is_rejected():
    schema = _json("schemas/artifacts/edit_decisions.schema.json")
    validator = Draft202012Validator(schema)
    artifact = {
        "version": "1.0",
        "renderer_family": "explainer-data",
        "render_runtime": "remotion",
        "composition_mode": "templated",
        "cuts": [
            {
                "id": "c1",
                "source": "clip.mp4",
                "type": "video",
                "in_seconds": 0,
                "out_seconds": 5,
                "motion_class": "source_motion",
            }
        ],
    }
    assert list(validator.iter_errors(artifact))


def test_hero_proposal_cannot_route_to_templated_final():
    schema = _json("schemas/artifacts/proposal_packet.schema.json")
    validator = Draft202012Validator(schema)

    invalid = _valid_proposal(
        _valid_proposal_plan(
            quality_tier="hero",
            delivery_kind="templated",
            composition_mode="templated",
        )
    )
    assert list(validator.iter_errors(invalid))

    valid = _valid_proposal(
        _valid_proposal_plan(
            quality_tier="hero",
            delivery_kind="bespoke",
            renderer_family="bespoke",
            composition_mode="atelier",
            art_direction="Subject-specific editorial signal system",
        )
    )
    assert list(validator.iter_errors(valid)) == []


def test_delivery_promise_counts_only_complete_semantic_beats():
    promise = DeliveryPromise(
        promise_type=PromiseType.DATA_EXPLAINER,
        motion_required=True,
        source_required=False,
        tone_mode="educational",
        quality_floor="presentable",
    )
    incomplete = [
        {
            "id": "c1",
            "type": "bar_chart",
            "in_seconds": 0,
            "out_seconds": 10,
            "motion_class": "procedural_semantic_motion",
        }
    ]
    assert promise.validate_cuts(incomplete)["valid"] is False

    complete = [
        {
            "id": "c1",
            "type": "bar_chart",
            "in_seconds": 0,
            "out_seconds": 10,
            "motion_class": "procedural_semantic_motion",
            "visual_state_before": "empty axes",
            "visual_action": "bars grow in spoken order",
            "visual_state_after": "ranked comparison",
        }
    ]
    assert promise.validate_cuts(complete)["valid"] is True


def test_slideshow_risk_penalizes_declared_motion_without_state_change():
    incomplete = [{"id": "s1", "motion_class": "procedural_semantic_motion"}]
    complete = [_semantic_scene()]
    assert score_slideshow_risk(incomplete)["average"] > score_slideshow_risk(complete)["average"]


def test_root_duration_uses_max_absolute_end_and_transitions_are_rendered():
    root = (ROOT / "remotion-composer/src/Root.tsx").read_text(encoding="utf-8")
    explainer = (ROOT / "remotion-composer/src/Explainer.tsx").read_text(encoding="utf-8")
    assert "Math.max(maxEnd" in root
    assert "summing durations would over-count" in root
    assert "<TransitionedScene cut={cut} theme={theme} />" in explainer
    assert "sceneDurationFrames={sceneDurationFrames}" in explainer
    assert "startFrom={Math.round(startFrom * fps)}" in explainer
    assert "audio.music!.ducking" in explainer


def test_scene_components_use_local_sequence_duration():
    component_paths = [
        "remotion-composer/src/components/ProgressBar.tsx",
        "remotion-composer/src/components/charts/BarChart.tsx",
        "remotion-composer/src/components/charts/LineChart.tsx",
        "remotion-composer/src/components/charts/PieChart.tsx",
        "remotion-composer/src/components/charts/KPIGrid.tsx",
    ]
    for relative in component_paths:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "sceneDurationFrames?: number" in content
        assert "sceneDurationFrames ?? compositionDurationInFrames" in content


def test_hyperframes_atelier_requires_workspace_inventory_and_duration():
    schema = _json("schemas/artifacts/edit_decisions.schema.json")
    validator = Draft202012Validator(schema)

    valid = {
        "version": "1.0",
        "renderer_family": "bespoke",
        "render_runtime": "hyperframes",
        "composition_mode": "atelier",
        "total_duration_seconds": 12,
        "bespoke": {
            "workspace_path": "projects/demo/hyperframes",
            "art_direction": "A project-specific kinetic editorial system",
            "scene_inventory": [
                {
                    "scene_id": "s1",
                    "primary_subject": "query fragments",
                    "signature_device_present": True,
                },
                {
                    "scene_id": "s2",
                    "primary_subject": "evidence lattice",
                    "signature_device_present": False,
                },
            ],
        },
    }
    assert list(validator.iter_errors(valid)) == []

    missing_workspace = json.loads(json.dumps(valid))
    del missing_workspace["bespoke"]["workspace_path"]
    assert list(validator.iter_errors(missing_workspace))

    missing_duration = json.loads(json.dumps(valid))
    del missing_duration["total_duration_seconds"]
    assert list(validator.iter_errors(missing_duration))


def test_hyperframes_atelier_never_scaffolds_over_workspace():
    source = (ROOT / "tools/video/hyperframes_compose.py").read_text(encoding="utf-8")
    assert "scaffold_workspace is forbidden for composition_mode='atelier'" in source
    assert "atelier workspace is hand-authored and must not be overwritten" in source
    assert "workspace_was_generated" in source


def test_video_compose_has_no_automatic_remotion_to_ffmpeg_fallback():
    source = (ROOT / "tools/video/video_compose.py").read_text(encoding="utf-8")
    assert "Content simplicity never authorizes a runtime swap" in source
    assert "Automatic fallback to FFmpeg is forbidden" in source
    assert "Approved production contract mismatch" in source


def test_reviewer_uses_actual_variation_verdict_names_and_blocks_revise():
    reviewer = (ROOT / "skills/meta/reviewer.md").read_text(encoding="utf-8")
    for verdict in ("strong", "acceptable", "revise", "fail"):
        assert f"`{verdict}`" in reviewer
    assert "Two autonomous revision rounds max" in reviewer
    assert "final_review.status != pass" in reviewer
