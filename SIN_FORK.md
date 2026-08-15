# OpenMontage Fork Layout

## Branches

- `main` — canonical SIN branch, containing the merged `sin/production` extensions and upstream history.
- `sin/production` — tested production branch containing the SIN platform extensions.
- `sin/pre-upstream-20260802` — immutable pre-update recovery point.
- `sin/core-snapshot-20260802` — original remote snapshot before the first upstream rebase.

## Remotes

```text
origin   https://github.com/SIN-Video-Center/OpenMontage.git
upstream https://github.com/calesthio/OpenMontage.git
```

## Related repositories

- `SIN-Video-Center/openmontage-overview-video` — private Overview-Video plugin.
- `Delqhi/openafd-overview-video` — private versioned OpenAfD production.

## Updating

From a clean `sin/production` checkout:

```bash
./scripts/sync_sin_upstream.sh
```

The script refuses dirty worktrees, updates the fork's `main` only by fast-forward, merges official upstream into `sin/production`, runs the extension and Overview contract suite, and pushes only after tests pass.

Do not use `git clean -fdx` in a production checkout. Machine-local plugin registration lives in `.openmontage/extensions.json`, and concrete productions live in their own repositories.
