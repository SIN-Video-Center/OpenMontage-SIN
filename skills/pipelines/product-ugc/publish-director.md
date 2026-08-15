# Product UGC Publish Director

## Mission

Package approved creative outputs for ShopSIN. OpenMontage does not directly publish to TikTok, social networks, or the storefront.

## Preconditions

- `final_review.status` is exactly `pass`.
- Human publish/export approval is explicit and recorded.
- Product ID, creative job ID, project ID, channel variants, disclosures, and source provenance are known.
- No unresolved product or compliance blocker is concealed by the creative output.

## Export bundle

Create a deterministic export directory containing:

- primary 9:16 video,
- thumbnail/poster frame,
- commerce image pack and channel crops,
- caption/subtitle file,
- platform caption drafts and CTA copy,
- commercial-disclosure text,
- realistic-AIGC disclosure text where applicable,
- source/provenance manifest,
- final review report,
- ShopSIN handoff JSON with product ID and creative job ID.

## Handoff status

The publish log must state that this is an export/handoff, not a platform publication. ShopSIN's control plane is responsible for matching approved product data, checking inventory/price/GPSR status, uploading through official APIs, and recording external IDs.

## Hard rules

- Do not upload directly from this pipeline.
- Do not omit disclosure text from metadata.
- Do not export a file that failed or skipped final review.
- Do not rename or replace assets without updating provenance.
- Do not mark a product as live.

Write the schema-valid publish log, include all paths and checksums, and checkpoint `awaiting_human` until export approval is recorded.
