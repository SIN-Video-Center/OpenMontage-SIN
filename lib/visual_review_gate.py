"""Governance rules for rendered semantic visual review artifacts."""

from __future__ import annotations

from typing import Any

_BLOCKING_DIMENSIONS = {
    "hook_0_3_seconds",
    "editorial_hierarchy",
    "keyframe_quality",
    "focus_choreography",
    "surface_coherence",
    "ui_legibility",
    "caption_readability",
    "motion_authorship",
    "professional_finish",
}

_HERO_PREMIUM_DIMENSIONS = {
    "editorial_hierarchy",
    "keyframe_quality",
    "focus_choreography",
    "surface_coherence",
    "motion_authorship",
    "professional_finish",
}


def validate_visual_review(
    review: dict[str, Any],
    *,
    quality_tier: str = "standard",
    video_category: str = "",
    require_human_approval: bool = False,
) -> dict[str, Any]:
    """Return a structured gate verdict without trusting the model's status alone."""
    violations: list[str] = []
    warnings: list[str] = []
    hero = quality_tier == "hero" or video_category == "overview-video"

    evidence = review.get("evidence") if isinstance(review.get("evidence"), dict) else {}
    frame_count = int(evidence.get("frame_count") or 0)
    sampled_frame_count = int(evidence.get("sampled_frame_count") or frame_count)
    minimum_frames = 12 if hero else 4
    if sampled_frame_count < minimum_frames:
        violations.append(f"Semantic visual review inspected {sampled_frame_count} rendered samples; {minimum_frames} required")
    if hero and not evidence.get("hook_window_reviewed"):
        violations.append("Semantic visual review did not inspect the 0–3 second hook window")
    if hero and not evidence.get("scene_coverage_complete"):
        expected = evidence.get("expected_scene_ids") or []
        reviewed = evidence.get("reviewed_scene_ids") or []
        missing = [scene_id for scene_id in expected if scene_id not in reviewed]
        detail = f": {', '.join(missing)}" if missing else ""
        violations.append("Semantic visual review did not cover every scene" + detail)

    dimensions = review.get("dimensions") if isinstance(review.get("dimensions"), dict) else {}
    threshold = 3.5 if hero else 3.0
    for name in _BLOCKING_DIMENSIONS:
        entry = dimensions.get(name) if isinstance(dimensions.get(name), dict) else {}
        score = float(entry.get("score") or 0)
        required = 4.0 if hero and name in _HERO_PREMIUM_DIMENSIONS else threshold
        if score < required:
            violations.append(f"Visual review dimension {name} scored {score:.1f}/5; {required:.1f} required")

    findings = review.get("findings") or []
    critical = [f for f in findings if isinstance(f, dict) and f.get("severity") == "critical"]
    high = [f for f in findings if isinstance(f, dict) and f.get("severity") == "high"]
    if critical:
        violations.append(f"Semantic visual review contains {len(critical)} critical finding(s)")
    if hero and high:
        violations.append(f"Semantic visual review contains {len(high)} high-severity finding(s)")
    elif high:
        warnings.append(f"Semantic visual review contains {len(high)} high-severity finding(s)")

    if review.get("status") != "pass":
        violations.append(f"Semantic visual review status is {review.get('status')!r}, not 'pass'")
    if int(review.get("iteration") or 1) > 3:
        violations.append("Visual review exceeded the three-iteration production ceiling")

    approval = review.get("human_approval") if isinstance(review.get("human_approval"), dict) else {}
    if require_human_approval and approval.get("status") != "approved":
        violations.append("Required human visual approval is not recorded")

    return {
        "valid": not violations,
        "violations": list(dict.fromkeys(violations)),
        "warnings": list(dict.fromkeys(warnings)),
        "critical_count": len(critical),
        "high_count": len(high),
        "required_score": threshold,
        "hero_premium_required_score": 4.0 if hero else None,
        "minimum_frames": minimum_frames,
    }
