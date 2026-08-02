# Caption and Language Governance

Captions are part of composition planning. They are never a decorative layer placed over a finished frame. Viewer-facing language is production content and must use correct Unicode, spelling, punctuation and timing.

## Non-negotiable rules

1. **Zero visual occlusion.** Captions may not cover a subject, chart, diagram, control, data label, animation path, product UI, face or other meaningful element at any rendered frame.
2. **Geometry and appearance are separate.** A reserved reading field defines where meaningful visuals may not enter. It does not require a visible bar, panel, divider or different background.
3. **Declared protected regions.** Every scene declares normalized rectangles for meaningful content, including the complete path of moving elements. The edit decision list carries time-coded protected regions.
4. **Blocking collision behavior.** `CaptionOverlay` evaluates active protected regions at render time. Any overlap throws and fails the render; there is no least-bad collision.
5. **Correct language.** German viewer-facing text uses Unicode NFC and normal orthography: `wählen`, `souverän`, `eigenständig`, `quellengestützt`. ASCII substitutes are blocking failures.
6. **Speech synchronization.** Captions are phrase- or word-timed from final narration. Visual actions are timed to the same spoken beats.
7. **No accidental duplicate messaging.** Do not repeat a full spoken sentence as both large headline and caption unless accessibility requirements demand verbatim subtitles; simplify other copy instead.

## Layout policies — geometry

### `reserved-rail`

Reserve 10–30% of the full frame at the top or bottom as a reading field. Meaningful visuals remain outside it throughout their complete motion paths. The scene background may and usually should continue through the field.

### `adaptive-regions`

Evaluate top and bottom candidates against active protected regions. Rendering fails when neither zone is free. This policy is not permission to cover a quieter graphic.

## Visual treatments — appearance

- `integrated-field` — transparent container over a continuous scene background. Use text shadow or a restrained local contrast treatment. Default for `overview-video`.
- `local-pill` — backing exists only behind the caption text, never as a full-width rail.
- `surface` — a visible caption surface. Use only when the approved art direction explicitly requires a designed lower-third or broadcast panel.

Geometry does not imply appearance. `reserved-rail + integrated-field` is valid and is the default Overview-Video solution.

Overview-Video rule:

```json
{
  "layout_policy": "reserved-rail",
  "preferred_zone": "bottom",
  "reserved_rail_height_ratio": 0.17,
  "visual_treatment": "integrated-field",
  "full_width_background": false,
  "safe_margin_px": 56,
  "protected_regions": []
}
```

An opaque full-width black bar, gradient rail or border used merely to make captions readable is a blocking Overview-Video defect.

## Protected-region contract

Coordinates are normalized to the full output frame. Regions must include complete animation paths, not only resting positions.

```json
{
  "id": "scene-03-evidence-graph",
  "scene_id": "scene-03",
  "x": 0.06,
  "y": 0.06,
  "width": 0.88,
  "height": 0.72,
  "start_ms": 17300,
  "end_ms": 26820,
  "description": "Evidence graph, labels and animated trace path"
}
```

Each scene also declares `caption_layout.preferred_zone` and the reason that the chosen geometry is safe.

## Pipeline enforcement

- `scene_plan.schema.json` defines protected regions and local caption placement.
- `edit_decisions.schema.json` defines geometry, visual treatment, language and time-coded protected regions.
- `video_compose._pre_compose_validation` blocks incomplete contracts, rail intersections, category violations, non-NFC text and known German ASCII substitutions.
- `CaptionOverlay` renders geometry and appearance independently and throws on active-region collisions.
- `final_review.subtitle_check` records layout, treatment, background continuity, full-width-bar status, protected-region verification, collision count and Unicode status.
- Only `final_review.status == "pass"` is deliverable.

## Review checklist

- Inspect every scene boundary, dense UI state and headline wrap at full resolution.
- Confirm meaningful graphics remain above/below the reserved reading field for their full motion path.
- Confirm the scene background continues naturally through an integrated caption field.
- Confirm captions are one or two lines, legible, synchronized and safely inside margins.
- Compare captions with approved script and final rendered narration.
- Run German Unicode and orthography lint for `de-*` productions.
- Reject manual reassurance; require a declared contract and evidence from the actual render.
