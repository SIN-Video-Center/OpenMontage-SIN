# Premium Product Film Standard

Status: binding for `quality_tier=hero`; binding for `video_category=overview-video`; strongly recommended for any launch, brand, product or flagship explainer.

A premium product film is not a technically correct composition with enough motion. It is an art-directed sequence in which every important frame has a clear subject, every movement changes attention or meaning, and every scene belongs to one coherent visual world.

The governing principle is simple:

> **If a representative frame looks weak when paused, motion is not allowed to hide the weakness. Fix the frame first.**

This standard closes the gap between "animated UI" and a directed product film.

## 1. Static keyframe quality floor

Before full animation, every scene must have at least one representative **proof frame** that can stand on its own as a premium editorial/product keyvisual.

For hero/overview work, a proof frame must have:

- one unmistakable focal subject;
- intentional negative space rather than accidental emptiness;
- a readable foreground/midground/background hierarchy;
- controlled light and local contrast that lead the eye;
- no debug-like labels, scene counters, decorative scaffolding or component clutter;
- product evidence large enough to understand at the delivery resolution;
- a composition that still works when all motion is paused.

The scene plan records this under `keyframe_contract`:

```json
{
  "focal_subject": "The source citation inside the real chat response",
  "hierarchy": "Citation first, answer second, supporting chrome recedes",
  "proof_frame": "The citation is visibly connected to its source passage",
  "still_quality_goal": "premium-keyvisual"
}
```

A weak proof frame blocks motion authoring. Do not add particles, glows, camera drift or faster easing to rescue an unresolved composition.

## 2. One focal subject per beat

A premium scene can contain many layers, but only one layer owns the viewer's attention at a time.

Every hero/overview scene records a `focus_path`:

```json
{
  "entry": "Viewer enters on the answer claim",
  "action": "Focus travels along the source link",
  "proof": "Original passage becomes the dominant object",
  "exit": "The passage hands focus to the next dossier beat"
}
```

Rules:

- The focal subject must be visually dominant by scale, contrast, sharpness, motion, position or isolation.
- Supporting UI must recede through crop, luminance, depth, blur, masking or reduced motion before adding more outlines.
- Two equally dominant panels are a failure unless the story is explicitly a comparison.
- A headline may lead a beat, but it must yield to evidence when the narration reaches the proof.
- Product UI is staged as evidence, not displayed as wallpaper.

## 3. Motion hierarchy: primary, secondary, ambient

Every hero/overview scene records a `motion_hierarchy`:

```json
{
  "primary": "Citation travels from answer to source passage",
  "secondary": "Product window eases into a tighter crop",
  "ambient": "Background light breathes below perceptual priority",
  "settle": "Source passage holds cleanly for 18 frames after the reveal"
}
```

### Primary motion

The primary motion changes meaning or attention. It is the scene's authored action.

Examples:

- a source is attached to a claim;
- a selected control changes state;
- a dataset converges into a result;
- a cursor performs a truthful product action;
- a diagram relationship is built;
- a before state transforms into a proof state.

### Secondary motion

Secondary motion supports the primary action: camera reframing, parallax, depth separation, local crop, focus pull or a subordinate reveal.

### Ambient motion

Ambient motion creates life without asking for attention: restrained light drift, low-energy particles, subtle texture or atmospheric depth.

Ambient motion never satisfies the semantic-motion contract.

### Timing discipline

- Prefer one primary event at a time.
- Use anticipation only when it improves comprehension or weight.
- Use overlap/follow-through for physical continuity, not decoration.
- Every primary event must have a readable settle/proof state.
- A constant translate/scale over the whole scene is camera drift, not authored choreography.
- Multiple elements moving continuously at similar speed produces visual noise and is a blocking hero defect.

## 4. Surface system, not a component zoo

A film needs one coherent material/surface language even when scene layouts vary.

Lock before authoring:

- corner-radius family;
- border/edge treatment;
- shadow and elevation ladder;
- background material;
- accent and glow discipline;
- typography roles;
- blur/depth rules;
- product-window treatment;
- icon and connector treatment.

For hero work, `taste_profile.surface_system` describes this contract.

Rules:

- Do not mix unrelated card styles, glow strengths, radii and shadow recipes across scenes.
- Do not wrap every screenshot in generic browser chrome. Use chrome only when browser/device context is semantically useful or belongs to the real product.
- Do not add decorative nested frames around already framed UI.
- At most one visible product-surface boundary should dominate a focal region.
- Prefer crop, light, focus, masking and depth before drawing an outline.
- If a border can be removed without losing information, remove it.

## 5. Product evidence choreography

Real product evidence leads. The composition directs attention through it.

For each UI/evidence beat:

1. Identify the exact region that proves the spoken claim.
2. Enter on a readable state.
3. Perform one truthful interaction or visual transformation.
4. Land on a proof state that can be held and inspected.
5. Hand focus to the next beat.

Avoid:

