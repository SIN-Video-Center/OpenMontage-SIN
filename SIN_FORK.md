# OpenMontage Fork Layout

## Branches

- `main` — sole canonical SIN branch, containing the merged SIN production extensions and upstream history.
- Historical SIN production/snapshot branches were removed after their contents were verified in `main`.

## Remotes

```text
origin   https://github.com/SIN-Video-Center/OpenMontage.git
upstream https://github.com/calesthio/OpenMontage.git
```

## Related repositories

- `SIN-Video-Center/openmontage-overview-video` — private Overview-Video plugin.
- `Delqhi/openafd-overview-video` — private versioned OpenAfD production.

## Updating

From a clean `main` checkout:

```bash
./scripts/sync_sin_upstream.sh
```

The script refuses dirty worktrees, merges official upstream into canonical `main`, runs the extension and Overview contract suite, and pushes only after tests pass.

Do not use `git clean -fdx` in a production checkout. Machine-local plugin registration lives in `.openmontage/extensions.json`, and concrete productions live in their own repositories.
