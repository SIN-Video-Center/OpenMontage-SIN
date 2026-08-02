# Remotion Skill

## Role in OpenMontage

Remotion is one governed composition runtime behind `video_compose`. It is selected
at proposal together with a separate authoring mode:

```text
render_runtime   = remotion
composition_mode = templated | atelier
```

It is not the universal default and must not replace an approved HyperFrames or
FFmpeg path at compose time.

## Authoring modes

### Templated

Use the shared `Explainer` scene catalog for:

- internal drafts and timing animatics;
- repeatable series/localization;
- approved standard data/education work whose information progressively changes
  with narration;
- existing Remotion-only presenter/caption workflows.

A card, chart, still, animated gradient, or moving background does not become
semantic motion merely because it is rendered in Remotion.

### Atelier

Use a project-local hand-authored composition for bespoke/hero work. Required:

- `quality_tier="hero"` or another approved bespoke brief;
- `delivery_kind="bespoke"`;
- `composition_mode="atelier"`;
- project-specific `art_direction`;
- complete `scene_inventory` with a unique primary subject per scene;
- the signature device used in at most two scenes;
- no import from stock creative components or a previous project's look.

Reuse engine knowledge only. The ordinary `Explainer` may make an animatic, never
the hero final.

## Runtime routing

| Use case | Route |
|---|---|
| Draft/animatic with exact timing/captions | Remotion templated |
| Repeatable data/education series | Remotion templated when semantic beat planning passes |
| Individual hero explainer/product film | Remotion Atelier or approved HyperFrames Atelier |
| Kinetic typography/HTML-native launch reel | Usually HyperFrames Atelier |
| Pure sequential trims/concat | FFmpeg |
| Approved runtime unavailable | Block and request a new approved proposal decision |

Never silently fall back.

## Canonical contracts

Read before authoring:

- `schemas/scene_types.registry.json`
- `schemas/artifacts/proposal_packet.schema.json`
- `schemas/artifacts/scene_plan.schema.json`
- `schemas/artifacts/edit_decisions.schema.json`
- `schemas/artifacts/final_review.schema.json`

Run `python scripts/generate_scene_contracts.py` after changing the scene registry.
Do not maintain another scene-type list in this skill.

## Absolute timeline

There is one final timeline:

```text
scene.start_seconds / scene.end_seconds = absolute final placement
cut.in_seconds / cut.out_seconds         = absolute final placement
cut.source_in_seconds                    = seek/trim inside source media
```

The composition duration is:

```text
max(cut.out_seconds)
```

It is not the sum of absolute cut end-times. `Root.tsx` and `Explainer.tsx` must use
the same contract.

## Local sequence duration

`useVideoConfig().durationInFrames` returns the full composition duration even
inside a `<Sequence>`. Any scene-local fade, chart build, camera move, or transition
therefore receives a local duration prop from `SceneRenderer`.

Current local-duration consumers include:

- image and video scenes;
- background-image layers;
- progress bars;
- bar, line, pie, and KPI charts;
- anime scenes.

New scene components must follow the same pattern.

## Visual beat and motion contract

Every narrated scene/cut carries:

- `primary_subject`
- `visual_state_before`
- `visual_action`
- `visual_state_after`
- `motion_class`
- `semantic_purpose`

Semantic classes:

```text
source_motion
generated_motion
procedural_semantic_motion
character_motion
ui_interaction
```

Weak/non-semantic classes:

```text
camera_only
decorative_loop
static_hold
```

A semantic class without concrete before/action/after states is treated as weak
motion. Charts count as semantic only when their data or relationships progressively
build with the spoken beat.

For presentable/hero work:

- semantic visual change meets the approved delivery-promise threshold;
- camera-only/decorative motion remains at or below 25%;
- no unapproved non-semantic hold lasts 2.5 seconds or more;
- an intentional long static hold requires `approved_hold_reason` and
  `motion_class="static_hold"` before render.

## Templated scene props

Scene and overlay type names come from `schemas/scene_types.registry.json`.
Scene-specific props and required fields come from
`schemas/artifacts/edit_decisions.schema.json`.

Examples:

- `hero_title` / `text_card` / `callout` require exact rendered text;
- `stat_card` requires `stat`;
- bar/pie/KPI components require `chartData`;
- line charts require `chartSeries`;
- comparison requires both labels and values;
- progress requires `progress`;
- terminal/screenshot/anime scenes require their matching structured media fields.

All props live at the top level of the cut object. Do not invent `props` or
`cut.overlay`. Use top-level `overlays[]`.

## Rendered transitions

`transition_in`, `transition_out`, and `transition_duration` must alter rendered
frames. The shared Explainer executes fade, slide, zoom, and wipe through a
scene-local transition wrapper. A new transition family needs implementation plus a
frame-based contract test; adding a string to JSON alone is insufficient.

