from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator, Tuple, cast

from ward import fixture, test  # type: ignore[attr-defined]

from k0.deployment.pulumi import _renderer as renderer
from k0.deployment.pulumi.components.secrets import SecretMaterial
from k0.deployment.pulumi.components.storage import StorageLayerConfig
from k0.deployment.pulumi.components.telemetry import TelemetryConfig


@fixture
def compose_dir() -> Iterator[Path]:
    with TemporaryDirectory() as tmp:
        base = Path(tmp)
        renderer.set_generated_directory_override(base)
        try:
            yield base
        finally:
            renderer.set_generated_directory_override(None)


@fixture
def datacenter_ha_pulumi_stub() -> (
    Iterator[Tuple[types.ModuleType, Dict[str, Dict[str, Any]], Dict[str, Any]]]
):
    secret_store: Dict[str, Dict[str, Any]] = {"k0-secrets": {}, "k0": {}}
    exports: Dict[str, Any] = {}

    class DummyLog:
        def warning(self, *args: Any, **kwargs: Any) -> None:
            pass

    class DummyConfig:
        def __init__(self, namespace: str) -> None:
            self.namespace = namespace

        def get_secret(self, key: str) -> Any:
            return secret_store.get(self.namespace, {}).get(key)

    def export(name: str, value: Any) -> None:
        exports[name] = value

    def config_factory(namespace: str) -> DummyConfig:
        return DummyConfig(namespace)

    module = types.ModuleType("pulumi_stub")
    module.Config = config_factory  # type: ignore[attr-defined]
    module.log = DummyLog()  # type: ignore[attr-defined]
    module.export = export  # type: ignore[attr-defined]

    original = sys.modules.get("pulumi")
    sys.modules["pulumi"] = module

    try:
        yield module, secret_store, exports
    finally:
        if original is not None:
            sys.modules["pulumi"] = original
        else:
            sys.modules.pop("pulumi", None)


@test("datacenter-ha orchestrate emits HA overlays and scaling metadata")
def _(
    workspace: Any = compose_dir,
    pulumi_ctx: Any = datacenter_ha_pulumi_stub,
) -> None:
    # Import AFTER pulumi stub is set up to ensure correct stub is used
    from k0.deployment.pulumi.stacks.datacenter_ha import (
        DatacenterHASettings,
        orchestrate,
    )

    base_path = cast(Path, workspace)
    _, secret_store, exports = cast(
        Tuple[types.ModuleType, Dict[str, Dict[str, Any]], Dict[str, Any]], pulumi_ctx
    )

    secret_store["k0-secrets"]["secret:ha-api"] = "dc-token"

    settings = DatacenterHASettings(
        peer_count=4,
        storage=StorageLayerConfig.from_mapping(
            {
                "enable_postgres": True,
                "snapshot_bucket": "familyos-ha",
                "blob_provider": "s3",
            }
        ),
        telemetry=TelemetryConfig.from_mapping(
            {
                "enable_grafana": True,
                "enable_alertmanager": True,
            }
        ),
        secrets=[
            SecretMaterial(name="ha-api", provider="pulumi", rotation_days=30),
            SecretMaterial(name="ops-token", provider="pulumi", rotation_days=45),
        ],
        enable_postgres=True,
        enable_blob_store_replication=True,
    )

    orchestrate(settings)

    artifacts_dir = base_path / "datacenter-ha"
    overlay_files = {
        "base": artifacts_dir / "datacenter-ha-overlay.yml",
        "postgres": artifacts_dir / "datacenter-ha-postgres.yml",
        "blob": artifacts_dir / "datacenter-ha-blob.yml",
    }

    for artifact in overlay_files.values():
        assert artifact.exists()
        assert "TODO(familyos)" in artifact.read_text(encoding="utf-8")

    secrets_dir = artifacts_dir / "secrets"
    assert (secrets_dir / "ha-api.json").exists()

    manifest_path = artifacts_dir / "datacenter-ha-bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    component_names = {entry["component"] for entry in manifest["components"]}
    assert component_names >= {
        "storage",
        "telemetry",
        "ha-overlay",
        "postgres-ha",
        "blob-replication",
        "secrets",
    }

    cluster_outputs = manifest["extra"]["outputs"]["cluster"]
    assert cluster_outputs["scaling"]["total_nodes"] >= settings.peer_count + 3
    assert cluster_outputs["artifacts"]["postgres"]["path"].endswith(
        "datacenter-ha-postgres.yml"
    )

    export_cluster = exports["datacenter-ha_cluster"]
    assert export_cluster["topology"]["services"]["postgresql"]["enabled"] is True
    assert export_cluster["artifacts"]["base"]["path"].endswith(
        "datacenter-ha-overlay.yml"
    )

    export_secrets = exports["datacenter-ha_secrets"]
    assert "ops-token" in export_secrets["missing"]
    assert any(
        item["path"].endswith("ha-api.json") for item in export_secrets["artifacts"]
    )
