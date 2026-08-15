# External Extensions

OpenMontage supports external extension roots so category-specific workflows can live outside the core fork and survive upstream updates.

## Registration

An extension root contains `openmontage-plugin.yaml` and may provide `pipeline_defs/`, `skills/`, `categories/`, `docs/`, `tools/`, or `tests/`.

Register an extension with its installer or directly through `lib.extensions.register_extension()`. The local registry is written to:

```text
.openmontage/extensions.json
```

The registry is intentionally ignored by Git because it contains machine-specific absolute paths.

For ephemeral environments, set a platform-separated path list:

```bash
export OPENMONTAGE_EXTENSION_PATHS=/path/to/plugin-a:/path/to/plugin-b
```

## Discovery order

Core pipeline manifests are searched first, followed by enabled extension roots. An explicit `defs_dir` passed to `load_pipeline()` remains isolated and does not search extensions. Skill references can be resolved with `lib.extensions.resolve_skill_path()`.

## Update workflow

1. Commit and push all work on a SIN feature branch.
2. Keep `origin` pointed at `SIN-Video-Center/OpenMontage` and `upstream` at `calesthio/OpenMontage`.
3. Fast-forward the fork's clean `main` from `upstream/main`.
4. Rebase or merge the SIN production branch onto the updated `main`.
5. Run core contract tests and each registered plugin's tests.
6. Render the reference production and inspect final audio plus representative frames.

External plugins and product-owned production workspaces are not touched by an OpenMontage core update. Product-specific films belong to their product repositories; a separate production repository is not required by the extension architecture.

## Current repositories

- Core fork: `SIN-Video-Center/OpenMontage`
- Overview plugin: `Delqhi/openmontage-overview-video`
- Example product-owned production workspace: `OpenAfD-Chat/tooling/video/openafd-chat-overview/`

### Automated fork synchronization

On the SIN production branch, run:

```bash
./scripts/sync_sin_upstream.sh
```

The helper refuses a dirty worktree, fast-forwards the fork mirror, merges upstream into the production branch, runs the binding extension/Overview tests, and pushes only after they pass.
