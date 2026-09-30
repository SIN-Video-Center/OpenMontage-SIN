# EXTERNAL-BLOCKERS.md

External authority blockers that require human or paid-account action. These are
out-of-scope for autonomous agent execution and are recorded once at the end of
an autonomous wave per the SIN-BRAIN global rules.

## Video Generation — Vercel AI Gateway Credit Gate

**Status:** BLOCKED (external)

**Date discovered:** 2025-08-15

**Evidence:**
```
IMAGE_POOL_FAILURE: Vercel image reference generation failed across eligible
pool entries: Free tier users do not have access to this model.
Upgrade to paid credits at https://vercel.com/d?to=%2F%5Bteam%5D%2F~%2Fai%3Fmodal%3Dtop-up
for unrestricted access.
```

**Details:**
- The `character_image_production` image alias (model-lock.json) routes through
  the Vercel AI Gateway to `gpt-image-1.5` (endpoint `/v1/images/edits`).
- This model is restricted to paid Vercel AI Gateway accounts. The current
  account is on a free tier with $0 balance.
- The Vercel AI Gateway requires a **minimum balance of $10** for image and
  video model endpoints that are gated behind paid tiers.
- The `generic_image_quality` alias (`flux-2-flex`, endpoint `/v1/images/generations`)
  works fully on the free tier — the golden reference image was generated
  successfully using this path without references.
- The character-consistency gate (rejecting prompt-only generation) works
  correctly. The `references` input format fix (`["node_id", 0]` linked tuple)
  is complete. Character image *production* is blocked only by the Vercel credit gate.

**What is needed to clear this blocker:**
1. Top up the Vercel AI Gateway account with at least $10 in paid credits.
2. Verify that `gpt-image-1.5` is accessible in the key pool (check
   `VERCEL_ALLOWED_MODELS` includes `openai/gpt-image-1.5`).
3. Re-run the character image generation script:
   ```bash
   python3 scripts/generate-character-image.py        --image /tmp/teddy-golden-reference.png        --alias character_image_production
   ```

**Note:** Video generation (`character_video_i2v` with `kling-v2.6-i2v` and
`video_quality_candidate` with `veo-3.1-generate-001`) is also gated behind the
same Vercel credit requirement and cannot proceed until credits are added.

## Resolution

On Vercel credit top-up (external action), run:
```bash
python3 -c "from tools._comfyui.client import ComfyUIClient;   c = ComfyUIClient(); print(c.is_available())"
```
and then execute the full production pipeline:
1. Generate Teds-Lernwelt character reference (Teddy sitting/reading) via
   `character_image_production` with linked `LoadImage` reference.
2. Video smoke test (Kling i2v on Teddy reference → 5s clip).
3. Full OpenMontage production render: Proposal → Scene Plan → Piper narration
   → `video_compose` → final review (pass/fail QC gate).
