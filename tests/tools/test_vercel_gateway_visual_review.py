import json
from pathlib import Path
from unittest.mock import patch

from schemas.artifacts import validate_artifact
from tools.analysis.vercel_gateway_visual_review import (
    VercelGatewayVisualReview,
    _normalise_review,
)
from tools.audio.vercel_gateway_tts import GatewayCredential


def _raw_review(status="pass"):
    names = [
        "hook_0_3_seconds", "editorial_hierarchy", "primary_subject_scale",
        "ui_legibility", "label_readability", "dead_space_discipline",
        "frame_and_container_discipline", "semantic_motion_clarity",
        "caption_readability", "caption_rhythm", "evidence_story_alignment",
        "professional_finish",
    ]
    return {
        "status": status,
        "summary": "Specific rendered-frame review.",
        "dimensions": {name: {"score": 4, "reason": "Visible evidence supports the score."} for name in names},
        "findings": [],
        "must_fix": [],
        "keep": ["Large product evidence"],
        "comparison": None,
        "confidence": 0.86,
    }


def test_normalise_review_blocks_false_pass_on_low_hero_dimension():
    raw = _raw_review("pass")
    raw["dimensions"]["ui_legibility"]["score"] = 2
    review = _normalise_review(raw, model="zai/glm-4.5v")
    assert review["status"] == "revise"
    assert review["dimensions"]["ui_legibility"]["score"] == 2


def test_execute_writes_schema_valid_artifact_without_secret(tmp_path: Path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"not-a-real-image-but-runtime-is-mocked")
    output = tmp_path / "visual_review.json"
    tool = VercelGatewayVisualReview()

    with patch.object(
        tool,
        "_credentials",
        return_value=[GatewayCredential("pool-1", "super-secret", "omniroute_pool")],
    ), patch.object(
        tool,
        "_runtime_call",
        return_value={
            "success": True,
            "review": _raw_review(),
            "generationId": "gen_visual_test",
            "generationInfo": {"totalCost": 0.0042},
        },
    ):
        result = tool.execute({
            "frame_paths": [str(frame)],
            "frame_metadata": [{"timestamp_seconds": 1.4, "scene_id": "hook", "label": "hook proof"}],
            "video_path": str(tmp_path / "candidate.mp4"),
            "context": {"video_category": "overview-video"},
            "iteration": 1,
            "output_path": str(output),
        })

    assert result.success is True
    artifact = json.loads(output.read_text())
    validate_artifact("visual_review", artifact)
    assert artifact["evidence"]["hook_window_reviewed"] is True
    assert artifact["human_approval"] == {"required": True, "status": "pending"}
    assert result.cost_usd == 0.0042
    assert result.data["credential_connection_id"] == "pool-1"
    assert "super-secret" not in json.dumps(result.data)
    assert "super-secret" not in output.read_text()


def test_execute_rotates_retryable_pool_error(tmp_path: Path):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    tool = VercelGatewayVisualReview()
    calls = []

    def fake_call(*, api_key, payload, timeout):
        calls.append(api_key)
        if api_key == "bad":
            error = RuntimeError("payment required")
            error.status_code = 402
            error.retryable = True
            raise error
        return {"success": True, "review": _raw_review(), "generationInfo": {"totalCost": 0.001}}

    with patch.object(
        tool,
        "_credentials",
        return_value=[
            GatewayCredential("pool-1", "bad", "omniroute_pool"),
            GatewayCredential("pool-2", "good", "omniroute_pool"),
        ],
    ), patch.object(tool, "_runtime_call", side_effect=fake_call):
        result = tool.execute({
            "frame_paths": [str(frame)],
            "output_path": str(tmp_path / "review.json"),
        })

    assert result.success is True
    assert calls == ["bad", "good"]
    assert result.data["pool_attempt_count"] == 2
