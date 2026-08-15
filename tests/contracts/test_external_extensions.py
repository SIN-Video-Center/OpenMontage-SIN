import json
import shutil
from pathlib import Path

from lib.extensions import (
    extension_roots,
    register_extension,
    resolve_skill_path,
    validate_extension_root,
)
from lib.pipeline_loader import _load_pipeline_cached, list_pipelines, load_pipeline

ROOT = Path(__file__).resolve().parents[2]


def _make_plugin(tmp_path: Path) -> Path:
    plugin = tmp_path / "overview-plugin"
    (plugin / "pipeline_defs").mkdir(parents=True)
    (plugin / "skills" / "categories").mkdir(parents=True)
    (plugin / "openmontage-plugin.yaml").write_text(
        "id: test-overview\nversion: '1.0.0'\nname: Test Overview\n",
        encoding="utf-8",
    )
    shutil.copy(
        ROOT / "pipeline_defs" / "framework-smoke.yaml",
        plugin / "pipeline_defs" / "external-smoke.yaml",
    )
    (plugin / "skills" / "categories" / "external-overview.md").write_text(
        "# External Overview\n", encoding="utf-8"
    )
    return plugin


def test_extension_registration_is_external_and_idempotent(tmp_path: Path):
    plugin = _make_plugin(tmp_path)
    registry = tmp_path / "config" / "extensions.json"
    register_extension(plugin, registry_path=registry)
    register_extension(plugin, registry_path=registry)

    payload = json.loads(registry.read_text())
    assert payload["version"] == 1
    assert payload["extensions"] == [{"path": str(plugin.resolve()), "enabled": True}]
    assert extension_roots(registry) == [plugin.resolve()]
    assert validate_extension_root(plugin)["surfaces"]["pipeline_defs"].endswith("pipeline_defs")


def test_external_pipeline_and_skill_are_discoverable(tmp_path: Path, monkeypatch):
    plugin = _make_plugin(tmp_path)
    monkeypatch.setenv("OPENMONTAGE_EXTENSION_PATHS", str(plugin))
    _load_pipeline_cached.cache_clear()

    manifest = load_pipeline("external-smoke")
    assert manifest["name"] == "framework-smoke"
    assert "external-smoke" in list_pipelines()
    assert resolve_skill_path("categories/external-overview") == (
        plugin / "skills" / "categories" / "external-overview.md"
    ).resolve()
