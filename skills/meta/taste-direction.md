# Taste Direction - Meta Skill

## When to Use

Use this before committing to visual identity, mood boards, proposal packets, custom playbooks, atelier composition, image reference batches, or brand-heavy videos.

This skill defines OpenMontage's video taste profile contract. Do not treat it as a frontend style recipe. The output is a compact video taste profile that travels through proposal, scene planning, asset prompts, edit, compose, and review.

## Output Contract

Write a `taste_profile` when the proposal or playbook needs a stronger creative contract:

```json
{
  "design_read": "Premium expert explainer: calm authority, high trust, low ornament.",
  "visual_variance": 4,
  "motion_intensity": 3,
  "information_density": 5,
  "palette_discipline": "Neutral base, one accent, no decorative gradients.",
  "layout_variation": "Alternate editorial split frames with data-forward full-frame scenes.",
  "reference_strategy": "One reference still per scene family before asset generation.",
  "focal_strategy": "One dominant subject per beat; evidence takes focus from typography when the claim lands.",
  "surface_system": "Matte dark surfaces, one restrained radius family, one elevation ladder, cyan only for active evidence.",
  "motion_grammar": "Primary semantic action + subordinate camera/depth + near-invisible ambience; every action settles into proof.",
  "transition_strategy": "Carry focus through shared geometry or deliberate hard cuts; no repeated effect punctuation.",
  "keyframe_quality_floor": "premium-keyvisual",
  "restraint_rules": ["No decorative browser chrome by default", "No simultaneous equal-weight panels"],
  "hero_moments": ["claim-to-source handoff", "final evidence synthesis"],
  "anti_patterns": ["generic AI-purple gradient backgrounds"],
  "quality_gates": ["Every scene should carry the design read without explanatory labels."]
}
```

`visual_variance`, `motion_intensity`, and `information_density` are 1-10 integer dials. For hero/product/overview work, the profile also carries a concrete **focal strategy, surface system, motion grammar, transition strategy, static keyframe quality floor, restraint rules, and planned hero moments**. Read `skills/meta/product-film-art-direction.md` and `docs/PREMIUM_PRODUCT_FILM_STANDARD.md`; these fields are not optional taste prose for hero work — they are downstream review contracts.

The three dials are:

| Dial | Low | Mid | High |
|------|-----|-----|------|
| `visual_variance` | Tight system, repeated grammar | Pattern with purposeful scene families | Each beat may use a distinct visual mode |
| `motion_intensity` | Calm holds, small transitions | Clear motion accents and reveals | Fast kinetic language, frequent directional changes |
| `information_density` | One idea per frame | Main idea plus support detail | Dense dashboards, diagrams, or layered callouts |

## Process

### 1. Make a Design Read

Before choosing a playbook or palette, state what the video needs to feel like and why. Tie it to the audience, promise, platform, and subject matter.

Good reads are specific:

- "Investor-facing AI launch: precise, restrained, and credible; avoid hype visuals."
- "Youth science short: bright, curious, and kinetic; make invisible physics feel tactile."
- "Security incident explainer: tense and surgical; high contrast, low ornament, readable evidence."

Weak reads are only adjectives:

- "modern and clean"
- "cinematic"
- "professional"

### 2. Set the Three Dials

Pick `visual_variance`, `motion_intensity`, and `information_density` before writing concepts. These numbers should explain later choices:

- High motion plus low information means short kinetic beats, not dense diagrams.
- Low motion plus high information means stable frames, chart builds, and long readable holds.
- High variance means scene families need stronger anchors: recurring type, palette, framing, or sound motif.

### 3. Choose a Style Path

Use the dials to pick one of three paths:

| Path | Use When | Artifact |
|------|----------|----------|
| Existing playbook | A preset honestly matches the read | `production_plan.playbook` |
| Custom playbook | The subject has its own visual world | generated `styles/<name>.yaml` with `taste_profile` |
| Atelier art direction | Hero work needs a one-off language | `production_plan.art_direction` plus `taste_profile` |

Do not let preset availability override the design read. If the content calls for a custom visual world, write the custom playbook or art direction.

### 4. Lock the premium frame/motion contract for hero work

For `quality_tier="hero"`, product/brand/launch work, or `video_category="overview-video"`, read `skills/meta/product-film-art-direction.md` before authoring scenes and add:

- `focal_strategy`
- `surface_system`
- `motion_grammar`
- `transition_strategy`
- `keyframe_quality_floor="premium-keyvisual"`
- `restraint_rules`
- `hero_moments`

A hero taste profile that only contains adjectives and 1–10 dials is incomplete. The next stage must be able to turn the profile into a keyframe board and motion hierarchy without inventing the art direction again.

### 5. Plan References

If the work uses AI image/video, mood boards, brand assets, or atelier composition, create a reference strategy:

- Use one reference still per scene family or major beat.
- Do not compress the whole direction into one mood board image.
- For brand/product work, create or inspect a brand kit before asset generation.
- For screen demos, inspect the real UI and write a redesign/audit note before styling overlays.

### 6. Carry the Profile Downstream

At proposal stage:

- Add `production_plan.taste_profile`.
- Log style/playbook selection in `decision_log`.
- Explain how the dials affect runtime, composition mode, and asset generation.

At scene planning:

- Vary layouts according to `visual_variance`.
- Keep on-screen text and callouts within `information_density`.
- Set transition families and camera movement from `motion_intensity`.
- For hero/overview work, write `keyframe_contract`, `focus_path`, and `motion_hierarchy` for every scene.
- Render the representative keyframe board before finishing motion. A weak paused frame is a send-back, not something motion is allowed to hide.

At assets:

- Include palette, texture, framing, and reference strategy in image/video prompts.
- Generate reference stills before full batches when the profile depends on visual nuance.

At edit/compose:

- Match hold times and cut rhythm to the motion dial.
- Avoid adding decorative overlays that violate the design read.

## Anti-Default Checklist

Flag these before moving forward:

- Generic AI-purple gradients or default corporate-blue visuals with no subject reason.
- Same transition on every cut when `visual_variance` is 4 or higher.
- Kinetic motion that makes narration harder to follow.
- Dense callouts when `information_density` is 4 or lower.
- Text-only slides unless the design read intentionally calls for typographic storytelling.
- Mood boards that look attractive but do not map to concrete scene families.
- Brand/product videos that never show or inspect the real brand/product surface.
- Hero scenes whose paused proof frame would look like an unresolved dashboard, wireframe, or generic UI showcase.
- Several elements moving continuously at equal energy with no dominant authored action.
- Repeated browser/device chrome, card stacks, or transition effects used as visual scaffolding rather than story-specific choices.

## Review Hooks

Reviewer should check:

- Does `taste_profile.design_read` explain a real creative choice?
- Do scene plans and edits respect the three dials?
- Are anti-patterns actually avoided?
- Is the reference strategy present when AI images/video or atelier work depends on visual nuance?
- For hero/product/overview work, are focal strategy, surface system, motion grammar, transition strategy, premium keyframe floor, restraint rules, and hero moments explicit?
- Could this video belong to any topic after replacing the title? If yes, the taste direction is too generic.
- Would representative scene frames still look premium if motion were paused? If no, the art direction is unresolved.
