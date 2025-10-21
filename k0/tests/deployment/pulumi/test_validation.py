from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator, cast

import yaml
from ward import fixture, test  # type: ignore[attr-defined]

from k0.deployment.pulumi.validation import (
    BundleManifestValidationError,
    load_and_validate_bundle_manifest,
)


@fixture
def temp_dir() -> Iterator[Path]:
    with TemporaryDirectory() as tmp:
        yield Path(tmp)


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def _valid_manifest() -> dict[str, object]:
    return {
        "stack": "local-single-node",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "components": [
            {
                "component": "storage",
                "path": "compose/generated/local-single-node/storage.yml",
                "sha256": "a" * 64,
                "size_bytes": 1024,
            }
        ],
        "secrets": {
            "missing": ["admin-token"],
            "metadata": [
                {
                    "name": "admin-token",
                    "provider": "pulumi",
                    "rotation_days": 30,
                    "hardware_binding": None,
                    "description": "",
                    "mount_path": None,
                    "config_key": "secret:admin-token",
                    "available": False,
                }
            ],
        },
        "extra": {
            "outputs": {
                "storage": {
                    "sqlite_path": "./data/k0.sqlite3",
                }
            }
        },
    }


@test("bundle manifest schema accepts valid documents")
def _(tmp_path: Any = temp_dir):
    manifest_path = cast(Path, tmp_path) / "bundle.yaml"
    manifest = _valid_manifest()
    _write_manifest(manifest_path, manifest)

    loaded = load_and_validate_bundle_manifest(manifest_path)

    assert loaded["stack"] == manifest["stack"]
    assert loaded["components"] == manifest["components"]


@test("bundle manifest schema rejects missing required fields")
def _(tmp_path: Any = temp_dir):
    manifest = _valid_manifest()
    manifest.pop("components")
    manifest_path = cast(Path, tmp_path) / "invalid.yaml"
    _write_manifest(manifest_path, manifest)

    try:
        load_and_validate_bundle_manifest(manifest_path)
    except BundleManifestValidationError as exc:
        assert any("components" in line for line in exc.errors)
    else:  # pragma: no cover - guard to ensure failure raises
        raise AssertionError("Expected BundleManifestValidationError")
