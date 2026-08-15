# Portable OpenMontage Agent State

The canonical cross-machine state for OpenMontage lives in Git:

- production code, skills, contracts, and runbooks
- `remotion-composer/artifacts/visual-design/motion-proofs/` visual proof artifacts
- `SIN_FORK.md` repository/branch/remote policy

The following files are machine-local runtime databases and are intentionally not canonical state:

- `.sin/context.db`
- `sin_goal_mode.db`

They are currently empty local SQLite stores and must not be used as the only source of project memory. Agents on another Mac should clone `https://github.com/SIN-Video-Center/OpenMontage.git` and use the tracked code, docs, tests, and visual proofs. Secrets, cookies, tokens, provider credentials, and host-specific runtime state remain outside Git.
