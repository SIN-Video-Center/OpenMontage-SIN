# Scene, Overlay, and Motion Registry

This file is generated from `schemas/scene_types.registry.json` by
`scripts/generate_scene_contracts.py`. Do not edit the lists manually.

The registry synchronizes:

- `scene_plan.schema.json`
- `edit_decisions.schema.json`
- `src/generated/sceneTypes.ts`
- this document

Scene-specific required props remain in `edit_decisions.schema.json` and the matching
renderer component.

## Scene types

| Type | Role |
|---|---|
| `talking_head` | pipeline/source/bespoke scene |
| `broll` | pipeline/source/bespoke scene |
| `video` | pipeline/source/bespoke scene |
| `animation` | pipeline/source/bespoke scene |
| `character_scene` | pipeline/source/bespoke scene |
| `diagram` | pipeline/source/bespoke scene |
| `text_card` | templated Remotion component |
| `transition` | pipeline/source/bespoke scene |
| `generated` | pipeline/source/bespoke scene |
| `screen_recording` | pipeline/source/bespoke scene |
| `hero_title` | templated Remotion component |
| `stat_card` | templated Remotion component |
| `bar_chart` | templated Remotion component |
| `line_chart` | templated Remotion component |
| `pie_chart` | templated Remotion component |
| `kpi_grid` | templated Remotion component |
| `comparison` | templated Remotion component |
| `callout` | templated Remotion component |
| `progress_bar` | templated Remotion component |
| `anime_scene` | templated Remotion component |
| `terminal_scene` | templated Remotion component |
| `screenshot_scene` | templated Remotion component |

## Overlay types

| Type |
|---|
| `section_title` |
| `stat_reveal` |
| `hero_title` |
| `provider_chip` |

## Motion classes

| Motion class | Quality meaning |
|---|---|
| `source_motion` | semantic |
| `generated_motion` | semantic |
| `procedural_semantic_motion` | semantic |
| `character_motion` | semantic |
| `ui_interaction` | semantic |
| `camera_only` | weak/non-semantic |
| `decorative_loop` | weak/non-semantic |
| `static_hold` | weak/non-semantic |

## Timeline contract

`in_seconds` and `out_seconds` are absolute final-timeline positions.
`source_in_seconds` is the source-media trim offset. Composition duration is the
maximum `out_seconds`.

## Adding a type

1. Add it once to `schemas/scene_types.registry.json`.
2. Add its props/conditional requirements to `edit_decisions.schema.json`.
3. Implement the renderer dispatch/component.
4. Run `python scripts/generate_scene_contracts.py`.
5. Run contract tests and a Golden Production render.
