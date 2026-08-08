# Editorial Performance, Hooks, and Caption Retention

Status: binding for `quality_tier=hero`; required by `video_category=overview-video`.

A technically correct narration is not automatically persuasive. Script, performance,
visual proof, music, and captions must create one directed viewer experience. This
contract converts editorial and retention principles into executable production gates.

## 1. The opening earns the next second

The 0–3 second window is a separate deliverable named `hook_window`.

Required:

- conflict, consequence, contradiction, a high-value question, or visible proof begins
  in the first spoken clause;
- first meaningful visual proof is visible no later than 3.0 seconds;
- no greeting, logo animation, chapter card, scene counter, generic setup, or feature
  inventory may consume the hook window;
- the hook and the first product proof must describe the same tension;
- the script declares one hook type: `evidence_gap`, `consequence`, `contradiction`,
  `question`, `before_after`, or `surprising_proof`;
- create at least three materially different hook candidates before final script lock;
- review the rendered frames at approximately 0.25, 1.5, and 2.8 seconds.

Do not treat “three seconds” as a universal magic number. It is the mandatory early
inspection window; actual success must be checked with platform retention data after
publication.

## 2. Performance plan, not a tone adjective

Every narration section must declare:

- `intent`: what the speaker wants the viewer to understand or feel;
- `operative_words`: the few words that carry the argument;
- `pace`: measured target such as restrained, compressed, accelerating, or deliberate;
- `pause_plan`: where silence creates tension or allows proof to land;
- `energy_curve`: entry, turn, and landing;
- `stance`: investigative, restrained authority, provocative challenge, explanatory,
  urgent consequence, or confidential expertise;
- `visual_landing`: the exact visible state that must coincide with the key word.

Forbidden performance directions:

- “professional”, “friendly”, “engaging”, or “confident” with no playable action;
- identical rhythm and emphasis across all sentences;
- reading punctuation mechanically;
- emphasis on adjectives while evidence nouns and consequence verbs remain flat;
- speed used to compensate for an over-written script.

For hero narration, audition the most demanding 6–12 second passage in at least three
performance variants. Compare intelligibility, authority, naturalness, brand
pronunciation, and whether operative words land with visual proof. Automatic speech
recognition verifies completeness; a human listening decision verifies performance.

## 3. Editorial writing for speech

- Lead with the claim, conflict, or consequence; qualify after attention is earned.
- Prefer concrete nouns and active verbs over institutional abstractions.
- One sentence carries one primary argument.
- Use causal progression: but, because, therefore, so.
- Replace feature lists with viewer consequences and visible mechanisms.
- Avoid slogan chains, repeated product names, bureaucratic nouns, and generic claims
  such as “revolutionary”, “powerful”, or “innovative”.
- A provocative line must remain factually defensible and must not promise a product
  capability that the visible evidence does not demonstrate.

## 4. Captions are edited rhythm

Accessibility captions remain faithful to the spoken content. Designed emphasis text is
a separate visual layer and may not silently replace or contradict the spoken sentence.

Landscape hero defaults:

- maximum two lines;
- target no more than 42 characters per line;
- adult reading speed no more than 17 characters per second unless language-specific
  delivery standards require a stricter value;
- minimum display time approximately 0.833 seconds; maximum 7 seconds;
- break at punctuation or natural syntactic boundaries, never between article and noun,
  preposition and phrase, name components, or auxiliary and verb;
- prefer 3–9 spoken words per phrase instead of one long sentence across the full width;
- time captions from final rendered-audio word timestamps, not planned timestamps;
- the phrase containing the operative word should appear as that word is spoken;
- no caption may preview the argumentative payoff so early that it destroys the spoken
  reveal;
- normal-size caption text requires at least 4.5:1 contrast; large text at least 3:1.

## 5. Visual editorial hierarchy

At 1920×1080:

- the primary real-UI subject occupies at least 45% of frame width or 35% of frame area;
- product UI text needed to prove a claim must be readable in the rendered frame;
- primary evidence labels are 32–44 px and sit next to or inside the subject they name;
- secondary support labels are at least 24 px;
- micro labels, scene counters, chapter numbers, and template navigation may not appear
  in the final film unless they are an approved editorial device with viewer value;
- one beat has one focal subject;
- do not show two similar full UI screens simultaneously when neither remains readable;
- sequence or crop evidence instead.

### Frame and container discipline

- no nested translucent rounded-rectangle outlines;
- no decorative frames, dividers, connector boxes, or focus rectangles without a
  semantic function;
- at most one visible product-surface boundary in a focal region;
- use crop, luminance, masking, depth of field, local contrast, and camera focus before
  adding a visible outline;
- if removing a frame changes no information, remove it.

## 6. Rendered learning loop

Hero/Overview delivery uses a maximum three-iteration loop:

1. render candidate;
2. sample 0–3 second hook and at least two representative frames per scene;
3. run deterministic motion, freeze, black-frame, layout, caption, and audio checks;
4. run a multimodal visual critic on the rendered evidence;
5. write `visual_review.json` and `revision_brief.md` with frame/time-specific actions;
6. revise code and render the next candidate;
7. compare equivalent before/after moments pairwise;
8. stop after iteration three and request a human decision instead of weakening gates.

The visual critic is advisory evidence, not a human replacement. A hero final requires a
human to open the video, inspect every critical/high referenced frame, listen to the
whole mixed narration, and record approval.

## 7. Post-publication learning

When platform analytics exist, store:

- 3-second view/hold metric where the platform exposes it;
- 30-second intro retention for long-form platforms;
- absolute and relative audience retention;
- first major dip and first major spike timestamps;
- caption-on/off or language observations when available;
- qualitative viewer comments tied to timestamps.

Create a hypothesis before changing the next version. Retention data identifies where
viewers leave; it does not prove why. Pair analytics with the rendered frame, spoken
line, visual action, and caption active at that timestamp.
