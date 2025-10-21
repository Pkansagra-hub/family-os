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

# NOTE: Import stack module INSIDE test function AFTER pulumi stub is set up
# from k0.deployment.pulumi.stacks.edge_cluster import EdgeClusterSettings, orchestrate


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
def edge_cluster_pulumi_stub() -> (
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


@test("edge-cluster orchestrate produces overlays, topology metadata, and exports")
def _(
    workspace: Any = compose_dir,
    pulumi_ctx: Any = edge_cluster_pulumi_stub,
) -> None:
    # Import AFTER pulumi stub is set up to ensure correct stub is used
    from k0.deployment.pulumi.stacks.edge_cluster import (
        EdgeClusterSettings,
        orchestrate,
    )

    base_path = cast(Path, workspace)
    _, secret_store, exports = cast(
        Tuple[types.ModuleType, Dict[str, Dict[str, Any]], Dict[str, Any]], pulumi_ctx
    )

    secret_store["k0-secrets"]["secret:api-token"] = "edge-token"

    settings = EdgeClusterSettings(
        node_count=5,
        storage=StorageLayerConfig.from_mapping(
            {
                "enable_postgres": False,
                "sqlite_path": str(base_path / "edge.sqlite3"),
                "kernel_port": 8081,
            }
        ),
        telemetry=TelemetryConfig.from_mapping(
            {
                "enable_grafana": True,
                "grafana_port": 4000,
            }
        ),
        secrets=[
            SecretMaterial(name="api-token", provider="pulumi", rotation_days=30),
            SecretMaterial(name="missing-secret", provider="pulumi", rotation_days=60),
        ],
    )

    orchestrate(settings)

    artifacts_dir = base_path / "edge-cluster"
    overlay_file = artifacts_dir / "edge-cluster-overlay.yml"
    secrets_dir = artifacts_dir / "secrets"

    assert overlay_file.exists()
    assert "TODO(familyos)" in overlay_file.read_text(encoding="utf-8")

    token_file = secrets_dir / "api-token.json"
    assert token_file.exists()
    payload = json.loads(token_file.read_text(encoding="utf-8"))
    assert payload["value"] == "edge-token"
    assert payload["available"] is True

    manifest_path = artifacts_dir / "edge-cluster-bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    component_names = {entry["component"] for entry in manifest["components"]}
    assert component_names >= {"storage", "telemetry", "cluster-overlay", "secrets"}
    cluster_outputs = manifest["extra"]["outputs"]["cluster"]
    assert cluster_outputs["topology"]["total_nodes"] == 5
    assert cluster_outputs["artifacts"]["overlay"]["compose_artifacts"][0][
        "path"
    ].endswith("edge-cluster-overlay.yml")

    export_cluster = exports["edge-cluster_cluster"]
    assert export_cluster["scaling"]["total_nodes"] == 5
    assert export_cluster["topology"]["tiers"][0]["role"] == "control"
    assert any(
        item["path"].endswith("api-token.json")
        for item in export_cluster["artifacts"]["secrets"]
    )

    export_secrets = exports["edge-cluster_secrets"]
    assert "handles" not in export_secrets
    assert "missing-secret" in export_secrets["missing"]
    assert "handles" not in export_secrets
    assert "missing-secret" in export_secrets["missing"]
    assert "handles" not in export_secrets
    assert "missing-secret" in export_secrets["missing"]

    export_secrets = exports["edge-cluster_secrets"]
    assert "handles" not in export_secrets
    assert "missing-secret" in export_secrets["missing"]