## Source media

- Images and videos use the existing asset resolver.
- `source_in_seconds` becomes `<OffthreadVideo startFrom={...}>` in frames.
- Templated image motion remains `camera_only` unless it performs a real information-
  bearing state change.
- Video sources are muted in the visual layer by default; narration/music/SFX use the
  explicit EDL audio contract.

## Audio contract

The shared composition supports:

- one narration track or absolute-timeline narration segments;
- music offset, looping, fade-in/out;
- narration-aware music ducking with reduction, attack, and release;
- SFX at absolute timeline positions;
- word/phrase captions burned through `CaptionOverlay`.

When narration and music coexist, configure `audio.music.ducking`. Final QA measures
the delivered mix, including integrated loudness and true peak.

## Governed final render

Use the high-level tool operation:

```python
from tools.video.video_compose import VideoCompose

result = VideoCompose().execute({
    "operation": "render",
    "proposal_packet": proposal_packet,
    "script_path": "projects/<slug>/artifacts/script.json",
    "scene_plan": scene_plan,
    "edit_decisions": edit_decisions,
    "asset_manifest": asset_manifest,
    "output_path": "projects/<slug>/renders/final.mp4",
})
```

For Atelier, the asset manifest may be absent when the composition owns project-local
assets, but proposal, approved script, complete scene plan, and edit decisions remain
mandatory.

Direct `npx remotion render` is for preview, stills, diagnostics, and authoring. It
must not be used to deliver a final while bypassing proposal preservation,
pre-compose validation, or final review.

## Pre-compose gates

Before render, `video_compose` verifies:

- approved runtime and composition mode;
- hero/bespoke routing;
- full scene plan rather than reconstructed cut metadata;
- delivery-promise and duration-weighted semantic-motion coverage;
- slideshow risk (`revise` blocks final work; hero/Atelier average must remain below
  2.0);
- absolute timeline and resolved assets/audio;
- Atelier art direction, scene inventory, subject distinctness, signature-device
  scarcity, and absence of stock creative imports.

## Render-based final review

Every final render is measured from the actual output:

1. ffprobe container, streams, duration, resolution, codec.
2. Representative and scene-boundary frames.
3. Timestamped contact sheet.
4. 2-FPS low-resolution frame-difference motion analysis.
5. Motion-coverage ratio against the approved quality floor.
6. Freeze/non-semantic holds with exact timecodes.
7. Perceptual-hash repeated-layout signals.
8. Black-frame detection.
9. Automatic transcription of the rendered output against the approved script for
   hero/broadcast work.
10. Loudness, true peak, clipping, expected ducking.
11. Subtitle/caption presence and timing.
12. Runtime and delivery-promise preservation.

`final_review.status == "pass"` is the only deliverable state. `revise` and `fail`
both return an unsuccessful tool result and require correction/re-rendering.

## Critical Remotion constraints

- Use `useCurrentFrame()`, `interpolate()`, and `spring()` for deterministic motion.
- Do not use CSS animations, timers, promises, or wall-clock state for rendered
  animation.
- Clamp interpolation at both ends.
- Pass local scene duration; do not use composition duration for scene-local timing.
- Keep project assets isolated; avoid cross-project staging collisions.
- Render in series unless the machine has enough memory for parallel Chromium.
- Exact titles, names, legal text, captions, and CTA copy must be rendered as text,
  never baked into generated images.

## Quality checklist

- [ ] Proposal quality/runtime/composition mode preserved.
- [ ] Absolute timeline and `source_in_seconds` validated.
- [ ] Complete semantic visual beat per narrated claim.
- [ ] Scene-local durations passed to all time-dependent components.
- [ ] Transitions visibly change rendered frames.
- [ ] Narration, music ducking, SFX, and captions configured.
- [ ] Atelier art direction and scene inventory pass when applicable.
- [ ] Governed `operation="render"` used with approved script and scene plan.
- [ ] Rendered-output transcript/audio/frame QA completed.
- [ ] Final-review status is exactly `pass`.

## Caption-safe rendering contract

The canonical implementation is
`remotion-composer/src/components/CaptionOverlay.tsx` plus
`components/captionLayout.ts`. Shared compositions must reserve physical stage
space through `getReservedCaptionRailHeight()` when captions use
`reserved-rail`. Project-local Atelier compositions must implement the same
geometry and pass time-coded protected regions to the caption renderer.

`CaptionOverlay` is required to throw when the selected caption rectangle
intersects an active protected region. Do not catch that error, choose a
least-bad overlap, or disable the collision guard. See
`docs/CAPTION_AND_LANGUAGE_GOVERNANCE.md`.
