from pathlib import Path

from PIL import Image

from tools.analysis.keyframe_board import KeyframeBoard


def test_keyframe_board_builds_scene_complete_contact_sheet(tmp_path: Path):
    proofs = []
    scenes = []
    for index in range(3):
        proof = tmp_path / f"scene-{index + 1}.png"
        Image.new("RGB", (1920, 1080), (20 + index * 20, 30, 40)).save(proof)
        proofs.append(proof)
        scenes.append(
            {
                "scene_id": f"scene-{index + 1}",
                "keyframes": [
                    {
                        "moment": "proof",
                        "output_path": str(proof),
                        "status": "approved",
                    }
                ],
            }
        )

    output = tmp_path / "board.jpg"
    result = KeyframeBoard().execute(
        {
            "visual_design_plan": {
                "scene_designs": scenes,
                "keyframe_board": {"output_path": str(output)},
            },
            "columns": 2,
        }
    )

    assert result.success is True
    assert output.is_file()
    assert result.data["scene_count"] == 3
    assert result.data["scene_ids"] == ["scene-1", "scene-2", "scene-3"]


def test_keyframe_board_blocks_missing_proof_file(tmp_path: Path):
    result = KeyframeBoard().execute(
        {
            "visual_design_plan": {
                "scene_designs": [
                    {
                        "scene_id": "scene-1",
                        "keyframes": [
                            {
                                "moment": "proof",
                                "output_path": str(tmp_path / "missing.png"),
                                "status": "approved",
                            }
                        ],
                    }
                ],
                "keyframe_board": {"output_path": str(tmp_path / "board.jpg")},
            }
        }
    )
    assert result.success is False
    assert "missing" in result.error.lower()
