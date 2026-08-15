# Edit Director — Explainer Pipeline

## When to Use

You are the Editor for a generated explainer video. You have an `asset_manifest` with all generated files, a `scene_plan` with visual structure, and a `script` with timing. Your job is to assemble the edit decision list (EDL): what plays when, how elements layer, where subtitles go, and how music and narration interact.

This is where raw assets become a coherent video. Good editing makes average assets shine; bad editing wastes great assets.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["assets"]["asset_manifest"]`, `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["script"]["script"]` | Assets, visual plan, timing |
| Playbook | Active style playbook | Transitions, pacing rules, overlay styles |

## Process

### Step 1: Map Assets to Timeline

For each scene in the scene plan:
1. Find the matching assets from the asset manifest (by `scene_id`)
2. Find the matching narration audio (by script section)
3. Note the scene's timing (`start_seconds`, `end_seconds`)

Build a timeline map:
```
0s-10s: scene-1 (talking_head) | narration-s1 | img-intro.png
10s-18s: scene-2 (diagram) | narration-s2 | diagram-flow.svg
18s-22s: scene-3 (text_card) | narration-s3 | [text overlay]
...
```

### Step 2: Define Cuts on One Absolute Timeline

`in_seconds` and `out_seconds` are absolute positions in the finished video. They are never trim offsets inside a source asset. Use `source_in_seconds` only when playback must begin partway through source media.

Each cut defines what visual is shown and when:

```json
{
  "id": "cut-1",
  "source": "video-scene-2",
  "type": "video",
  "in_seconds": 10,
  "out_seconds": 18,
  "source_in_seconds": 3.2,
  "layer": "primary",
  "motion_class": "source_motion",
  "visual_state_before": "The raw query is waiting at the left edge.",
  "visual_action": "The query enters the encoder and becomes a vector.",
  "visual_state_after": "The vector reaches the nearest-neighbour index.",
  "semantic_purpose": "Show transformation and retrieval, not generic activity.",
  "transform": {
    "scale": 1.0,
    "position": "center",
    "animation": "ken-burns-slow-zoom"
  },
  "transition_in": "fade",
  "transition_out": "dissolve",
  "transition_duration": 0.4
}
```

**Layering rules:**
- `primary` — main visual; primary cuts must not overlap unless the selected runtime explicitly supports and the scene plan requires it.
- `overlay` — text/stat/key-term layers on top of the primary.
- `background` — solid color, texture, or relevant motion layer behind everything.

**Contract rule:** Copy the approved scene's `motion_class`, before/action/after states, semantic purpose, and primary subject into the corresponding cut. Do not replace these with a vague `animation` string.

### Step 3: Configure Subtitles

Subtitles are mandatory for all explainer content:

```json
{
  "subtitles": {
    "enabled": true,
    "style": "word-by-word",
    "font": "Inter",
    "font_size": 48,
    "color": "#FFFFFF",
    "background": "#00000088",
    "position": "bottom-center",
    "max_words_per_line": 8
  }
}
```

**Subtitle timing**: Derive from narration audio timestamps. Each word should highlight as it's spoken (word-by-word style) or display in phrase chunks (phrase style).

Use the playbook's typography for font choices.

### Step 4: Configure Audio Layers

```json
{
  "audio": {
    "narration": {
      "segments": [
        { "asset_id": "narration-s1", "start_seconds": 0 },
        { "asset_id": "narration-s2", "start_seconds": 10 }
      ]
    },
    "music": {
      "asset_id": "music-bg",
      "volume": 0.08,
      "fade_in_seconds": 2,
      "fade_out_seconds": 3,
      "ducking": {
        "enabled": true,
        "threshold_db": -3,
        "reduction_db": -8,
        "attack_ms": 200,
        "release_ms": 500
      }
    },
    "sfx": []
  }
}
```

**Music ducking**: Music volume drops when narration plays, rises during pauses. Use playbook's `audio.ducking_threshold_db`.

### Step 5: Apply Pacing Rules

Check the playbook's `motion.pacing_rules`:
- No cut shorter than `min_scene_hold_seconds`
- No cut longer than `max_scene_hold_seconds`
- Text cards hold for `text_card_hold_seconds`
- Transitions use `transition_duration_seconds`

Adjust cut timing if any violates these rules.

### Step 6: Verify Edit Completeness

**Timeline coverage:**
- [ ] All cut timestamps are absolute final-timeline positions.
- [ ] `source_in_seconds` is used for source trimming; `in_seconds` is never reused as a source seek.
- [ ] Cuts span full video duration (no accidental black frames).
- [ ] No overlapping primary cuts unless deliberately supported by the approved runtime.
- [ ] Every scene in scene_plan has at least one corresponding cut and retains its semantic motion fields.

**Asset references:**
- [ ] Every cut's `source` references a valid asset_id from the manifest
- [ ] Every narration segment references a valid audio asset
- [ ] Music asset exists

**Audio sync:**
- [ ] Narration segments are ordered and non-overlapping
- [ ] Narration timing aligns with corresponding visual cuts
- [ ] Music ducking is configured

**Subtitles:**
- [ ] Subtitles enabled
- [ ] Subtitle style uses playbook-compatible fonts and colors

### Step 7: Self-Evaluate

Score (1-5):

| Criterion | Question |
|-----------|----------|
| **Continuity** | Does every second of the video have a visual? |
| **Pacing** | Do cuts follow the playbook's timing rules? |
| **Audio-visual sync** | Does what you see match what you hear at every moment? |
| **Subtitle quality** | Are subtitles readable and correctly timed? |
| **Transition coherence** | Do transitions follow the playbook's allowed set? |

If any dimension scores below 3, revise.

### Step 8: Submit

Validate the edit_decisions artifact against the schema and persist via checkpoint.

## Common Pitfalls

- **Confusing timeline and trim time**: `in_seconds=10` means the cut starts at 10 seconds in the final video. To start 3.2 seconds into the source, set `source_in_seconds=3.2`.
- **Forgetting gaps**: If scene-1 ends at 10s and scene-2 starts at 10.5s, there's a 0.5s black frame unless the gap is intentionally filled.
- **Audio drift**: Narration audio may be slightly longer/shorter than planned. Adjust visual cuts to match actual narration durations, not planned durations.
- **No ducking**: Music playing at full volume under narration makes the video unwatchable. Always configure ducking.
- **Same transition everywhere**: Varying transitions creates rhythm. Use the playbook's allowed set, but don't use the same one for every cut.
- **Subtitle font mismatch**: Subtitles should use the playbook's body font, not a random default.

## Binding subtitle layout contract

Subtitles require the complete machine-readable contract from
`docs/CAPTION_AND_LANGUAGE_GOVERNANCE.md`: `language_code`,
`unicode_normalization="NFC"`, `layout_policy`, `preferred_zone`, safe margin,
rail size when applicable, and time-coded `protected_regions`. Copy every scene's
protected regions into the EDL with scene and time identifiers. The EDL is invalid
when subtitles are enabled but these fields are absent.

Prefer phrase timing based on the final narration performance. Align each phrase
with the scene's semantic visual action, not merely the scene start and end. A
caption may never cover content; changing opacity, shrinking the font, or placing
it over a quieter graphic does not resolve a collision.

## Overview-Video category overlay

Copy `video_category` unchanged. Configure captions with `visual_treatment="integrated-field"` and `full_width_background=false`. Final narration take durations define the timeline. Caption phrase onset, visual action onset, and spoken claim must describe the same beat.
