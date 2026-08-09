# Product Film Art Direction — Meta Skill

## When to use

Read this for every `quality_tier="hero"` product, launch, brand, flagship explainer, and every `video_category="overview-video"`.

This skill turns a brief into a frame-first motion direction before scene code is written. It supplements `taste-direction.md` and `bespoke-composition.md`; it does not provide a reusable visual template.

Binding standard: `docs/PREMIUM_PRODUCT_FILM_STANDARD.md`.

## Core rule

> Build the premium still first. Animate the hierarchy second.

A technically moving scene with a weak still is not acceptable hero work.

## Required proposal additions

The `taste_profile` for hero/product work must include:

- `focal_strategy` — how the viewer's eye is directed and handed between subjects;
- `surface_system` — material, radius, edge, shadow, glow, depth and UI-window rules;
- `motion_grammar` — primary/secondary/ambient motion and timing character;
- `transition_strategy` — how attention crosses cuts;
- `keyframe_quality_floor` — `premium-keyvisual` for hero/overview work;
- `restraint_rules` — explicit things the film will not do;
- `hero_moments` — 2–4 intended peaks for a typical 45–90 second film.

If these are absent, stop before scene authoring.

## Scene planning contract

Every hero/overview scene must record three blocks.

### `keyframe_contract`

```json
{
  "focal_subject": "specific dominant object",
  "hierarchy": "what is first, second and intentionally recessed",
  "proof_frame": "the visible state that proves the spoken claim",
  "still_quality_goal": "premium-keyvisual"
}
```

### `focus_path`

```json
{
  "entry": "where the eye starts",
  "action": "how attention changes",
  "proof": "where attention lands",
  "exit": "what carries the viewer into the next scene"
}
```

### `motion_hierarchy`

```json
{
  "primary": "meaningful authored state change",
  "secondary": "supporting camera/depth/reveal movement",
  "ambient": "subordinate atmosphere, if any",
  "settle": "readable proof-state hold"
}
```

Do not write vague values such as `nice animation`, `camera move`, `cinematic`, or `subtle motion`.

## Keyframe-board gate

Before full motion authoring:

1. Render one representative proof still per scene.
2. Render a second still when the focal hierarchy changes materially inside the beat.
3. Review all stills together.
4. Block and recompose any scene that fails as a paused premium frame.
5. Check the board for repeated silhouette, repeated product-window size, repeated split-screen layout, and repeated focal placement.
6. Confirm that the signature device is scarce.

A scene must not advance because motion might make it feel better later.

## Art-direction checks

### Focal hierarchy

- One dominant subject at a time.
- Supporting UI recedes through scale, crop, luminance, focus, blur or reduced motion.
- Do not solve hierarchy by adding more borders.
- A large headline must yield when product evidence becomes the proof.

### Surface coherence

- Lock a radius family, edge treatment, elevation ladder, glow discipline and typography role system.
- Generic browser traffic lights/chrome are not a default premium treatment. Use them only when browser/device context matters or is true to the product.
- Never stack decorative frames around already framed UI.
- Keep one dominant surface boundary in a focal region.

### Motion authorship

- Primary motion explains meaning.
- Secondary motion supports focus.
- Ambient motion stays below perceptual priority.
- Every primary event lands in a readable settle state.
- Constant translate/scale through an entire scene is camera drift, not authored choreography.
- Avoid several unrelated elements moving continuously at the same energy.

### Transition direction

The transition must answer: **what does the viewer follow into the next beat?**

Prefer shared geometry, continuing camera direction, focus transfer, object carry, diagram completion, or a deliberate hard cut. Avoid a repeated transition effect as the film's default punctuation.

## UI evidence direction

When real product UI exists:

- identify the exact region proving the claim;
- crop to it before adding annotation;
- perform one truthful interaction/state change;
- keep necessary UI text readable at delivery resolution;
- let labels remain physically attached to the evidence;
- hold the proof state long enough to inspect;
- never fabricate functionality for visual convenience.

## Motion-library doctrine

Reusable library material should be **principle-level**:

- easing and timing families;
- focus-transfer patterns;
- deterministic spring/physics helpers;
- depth/elevation tokens;
- caption-safe geometry;
- motion hierarchy vocabulary;
- review and snapshot helpers.

Do not turn a successful hero scene into a new universal component. The next hero piece reuses the mechanics, not the finished composition.

## Review handoff

Before compose, hand the reviewer:

- `taste_profile` with all premium fields;
- scene-by-scene `keyframe_contract`, `focus_path`, and `motion_hierarchy`;
- representative stills/keyframe board;
- art-direction note;
- intended hero moments and transition strategy.

After render, `visual_review_loop` must judge the premium dimensions defined in `docs/PREMIUM_PRODUCT_FILM_STANDARD.md`. For hero/overview work, a single high-severity rendered finding blocks delivery until fixed or escalated at the iteration ceiling.