- full-screen screenshots shrunk until no text is readable;
- two similar screenshots side-by-side without an explicit comparison;
- fake clicks, fake controls or fabricated feature states;
- a screenshot that simply drifts while narration describes something else;
- detached metadata labels floating far from the evidence they name.

## 6. Typography as direction, not scaffolding

Typography is a scene subject only when the story needs a typographic beat.

- Use intentional line breaks and optical balance.
- Do not repeat a large headline plus a caption saying the same sentence.
- Do not place a large headline beside dense UI unless one clearly yields to the other.
- Do not use scene numbers, chapter counters or template navigation as decoration.
- Small labels support a focal subject; they do not carry the primary claim.
- When evidence becomes important, reduce headline dominance instead of keeping both at maximum contrast.

## 7. Transition choreography

A transition is a **handoff of attention**, not an effect inserted between scenes.

`taste_profile.transition_strategy` defines the family. Each scene's exit should explain what the eye follows into the next beat.

Preferred transition logic:

- shared geometry morphs or aligns;
- a selected object becomes the next scene's subject;
- camera direction continues across the cut;
- luminance or focus transfers to the next evidence region;
- a line/connector completes into the next diagram;
- a hard cut lands on a strong visual contrast when that is more powerful than an effect.

Avoid:

- the same wipe, glow sweep or zoom on every cut;
- transitions that briefly become the most visually important thing in the film;
- an effect that has no relationship to either scene;
- hiding a weak scene change behind motion blur.

## 8. Hero moments and restraint

A hero film needs memorable moments, not maximum intensity everywhere.

- Plan 2–4 hero moments for a typical 45–90 second film.
- The signature device remains scarce: one or at most two beats.
- Surround high-energy moments with calmer evidence holds so contrast exists.
- Use high motion only where narration or music earns it.
- A premium film may be visually quiet. Quiet is not static when focus, evidence and timing are directed.

`taste_profile.hero_moments` records the intended peaks. `taste_profile.restraint_rules` records what the film deliberately refuses to do.

## 9. Keyframe board before full render

For hero/overview work:

1. Author enough of every scene to render a representative proof frame.
2. Render one proof frame per scene; render a second frame for scenes whose hierarchy changes materially.
3. Inspect the board as a set of still images before full animation.
4. Reject any frame that looks like a wireframe, generic dashboard showcase, debug UI, template card stack or unresolved layout.
5. Check the entire board for silhouette and scale variation.
6. Only then finish motion and render a candidate.

The board is not optional polish. It is the cheapest point to catch art-direction failure.

## 10. Rendered review dimensions

Hero/overview semantic visual review must score these dimensions from actual rendered evidence:

- `hook_0_3_seconds`
- `editorial_hierarchy`
- `keyframe_quality`
- `focus_choreography`
- `surface_coherence`
- `primary_subject_scale`
- `ui_legibility`
- `label_readability`
- `dead_space_discipline`
- `frame_and_container_discipline`
- `semantic_motion_clarity`
- `motion_authorship`
- `transition_quality`
- `restraint_and_density`
- `caption_readability`
- `caption_rhythm`
- `evidence_story_alignment`
- `professional_finish`

For hero/overview work, the premium dimensions (`editorial_hierarchy`, `keyframe_quality`, `focus_choreography`, `surface_coherence`, `motion_authorship`, `professional_finish`) must score at least 4/5. A high-severity rendered finding blocks delivery until revised or explicitly escalated after the iteration ceiling.

The rendered critic receives **motion strips** rather than relying on isolated stills: one hook strip and one strip per scene, each containing early → primary proof → late/exit samples from the real MP4. The critic must read each strip left-to-right and judge only visible state/focus changes. The review records both image count and underlying sampled-frame count, and hero/overview review blocks when any expected scene is missing from evidence.

## 11. What may be reused

OpenMontage may reuse **mechanics and design tokens**, not a finished hero look.

Safe to reuse:

- easing/timing knowledge;
- deterministic animation helpers;
- caption-safe geometry;
- focus and depth principles;
- shadow/elevation scales as a starting system;
- motion-hierarchy vocabulary;
- keyframe-review workflow;
- renderer/runtime mechanics;
- accessibility and QA gates.

Not safe to reuse in Atelier hero work:

- a previous project's hero component;
- a finished browser/device frame merely recolored;
- a signature transition copied from another film;
- a recurring card/diagram layout used as the spine of multiple scenes;
- a previous project's distinctive palette, typography pairing or signature device.

The goal is **consistently high quality without visually identical output**.

## 12. Definition of premium-ready

A hero/overview candidate is not premium-ready until all are true:

- every scene has a recorded keyframe contract, focus path and motion hierarchy;
- representative proof frames pass the static keyframe board review;
- the contact sheet shows meaningful variation in silhouette, scale and focal placement;
- semantic motion is carried by authored state change, not background drift;
- product evidence is readable and staged around the spoken claim;
- surface and typography systems are coherent across scenes;
- transitions hand focus rather than advertise themselves;
- rendered semantic visual review passes the premium thresholds;
- deterministic technical QA passes;
- a human watches the complete mixed film and approves the exact final render.
