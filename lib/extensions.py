"""External extension discovery for OpenMontage.

Extensions live outside the core repository and are registered either through
``OPENMONTAGE_EXTENSION_PATHS`` (``os.pathsep`` separated) or through
``.openmontage/extensions.json``. Keeping extension roots external lets a fork
receive upstream updates without copying category-specific files into core.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = REPO_ROOT / ".openmontage" / "extensions.json"
PLUGIN_MANIFEST_NAMES = ("openmontage-plugin.yaml", "openmontage-plugin.yml")


def _normalize_root(value: str | Path, *, base: Path = REPO_ROOT) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _env_roots() -> list[Path]:
    raw = os.environ.get("OPENMONTAGE_EXTENSION_PATHS", "")
    return [_normalize_root(item) for item in raw.split(os.pathsep) if item.strip()]


def _registry_roots(registry_path: Path) -> list[Path]:
    if not registry_path.is_file():
        return []
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    entries = payload.get("extensions", []) if isinstance(payload, dict) else []
    roots: list[Path] = []
    for entry in entries:
        if isinstance(entry, str):
            value, enabled = entry, True
        elif isinstance(entry, dict):
            value = entry.get("path")
            enabled = entry.get("enabled", True)
        else:
            continue
        if value and enabled:
            roots.append(_normalize_root(value, base=registry_path.parent))
    return roots


def extension_roots(registry_path: Path | None = None) -> list[Path]:
    """Return enabled, existing extension roots in deterministic order."""
    registry = (registry_path or DEFAULT_REGISTRY_PATH).resolve()
    candidates = [*_env_roots(), *_registry_roots(registry)]
    seen: set[Path] = set()
    roots: list[Path] = []
    for root in candidates:
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        roots.append(root)
    return roots


def extension_subdirs(name: str, registry_path: Path | None = None) -> list[Path]:
    """Return existing ``<extension>/<name>`` directories."""
    return [path for root in extension_roots(registry_path) if (path := root / name).is_dir()]


def load_plugin_manifest(root: str | Path) -> dict[str, Any]:
    """Load and minimally validate an extension's plugin manifest."""
    extension_root = _normalize_root(root)
    manifest_path = next(
        (extension_root / name for name in PLUGIN_MANIFEST_NAMES if (extension_root / name).is_file()),
        None,
    )
    if manifest_path is None:
        raise FileNotFoundError(
            f"No OpenMontage plugin manifest found in {extension_root}; expected one of "
            f"{', '.join(PLUGIN_MANIFEST_NAMES)}"
        )
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or not payload.get("id") or not payload.get("version"):
        raise ValueError(f"Invalid OpenMontage plugin manifest: {manifest_path}")
    payload["_root"] = str(extension_root)
    payload["_manifest_path"] = str(manifest_path)
    return payload


def validate_extension_root(root: str | Path) -> dict[str, Any]:
    """Return the validated manifest and discovered extension surfaces."""
    manifest = load_plugin_manifest(root)
    extension_root = Path(manifest["_root"])
    manifest["surfaces"] = {
        name: str(extension_root / name)
        for name in ("pipeline_defs", "skills", "tools", "categories", "docs", "tests")
        if (extension_root / name).exists()
    }
    return manifest


def register_extension(
    root: str | Path,
    *,
    registry_path: Path | None = None,
    enabled: bool = True,
) -> Path:
    """Register an external extension atomically and return the registry path."""
    extension_root = _normalize_root(root)
    validate_extension_root(extension_root)
    registry = (registry_path or DEFAULT_REGISTRY_PATH).resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {"version": 1, "extensions": []}
    if registry.is_file():
        try:
            existing = json.loads(registry.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload.update(existing)
        except (OSError, json.JSONDecodeError):
            pass

    entries = payload.setdefault("extensions", [])
    normalized: list[dict[str, Any]] = []
    found = False
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, str):
            entry = {"path": entry, "enabled": True}
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        existing_root = _normalize_root(entry["path"], base=registry.parent)
        if existing_root == extension_root:
            normalized.append({"path": str(extension_root), "enabled": enabled})
            found = True
        else:
            normalized.append({"path": str(existing_root), "enabled": entry.get("enabled", True)})
    if not found:
        normalized.append({"path": str(extension_root), "enabled": enabled})
    payload["extensions"] = normalized

    temp = registry.with_suffix(registry.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(registry)
    return registry


def extension_cache_key(registry_path: Path | None = None) -> str:
    """Return a cache key that changes when roots or manifests change."""
    parts: list[str] = []
    for root in extension_roots(registry_path):
        manifest = next((root / name for name in PLUGIN_MANIFEST_NAMES if (root / name).exists()), None)
        mtime = manifest.stat().st_mtime_ns if manifest else 0
        parts.append(f"{root}:{mtime}")
    return "|".join(parts)


def resolve_skill_path(reference: str, registry_path: Path | None = None) -> Path:
    """Resolve a skill reference from core first, then external extensions."""
    suffixes = ("", ".md") if not reference.endswith(".md") else ("",)
    roots: Iterable[Path] = [REPO_ROOT / "skills", *extension_subdirs("skills", registry_path)]
    searched: list[Path] = []
    for root in roots:
        for suffix in suffixes:
            candidate = root / f"{reference}{suffix}"
            searched.append(candidate)
            if candidate.is_file():
                return candidate.resolve()
    raise FileNotFoundError(
        f"Skill not found: {reference}. Searched: " + ", ".join(str(path) for path in searched)
    )
