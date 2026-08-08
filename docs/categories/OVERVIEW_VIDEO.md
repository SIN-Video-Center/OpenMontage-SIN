# Overview-Video Production Standard

Status: binding, category ID `overview-video`

An Overview-Video gives a new viewer a confident high-level understanding of a product, system, organisation or capability. It must answer five questions without becoming a feature list:

1. What problem or risk exists?
2. What is the product or system?
3. How does its core mechanism work?
4. What evidence makes the claim credible?
5. What control or outcome does the viewer gain?

## Category promise

The final film must feel like a directed product story, not a narrated slide deck, animated poster, generic template reel or screen recording with captions. Visual state changes must carry meaning. Real product evidence should lead; abstract motion graphics should explain relationships that the UI alone cannot show.

## Required narrative arc

For a 45–90 second Overview-Video:

- **Hook / risk** — expose the problem or failure mode.
- **Product premise** — state the differentiating idea in one adult, precise sentence.
- **Mechanism** — demonstrate the core workflow progressively.
- **Evidence** — reveal how claims remain traceable, measurable or verifiable.
- **Control** — show ownership, configuration, safety or operational sovereignty where relevant.
- **Synthesis** — compress the benefit into one memorable contrast.
- **Landing** — exact product name and restrained closing line; no new feature dump.

Use causal transitions: therefore, but, because, so. Avoid disconnected slogans and fragments that sound as though the viewer is being spoken down to.

## Voice and pronunciation

- Narration is written for speech, but remains intellectually adult and grammatically complete.
- Target voice occupancy is 85–93% of runtime; leave deliberate visual breathing room.
- Generate a brand-sensitive sample before the batch.
- Every acronym, brand and non-obvious name must have separate **display text** and **spoken text** when needed.
- The TTS request must apply the pronunciation guide before generation.
- The generated take must be transcribed and checked against approved transcript aliases before use.
- A wrong brand pronunciation is a blocking asset failure, even if the rest of the take sounds good.
- Provider, model, voice profile or pronunciation text may not change after sample approval without a new sample.
- Automatic fallback to a lower-quality voice is forbidden for hero work.

German example:

```json
{
  "display_text": "OpenAfD Chat",
  "spoken_text": "Open A Eff De Chat",
  "expected_transcript_aliases": ["Open A Eff De Chat", "Open A F D Chat"]
}
```

## Visual language

Overview-Video design should be restrained product editorial:

- one coherent surface system;
- one primary accent plus restrained supporting tones;
- precise typography with intentional line breaks;
- calm depth, soft light and controlled contrast;
- motion that follows information, not decorative loops;
- actual product UI, source material or system evidence wherever available;
- abstract diagrams only when they clarify flow, provenance, transformation or control.

A reference may inspire qualities, not identity theft. Do not copy OpenAI/ChatGPT logos, proprietary component shapes or a recognizable screen wholesale. It is acceptable to pursue the underlying qualities: clarity, whitespace, subtle depth, disciplined typography and quiet motion.

### Typography gates

- A hero headline must be intentionally line-broken and reviewed at representative frames.
- Avoid orphaned final words and accidental one-word second lines.
- Do not combine more than two strong typographic scales in one frame.
- Small labels may support hierarchy; they may not carry the primary claim.
- Exact product and legal text must be rendered by the runtime, never baked into generated imagery.

### Semantic motion gates

- At least 80% of spoken time must have meaningful visual change.
- Every spoken claim maps to a before → action → after state.
- Motion should land on the noun or verb it explains.
- Camera drift, glow sweeps and particles do not count as semantic motion.
- No unexplained static hold may exceed 2.5 seconds.
- The same card grid or composition may not be recycled across consecutive scenes.

## UI evidence choreography

When product UI exists, do not merely place a screenshot in a frame. Direct the viewer's attention through it:

- crop to the feature being discussed;
- reveal only the relevant region;
- animate cursor, selection, source link or state transition when truthful;
- connect UI elements to an explanatory diagram when the relationship is not obvious;
- preserve UI proportions and text legibility;
- never fabricate a capability the product does not show.

