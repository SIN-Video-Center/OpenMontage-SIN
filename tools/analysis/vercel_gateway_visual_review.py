"""Multimodal post-render design review through Vercel AI Gateway.

This tool complements deterministic frame, motion, caption, and audio checks. It
reviews the *rendered evidence* (not source declarations) for hierarchy,
legibility, editorial intent, hook strength, and common template/scaffolding
artifacts. A vision-model verdict never replaces human approval for hero work.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from schemas.artifacts import validate_artifact
from tools.audio.vercel_gateway_tts import GatewayCredential, VercelGatewayTTS
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

RUNTIME_DIR = Path(__file__).resolve().parent / "vercel_gateway_visual_runtime"
RUNTIME_SCRIPT = RUNTIME_DIR / "review.mjs"
_RETRYABLE_STATUS_CODES = {401, 402, 403, 408, 409, 429, 500, 502, 503, 504}

_DIMENSIONS = (
    "hook_0_3_seconds",
    "editorial_hierarchy",
    "primary_subject_scale",
    "ui_legibility",
    "label_readability",
    "dead_space_discipline",
    "frame_and_container_discipline",
    "semantic_motion_clarity",
    "caption_readability",
    "caption_rhythm",
    "evidence_story_alignment",
    "professional_finish",
)

_SYSTEM_PROMPT = """You are a senior broadcast motion designer, investigative video editor, accessibility caption editor, and product-film creative director.

Review only what is visibly evidenced in the supplied rendered frames. Be severe, specific, and production-oriented. Do not praise a frame merely because it is clean, dark, modern, animated, or technically valid. Detect work that looks like a wireframe, debug overlay, UI scaffold, generic template, slideshow, or unfinished Figma composition.

If the context contains an `art_direction`, `taste_profile`, or `tone_mode`, treat it as the governing design contract. Read deliberate brand marks, accent colors, typographic callouts, and real-UI screencaps as intentional creative choices to be judged against that contract — do not auto-classify them as debug artifacts, inspector highlights, or raw screen captures. Only call them problems when they violate the stated direction, look unfinished against their own palette, or harm legibility. When the context says "real-UI-led editorial product film" or similar, expect the delivered frames to show UI, and weigh how well the composition frames that UI, not whether UI exists at all.

Return one JSON object only. Do not wrap it in markdown. Required shape:
{
  "status": "pass" | "revise" | "fail",
  "summary": "one concise paragraph",
  "dimensions": {
    "hook_0_3_seconds": {"score": 0-5, "reason": "..."},
    "editorial_hierarchy": {"score": 0-5, "reason": "..."},
    "primary_subject_scale": {"score": 0-5, "reason": "..."},
    "ui_legibility": {"score": 0-5, "reason": "..."},
    "label_readability": {"score": 0-5, "reason": "..."},
    "dead_space_discipline": {"score": 0-5, "reason": "..."},
    "frame_and_container_discipline": {"score": 0-5, "reason": "..."},
    "semantic_motion_clarity": {"score": 0-5, "reason": "..."},
    "caption_readability": {"score": 0-5, "reason": "..."},
    "caption_rhythm": {"score": 0-5, "reason": "..."},
    "evidence_story_alignment": {"score": 0-5, "reason": "..."},
    "professional_finish": {"score": 0-5, "reason": "..."}
  },
  "findings": [
    {
      "severity": "critical" | "high" | "medium" | "low",
      "frame_index": 0,
      "timestamp_seconds": 0.0,
      "scene_id": "...",
      "category": "hierarchy|legibility|hook|caption|motion|template_artifact|evidence|voice_script|other",
      "observation": "what is visibly wrong",
      "why_it_matters": "viewer consequence",
      "action": "specific implementation change"
    }
  ],
  "must_fix": ["ordered concrete actions"],
  "keep": ["only elements that demonstrably work"],
  "comparison": null | {"winner": "candidate_a|candidate_b|tie", "reasons": ["..."]},
  "confidence": 0.0-1.0
}

Scoring: 5 = broadcast-ready; 4 = strong with minor polish; 3 = acceptable but visibly generic/weak; 2 = clear revision required; 1 = fundamentally poor; 0 = absent or broken. For hero/overview work, any critical finding, two or more high findings, or a score below 3 in hook, hierarchy, UI legibility, captions, or professional finish requires revision.

