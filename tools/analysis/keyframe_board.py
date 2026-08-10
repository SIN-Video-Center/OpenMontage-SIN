"""Build a deterministic review board from visual-design proof keyframes."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolTier,
)


class KeyframeBoard(BaseTool):
    name = "keyframe_board"
    version = "1.0.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "pillow"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["python:PIL"]
    install_instructions = "Install Pillow in the OpenMontage Python environment."
    agent_skills = []
    capabilities = ["build_visual_design_board", "proof_keyframe_contact_sheet"]
    best_for = ["hero/overview frame-first review before full motion rendering"]

    input_schema = {
        "type": "object",
        "required": ["visual_design_plan"],
        "properties": {
            "visual_design_plan": {"type": "object"},
            "project_root": {"type": "string"},
            "output_path": {"type": "string"},
            "columns": {"type": "integer", "minimum": 1, "maximum": 4, "default": 2},
            "tile_width": {"type": "integer", "minimum": 320, "maximum": 1920, "default": 960},
            "tile_height": {"type": "integer", "minimum": 180, "maximum": 1080, "default": 540},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=1024, vram_mb=0, disk_mb=250)
    side_effects = ["writes a keyframe-board image"]
    user_visible_verification = ["Inspect the full board at 100% and reject weak paused frames before motion authoring"]

    @staticmethod
    def _resolve(path_value: str, root: Path) -> Path:
        path = Path(path_value).expanduser()
        return path if path.is_absolute() else (root / path).resolve()

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        plan = inputs.get("visual_design_plan") or {}
        root = Path(inputs.get("project_root") or ".").expanduser().resolve()
        scene_designs = plan.get("scene_designs") or []
        selected: list[tuple[str, Path]] = []
        missing: list[str] = []

        for scene in scene_designs:
            scene_id = str(scene.get("scene_id") or "unknown")
            proofs = [
                frame for frame in (scene.get("keyframes") or [])
                if isinstance(frame, dict) and frame.get("moment") == "proof"
            ]
            if not proofs:
                missing.append(f"{scene_id}: no proof keyframe declared")
                continue
            proof = next((f for f in proofs if f.get("status") in {"approved", "rendered"}), proofs[0])
            value = str(proof.get("output_path") or "").strip()
            if not value:
                missing.append(f"{scene_id}: proof keyframe has no output_path")
                continue
            path = self._resolve(value, root)
            if not path.is_file():
                missing.append(f"{scene_id}: proof keyframe file missing: {path}")
                continue
            selected.append((scene_id, path))

        if missing:
            return ToolResult(
                success=False,
                error="Cannot build keyframe board:\n" + "\n".join(f"  • {item}" for item in missing),
            )
        if not selected:
            return ToolResult(success=False, error="No proof keyframes available")

        board_cfg = plan.get("keyframe_board") or {}
        output_value = str(inputs.get("output_path") or board_cfg.get("output_path") or "artifacts/keyframes/keyframe-board.jpg")
        output = self._resolve(output_value, root)
        output.parent.mkdir(parents=True, exist_ok=True)

        cols = int(inputs.get("columns", 2))
        tile_w = int(inputs.get("tile_width", 960))
        tile_h = int(inputs.get("tile_height", 540))
        label_h = 56
        gap = 20
        margin = 28
        rows = math.ceil(len(selected) / cols)
        board_w = margin * 2 + cols * tile_w + (cols - 1) * gap
        board_h = margin * 2 + rows * (tile_h + label_h) + (rows - 1) * gap
        canvas = Image.new("RGB", (board_w, board_h), (15, 17, 21))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default(size=22)

        for index, (scene_id, path) in enumerate(selected):
            row, col = divmod(index, cols)
            x = margin + col * (tile_w + gap)
            y = margin + row * (tile_h + label_h + gap)
            with Image.open(path) as source:
                frame = ImageOps.fit(source.convert("RGB"), (tile_w, tile_h), method=Image.Resampling.LANCZOS)
            canvas.paste(frame, (x, y))
            draw.rectangle((x, y + tile_h, x + tile_w, y + tile_h + label_h), fill=(23, 26, 32))
            draw.text((x + 16, y + tile_h + 15), f"{index + 1:02d}  {scene_id}", font=font, fill=(235, 238, 244))

        canvas.save(output, quality=94, optimize=True)
        return ToolResult(
            success=True,
            data={
                "output_path": str(output),
                "scene_count": len(selected),
                "scene_ids": [scene_id for scene_id, _ in selected],
                "proof_paths": [str(path) for _, path in selected],
                "columns": cols,
            },
            artifacts=[str(output)],
            duration_seconds=round(time.time() - started, 3),
        )
