from __future__ import annotations

import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Dict, Iterator, Mapping, MutableMapping, cast

from ward import fixture, test  # type: ignore[attr-defined]

from k0.deployment.pulumi import smoke
from k0.deployment.pulumi.validation import load_and_validate_bundle_manifest


class FakeConfigValue:
    def __init__(self, value: str, secret: bool) -> None:
        self.value = value
        self.secret = secret


class FakePreviewResult:
    def __init__(self, change_summary: Mapping[str, int] | None = None) -> None:
        self.change_summary = change_summary


class FakeWorkspace:
    def __init__(self, module: "FakeAutomationModule", stack_name: str) -> None:
        self._module = module
        self._stack_name = stack_name

    def remove_stack(self, stack_name: str) -> None:
        self._module.removed_stacks.append(stack_name)


class FakeStack:
    def __init__(
        self,
        *,
        program: Any,
        module: "FakeAutomationModule",
        stack_name: str,
    ) -> None:
        self._program = program
        self._module = module
        self._stack_name = stack_name
        self._config: MutableMapping[str, FakeConfigValue] = {}
        self.workspace = FakeWorkspace(module, stack_name)

    def set_all_config(self, config: Mapping[str, FakeConfigValue]) -> None:
        self._config = dict(config)
        self._module.last_config = dict(config)

    def preview(self, on_output: Any | None = None) -> FakePreviewResult:
        if on_output is not None:
            on_output("preview: starting")
        self._program()
        self._module.preview_calls += 1
        return FakePreviewResult(change_summary={})


class FakeAutomationModule:
    ConfigValue = FakeConfigValue

    def __init__(self) -> None:
        self.preview_calls = 0
        self.last_config: Dict[str, FakeConfigValue] = {}
        self.removed_stacks: list[str] = []
        self.last_options: SimpleNamespace | None = None
        self.last_stack: FakeStack | None = None

    def ProjectSettings(self, **kwargs: Any) -> SimpleNamespace:  # noqa: N802
        return SimpleNamespace(**kwargs)

    def ProjectBackend(self, **kwargs: Any) -> SimpleNamespace:  # noqa: N802
        return SimpleNamespace(**kwargs)

    def StackSettings(self, **kwargs: Any) -> SimpleNamespace:  # noqa: N802
        return SimpleNamespace(**kwargs)

    def LocalWorkspaceOptions(self, **kwargs: Any) -> SimpleNamespace:  # noqa: N802
        options = SimpleNamespace(**kwargs)
        self.last_options = options
        return options

    def create_or_select_stack(  # noqa: N802
        self,
        *,
        stack_name: str,
        project_name: str,
        program: Any,
        opts: Any,
    ) -> FakeStack:
        _ = project_name
        self.last_options = opts
        stack = FakeStack(program=program, module=self, stack_name=stack_name)
        self.last_stack = stack
        return stack


@fixture
def fake_automation_module() -> Iterator[FakeAutomationModule]:
    yield FakeAutomationModule()


@fixture
def smoke_workspace() -> Iterator[Path]:
    with TemporaryDirectory() as tmp:
        yield Path(tmp)


@fixture
def pulumi_module_stub() -> Iterator[None]:
    original = sys.modules.get("pulumi")

    class DummyConfig:
        def __init__(self, namespace: str) -> None:
            self.namespace = namespace

        def get(self, _key: str, _default: Any | None = None) -> Any | None:
            return None

        def get_bool(self, _key: str) -> Any | None:
            return None

        def get_int(self, _key: str) -> Any | None:
            return None

        def get_object(self, _key: str) -> Any | None:
            return None

        def get_secret(self, _key: str) -> Any | None:
            return None

    class DummyLog:
        def warning(self, *args: Any, **kwargs: Any) -> None:
            pass

    module = types.ModuleType("pulumi_stub")
    module.Config = DummyConfig  # type: ignore[attr-defined]
    module.log = DummyLog()  # type: ignore[attr-defined]
    module._exports: Dict[str, Any] = {}  # type: ignore[attr-defined]

    def export(name: str, value: Any) -> None:
        module._exports[name] = value  # type: ignore[attr-defined]

    module.export = export  # type: ignore[attr-defined]

    sys.modules["pulumi"] = module
    try:
        yield
    finally:
        if original is not None:
            sys.modules["pulumi"] = original
        else:
            sys.modules.pop("pulumi", None)


@test("Pulumi smoke harness generates validated manifests")
def _(
    automation: Any = fake_automation_module,
    workspace: Any = smoke_workspace,
    _pulumi: Any = pulumi_module_stub,
):
    automation_module = cast(FakeAutomationModule, automation)
    artifacts_root = cast(Path, workspace) / "smoke-artifacts"
    config_payload: Dict[str, Any] = {
        "config": {
            "k0-storage": {
                "kernel_port": 9000,
            }
        },
        "secrets": [
            {
                "key": "k0-secrets:secret:api-token",
                "value": "secret-value",
            }
        ],
    }

    summary = smoke.run_preview(
        "local-single-node",
        config=config_payload,
        artifacts_root=artifacts_root,
        automation_module=automation_module,
    )

    assert automation_module.preview_calls == 1
    assert "k0-storage:kernel_port" in automation_module.last_config
    storage_cfg = automation_module.last_config["k0-storage:kernel_port"]
    assert storage_cfg.value == "9000"
    assert storage_cfg.secret is False

    secret_cfg = automation_module.last_config["k0-secrets:secret:api-token"]
    assert secret_cfg.secret is True
    assert secret_cfg.value == "secret-value"

    assert summary.manifest_yaml.exists()
    assert summary.manifest_json.exists()

    manifest_data = load_and_validate_bundle_manifest(summary.manifest_yaml)
    assert manifest_data["stack"] == "local-single-node"

    assert automation_module.removed_stacks == ["preview-local-single-node"]


@test("Pulumi smoke harness supports edge-cluster stack")
def _(
    automation: Any = fake_automation_module,
    workspace: Any = smoke_workspace,
    _pulumi: Any = pulumi_module_stub,
) -> None:
    automation_module = cast(FakeAutomationModule, automation)
    artifacts_root = cast(Path, workspace) / "edge-cluster-artifacts"

    summary = smoke.run_preview(
        "edge-cluster",
        config={},
        artifacts_root=artifacts_root,
        automation_module=automation_module,
    )

    assert summary.stack == "edge-cluster"
    manifest = load_and_validate_bundle_manifest(summary.manifest_yaml)
    assert manifest["stack"] == "edge-cluster"
    module = sys.modules["pulumi"]
    exports = getattr(module, "_exports", {})
    assert "edge-cluster_cluster" in exports
    assert automation_module.removed_stacks == ["preview-edge-cluster"]


@test("Pulumi smoke harness supports datacenter-ha stack")
def _(
    automation: Any = fake_automation_module,
    workspace: Any = smoke_workspace,
    _pulumi: Any = pulumi_module_stub,
) -> None:
    automation_module = cast(FakeAutomationModule, automation)
    artifacts_root = cast(Path, workspace) / "datacenter-ha-artifacts"

    summary = smoke.run_preview(
        "datacenter-ha",
        config={},
        artifacts_root=artifacts_root,
        automation_module=automation_module,
    )

    assert summary.stack == "datacenter-ha"
    manifest = load_and_validate_bundle_manifest(summary.manifest_json)
    assert manifest["stack"] == "datacenter-ha"
    module = sys.modules["pulumi"]
    exports = getattr(module, "_exports", {})
    assert "datacenter-ha_cluster" in exports
    assert automation_module.removed_stacks == ["preview-datacenter-ha"]
