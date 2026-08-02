// AUTO-GENERATED CONTRACT MIRROR.
// Source: schemas/scene_types.registry.json
// Regenerate with: python scripts/generate_scene_contracts.py

export const SCENE_TYPES = [
  "talking_head",
  "broll",
  "video",
  "animation",
  "character_scene",
  "diagram",
  "text_card",
  "transition",
  "generated",
  "screen_recording",
  "hero_title",
  "stat_card",
  "bar_chart",
  "line_chart",
  "pie_chart",
  "kpi_grid",
  "comparison",
  "callout",
  "progress_bar",
  "anime_scene",
  "terminal_scene",
  "screenshot_scene",
] as const;

export type SceneType = (typeof SCENE_TYPES)[number];

export const OVERLAY_TYPES = [
  "section_title",
  "stat_reveal",
  "hero_title",
  "provider_chip",
] as const;

export type OverlayType = (typeof OVERLAY_TYPES)[number];

export const MOTION_CLASSES = [
  "source_motion",
  "generated_motion",
  "procedural_semantic_motion",
  "character_motion",
  "ui_interaction",
  "camera_only",
  "decorative_loop",
  "static_hold",
] as const;

export type MotionClass = (typeof MOTION_CLASSES)[number];
