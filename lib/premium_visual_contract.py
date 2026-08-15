"""Premium frame-first scene-plan governance for hero and overview videos.

The deterministic checks here do not pretend to judge taste. They verify that the
art-direction information required for a meaningful rendered review is actually
present before compose: a resolved keyframe intent, focus choreography, and an
authored motion hierarchy for every scene.
"""

from __future__ import annotations

from typing import Any

_REQUIRED_KEYFRAME_FIELDS = ("focal_subject", "hierarchy", "proof_frame", "still_quality_goal")
_REQUIRED_FOCUS_FIELDS = ("entry", "action", "proof", "exit")
_REQUIRED_MOTION_FIELDS = ("primary", "secondary", "ambient", "settle")

_AMBIENT_PRIMARY_TERMS = {
    "camera move",
    "camera drift",
    "subtle motion",
    "ambient motion",
    "glow",
    "glow sweep",
    "parallax",
    "zoom",
    "slow zoom",
    "pan",
    "drift",
    "particles",
    "background motion",
}


def _missing_fields(value: Any, fields: tuple[str, ...]) -> list[str]:
    if not isinstance(value, dict):
        return list(fields)
    return [field for field in fields if not str(value.get(field) or "").strip()]


def _looks_ambient_only(value: str) -> bool:
    normalised = " ".join(value.lower().replace("-", " ").split())
    if not normalised:
        return True
    return normalised in _AMBIENT_PRIMARY_TERMS


def validate_premium_scene_plan(
    scene_plan: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    quality_tier: str = "standard",
    video_category: str = "",
) -> dict[str, Any]:
    """Validate frame-first premium planning for hero/overview work.

    The contract is active when ``quality_tier == 'hero'`` or
    ``video_category == 'overview-video'``. Standard/draft work is left untouched.
    """
    active = str(quality_tier).lower() == "hero" or str(video_category).lower() == "overview-video"
    if not active:
        return {"active": False, "valid": True, "violations": [], "warnings": [], "scene_count": 0}

    if isinstance(scene_plan, dict):
        scenes = scene_plan.get("scenes") or []
    else:
        scenes = scene_plan or []

    violations: list[str] = []
    warnings: list[str] = []
    if not scenes:
        violations.append("Premium hero/overview contract requires a non-empty scene plan")
        return {
            "active": True,
            "valid": False,
            "violations": violations,
            "warnings": warnings,
            "scene_count": 0,
        }

    focal_subjects: list[tuple[str, str]] = []
    hero_moments = 0

    for index, scene in enumerate(scenes):
        scene_id = str(scene.get("id") or f"scene-{index + 1}")
        keyframe = scene.get("keyframe_contract")
        focus = scene.get("focus_path")
        motion = scene.get("motion_hierarchy")

        missing_keyframe = _missing_fields(keyframe, _REQUIRED_KEYFRAME_FIELDS)
        if missing_keyframe:
            violations.append(
                f"{scene_id}: premium keyframe_contract missing {', '.join(missing_keyframe)}"
            )
        elif str(keyframe.get("still_quality_goal") or "") != "premium-keyvisual":
            violations.append(
                f"{scene_id}: keyframe_contract.still_quality_goal must be 'premium-keyvisual'"
            )
        else:
            focal_subjects.append((scene_id, " ".join(str(keyframe["focal_subject"]).lower().split())))

        missing_focus = _missing_fields(focus, _REQUIRED_FOCUS_FIELDS)
        if missing_focus:
            violations.append(f"{scene_id}: focus_path missing {', '.join(missing_focus)}")

        missing_motion = _missing_fields(motion, _REQUIRED_MOTION_FIELDS)
        if missing_motion:
            violations.append(f"{scene_id}: motion_hierarchy missing {', '.join(missing_motion)}")
        elif _looks_ambient_only(str(motion.get("primary") or "")):
            violations.append(
                f"{scene_id}: motion_hierarchy.primary is ambient/camera-only; describe the authored semantic action"
            )

        if scene.get("hero_moment"):
            hero_moments += 1

        motion_class = str(scene.get("motion_class") or "")
        if motion_class in {"camera_only", "decorative_loop"}:
            warnings.append(
                f"{scene_id}: hero/overview scene uses motion_class={motion_class}; ensure the planned primary action is implemented as a real semantic state change"
            )

    seen: dict[str, str] = {}
    for scene_id, focal in focal_subjects:
        if not focal:
            continue
        if focal in seen:
            violations.append(
                f"Premium focal-subject repetition: {seen[focal]} and {scene_id} share keyframe focal_subject {focal!r}"
            )
        else:
            seen[focal] = scene_id

    if hero_moments == 0:
        warnings.append("Premium scene plan declares no hero_moment; plan at least one memorable visual peak")
    elif hero_moments > max(4, (len(scenes) + 1) // 2):
        warnings.append(
            f"Premium scene plan declares {hero_moments} hero moments across {len(scenes)} scenes; reduce peaks so contrast and restraint remain visible"
        )

    return {
        "active": True,
        "valid": not violations,
        "violations": list(dict.fromkeys(violations)),
        "warnings": list(dict.fromkeys(warnings)),
        "scene_count": len(scenes),
        "hero_moment_count": hero_moments,
    }
