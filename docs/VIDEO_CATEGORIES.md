# Video Categories

OpenMontage separates **what kind of viewer experience is being produced** from **how it is produced**.

## Four independent decisions

1. **Video category** — the audience-facing narrative and quality contract, for example `overview-video`.
2. **Pipeline** — the operational workflow and stage sequence, for example `animated-explainer`.
3. **Renderer family / composition mode** — the creative grammar and authoring class, for example `bespoke` + `atelier`.
4. **Render runtime** — the technical engine, for example Remotion, HyperFrames or FFmpeg.

A category may use different pipelines and runtimes. A runtime never determines the category. Agents must preserve the approved `video_category` from proposal through scene plan, edit, compose, review and publish.

## Category lifecycle

A category becomes active only when all of the following exist:

- a machine-readable entry in `schemas/video_categories.registry.json`;
- a binding category contract under `docs/categories/`;
- an operational skill under `skills/categories/`;
- schema support and cross-artifact preservation checks;
- category-specific automated tests;
- at least one reference project that passes final QA.

Planned names are not production-ready categories. An agent must not invent rules for a planned category or silently treat it like an Overview-Video.

## Active category

- `overview-video` — see `docs/categories/OVERVIEW_VIDEO.md` and `skills/categories/overview-video.md`.

## Planned categories

Werbespot, Social-Media-Clip, Tutorial, Dokumentation, Satire-Video, Movie, Kinderfilm, UGC-Clip and Produktvideo are registered as planned only. Each will receive a separate narrative, visual, audio, caption and QA contract before use.