## Caption field — geometry without a bar

Captions and meaningful graphics must never overlap. This is solved by spatial planning, not by covering the bottom of the finished frame.

For the default landscape Overview-Video:

- reserve the lower 15–19% as a **reading field**;
- keep the full motion path of meaningful graphics above that field;
- continue the scene background through the reading field;
- use `visual_treatment="integrated-field"`;
- do not draw an opaque full-width rectangle, gradient rail, border or divider;
- use text shadow or a restrained local backing only when contrast requires it;
- keep captions to one or two lines, centered within safe margins;
- review opening, transitions, densest UI scene and closing at full resolution.

A full-width opaque caption bar is a blocking Overview-Video defect unless the approved art direction explicitly makes it a designed broadcast lower-third. It is not the default safety mechanism.

## Audio-visual synchronization

The final audio durations, not planned timestamps, define the edit. Each narration segment owns:

- actual start and end;
- delivery cue;
- caption phrase timing;
- visual action onset;
- visual proof state;
- pause after the beat.

A scene that visually demonstrates a different claim from the one currently spoken fails review, even when both claims are true elsewhere in the film.

## Required stage gates

### Proposal

- Declare `video_category="overview-video"`.
- Define the five-question viewer promise and art direction.
- Choose hero/standard, bespoke/templated, motion expectation, runtime and composition mode independently.

### Script

- Fit the real duration budget.
- Include pronunciation guides for all risky names.
- Include one visual action cue per claim.
- Reject childish simplification, slogan chains and grammatical fragments unless deliberately used as a brief title.

### Assets

- Approve and transcribe a voice sample before batch generation.
- Verify every final narration take for pronunciation and completeness.
- Inventory real UI and source evidence before generating substitutes.

### Scene plan

- Declare protected regions including complete motion paths.
- Keep meaningful content above the caption reading field.
- Plan actual UI choreography and visual proof states.
- Validate headline wrapping at representative frames.

### Edit

- Use final narration durations.
- Declare `visual_treatment="integrated-field"` and `full_width_background=false`.
- Align caption phrases and visual actions to the same spoken beat.

### Compose

- Render one continuous scene background across the full frame.
- Treat caption geometry and caption appearance as separate concerns.
- Block category, pronunciation, text, occlusion and runtime contract violations.

### Final review

The final is blocked unless all are true:

- category contract preserved;
- correct brand pronunciation verified from rendered audio;
- captions present, legible, synchronized and occlusion-free;
- caption background continuity confirmed;
- no full-width caption bar detected;
- German Unicode and orthography pass;
- actual UI is legible and visually relevant;
- semantic motion and scene variety pass;
- no black frames, freezes, missing assets, clipping or wrong audio;
- contact sheet and rendered-audio transcript were inspected.


## Hook, performance, and retention gates

Read `docs/EDITORIAL_PERFORMANCE_AND_RETENTION.md`. The 0–3 second hook window is a
separate reviewed deliverable. It must contain tension and visible product proof, not a
logo, chapter card, scene number, or generic setup. Hero narration requires a playable
performance plan and a human listening decision; ASR alone verifies words, not
persuasion.

## Frame discipline and rendered learning loop

- Real UI that proves a claim occupies at least 45% of frame width or 35% of frame area.
- Evidence labels are 32–44 px at 1080p and remain physically attached to the subject.
- Never place two similar full UI screenshots side by side when neither remains readable.
- Decorative nested frames, rounded outline stacks, chapter counters, and visual
  scaffolding are blocking defects.
- Hero/Overview compose must run `visual_review_loop` on 0–3 second hook frames and
  at least two representative frames per scene.
- Store `visual_review.json` and `revision_brief.md`; revise and rerender when the gate
  reports `revise`.
- Maximum automatic iterations: three. Final delivery still requires human viewing and
  listening approval.

## Reference project

`projects/openafd-v3-motion-led` is the first category reference project. It is not accepted as a reference until its governed final review reports `pass` against this document.
