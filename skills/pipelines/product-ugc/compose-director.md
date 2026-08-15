# Product UGC Compose Director

## Mission

Render the approved vertical product video through the locked runtime and authoring mode, then measure the actual file. A render is not deliverable until `final_review.status` is exactly `pass`.

## Required render contract

Pass the approved proposal packet, complete scene plan, asset manifest, script, and edit decisions to `video_compose operation="render"`. Do not reconstruct a reduced contract from cuts alone. Preserve `renderer_family`, `render_runtime`, `composition_mode`, quality tier, motion expectation, and delivery promise.

If HyperFrames is locked, run its lint/validate checks before render. If Remotion or HyperFrames becomes unavailable, stop and escalate. Do not swap runtimes or downgrade to a still-led animatic without explicit user approval and a revised decision log.

## Output requirements

- Primary video: 1080x1920, 9:16, expected duration from proposal.
- Thumbnail/poster frame.
- Captions/subtitles.
- Approved product image pack and channel crops.
- Render report with provider/runtime/model/cost provenance.

## Mandatory rendered-file review

Run the governed final review, including:

- ffprobe/container, codec, dimensions, frame rate, duration, and audio channels,
- scene-boundary frames and contact sheet,
- 2-FPS motion stream,
- freeze intervals, repeated layouts, black frames, and accidental blank frames,
- rendered transcript against approved script,
- caption presence, timing, safe areas, and spelling,
- loudness, true peak, voice/music balance, and ducking,
- disclosure visibility and duration,
- product identity/fidelity across representative frames,
- delivery-promise and runtime preservation.

## Blocking conditions

Any of these block delivery: `final_review.status` of `revise` or `fail`, unsupported claim in render, product identity drift, unreadable captions, missing disclosure, wrong runtime, missing asset, broken audio, black/frozen output, or a misleading product demonstration.

Write schema-valid `render_report` and `final_review`. Only `pass` advances to publish/export.
