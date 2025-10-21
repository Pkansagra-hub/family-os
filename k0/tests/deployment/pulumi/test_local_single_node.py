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
from k0.deployment.pulumi.stacks.local_single_node import (
    LocalSingleNodeSettings,
    orchestrate,
)


@fixture
def compose_dir() -> Iterator[Path]:
    temp_dir = TemporaryDirectory()
    base_path = Path(temp_dir.name)
    renderer.set_generated_directory_override(base_path)

    yield base_path

    renderer.set_generated_directory_override(None)
    temp_dir.cleanup()


@fixture
def pulumi_stub() -> (
    Iterator[Tuple[types.ModuleType, Dict[str, Dict[str, Any]], Dict[str, Any]]]
):
    secret_store: Dict[str, Dict[str, Any]] = {
        "k0-secrets": {},
        "k0": {},
    }
    exports: Dict[str, Any] = {}

    class DummyLog:
        def __init__(self) -> None:
            self.records: list[Tuple[str, Tuple[Any, ...]]] = []

        def warning(self, message: str, *args: Any) -> None:
            self.records.append((message, args))

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


@test("local-single-node orchestrate writes bundle and exports stack outputs")
def _(_compose_dir: Any = compose_dir, pulumi_ctx: Any = pulumi_stub) -> None:
    compose_path = cast(Path, _compose_dir)
    _, secret_store, exports = cast(
        Tuple[types.ModuleType, Dict[str, Dict[str, Any]], Dict[str, Any]], pulumi_ctx
    )

    secret_store["k0-secrets"]["secret:kernel-api-key"] = "token123"

    settings = LocalSingleNodeSettings(
        storage=StorageLayerConfig.from_mapping(
            {
                "enable_postgres": True,
                "sqlite_path": str(compose_path / "k0.sqlite3"),
                "kernel_image": "familyos/kernel:test",
                "worker_image": "familyos/worker:test",
                "env_file": "./env/local.env",
                "kernel_port": 9090,
                "extra_tags": {"team": "ops"},
            }
        ),
        telemetry=TelemetryConfig.from_mapping(
            {
                "enable_grafana": False,
                "enable_alertmanager": True,
                "dashboards_path": "generated/dashboards",
                "alert_rules_path": "generated/rules",
                "grafana_admin_password": "Secret123",
            }
        ),
        secrets=[
            SecretMaterial(name="kernel-api-key", provider="pulumi", rotation_days=30),
            SecretMaterial(name="grafana-admin", provider="pulumi", rotation_days=60),
        ],
    )

    orchestrate(settings)

    bundle_dir = compose_path / "local-single-node"
    json_manifest = bundle_dir / "local-single-node-bundle.json"
    yaml_manifest = bundle_dir / "local-single-node-bundle.yaml"
    storage_fragment = bundle_dir / "local-single-node-storage.yml"
    telemetry_fragment = bundle_dir / "local-single-node-telemetry.yml"

    assert json_manifest.exists()
    assert yaml_manifest.exists()
    assert storage_fragment.exists()
    assert telemetry_fragment.exists()

    secrets_dir = bundle_dir / "secrets"
    kernel_secret_file = secrets_dir / "kernel-api-key.json"
    assert kernel_secret_file.exists()
    secret_payload = json.loads(kernel_secret_file.read_text(encoding="utf-8"))
    assert secret_payload["name"] == "kernel-api-key"
    assert secret_payload["value"] == "token123"
    assert secret_payload["available"] is True

    manifest = json.loads(json_manifest.read_text(encoding="utf-8"))
    assert manifest["stack"] == "local-single-node"
    assert {entry["component"] for entry in manifest["components"]} == {
        "storage",
        "telemetry",
        "secrets",
    }
    assert manifest["secrets"]["missing"] == ["grafana-admin"]
    assert manifest["extra"]["outputs"]["storage"]["kernel_port"] == 9090
    assert manifest["extra"]["outputs"]["telemetry"]["enable_grafana"] is False
    assert manifest["extra"]["outputs"]["secrets"]["missing"] == ["grafana-admin"]
    assert manifest["extra"]["outputs"]["secrets"]["artifacts"][0]["path"].endswith(
        "kernel-api-key.json"
    )

    assert "local-single-node_storage" in exports
    assert "local-single-node_telemetry" in exports
    assert "local-single-node_secrets" in exports
    assert "local-single-node_bundle" in exports

    bundle_export = exports["local-single-node_bundle"]
    for artifact_info in bundle_export["artifacts"].values():
        path = Path(artifact_info["path"])
        assert path.exists()
        assert artifact_info["sha256"]

    secrets_export = exports["local-single-node_secrets"]
    assert "handles" not in secrets_export
    assert "grafana-admin" in secrets_export["missing"]
    assert any(
        item["path"].endswith("kernel-api-key.json")
        for item in secrets_export["artifacts"]
    )
    metadata_names = [entry["name"] for entry in secrets_export["metadata"]]
    assert "kernel-api-key" in metadata_names

    storage_export = exports["local-single-node_storage"]
    assert storage_export["enable_postgres"] is True
    assert storage_export["kernel_port"] == 9090

    telemetry_export = exports["local-single-node_telemetry"]
    assert telemetry_export["enable_grafana"] is False
    assert telemetry_export["enable_alertmanager"] is True
