"""Delivery promise classifier.

Before provider selection, classify what the production is actually promising
to deliver. This prevents the most damaging failure mode: silently downgrading
from motion-led to still-led without the user knowing.

The delivery promise is set at the proposal stage and locked. If the compose
stage can't honor it, the system must stop and ask — not silently substitute.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class PromiseType(Enum):
    MOTION_LED = "motion_led"
    SOURCE_LED = "source_led"
    DATA_EXPLAINER = "data_explainer"
    TEACHER_EXPLAINER = "teacher_explainer"
    SCREEN_DEMO = "screen_demo"
    AVATAR_PRESENTER = "avatar_presenter"
    HYBRID = "hybrid"
    LOCALIZATION = "localization"


# Rules per promise type — what is and isn't acceptable
PROMISE_RULES: dict[str, dict[str, Any]] = {
    "motion_led": {
        "still_fallback_allowed": False,
        "requires_video_generation": True,
        "min_motion_ratio": 0.8,  # Semantic motion coverage for presentable/final work
        "description": "Video's quality depends on real motion — generated video clips, footage, or animation.",
    },
    "source_led": {
        "still_fallback_allowed": True,
        "requires_video_generation": False,
        "min_motion_ratio": 0.3,
        "description": "User-provided footage is the primary medium. Generated assets fill gaps only.",
    },
    "data_explainer": {
        "still_fallback_allowed": True,
        "requires_video_generation": False,
        "min_motion_ratio": 0.6,
        "description": "Data visualization and explanation. Data relationships must build progressively with the narration.",
    },
    "teacher_explainer": {
        "still_fallback_allowed": True,
        "requires_video_generation": False,
        "min_motion_ratio": 0.5,
        "description": "Educational content. Clarity comes from semantic visual changes, not static illustrated voice-over.",
    },
    "screen_demo": {
        "still_fallback_allowed": True,
        "requires_video_generation": False,
        "min_motion_ratio": 0.6,
        "description": "Screen recording or product demo. UI interactions and state changes must track the narration.",
    },
    "avatar_presenter": {
        "still_fallback_allowed": False,
        "requires_video_generation": True,
        "min_motion_ratio": 0.7,
        "description": "AI avatar or talking head presentation. Requires sustained presenter or supporting semantic motion.",
    },
    "hybrid": {
        "still_fallback_allowed": True,
        "requires_video_generation": False,
        "min_motion_ratio": 0.4,
        "description": "Mix of source footage, generated content, and graphics with meaningful visual response.",
    },
    "localization": {
        "still_fallback_allowed": True,
        "requires_video_generation": False,
        "min_motion_ratio": 0.3,
        "description": "Translation/dubbing of existing video. Preserving source motion, timing, and clarity.",
    },
}


@dataclass
class DeliveryPromise:
    """Classifies what the production promises to deliver."""

    promise_type: PromiseType
    motion_required: bool
    source_required: bool
    tone_mode: str          # "cinematic", "educational", "corporate", "playful", "raw"
    quality_floor: str      # "draft", "presentable", "broadcast"
    approved_fallback: str | None = None  # "animatic", "still_led", or None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["promise_type"] = self.promise_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeliveryPromise":
        return cls(
            promise_type=PromiseType(data["promise_type"]),
            motion_required=data.get("motion_required", False),
            source_required=data.get("source_required", False),
            tone_mode=data.get("tone_mode", "corporate"),
            quality_floor=data.get("quality_floor", "presentable"),
            approved_fallback=data.get("approved_fallback"),
        )

    def get_rules(self) -> dict[str, Any]:
        """Get the enforcement rules for this promise type."""
        return PROMISE_RULES.get(self.promise_type.value, {})

    def validate_cuts(self, cuts: list[dict]) -> dict[str, Any]:
        """Validate a list of edit cuts against this delivery promise.

        Returns a dict with 'valid', 'violations', and 'motion_ratio'.
        """
        rules = self.get_rules()
        violations = []

        if not cuts:
            return {"valid": False, "violations": ["No cuts provided"], "motion_ratio": 0.0}

        # Measure duration-weighted semantic motion rather than trusting the mere
        # presence of an animation field. Camera-only zooms and decorative loops do
        # not explain a narrated beat; progressive charts, diagrams and UI changes do.
        semantic_classes = frozenset({
            "source_motion",
            "generated_motion",
            "procedural_semantic_motion",
            "character_motion",
            "ui_interaction",
        })
        weak_classes = frozenset({"camera_only", "decorative_loop"})
        inherently_semantic_types = frozenset({
            "video", "animation", "avatar", "character_scene", "anime_scene",
            "screen_recording", "terminal_scene", "screenshot_scene",
        })
        component_types = frozenset({
            "text_card", "hero_title", "stat_card", "bar_chart", "line_chart",
            "pie_chart", "kpi_grid", "comparison", "progress_bar", "callout",
            "diagram",
        })

        semantic_duration = 0.0
        weak_duration = 0.0
        static_duration = 0.0
        total_duration = 0.0
        semantic_cuts = 0
        weak_cuts = 0
        static_cuts = 0
        long_nonsemantic_holds: list[str] = []

        for cut in cuts:
            start = float(cut.get("in_seconds", 0) or 0)
            end = float(cut.get("out_seconds", start + 1) or (start + 1))
            duration = max(0.001, end - start)
            total_duration += duration

            source = str(cut.get("source", ""))
            cut_type = str(cut.get("type", ""))
            motion_class = str(cut.get("motion_class", ""))
            has_state_change = all(
                bool(cut.get(field))
                for field in ("visual_state_before", "visual_action", "visual_state_after")
            )

            if not motion_class and source:
                ext = source.rsplit(".", 1)[-1].lower() if "." in source else ""
                if ext in ("mp4", "mov", "webm", "avi", "mkv"):
                    motion_class = "source_motion"
            if not motion_class and cut_type in inherently_semantic_types:
                motion_class = "procedural_semantic_motion"
            if not motion_class and cut_type in component_types and has_state_change:
                motion_class = "procedural_semantic_motion"
            if not motion_class and (cut.get("animation") or (cut.get("transform") or {}).get("animation")):
                motion_class = "camera_only"
            if not motion_class:
                motion_class = "static_hold"

            if motion_class in semantic_classes and has_state_change:
                semantic_duration += duration
                semantic_cuts += 1
            elif motion_class in semantic_classes or motion_class in weak_classes:
                # A semantic label without concrete before/action/after states is an
                # unproven intent declaration and therefore remains weak motion.
                weak_duration += duration
                weak_cuts += 1
                if duration > 2.5:
                    long_nonsemantic_holds.append(str(cut.get("id", "unknown")))
            else:
                static_duration += duration
                static_cuts += 1
                if duration > 2.5:
                    long_nonsemantic_holds.append(str(cut.get("id", "unknown")))

        motion_ratio = semantic_duration / total_duration if total_duration else 0.0
        weak_ratio = weak_duration / total_duration if total_duration else 0.0
        static_ratio = static_duration / total_duration if total_duration else 0.0

        min_ratio = float(rules.get("min_motion_ratio", 0.0))
        if self.quality_floor == "draft":
            min_ratio *= 0.5
        if motion_ratio < min_ratio:
            violations.append(
                f"Semantic motion coverage {motion_ratio:.0%} is below minimum "
                f"{min_ratio:.0%} for {self.promise_type.value}/{self.quality_floor}. "
                "Camera-only zooms and decorative loops do not count."
            )

        if self.quality_floor in ("presentable", "broadcast") and weak_ratio > 0.25:
            violations.append(
                f"Camera-only/decorative motion covers {weak_ratio:.0%} of the timeline; "
                "the maximum for presentable/final work is 25%."
            )

        if self.quality_floor in ("presentable", "broadcast") and long_nonsemantic_holds:
            violations.append(
                "Non-semantic visual holds longer than 2.5s: "
                + ", ".join(long_nonsemantic_holds)
                + ". Add a narrated state change or explicitly shorten the hold."
            )

        nonsemantic_duration = weak_duration + static_duration
        if not rules.get("still_fallback_allowed", True) and nonsemantic_duration > total_duration * 0.5:
            if self.approved_fallback != "still_led":
                violations.append(
                    f"{self.promise_type.value} does not allow still-led fallback, "
                    f"but {nonsemantic_duration / total_duration:.0%} of the timeline "
                    "is camera-only, decorative, or static."
                )

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "motion_ratio": motion_ratio,
            "semantic_motion_ratio": motion_ratio,
            "camera_only_ratio": weak_ratio,
            "static_ratio": static_ratio,
            "motion_cuts": semantic_cuts,
            "slide_cuts": weak_cuts,
            "still_cuts": static_cuts,
            "semantic_duration_seconds": round(semantic_duration, 3),
            "total_duration_seconds": round(total_duration, 3),
        }


def classify_from_brief(
    pipeline_type: str,
    user_intent: dict[str, Any],
) -> DeliveryPromise:
    """Classify delivery promise from pipeline type and user intent.

    This provides a sensible default. The proposal-director should refine
    it based on research and capability checks.

    Args:
        pipeline_type: Pipeline manifest name.
        user_intent: Dict with keys like 'motion_required', 'has_footage',
                     'tone', 'quality', 'platform'.
    """
    # Pipeline → default promise type mapping
    pipeline_defaults: dict[str, PromiseType] = {
        "cinematic": PromiseType.MOTION_LED,
        "animated-explainer": PromiseType.DATA_EXPLAINER,
        "animation": PromiseType.MOTION_LED,
        "talking-head": PromiseType.AVATAR_PRESENTER,
        "avatar-spokesperson": PromiseType.AVATAR_PRESENTER,
        "screen-demo": PromiseType.SCREEN_DEMO,
        "hybrid": PromiseType.HYBRID,
        "localization-dub": PromiseType.LOCALIZATION,
        "podcast-repurpose": PromiseType.SOURCE_LED,
        "clip-factory": PromiseType.SOURCE_LED,
    }

    promise_type = pipeline_defaults.get(pipeline_type, PromiseType.HYBRID)

    # Override with explicit user intent
    if user_intent.get("motion_required") is False and promise_type == PromiseType.MOTION_LED:
        promise_type = PromiseType.HYBRID

    source_required = user_intent.get("has_footage", False)
    if source_required and promise_type not in (PromiseType.SOURCE_LED, PromiseType.LOCALIZATION):
        promise_type = PromiseType.SOURCE_LED

    motion_required = user_intent.get("motion_required", promise_type in (
        PromiseType.MOTION_LED, PromiseType.AVATAR_PRESENTER,
    ))

    tone_mode = user_intent.get("tone", "corporate")
    quality_floor = user_intent.get("quality", "presentable")

    return DeliveryPromise(
        promise_type=promise_type,
        motion_required=motion_required,
        source_required=source_required,
        tone_mode=tone_mode,
        quality_floor=quality_floor,
    )
