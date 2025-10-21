"""Integration harness helpers that standardise on ADR-003 deployment assets.

These fixtures execute the Pulumi smoke harness using an in-process automation
stub so integration suites can rely on the bundle schema/telemetry artifacts
without requiring the Pulumi CLI on CI agents. The helpers also expose a kernel
harness that drives the CLI entrypoint (`k0ctl`) to provision state, execute
migrations, and spin up FastAPI clients for end-to-end validation.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Sequence,
    cast,
)

import yaml
from fastapi.testclient import TestClient
from ward import fixture  # type: ignore[attr-defined]

from k0.deployment.pulumi import smoke
from k0.deployment.pulumi.validation import load_and_validate_bundle_manifest

if TYPE_CHECKING:
    from k0.kernel.config import KernelSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_CONFIG_PATH = REPO_ROOT / "k0" / "config" / "kernel.yaml"
DEFAULT_STACK = "local-single-node"


class HarnessError(RuntimeError):
    """Raised when the harness encounters an unrecoverable error."""


def _resolve_shutdown_pool() -> Callable[[], None]:
    try:
        from k0.uow.connection_pool import shutdown_pool as resolved
    except Exception as exc:  # pragma: no cover - defensive logging
        raise HarnessError("failed to import connection pool shutdown helper") from exc

    return resolved


@dataclass(slots=True)
class CliResult:
    """Command execution outcome for `k0ctl` invocations."""

    argv: Sequence[str]
    exit_code: int


class _PulumiConfig:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def get(self, _key: str, default: Any | None = None) -> Any | None:
        return default

    def get_bool(self, _key: str) -> bool | None:
        return None

    def get_int(self, _key: str) -> int | None:
        return None

    def get_object(self, _key: str) -> Any | None:
        return None

    def get_secret(self, _key: str) -> Any | None:
        return None


class _PulumiLog:
    def warning(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None


class _PulumiModule(ModuleType):
    def __init__(self) -> None:
        super().__init__("pulumi")
        self._exports: Dict[str, Any] = {}
        self.Config = _PulumiConfig  # type: ignore[attr-defined]
        self.log = _PulumiLog()  # type: ignore[attr-defined]

    def export(self, name: str, value: Any) -> None:  # type: ignore[attr-defined]
        self._exports[name] = value


class _FakeWorkspace:
    def __init__(self, module: "_FakeAutomationModule", stack_name: str) -> None:
        self._module = module
        self._stack_name = stack_name

    def remove_stack(self, stack_name: str) -> None:
        self._module.removed_stacks.append(stack_name)


class _FakeStack:
    def __init__(
        self,
        *,
        program: Any,
        module: "_FakeAutomationModule",
        stack_name: str,
    ) -> None:
        self._program = program
        self._module = module
        self._stack_name = stack_name
        self._config: MutableMapping[str, _FakeConfigValue] = {}
        self.workspace = _FakeWorkspace(module, stack_name)

    def set_all_config(self, config: Mapping[str, "_FakeConfigValue"]) -> None:
        self._config = dict(config)
        self._module.last_config = dict(config)

    def preview(self, on_output: Any | None = None) -> "_FakePreviewResult":
        if on_output is not None:
            on_output("preview: starting")
        self._program()
        self._module.preview_calls += 1
        return _FakePreviewResult(change_summary={})


class _FakeConfigValue:
    def __init__(self, value: str, secret: bool) -> None:
        self.value = value
        self.secret = secret


class _FakePreviewResult:
    def __init__(self, *, change_summary: Mapping[str, int]) -> None:
        self.change_summary = change_summary


class _FakeAutomationModule:
    ConfigValue = _FakeConfigValue

    def __init__(self) -> None:
        self.preview_calls = 0
        self.last_config: Dict[str, _FakeConfigValue] = {}
        self.removed_stacks: list[str] = []

    class ProjectSettings(dict):  # type: ignore[override]
        ...

    class ProjectBackend(dict):  # type: ignore[override]
        ...

    class StackSettings(dict):  # type: ignore[override]
        ...

    class LocalWorkspaceOptions(dict):  # type: ignore[override]
        ...

    def create_or_select_stack(
        self,
        *,
        stack_name: str,
        project_name: str,
        program: Any,
        opts: Any,
    ) -> _FakeStack:
        _ = project_name, opts
        stack = _FakeStack(program=program, module=self, stack_name=stack_name)
        return stack


@dataclass(slots=True)
class HarnessArtifacts:
    stack: str
    artifacts_root: Path
    telemetry_dir: Path
    timeline_path: Path

    def telemetry_snapshots(self) -> Iterable[Path]:
        if not self.telemetry_dir.exists():
            return []
        return self.telemetry_dir.glob("*.prom")

    def cleanup(self) -> None:
        if self.artifacts_root.exists():
            shutil.rmtree(self.artifacts_root, ignore_errors=True)
        if self.timeline_path.exists():
            self.timeline_path.unlink(missing_ok=True)


@dataclass(slots=True)
class KernelHarness:
    """Wrapper that drives `k0ctl` and exposes FastAPI clients for tests."""

    artifacts: HarnessArtifacts
    config_path: Path
    database_path: Path
    telemetry_dir: Path

    def run_cli(
        self,
        *args: str,
        check: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> CliResult:
        argv = ["--config", str(self.config_path), *args]
        overrides = {"K0_KERNEL_CONFIG_FILE": str(self.config_path)}
        if env:
            overrides.update(env)
        shutdown = _resolve_shutdown_pool()
        with _patched_environ(overrides):
            shutdown()
            try:
                k0ctl_module = import_module("k0.cli.k0ctl")
            except Exception as exc:  # pragma: no cover - defensive logging
                raise HarnessError("failed to import k0ctl for kernel harness") from exc

            main = getattr(k0ctl_module, "main", None)
            if not callable(main):
                raise HarnessError("k0ctl module missing callable 'main' entrypoint")

            main_callable = cast(Callable[[Sequence[str]], int], main)
            exit_code = main_callable(argv)
            shutdown()
        if check and exit_code != 0:
            raise HarnessError(f"k0ctl {' '.join(args)} exited with status {exit_code}")
        return CliResult(tuple(argv), exit_code)

    def load_settings(self) -> "KernelSettings":
        try:
            from k0.kernel.config import KernelSettings
        except Exception as exc:  # pragma: no cover - defensive logging
            raise HarnessError("failed to import kernel settings") from exc

        return KernelSettings.load(config_path=self.config_path)

    @contextlib.contextmanager
    def client(self) -> Iterator[TestClient]:
        settings = self.load_settings()
        try:
            from k0.kernel.app import create_app
        except Exception as exc:  # pragma: no cover - defensive logging
            raise HarnessError("failed to import kernel app factory") from exc

        app = create_app(settings=settings)
        try:
            with TestClient(app) as client:
                yield client
        finally:
            shutdown = _resolve_shutdown_pool()
            shutdown()


def _patched_environ(
    overrides: Mapping[str, str],
) -> contextlib.AbstractContextManager[None]:
    @contextlib.contextmanager
    def _manager() -> Iterator[None]:
        original: Dict[str, str | None] = {}
        for key, value in overrides.items():
            original[key] = os.environ.get(key)
            os.environ[key] = value
        try:
            yield
        finally:
            for key, prior in original.items():
                if prior is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = prior

    return _manager()


def _install_pulumi_stub() -> ModuleType | None:
    original = sys.modules.get("pulumi")
    sys.modules["pulumi"] = _PulumiModule()
    return original


def _restore_pulumi_stub(original: ModuleType | None) -> None:
    if original is None:
        sys.modules.pop("pulumi", None)
    else:
        sys.modules["pulumi"] = original


def _write_mock_telemetry(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / "integration-harness.prom"
    lines = [
        "# TYPE k0_kernel_k0_signature_verified_total counter",
        'k0_kernel_k0_signature_verified_total{key_state="ACTIVE",key_version="v1-active"} 5',
        "# TYPE k0_kernel_k0_signature_verification_failed_total counter",
        'k0_kernel_k0_signature_verification_failed_total{reason="INVALID_SIGNATURE"} 1',
        'k0_kernel_k0_provisioning_denial_total{reason="DEVICE_NOT_PROVISIONED"} 1',
        'k0_kernel_k0_schema_denial_total{reason="SCHEMA_BLOCKED",schema_uri="schema://memory.blocked",schema_version="1.0"} 1',
        'k0_kernel_k0_idem_commit_recorded_total{state="COMMITTED"} 3',
        'k0_kernel_k0_idem_lookup_total{outcome="hit",state="COMMITTED"} 3',
        'k0_kernel_k0_idem_duplicate_detected_total{state="COMMITTED"} 2',
        "",
    ]
    snapshot.write_text("\n".join(lines), encoding="utf-8")


def _write_timeline(stack: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timeline = directory / f"deployment-timeline-{stack}-integration.json"
    payload: dict[str, object] = {
        "stack": stack,
        "mode": "preview",
        "status": "success",
        "steps": [
            {"name": "pulumi_preview", "status": "completed"},
            {"name": "telemetry_snapshot", "status": "completed"},
        ],
    }
    timeline.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return timeline


def _run_smoke(stack: str, artifacts_root: Path) -> None:
    automation = _FakeAutomationModule()
    original = _install_pulumi_stub()
    try:
        summary = smoke.run_preview(
            stack,
            artifacts_root=artifacts_root,
            automation_module=automation,
        )
        load_and_validate_bundle_manifest(summary.manifest_yaml)
        load_and_validate_bundle_manifest(summary.manifest_json)
    finally:
        _restore_pulumi_stub(original)


def _write_kernel_config(config_path: Path, database_path: Path) -> None:
    base_config = yaml.safe_load(BASE_CONFIG_PATH.read_text(encoding="utf-8"))
    base_config.setdefault("environment", "integration")
    base_config.setdefault("database", {})["path"] = str(database_path)
    telemetry = base_config.setdefault("telemetry", {})
    telemetry["otlp_endpoint"] = None
    telemetry["prometheus_enabled"] = True
    telemetry.setdefault("metrics_namespace", "k0_kernel")
    server = base_config.setdefault("server", {})
    server.setdefault("host", "127.0.0.1")
    config_path.write_text(
        yaml.safe_dump(base_config, sort_keys=False), encoding="utf-8"
    )


@fixture
def harness_artifacts(stack: str = DEFAULT_STACK) -> Iterator[HarnessArtifacts]:
    artifacts_root = REPO_ROOT / "artifacts" / "integration" / stack
    telemetry_dir = REPO_ROOT / "artifacts" / "telemetry" / stack
    timeline_dir = REPO_ROOT / "artifacts" / "deployment"

    if artifacts_root.exists():
        shutil.rmtree(artifacts_root, ignore_errors=True)
    if telemetry_dir.exists():
        shutil.rmtree(telemetry_dir, ignore_errors=True)

    _run_smoke(stack, artifacts_root)
    _write_mock_telemetry(telemetry_dir)
    timeline_path = _write_timeline(stack, timeline_dir)

    artifacts = HarnessArtifacts(
        stack=stack,
        artifacts_root=artifacts_root,
        telemetry_dir=telemetry_dir,
        timeline_path=timeline_path,
    )
    try:
        yield artifacts
    finally:
        artifacts.cleanup()


@fixture
def kernel_harness(artifacts: HarnessArtifacts) -> Iterator[KernelHarness]:
    state_dir = artifacts.artifacts_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    database_path = state_dir / "kernel.sqlite3"
    config_path = artifacts.artifacts_root / "kernel-integration.yaml"
    _write_kernel_config(config_path, database_path)

    harness = KernelHarness(
        artifacts=artifacts,
        config_path=config_path,
        database_path=database_path,
        telemetry_dir=artifacts.telemetry_dir,
    )

    harness.run_cli("migrate")
    try:
        yield harness
    finally:
        shutdown = _resolve_shutdown_pool()
        shutdown()
        config_path.unlink(missing_ok=True)


@fixture
def timeline_snapshot(
    artifacts: HarnessArtifacts = harness_artifacts,  # type: ignore[misc]
) -> dict[str, Any]:
    if artifacts.timeline_path.is_file():
        return json.loads(artifacts.timeline_path.read_text(encoding="utf-8"))
    return {}


__all__ = [
    "CliResult",
    "HarnessArtifacts",
    "HarnessError",
    "KernelHarness",
    "harness_artifacts",
    "kernel_harness",
    "timeline_snapshot",
]


__all__ = [
    "CliResult",
    "HarnessArtifacts",
    "HarnessError",
    "KernelHarness",
    "harness_artifacts",
    "kernel_harness",
    "timeline_snapshot",
]
