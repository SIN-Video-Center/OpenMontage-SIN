import json
from pathlib import Path
from unittest.mock import patch

from lib.visual_review_gate import validate_visual_review
from tools.analysis.visual_review_loop import VisualReviewLoop, _sample_plan
from tools.base_tool import ToolResult


def _review(iteration=1, status="pass"):
    names = [
        "hook_0_3_seconds", "editorial_hierarchy", "keyframe_quality",
        "focus_choreography", "surface_coherence", "primary_subject_scale",
        "ui_legibility", "label_readability", "dead_space_discipline",
        "frame_and_container_discipline", "semantic_motion_clarity", "motion_authorship",
        "transition_quality", "restraint_and_density", "caption_readability",
        "caption_rhythm", "evidence_story_alignment", "professional_finish",
    ]
    return {
        "version": "1.0",
        "video_path": "candidate.mp4",
        "iteration": iteration,
        "review_mode": "single",
        "reviewer": {"provider": "vercel-ai-gateway", "model": "zai/glm-4.5v", "transport": "test", "human_replacement": False},
        "evidence": {
            "frame_paths": [f"f{i}.jpg" for i in range(12)],
            "frame_metadata": [{"index": i, "path": f"f{i}.jpg", "label": "frame", "timestampSeconds": 1.0 if i == 0 else i + 3.0, "sceneId": "hook" if i == 0 else "scene", "sampleCount": 1} for i in range(12)],
            "frame_count": 12,
            "sampled_frame_count": 12,
            "hook_window_reviewed": True,
            "expected_scene_ids": ["scene"],
            "reviewed_scene_ids": ["scene"],
            "scene_coverage_complete": True,
        },
        "status": status,
        "summary": "review",
        "dimensions": {name: {"score": 4, "reason": "evidence"} for name in names},
        "findings": [],
        "must_fix": [],
        "keep": [],
        "comparison": None,
        "confidence": 0.8,
        "model": "zai/glm-4.5v",
        "human_approval": {"required": True, "status": "pending"},
    }


def test_sample_plan_always_covers_three_second_hook():
    plan = _sample_plan(62.0, [{"id": "s1", "start": 0, "end": 8}, {"id": "s2", "start": 8, "end": 17}])
    assert len(plan) <= 16
    assert [round(v["timestamp_seconds"], 1) for v in plan[:3]] == [0.2, 1.5, 2.8]
    assert {item["scene_id"] for item in plan} >= {"hook", "s1", "s2"}
    assert any(item["label"] == "scene primary proof state" for item in plan if item["scene_id"] == "s1")


def test_sample_plan_preserves_every_scene_under_frame_budget():
    windows = [{"id": f"s{i}", "start": float(i * 8), "end": float((i + 1) * 8)} for i in range(7)]
    plan = _sample_plan(60.0, windows)
    assert len(plan) == 16
    sampled = {item["scene_id"] for item in plan}
    assert {f"s{i}" for i in range(7)} <= sampled


def test_visual_review_gate_requires_strong_hero_scores_and_evidence():
    review = _review()
    assert validate_visual_review(review, quality_tier="hero", video_category="overview-video")["valid"] is True
    review["dimensions"]["editorial_hierarchy"]["score"] = 3.0
    result = validate_visual_review(review, quality_tier="hero", video_category="overview-video")
    assert result["valid"] is False
    assert any("editorial_hierarchy" in issue for issue in result["violations"])


def test_visual_review_gate_blocks_incomplete_scene_coverage():
    review = _review()
    review["evidence"]["expected_scene_ids"] = ["s1", "s2"]
    review["evidence"]["reviewed_scene_ids"] = ["s1"]
    review["evidence"]["scene_coverage_complete"] = False
    result = validate_visual_review(review, quality_tier="hero", video_category="overview-video")
    assert result["valid"] is False
    assert any("s2" in issue for issue in result["violations"])


def test_loop_writes_revision_brief_and_stops_at_iteration_three(tmp_path: Path):
    video = tmp_path / "candidate.mp4"
    video.write_bytes(b"video")
    frames = [tmp_path / f"frame{i}.jpg" for i in range(12)]
    for frame in frames:
        frame.write_bytes(b"frame")

    review = _review(iteration=3, status="revise")
    review["findings"] = [{
        "severity": "high", "frame_index": 2, "timestamp_seconds": 2.8,
        "scene_id": "hook", "category": "hook", "observation": "Weak opening",
        "why_it_matters": "No reason to continue", "action": "Open on visible evidence",
    }]
    review["must_fix"] = ["Open on visible evidence"]
    review["dimensions"]["hook_0_3_seconds"]["score"] = 2

    def fake_critic(inputs):
        output = Path(inputs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        review["evidence"]["frame_paths"] = [str(path) for path in frames]
        review["evidence"]["frame_metadata"] = [
            {"index": i, "path": str(path), "label": "frame", "timestampSeconds": 1.0 if i == 0 else i + 3.0, "sceneId": "hook" if i == 0 else "scene", "sampleCount": 1}
            for i, path in enumerate(frames)
        ]
        output.write_text(json.dumps(review))
        return ToolResult(success=True, artifacts=[str(output)], cost_usd=0.01, model="zai/glm-4.5v")

    strip_plan = [
        {"timestamp_seconds": 1.5, "scene_id": "hook", "label": "MOTION STRIP hook", "sample_count": 3},
        *[
            {"timestamp_seconds": float(i + 4), "scene_id": "scene", "label": "MOTION STRIP scene", "sample_count": 3}
            for i in range(11)
        ],
    ]
    with patch("tools.analysis.visual_review_loop._probe_duration", return_value=62.0), patch(
        "tools.analysis.visual_review_loop._extract_motion_strips", return_value=(frames, strip_plan)
    ), patch(
        "tools.analysis.visual_review_loop.VercelGatewayVisualReview.execute", side_effect=fake_critic
    ):
        result = VisualReviewLoop().execute({
            "video_path": str(video),
            "iteration": 3,
            "output_dir": str(tmp_path / "review"),
        })

    assert result.success is True
    assert result.data["status"] == "iteration_ceiling_requires_human_decision"
    brief = Path(result.data["revision_brief_path"]).read_text()
    assert "Open on visible evidence" in brief
