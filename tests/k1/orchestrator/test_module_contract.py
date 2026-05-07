"""
Epic 7.4.1 -- Orchestrator module contract compliance tests.

Verifies declarations in:
  k1/contracts/modules/orchestrator/module.contract.yaml

Scope:
  - Contract loads and has expected metadata shape.
  - Every declared export is available from k1.orchestrator.
  - Exported API surface includes service/factory/port expectations.
  - Declared module dependencies are importable.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = (
    _REPO_ROOT / "k1" / "contracts" / "modules" / "orchestrator" / "module.contract.yaml"
)


with _CONTRACT_PATH.open("r", encoding="utf-8") as _f:
    _CONTRACT: dict[str, Any] = yaml.safe_load(_f)

_EXPORT_SYMBOLS = [item["symbol"] for item in _CONTRACT.get("exports", [])]

_PORT_METHODS: dict[str, list[str]] = {
    "IMailboxPort": ["enqueue", "dequeue", "depth", "peek_priority"],
    "IFabricGatewayPort": ["execute", "execute_batch", "query_registry"],
    "IPlannerPort": ["request_plan", "cancel_plan", "micro_replan"],
    "IStateReadPort": ["read_section", "read_sections", "get_snapshot"],
    "IDeltaEmitPort": ["emit", "emit_progress"],
    "IBridgeWritePort": ["submit_audit", "write_wal", "read_wal", "list_wal_ids"],
    "IEventSubscriptionPort": ["subscribe", "unsubscribe", "emit"],
    "IWorkflowStoragePort": ["save_workflow", "get_workflow", "list_workflows"],
}


class TestModuleContractLoad:
    def test_contract_exists(self) -> None:
        assert _CONTRACT_PATH.exists(), f"Missing contract file: {_CONTRACT_PATH}"

    def test_contract_metadata_shape(self) -> None:
        metadata = _CONTRACT.get("metadata", {})
        assert metadata.get("module_id") == "orchestrator"
        assert isinstance(_CONTRACT.get("contract_version"), int)
        assert _CONTRACT.get("exports"), "Contract must declare at least one export"

    def test_entrypoint_format(self) -> None:
        entrypoints = _CONTRACT.get("entrypoints", {})
        for key in ("init", "shutdown"):
            value = entrypoints.get(key, "")
            assert ":" in value, f"Entrypoint '{key}' should be in module:function format"
            module_name, function_name = value.split(":", 1)
            assert module_name == "orchestrator"
            assert function_name


class TestDeclaredExports:
    def test_all_declared_exports_available_from_package(self) -> None:
        mod = importlib.import_module("k1.orchestrator")
        missing = [symbol for symbol in _EXPORT_SYMBOLS if not hasattr(mod, symbol)]
        assert not missing, f"Missing declared exports from k1.orchestrator: {missing}"

    def test_declared_exports_present_in_dunder_all(self) -> None:
        mod = importlib.import_module("k1.orchestrator")
        declared_set = set(_EXPORT_SYMBOLS)
        public_set = set(getattr(mod, "__all__", []))
        missing = sorted(declared_set - public_set)
        assert not missing, f"Declared exports not present in __all__: {missing}"

    def test_declared_export_source_files_target_package_root(self) -> None:
        sources = {item.get("from_file") for item in _CONTRACT.get("exports", [])}
        assert sources == {"k1/orchestrator/__init__.py"}


class TestServiceAndFactorySurface:
    def test_orchestrator_service_has_required_async_methods(self) -> None:
        mod = importlib.import_module("k1.orchestrator")
        service_cls = getattr(mod, "OrchestratorService")
        assert inspect.isclass(service_cls)

        for method in ("init", "shutdown", "crash_recovery", "process"):
            assert hasattr(service_cls, method), f"OrchestratorService missing method: {method}"
            assert inspect.iscoroutinefunction(
                getattr(service_cls, method)
            ), f"OrchestratorService.{method} must be async"

    def test_orchestrator_factory_has_required_methods(self) -> None:
        mod = importlib.import_module("k1.orchestrator")
        factory_cls = getattr(mod, "OrchestratorFactory")
        assert inspect.isclass(factory_cls)

        for method in (
            "create_standalone",
            "create_for_testing",
            "create_with_ports",
            "create_production",
        ):
            assert hasattr(factory_cls, method), f"OrchestratorFactory missing method: {method}"
            assert inspect.iscoroutinefunction(
                getattr(factory_cls, method)
            ), f"OrchestratorFactory.{method} must be async"


class TestPortSurfaceFromContract:
    def test_declared_port_symbols_have_required_methods(self) -> None:
        mod = importlib.import_module("k1.orchestrator")

        for symbol, required_methods in _PORT_METHODS.items():
            assert (
                symbol in _EXPORT_SYMBOLS
            ), f"Port symbol not declared in contract exports: {symbol}"
            port_cls = getattr(mod, symbol)
            assert inspect.isclass(port_cls), f"{symbol} must be a class/protocol"

            for method in required_methods:
                assert hasattr(port_cls, method), f"{symbol} missing method: {method}"


class TestContractDependencies:
    def test_declared_dependencies_are_importable(self) -> None:
        for dep in _CONTRACT.get("dependencies", []):
            module_name = dep.get("module")
            required = dep.get("required", True)
            assert module_name, f"Dependency missing module name: {dep}"

            imported = None
            for candidate in (f"k1.{module_name}", module_name):
                try:
                    imported = importlib.import_module(candidate)
                    break
                except ModuleNotFoundError:
                    continue

            if required:
                assert imported is not None, f"Required dependency not importable: {module_name}"
