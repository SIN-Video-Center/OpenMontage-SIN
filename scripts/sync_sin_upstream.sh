#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(git branch --show-current)" != "sin/production" ]]; then
  echo "Run this script from branch sin/production." >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree must be clean before an upstream sync." >&2
  exit 2
fi

printf '%s\n' 'Fetching official upstream and fork...'
git fetch upstream --prune
git fetch origin --prune

printf '%s\n' 'Fast-forwarding fork main from official upstream...'
git push origin upstream/main:refs/heads/main
git branch -f main upstream/main

printf '%s\n' 'Merging upstream into sin/production...'
git merge --no-edit upstream/main

printf '%s\n' 'Running SIN extension and Overview contracts...'
python3 -m pytest -q \
  tests/contracts/test_external_extensions.py \
  tests/contracts/test_overview_video_contract.py \
  tests/contracts/test_pronunciation_contract.py \
  tests/contracts/test_caption_layout_contract.py \
  tests/contracts/test_text_quality_contract.py \
  tests/contracts/test_video_contract_alignment.py \
  tests/tools/test_vercel_gateway_tts.py \
  tests/tools/test_voicebox_tts.py

printf '%s\n' 'Pushing tested production branch...'
git push origin sin/production

printf '%s\n' 'OpenMontage-SIN is synchronized.'
