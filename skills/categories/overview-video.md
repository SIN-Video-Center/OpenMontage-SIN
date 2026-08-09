# Overview-Video Category Skill

Read `docs/categories/OVERVIEW_VIDEO.md` **and** `docs/PREMIUM_PRODUCT_FILM_STANDARD.md` before producing any artifact whose approved `video_category` is `overview-video`. Also load `skills/meta/product-film-art-direction.md` before scene authoring.

## Routing

This skill supplements, but does not replace, the active pipeline director skill. Preserve these independent fields:

- `video_category=overview-video`
- pipeline
- quality tier
- delivery kind
- motion expectation
- renderer family
- composition mode
- render runtime

## Mandatory workflow

1. Translate the brief into the five-question Overview promise: problem, identity, mechanism, evidence, control/outcome.
2. Write an adult causal narration within the real duration budget.
3. Build a pronunciation lexicon with display and spoken forms before TTS.
4. Generate and transcribe the most pronunciation-sensitive sample; batch only after it passes.
5. Inventory real product UI/source evidence before authoring generic motion graphics.
6. Build a claim-to-visual beat map. Each claim needs a before, semantic action and proof state.
7. For every scene, write `keyframe_contract`, `focus_path`, and `motion_hierarchy`; do not author vague camera-only motion.
8. Render a representative keyframe board before full motion. Recompose any paused frame that is not premium-keyvisual quality.
9. Reserve a lower reading field geometrically while continuing the scene background through it.
10. Use `integrated-field` captions; never add a full-width opaque safety bar.
11. Synchronize final audio, captions and visual action from actual take timings.
12. Render and inspect the 0–3 second hook at 0.25, 1.5, and 2.8 seconds.
13. Run `visual_review_loop`; use its frame-specific revision brief to change code and rerender.
14. Compare the new candidate against the previous candidate; never weaken the gate to force a pass.
15. Stop after three iterations and require a human to view the full film and listen to the mixed narration.

## Immediate send-backs

Send the stage back when any of these appear:

- brand or acronym lacks a pronunciation guide;
- TTS sample is unapproved, mistranscribed or wrong;
- narration reads like disconnected slogans or childish simplification;
- the plan uses generic cards instead of available product evidence;
- a scene relies on camera drift or glow as its only motion;
- a hero scene has no `keyframe_contract`, `focus_path`, or `motion_hierarchy`;
- a representative paused frame looks like a dashboard showcase, component demo, wireframe, or generic UI wrapper rather than a directed keyvisual;
- two or more equally dominant subjects compete without an explicit comparison purpose;
- the same browser/device chrome, card stack, or transition effect becomes the visual spine across scenes;
- several unrelated elements move continuously at equal energy without a primary authored action or readable settle state;
- a headline has accidental wrapping or orphan words;
- captions overlap a motion path;
- caption safety is implemented as a black/full-width bar;
- scene, caption and spoken claim do not describe the same beat;
- a final review did not inspect the actual render;
- decorative/nested frame scaffolding, scene counters, tiny evidence labels, or unreadable UI survive in rendered frames;
- the 0–3 second hook contains no conflict and no visible proof;
- narration has no playable performance plan or has not passed a human listening decision.
