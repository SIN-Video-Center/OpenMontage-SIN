#!/usr/bin/env python3
"""Synchronize scene vocabulary from the canonical registry.

This script intentionally owns only shared vocabulary. Scene-specific props remain
in edit_decisions.schema.json and renderer components, but their type enum is always
rewritten from schemas/scene_types.registry.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "schemas" / "scene_types.registry.json"
SCENE_SCHEMA_PATH = ROOT / "schemas" / "artifacts" / "scene_plan.schema.json"
EDL_SCHEMA_PATH = ROOT / "schemas" / "artifacts" / "edit_decisions.schema.json"
TS_PATH = ROOT / "remotion-composer" / "src" / "generated" / "sceneTypes.ts"
DOC_PATH = ROOT / "remotion-composer" / "SCENE_TYPES.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ts_array(name: str, values: list[str]) -> str:
    rows = "\n".join(f'  "{value}",' for value in values)
    return f"export const {name} = [\n{rows}\n] as const;\n"


def main() -> None:
    registry = load(REGISTRY_PATH)
    scene_types = list(registry["scene_types"])
    overlay_types = list(registry["overlay_types"])
    motion_classes = list(registry["motion_classes"])

    if len(scene_types) != len(set(scene_types)):
        raise SystemExit("Duplicate scene types in canonical registry")
    if len(overlay_types) != len(set(overlay_types)):
        raise SystemExit("Duplicate overlay types in canonical registry")
    if len(motion_classes) != len(set(motion_classes)):
        raise SystemExit("Duplicate motion classes in canonical registry")

    scene_schema = load(SCENE_SCHEMA_PATH)
    scene_item = scene_schema["properties"]["scenes"]["items"]
    scene_item["properties"]["type"]["enum"] = scene_types
    scene_item["properties"]["motion_class"]["enum"] = motion_classes
    dump(SCENE_SCHEMA_PATH, scene_schema)

    edl_schema = load(EDL_SCHEMA_PATH)
    cut = edl_schema["$defs"]["cut"]
    cut["properties"]["type"]["enum"] = scene_types
    cut["properties"]["motion_class"]["enum"] = motion_classes
    edl_schema["$defs"]["overlay"]["properties"]["type"]["enum"] = overlay_types
    dump(EDL_SCHEMA_PATH, edl_schema)

    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = "\n".join(
        [
            "// AUTO-GENERATED CONTRACT MIRROR.",
            "// Source: schemas/scene_types.registry.json",
            "// Regenerate with: python scripts/generate_scene_contracts.py",
            "",
            ts_array("SCENE_TYPES", scene_types).rstrip(),
            "",
            "export type SceneType = (typeof SCENE_TYPES)[number];",
            "",
            ts_array("OVERLAY_TYPES", overlay_types).rstrip(),
            "",
            "export type OverlayType = (typeof OVERLAY_TYPES)[number];",
            "",
            ts_array("MOTION_CLASSES", motion_classes).rstrip(),
            "",
            "export type MotionClass = (typeof MOTION_CLASSES)[number];",
            "",
        ]
    )
    TS_PATH.write_text(ts, encoding="utf-8")

    templated = set(registry.get("templated_remotion_types", []))
    scene_rows = "\n".join(
        f"| `{value}` | {'templated Remotion component' if value in templated else 'pipeline/source/bespoke scene'} |"
        for value in scene_types
    )
    overlay_rows = "\n".join(f"| `{value}` |" for value in overlay_types)
    motion_rows = "\n".join(
        f"| `{value}` | {'semantic' if value not in {'camera_only', 'decorative_loop', 'static_hold'} else 'weak/non-semantic'} |"
        for value in motion_classes
    )
    doc = f"""# Scene, Overlay, and Motion Registry

This file is generated from `schemas/scene_types.registry.json` by
`scripts/generate_scene_contracts.py`. Do not edit the lists manually.

The registry synchronizes:

- `scene_plan.schema.json`
- `edit_decisions.schema.json`
- `src/generated/sceneTypes.ts`
- this document

Scene-specific required props remain in `edit_decisions.schema.json` and the matching
renderer component.

## Scene types

| Type | Role |
|---|---|
{scene_rows}

## Overlay types

| Type |
|---|
{overlay_rows}

## Motion classes

| Motion class | Quality meaning |
|---|---|
{motion_rows}

## Timeline contract

`in_seconds` and `out_seconds` are absolute final-timeline positions.
`source_in_seconds` is the source-media trim offset. Composition duration is the
maximum `out_seconds`.

## Adding a type

1. Add it once to `schemas/scene_types.registry.json`.
2. Add its props/conditional requirements to `edit_decisions.schema.json`.
3. Implement the renderer dispatch/component.
4. Run `python scripts/generate_scene_contracts.py`.
5. Run contract tests and a Golden Production render.
"""
    DOC_PATH.write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    main()
