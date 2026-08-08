"""Rendered-video visual learning loop.

Each iteration samples the delivered MP4, invokes the multimodal critic, applies
independent governance rules, and writes a concrete revision brief. Agents use
that brief to change the composition, render the next candidate, and optionally
run a pairwise A/B review. The loop stops after three iterations and requires a
human decision for hero work.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from lib.visual_review_gate import validate_visual_review
from tools.analysis.vercel_gateway_visual_review import VercelGatewayVisualReview
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


def _probe_duration(video_path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("ffprobe could not read candidate video")
    return float(proc.stdout.strip())


def _scene_windows(edit_decisions: dict[str, Any] | None, duration: float) -> list[dict[str, Any]]:
    windows = []
    for index, cut in enumerate((edit_decisions or {}).get("cuts") or []):
        start = float(cut.get("in_seconds") or 0)
        end = float(cut.get("out_seconds") or start)
        if end > start:
            windows.append({"id": str(cut.get("id") or f"scene-{index + 1}"), "start": start, "end": min(end, duration)})
    if not windows:
        windows = [{"id": "video", "start": 0.0, "end": duration}]
    return windows


def _sample_plan(duration: float, windows: list[dict[str, Any]], max_frames: int = 16) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = [
        {"timestamp_seconds": min(0.25, max(0.0, duration - 0.02)), "scene_id": "hook", "label": "hook opening"},
        {"timestamp_seconds": min(1.5, max(0.0, duration - 0.02)), "scene_id": "hook", "label": "hook development"},
        {"timestamp_seconds": min(2.8, max(0.0, duration - 0.02)), "scene_id": "hook", "label": "hook payoff"},
    ]
    for window in windows:
        span = max(0.01, window["end"] - window["start"])
        for fraction, label in ((0.22, "scene early"), (0.62, "scene primary state")):
            samples.append({
                "timestamp_seconds": min(duration - 0.02, window["start"] + span * fraction),
                "scene_id": window["id"],
                "label": label,
            })
    unique: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for sample in samples:
        key = (round(float(sample["timestamp_seconds"]) * 10), str(sample["scene_id"]))
        if key not in seen and sample["timestamp_seconds"] >= 0:
            seen.add(key)
            unique.append(sample)
    if len(unique) <= max_frames:
        return unique
    # Preserve all three hook samples, then distribute remaining slots across scenes.
    hook = unique[:3]
    rest = unique[3:]
    slots = max_frames - len(hook)
    chosen = [rest[round(i * (len(rest) - 1) / max(1, slots - 1))] for i in range(slots)]
    return hook + chosen


def _extract_frames(video_path: Path, plan: list[dict[str, Any]], frame_dir: Path) -> list[Path]:
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index, sample in enumerate(plan):
        output = frame_dir / f"frame_{index:02d}_{sample['timestamp_seconds']:.3f}s.jpg"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(sample["timestamp_seconds"]), "-i", str(video_path), "-frames:v", "1", "-q:v", "2", str(output)],
            capture_output=True, timeout=60, check=False,
        )
        if proc.returncode != 0 or not output.is_file():
            raise RuntimeError(f"Could not extract visual-review frame at {sample['timestamp_seconds']:.3f}s")
        frames.append(output)
    return frames


def _revision_brief(review: dict[str, Any], gate: dict[str, Any]) -> str:
    lines = [
        "# Rendered visual revision brief",
        "",
        f"**Status:** {review.get('status')}  ",
        f"**Iteration:** {review.get('iteration')} / 3  ",
        f"**Gate:** {'PASS' if gate.get('valid') else 'REVISE'}",
        "",
        "## Executive diagnosis",
        "",
        str(review.get("summary") or "No summary supplied."),
        "",
    ]
    if gate.get("violations"):
        lines.extend(["## Blocking governance findings", ""])
        lines.extend(f"- {value}" for value in gate["violations"])
        lines.append("")
    lines.extend(["## Required changes in order", ""])
    actions = review.get("must_fix") or [f.get("action") for f in review.get("findings") or [] if f.get("severity") in {"critical", "high"}]
    lines.extend(f"{index}. {value}" for index, value in enumerate(actions, 1) if value)
    lines.extend(["", "## Frame-specific evidence", ""])
    for finding in review.get("findings") or []:
        lines.append(
            f"- **{finding.get('severity', 'medium').upper()} · {finding.get('timestamp_seconds', 0):.2f}s · "
            f"{finding.get('scene_id', 'unknown')}** — {finding.get('observation', '')}  "
        )
        lines.append(f"  **Change:** {finding.get('action', '')}")
    lines.extend([
        "",
        "## Iteration rule",
        "",
        "Render a new candidate only after the blocking actions are reflected in code. Run pairwise review against this candidate. "
        "After iteration 3, stop automatic revision and request a human decision instead of weakening the gate.",
        "",
    ])
    return "\n".join(lines)


class VisualReviewLoop(BaseTool):
    name = "visual_review_loop"
    version = "1.0.0"
    tier = ToolTier.ANALYZE
    capability = "visual_review"
    provider = "openmontage"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.HYBRID
    capabilities = ["frame_sampling", "hook_sampling", "semantic_visual_review", "revision_brief", "three_iteration_ceiling"]
    supports = {"automatic_frame_inspection": True, "max_iterations": 3, "human_final_lock": True}
    best_for = ["iterative post-render review of hero and overview videos"]
    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {"type": "string"},
            "edit_decisions": {"type": "object"},
            "edit_decisions_path": {"type": "string"},
            "context": {"type": "object"},
            "quality_tier": {"type": "string", "default": "hero"},
            "video_category": {"type": "string", "default": "overview-video"},
            "iteration": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
            "model": {"type": "string", "default": "zai/glm-4.5v"},
            "output_dir": {"type": "string"},
            "api_key": {"type": "string"},
            "omniroute_db_path": {"type": "string"}
        }
    }
    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=1024, disk_mb=500, network_required=True)
    side_effects = ["extracts rendered frames", "calls visual-review model", "writes review and revision brief"]

    def get_status(self) -> ToolStatus:
        return VercelGatewayVisualReview().get_status()

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        video_path = Path(str(inputs.get("video_path") or "")).expanduser().resolve()
        if not video_path.is_file():
            return ToolResult(success=False, error=f"Candidate video not found: {video_path}")
        iteration = int(inputs.get("iteration", 1))
        if iteration < 1 or iteration > 3:
            return ToolResult(success=False, error="iteration must be between 1 and 3")

        edit_decisions = inputs.get("edit_decisions") if isinstance(inputs.get("edit_decisions"), dict) else None
        if edit_decisions is None and inputs.get("edit_decisions_path"):
            edit_decisions = json.loads(Path(inputs["edit_decisions_path"]).expanduser().read_text(encoding="utf-8"))
        duration = _probe_duration(video_path)
        windows = _scene_windows(edit_decisions, duration)
        plan = _sample_plan(duration, windows)
        output_dir = Path(inputs.get("output_dir") or video_path.parent / "visual_review").expanduser().resolve()
        iteration_dir = output_dir / f"iteration_{iteration:02d}"
        frames = _extract_frames(video_path, plan, iteration_dir / "frames")

        review_path = iteration_dir / "visual_review.json"
        incoming_context = dict(inputs.get("context") or {})
        bespoke = (edit_decisions or {}).get("bespoke") if isinstance(edit_decisions, dict) else None
        art_direction = (
            incoming_context.get("art_direction")
            or (bespoke or {}).get("art_direction")
            or (edit_decisions or {}).get("art_direct")
        )
        taste_profile = (
            incoming_context.get("taste_profile")
            or (edit_decisions or {}).get("taste_profile")
        )
        tone_mode = (
            incoming_context.get("tone_mode")
            or (edit_decisions or {}).get("tone_mode")
        )
        critic_inputs = {
            "frame_paths": [str(path) for path in frames],
            "frame_metadata": plan,
            "video_path": str(video_path),
            "model": inputs.get("model", "zai/glm-4.5v"),
            "context": {
                **incoming_context,
                "video_category": inputs.get("video_category", "overview-video"),
                "quality_tier": inputs.get("quality_tier", "hero"),
                "duration_seconds": round(duration, 3),
                "scene_windows": windows,
                **({"art_direction": art_direction} if art_direction else {}),
                **({"taste_profile": taste_profile} if taste_profile else {}),
                **({"tone_mode": tone_mode} if tone_mode else {}),
            },
            "iteration": iteration,
            "output_path": str(review_path),
        }
        for key in ("api_key", "omniroute_db_path", "max_pool_attempts", "timeout_seconds", "base_url"):
            if inputs.get(key) is not None:
                critic_inputs[key] = inputs[key]
        critic = VercelGatewayVisualReview().execute(critic_inputs)
        if not critic.success:
            return ToolResult(success=False, error=critic.error, duration_seconds=round(time.time() - started, 2), model=critic.model)

        review = json.loads(review_path.read_text(encoding="utf-8"))
        gate = validate_visual_review(
            review,
            quality_tier=str(inputs.get("quality_tier", "hero")),
            video_category=str(inputs.get("video_category", "overview-video")),
            require_human_approval=False,
        )
        review["governance_gate"] = gate
        review["automatic_loop_status"] = (
            "candidate_passed_requires_human_approval" if gate["valid"]
            else "iteration_ceiling_requires_human_decision" if iteration >= 3
            else "revise_and_rerender"
        )
        review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        brief_path = iteration_dir / "revision_brief.md"
        brief_path.write_text(_revision_brief(review, gate), encoding="utf-8")
        history_path = output_dir / "history.jsonl"
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "iteration": iteration,
                "video_path": str(video_path),
                "review_path": str(review_path),
                "gate_valid": gate["valid"],
                "automatic_loop_status": review["automatic_loop_status"],
                "must_fix": review.get("must_fix") or [],
            }, ensure_ascii=False) + "\n")

        return ToolResult(
            success=True,
            data={
                "status": review["automatic_loop_status"],
                "gate_valid": gate["valid"],
                "iteration": iteration,
                "review_path": str(review_path),
                "revision_brief_path": str(brief_path),
                "frame_paths": [str(path) for path in frames],
                "human_approval_required": True,
            },
            artifacts=[str(review_path), str(brief_path), str(history_path), *[str(path) for path in frames]],
            cost_usd=critic.cost_usd,
            duration_seconds=round(time.time() - started, 2),
            model=critic.model,
        )