Specific anti-patterns to detect:
- nested translucent rounded rectangles, outline frames, decorative containers, and visible scaffolding without semantic purpose;
- tiny UI islands, unreadable screenshots, labels detached from the thing they name, or labels treated as metadata;
- excessive dead space that does not create tension or hierarchy;
- two similar screenshots shown simultaneously so neither can be read;
- micro labels such as scene numbers/category names that look like debug information;
- oversized headlines that overpower the evidence;
- long flat subtitle lines, poor phrase breaks, weak contrast, or captions competing with the image;
- an opening that delays conflict, proof, surprise, consequence, or a compelling question beyond three seconds;
- camera motion that does not clarify meaning;
- narration/caption wording that is generic, bureaucratic, repetitive, or emotionally flat.
"""


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise_review(raw: dict[str, Any], *, model: str) -> dict[str, Any]:
    dimensions = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else {}
    normalised_dimensions: dict[str, dict[str, Any]] = {}
    for name in _DIMENSIONS:
        entry = dimensions.get(name) if isinstance(dimensions.get(name), dict) else {}
        score = max(0.0, min(5.0, _safe_float(entry.get("score"), 0.0)))
        normalised_dimensions[name] = {
            "score": round(score, 2),
            "reason": str(entry.get("reason") or "No reason supplied by reviewer.")[:1200],
        }

    findings = []
    for item in raw.get("findings") or []:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "medium").lower()
        if severity not in {"critical", "high", "medium", "low"}:
            severity = "medium"
        findings.append({
            "severity": severity,
            "frame_index": max(0, int(_safe_float(item.get("frame_index"), 0))),
            "timestamp_seconds": round(max(0.0, _safe_float(item.get("timestamp_seconds"), 0.0)), 3),
            "scene_id": str(item.get("scene_id") or "unknown")[:120],
            "category": str(item.get("category") or "other")[:80],
            "observation": str(item.get("observation") or "")[:2000],
            "why_it_matters": str(item.get("why_it_matters") or "")[:2000],
            "action": str(item.get("action") or "")[:2400],
        })

    status = str(raw.get("status") or "revise").lower()
    if status not in {"pass", "revise", "fail"}:
        status = "revise"
    critical = sum(f["severity"] == "critical" for f in findings)
    high = sum(f["severity"] == "high" for f in findings)
    blocking_names = {
        "hook_0_3_seconds", "editorial_hierarchy", "ui_legibility",
        "caption_readability", "professional_finish",
    }
    blocking_low = any(normalised_dimensions[name]["score"] < 3 for name in blocking_names)
    if status == "pass" and (critical or high >= 2 or blocking_low):
        status = "revise"

    comparison = raw.get("comparison") if isinstance(raw.get("comparison"), dict) else None
    if comparison:
        winner = str(comparison.get("winner") or "tie")
        if winner not in {"candidate_a", "candidate_b", "tie"}:
            winner = "tie"
        comparison = {
            "winner": winner,
            "reasons": [str(v)[:1000] for v in (comparison.get("reasons") or [])[:12]],
        }

    return {
        "status": status,
        "summary": str(raw.get("summary") or "")[:3000],
        "dimensions": normalised_dimensions,
        "findings": findings,
        "must_fix": [str(v)[:1600] for v in (raw.get("must_fix") or [])[:24]],
        "keep": [str(v)[:1200] for v in (raw.get("keep") or [])[:16]],
        "comparison": comparison,
        "confidence": round(max(0.0, min(1.0, _safe_float(raw.get("confidence"), 0.5))), 3),
        "model": model,
    }


class VercelGatewayVisualReview(BaseTool):
    name = "vercel_gateway_visual_review"
    version = "1.0.0"
    tier = ToolTier.ANALYZE
    capability = "visual_review"
    provider = "vercel-ai-gateway"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["binary:node"]
    install_instructions = (
        "Install Node.js >=22, run `npm install --prefix "
        "tools/analysis/vercel_gateway_visual_runtime`, and configure an active "
        "Vercel AI Gateway credential or OmniRoute gateway pool."
    )
    capabilities = [
        "rendered_frame_review", "multi_image_review", "hook_review",
        "editorial_hierarchy_review", "caption_design_review", "pairwise_comparison",
        "omniroute_key_pool",
    ]
    supports = {
        "multiple_images": True,
        "pairwise_comparison": True,
        "structured_findings": True,
        "human_replacement": False,
        "key_pool_rotation": True,
    }
    best_for = [
        "post-render hero and overview-video design criticism",
        "finding unreadable UI, decorative framing, weak hierarchy, and caption problems",
        "A/B comparison of successive render candidates",
    ]
    not_good_for = [
        "replacing deterministic technical QA",
        "replacing final human approval",
        "judging motion from a single still",
    ]
    input_schema = {
        "type": "object",
        "required": ["frame_paths"],
        "properties": {
            "frame_paths": {"type": "array", "minItems": 1, "maxItems": 16, "items": {"type": "string"}},
            "frame_metadata": {"type": "array", "items": {"type": "object"}},
            "video_path": {"type": "string"},
            "model": {"type": "string", "default": "zai/glm-4.5v"},
            "review_mode": {"type": "string", "enum": ["single", "pairwise"], "default": "single"},
            "candidate_split_index": {"type": "integer", "minimum": 1},
            "context": {"type": "object"},
            "iteration": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
            "output_path": {"type": "string"},
            "api_key": {"type": "string", "description": "Runtime-only; never logged or returned."},
            "omniroute_db_path": {"type": "string"},
            "max_pool_attempts": {"type": "integer", "minimum": 1, "maximum": 20, "default": 6},
            "timeout_seconds": {"type": "number", "minimum": 10, "maximum": 600, "default": 180},
        },
    }
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=768, disk_mb=150, network_required=True)
    retry_policy = RetryPolicy(max_retries=2, backoff_seconds=1.0, retryable_errors=["rate_limit", "timeout", "gateway_error"])
    side_effects = ["calls paid Vercel AI Gateway model", "writes visual review JSON artifact"]
    user_visible_verification = [
        "Open the contact sheet and every critical/high referenced frame",
        "Confirm findings are grounded in visible evidence",
        "Require human approval for hero/overview final delivery",
    ]

    def _credentials(self, inputs: dict[str, Any]) -> list[GatewayCredential]:
        # Reuse the production-tested resolver so speech and visual review share
        # the same encrypted OmniRoute pool without copying or exposing secrets.
        return VercelGatewayTTS()._credentials(inputs)

    def get_status(self) -> ToolStatus:
        runtime_ready = (
            shutil.which("node") is not None
            and RUNTIME_SCRIPT.is_file()
            and (RUNTIME_DIR / "node_modules" / "ai" / "package.json").is_file()
            and (RUNTIME_DIR / "node_modules" / "@ai-sdk" / "gateway" / "package.json").is_file()
        )
        return ToolStatus.AVAILABLE if runtime_ready and self._credentials({}) else ToolStatus.UNAVAILABLE

    @staticmethod
    def _runtime_call(*, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        env = os.environ.copy()
        env["AI_GATEWAY_API_KEY"] = api_key
        env.pop("VERCEL_AI_GATEWAY_API_KEY", None)
        process = subprocess.run(
            [shutil.which("node") or "node", str(RUNTIME_SCRIPT)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=RUNTIME_DIR,
            env=env,
            timeout=timeout,
            check=False,
        )
        try:
            result = json.loads(process.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI SDK visual-review runtime returned invalid JSON: "
                + (process.stderr or process.stdout or "")[:500]
            ) from exc
        if process.returncode != 0 or not result.get("success"):
            status_code = result.get("statusCode")
            error = RuntimeError(str(result.get("error") or process.stderr or "visual review failed")[:1000])
            setattr(error, "status_code", status_code)
            setattr(error, "retryable", bool(result.get("retryable", status_code in _RETRYABLE_STATUS_CODES)))
            raise error
        return result

    @staticmethod
    def _build_user_prompt(inputs: dict[str, Any], frame_count: int) -> str:
        context = inputs.get("context") if isinstance(inputs.get("context"), dict) else {}
        mode = str(inputs.get("review_mode") or "single")
        split = inputs.get("candidate_split_index")
        comparison = ""
        if mode == "pairwise":
            comparison = (
                f"This is a pairwise review. Frames 0..{int(split or 1) - 1} are candidate_a; "
                f"frames {int(split or 1)}..{frame_count - 1} are candidate_b. Compare equivalent "
                "moments and select a winner only when visibly justified."
            )
        return (
            "Review the supplied rendered evidence as a finished professional video, not as a code prototype.\n"
            + comparison
            + "\nPROJECT CONTEXT:\n"
            + json.dumps(context, ensure_ascii=False, indent=2)[:18000]
            + "\n\nJudge the actual images against the context. Every critical or high finding must cite a frame index, "
              "timestamp, and concrete implementation action. If motion cannot be inferred from stills, state that limitation; "
              "do not invent it. The first frames marked within 0–3 seconds are the hook evidence."
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        paths = [Path(value).expanduser().resolve() for value in (inputs.get("frame_paths") or [])]
        if not paths:
            return ToolResult(success=False, error="frame_paths must contain at least one image")
        if len(paths) > 16:
            return ToolResult(success=False, error="visual review accepts at most 16 images per request")
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            return ToolResult(success=False, error="Missing review frame(s): " + ", ".join(missing[:8]))

        metadata = inputs.get("frame_metadata") or []
        frames: list[dict[str, Any]] = []
        for index, path in enumerate(paths):
            item = metadata[index] if index < len(metadata) and isinstance(metadata[index], dict) else {}
            frames.append({
                "index": index,
                "path": str(path),
                "label": str(item.get("label") or path.name),
                "timestampSeconds": _safe_float(item.get("timestamp_seconds"), 0.0),
                "sceneId": str(item.get("scene_id") or "unknown"),
            })

        model = str(inputs.get("model") or "zai/glm-4.5v")
        payload = {
            "model": model,
            "systemPrompt": _SYSTEM_PROMPT,
            "userPrompt": self._build_user_prompt(inputs, len(frames)),
            "frames": frames,
            "temperature": 0.1,
            "maxOutputTokens": 5000,
        }
        if inputs.get("base_url"):
            payload["baseURL"] = str(inputs["base_url"])

        credentials = self._credentials(inputs)
        if not credentials:
            return ToolResult(success=False, error="No Vercel AI Gateway credential available. " + self.install_instructions)
        max_attempts = min(int(inputs.get("max_pool_attempts", 6)), len(credentials))
        timeout = float(inputs.get("timeout_seconds", 180))
        selected: GatewayCredential | None = None
        runtime_result: dict[str, Any] = {}
        errors: list[str] = []
        for credential in credentials[:max_attempts]:
            try:
                runtime_result = self._runtime_call(api_key=credential.api_key, payload=payload, timeout=timeout)
                selected = credential
                break
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                status = getattr(exc, "status_code", None)
                errors.append(f"{credential.connection_id}: {('HTTP ' + str(status) + ' ') if status else ''}{str(exc)[:360]}")
                if not bool(getattr(exc, "retryable", True)):
                    break
        if selected is None:
            return ToolResult(
                success=False,
                error="Vercel AI Gateway visual review failed across credential pool: " + " | ".join(errors),
                duration_seconds=round(time.time() - started, 2),
                model=model,
            )

        review = _normalise_review(runtime_result.get("review") or {}, model=model)
        artifact = {
            "version": "1.0",
            "video_path": str(inputs.get("video_path") or ""),
            "iteration": int(inputs.get("iteration", 1)),
            "review_mode": str(inputs.get("review_mode") or "single"),
            "reviewer": {
                "provider": self.provider,
                "model": model,
                "transport": "vercel-ai-sdk-gateway-language-model-v4",
                "human_replacement": False,
            },
            "evidence": {
                "frame_paths": [str(path) for path in paths],
                "frame_metadata": frames,
                "frame_count": len(paths),
                "hook_window_reviewed": any(0 <= frame["timestampSeconds"] <= 3.0 for frame in frames),
            },
            **review,
            "human_approval": {"required": True, "status": "pending"},
        }
        validate_artifact("visual_review", artifact)
        output_path = Path(inputs.get("output_path") or "visual_review.json").expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        generation_info = runtime_result.get("generationInfo") or {}
        cost = _safe_float(generation_info.get("totalCost"), 0.0)
        return ToolResult(
            success=True,
            data={
                "status": artifact["status"],
                "summary": artifact["summary"],
                "critical_findings": sum(v["severity"] == "critical" for v in artifact["findings"]),
                "high_findings": sum(v["severity"] == "high" for v in artifact["findings"]),
                "must_fix": artifact["must_fix"],
                "output": str(output_path),
                "provider": self.provider,
                "model": model,
                "credential_source": selected.source,
                "credential_connection_id": selected.connection_id,
                "pool_attempt_count": len(errors) + 1,
                "gateway_generation_id": runtime_result.get("generationId"),
                "human_approval_required": True,
            },
            artifacts=[str(output_path)],
            cost_usd=round(cost, 6),
            duration_seconds=round(time.time() - started, 2),
            model=model,
        )
