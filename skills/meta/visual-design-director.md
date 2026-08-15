# Visual Design Director — Meta Skill

## When to use

Mandatory for every `quality_tier="hero"` production and every `video_category="overview-video"`.

This stage happens **after scene planning and before asset production / motion composition**. Its job is to convert narrative beats into deliberately designed frames and art assets. Remotion, HyperFrames, or any other runtime is not allowed to become the art director by default.

Binding artifact: `schemas/artifacts/visual_design_plan.schema.json`.

## Core rule

> Do not animate raw ingredients. Design the finished frame first, build the visual material, prove it as a keyframe, then author motion.

The runtime renders what it is given. A technically perfect render of a generic screenshot, card stack, gradient, and slow zoom is still a generic video.

## Required production order

1. Inventory truthful product/source evidence.
2. Choose a visual concept for every scene.
3. Decide which visual material must be **built before animation**.
4. Create those assets: source crops, SVG/vector art, diagrams, abstractions, raster illustration, masks, textures, typography layouts, or 3D/procedural elements as appropriate.
5. Assemble one representative proof keyframe per scene.
6. Render the proof keyframes at delivery resolution.
7. Build and review one keyframe board containing every scene. Use the deterministic `keyframe_board` tool when available rather than hand-stitching a contact sheet.
8. Recompose weak frames until the board is approved.
9. Only then write the final motion choreography and composition code.

## Asset strategy

Do not force every scene into the same medium. Choose intentionally from:

- `source_capture` — truthful product/source evidence, cropped around the actual proof;
- `svg_vector` — precise editorial shapes, connectors, masks, iconography, logos, line systems;
- `procedural_graphic` — deterministic geometry/data artwork authored in code;
- `vector_diagram` — designed relationships/processes, preferably progressively animatable;
- `raster_illustration` — generated or hand-created editorial imagery where literal product UI is not the subject;
- `ui_abstraction` — a truthful simplified representation derived from real product evidence, never fabricated functionality;
- `kinetic_typography` — typography is the visual subject, not merely a label beside a screenshot;
- `3d_render` — depth/material object when the concept earns it;
- `video_source` — real or generated motion source when the scene needs footage rather than composition.

A professional film normally mixes several of these across the timeline. **`source_capture` alone in every scene is a warning sign.**

## What "build assets first" means

Examples:

- A source relationship should have a deliberate vector path / node system, not a `<div>` line added during animation.
- A product screenshot may need a designed crop, matte, mask, reflection, depth plate, or UI abstraction before it is animated.
- A mechanism scene may need a custom SVG/vector diagram whose geometry is designed as a still before nodes animate.
- A hero claim may need a typographic composition with exact line breaks, scale relationships, and negative space before kinetic type is added.
- A transition object may need a shared vector/shape identity that exists in both adjacent scenes before transition timing is authored.

## Keyframe proof gate

Every scene needs at least one `moment="proof"` keyframe in `visual_design_plan.scene_designs[].keyframes`.

Before a full hero/overview render:

- the proof frame must be rendered to an actual image file;
- `status` must be `approved`;
- `output_path` must exist;
- the global `keyframe_board.status` must be `approved`;
- the board must contain every scene ID.

`video_compose` enforces this. Missing visual design or missing proof files are render blockers.

## Composition blueprint

For every scene describe:

- `focal_zone` — where attention lands;
- `negative_space` — intentional breathing room, not leftover space;
- `foreground` — highest-priority layer;
- `midground` — product/support layer;
- `background` — atmosphere/context kept below focal priority;
- `evidence_legibility` — how the proof remains understandable at delivery resolution.

This prevents the common failure mode of discovering composition accidentally while writing React/CSS.

## Motion blueprint

Motion is authored only after the proof frame works. Record:

- `primary_action` — semantic change;
- `focus_transfer` — how attention moves;
- `secondary_action` — supporting camera/depth motion;
- `transition_handoff` — what object/geometry/focus crosses into the next beat;
- `settle_state` — the readable proof hold.

Do not use `slow zoom`, `subtle parallax`, `glow drift`, or `panel slides in` as the primary action unless that movement itself carries the meaning.

## Anti-cheap defaults

Immediate send-back for hero/overview work:

- screenshot inside generic browser chrome with headline beside it as the dominant repeated grammar;
- same card/window silhouette reused through most scenes;
- generic grid + glow + floating particles used as the main visual identity;
- generated UI that invents functionality;
- arbitrary SVG decoration unrelated to narrative meaning;
- diagrams rendered as complete static plates then merely faded or zoomed;
- three or more scenes whose only asset strategy is `source_capture` with no meaningful transformation;
- animation code being written before proof frames have been produced;
- typography used as scaffolding rather than designed editorial composition;
- transitions chosen as effects instead of focus handoffs.

## Reuse doctrine

Reuse mechanics, not finished creative output.

Safe to reuse:

- SVG/path utilities;
- easing and spring helpers;
- mask/reveal mechanics;
- depth/elevation primitives;
- layout measurement helpers;
- diagram routing algorithms;
- deterministic typography measurement;
- keyframe-board tooling.

Do not reuse another project's hero frame, signature diagram, product window, palette, or signature transition as the default for a new hero film.
