from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator, Tuple, cast

from ward import fixture, test  # type: ignore[attr-defined]

from k0.deployment.pulumi import _renderer as renderer
from k0.deployment.pulumi import bundle as bundle_mod
from k0.deployment.pulumi.components import secrets as secrets_mod
from k0.deployment.pulumi.components import storage as storage_mod
from k0.deployment.pulumi.components import telemetry as telemetry_mod


@fixture
def compose_dir() -> Iterator[Path]:
    temp = TemporaryDirectory()
    base = Path(temp.name)

    renderer.set_generated_directory_override(base)

    yield base

    renderer.set_generated_directory_override(None)

    temp.cleanup()


@fixture
def pulumi_module() -> Iterator[Tuple[types.ModuleType, Dict[str, Dict[str, Any]]]]:
    secrets_store: Dict[str, Dict[str, Any]] = {
        "k0-secrets": {"secret:kernel-api-key": "token123"},
        "k0": {},
    }

    class DummyConfig:
        def __init__(self, namespace: str):
            self.namespace = namespace

        def get_secret(self, key: str) -> Any:
            return secrets_store.get(self.namespace, {}).get(key)

    class DummyLog:
        def warning(self, *args: Any, **kwargs: Any) -> None:
            pass

    def config_factory(namespace: str) -> DummyConfig:
        return DummyConfig(namespace)

    module: types.ModuleType = types.ModuleType("pulumi_stub")
    module.Config = config_factory  # type: ignore[attr-defined]
    module.log = DummyLog()  # type: ignore[attr-defined]

    original = sys.modules.get("pulumi")
    sys.modules["pulumi"] = module

    yield module, secrets_store

    if original is not None:
        sys.modules["pulumi"] = original
    else:
        sys.modules.pop("pulumi", None)


@test("storage component renders compose artifact with metadata")
def _(generated_dir: Any = compose_dir) -> None:
    directory = cast(Path, generated_dir)
    config = storage_mod.StorageLayerConfig.from_mapping(
        {
            "enable_postgres": True,
            "sqlite_path": str(directory / "k0.sqlite3"),
            "kernel_image": "familyos/kernel:test",
            "worker_image": "familyos/worker:test",
            "env_file": "./env/local.env",
            "kernel_port": 9090,
            "extra_tags": {"team": "ops"},
        }
    )

    result = storage_mod.register_storage_components(stack_name="test", config=config)

    assert result.outputs["enable_postgres"] is True
    assert result.outputs["kernel_port"] == 9090
    assert result.outputs["kernel_image"] == "familyos/kernel:test"

    artifact_path = directory / "test" / "test-storage.yml"
    assert artifact_path.exists()
    content = artifact_path.read_text(encoding="utf-8")
    assert "familyos/kernel:test" in content
    assert "./env/local.env" in content


@test("telemetry component toggles services in compose output")
def _(generated_dir: Any = compose_dir) -> None:
    directory = cast(Path, generated_dir)
    config = telemetry_mod.TelemetryConfig.from_mapping(
        {
            "enable_grafana": False,
            "enable_alertmanager": True,
            "dashboards_path": "generated/dashboards",
            "alert_rules_path": "generated/rules",
            "grafana_admin_password": "Secret123",
        }
    )

    result = telemetry_mod.provision_telemetry(stack_name="telemetry", config=config)

    artifact_path = directory / "telemetry" / "telemetry-telemetry.yml"
    assert artifact_path.exists()
    rendered = artifact_path.read_text(encoding="utf-8")
    assert "alertmanager" in rendered
    assert "grafana" not in rendered
    assert "networks:\n      - k0-local" in rendered
    assert result.outputs["enable_grafana"] is False
    assert result.outputs["enable_alertmanager"] is True
    assert result.outputs["network_name"] == "k0-local"
    assert result.outputs["dashboards_path"] == "./generated/dashboards"
    assert result.outputs["alert_rules_path"] == "./generated/rules"


@test("telemetry component mounts dashboards when grafana enabled")
def _(generated_dir: Any = compose_dir) -> None:
    directory = cast(Path, generated_dir)
    config = telemetry_mod.TelemetryConfig.from_mapping(
        {
            "enable_grafana": True,
            "dashboards_path": "./dashboards",
            "grafana_provisioning": "./provisioning",
            "alert_rules_path": "./rules",
            "grafana_admin_password": "Secret123",
        }
    )

    telemetry_mod.provision_telemetry(stack_name="test", config=config)

    artifact_path = directory / "test" / "test-telemetry.yml"
    assert artifact_path.exists()
    rendered = artifact_path.read_text(encoding="utf-8")
    assert "./provisioning:/etc/grafana/provisioning:ro" in rendered
    assert "./dashboards:/var/lib/grafana/dashboards:ro" in rendered

    dashboards_dir = directory / "test" / "dashboards"
    assert dashboards_dir.exists()
    assert (dashboards_dir / "kernel_overview.json").exists()

    rules_dir = directory / "test" / "rules"
    assert rules_dir.exists()
    assert (rules_dir / "slo_alerts.yaml").exists()

    provisioning_file = (
        directory / "test" / "provisioning" / "dashboards" / "dashboards.yaml"
    )
    assert provisioning_file.exists()
    provisioning_text = provisioning_file.read_text(encoding="utf-8")
    assert "/var/lib/grafana/dashboards" in provisioning_text

    checksums_dashboards = dashboards_dir.parent / "checksums_dashboards.json"
    checksums_rules = rules_dir.parent / "checksums_rules.json"
    assert checksums_dashboards.exists()
    assert checksums_rules.exists()


@test("sync_secrets reports missing entries and returns handles")
def _(pulumi_ctx: Any = pulumi_module) -> None:
    _, secrets_store = cast(
        Tuple[types.ModuleType, Dict[str, Dict[str, Any]]], pulumi_ctx
    )
    secrets_store.setdefault("k0", {})

    materials = [
        secrets_mod.SecretMaterial(
            name="kernel-api-key", provider="pulumi", rotation_days=30
        ),
        secrets_mod.SecretMaterial(
            name="grafana-admin", provider="pulumi", rotation_days=60
        ),
    ]

    result = secrets_mod.sync_secrets(stack_name="test", secrets=materials)

    assert result.handles["kernel-api-key"] == "token123"
    assert "grafana-admin" in result.missing
    assert any(
        meta["name"] == "grafana-admin" and meta["available"] is False
        for meta in result.metadata
    )


@test("bundle manifest writer emits json and yaml summaries")
def _(_generated_dir: Any = compose_dir) -> None:
    artifact = renderer.write_raw_artifact(
        target_name="demo.yml",
        data=b"services: {}\n",
        subdir="bundle",
    )

    components = [bundle_mod.BundleComponent(name="storage", artifact=artifact)]
    secret_result = secrets_mod.SecretSyncResult(
        handles={}, metadata=[], missing=["test"]
    )

    bundle = bundle_mod.write_bundle_manifest(
        stack_name="bundle",
        components=components,
        secrets=secret_result,
    )

    json_path = Path(bundle.json_artifact.path)
    yaml_path = Path(bundle.yaml_artifact.path)

    assert json_path.exists()
    assert yaml_path.exists()

    manifest = json.loads(json_path.read_text(encoding="utf-8"))
    assert manifest["stack"] == "bundle"
    assert manifest["secrets"]["missing"] == ["test"]
    assert manifest["components"][0]["component"] == "storage"
