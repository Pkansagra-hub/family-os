"""
Epic 7.4.2 -- Orchestrator wiring contract compliance tests.

Validates runtime compliance against:
  k1/contracts/modules/orchestrator/wiring.contract.yaml

Notes:
  - Contract YAML is parsed at runtime (anti-hardcode policy).
  - Known contract drift points are surfaced as strict xfail markers.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = (
    _REPO_ROOT / "k1" / "contracts" / "modules" / "orchestrator" / "wiring.contract.yaml"
)

with _CONTRACT_PATH.open("r", encoding="utf-8") as _f:
    _CONTRACT: dict[str, Any] = yaml.safe_load(_f)

_REQUIRED_FILES = [item["path"] for item in _CONTRACT["code"]["required_files"]]

_PORT_METHODS: dict[str, list[str]] = {
    "IMailboxPort": ["enqueue", "dequeue", "depth", "peek_priority"],
    "IFabricGatewayPort": [
        "execute",
        "execute_batch",
        "query_registry",
        "query_registry_by_category",
    ],
    "IPlannerPort": ["request_plan", "cancel_plan", "micro_replan"],
    "IStateReadPort": ["read_section", "read_sections", "get_snapshot"],
    "IDeltaEmitPort": ["emit", "emit_progress"],
    "IBridgeWritePort": [
        "submit_audit",
        "write_wal",
        "read_wal",
        "list_wal_ids",
        "submit_deferred_result",
    ],
    "IEventSubscriptionPort": ["subscribe", "unsubscribe", "emit"],
    "IWorkflowStoragePort": [
        "save_workflow",
        "get_workflow",
        "list_workflows",
        "delete_workflow",
        "save_trigger",
        "get_due_triggers",
        "update_trigger_state",
        "save_run",
        "get_runs",
        "save_gap",
        "get_pending_gaps",
    ],
}


class _DummyPlannerMailbox:
    async def enqueue(self, request: Any) -> None:
        return None

    async def send_cancel(self, request_id: str) -> None:
        return None

    async def micro_replan(self, request: Any) -> Any:
        return None


class _DummyStateReader:
    def read_section(self, session_id: str, section: str) -> dict[str, Any] | None:
        return {}

    def read_sections(self, session_id: str, names: list[str]) -> dict[str, Any]:
        return {}

    def get_snapshot(self, session_id: str) -> Any:
        return SimpleNamespace(session_id=session_id, sections={}, timestamp_ms=0)


class _DummyEventPort:
    def emit(self, topic: str, payload: dict[str, Any]) -> None:
        return None

    def subscribe(self, topic: str, handler: Any) -> Any:
        return SimpleNamespace(subscription_id="sub", topic=topic)

    def unsubscribe(self, handle: Any) -> bool:
        return True


class _DummyDeltaBus:
    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: dict[str, Any],
    ) -> None:
        return None


class _DummyBridgeClient:
    async def write(self, channel: str, payload: dict[str, Any], *, trace_id: str) -> None:
        return None

    async def read(self, channel: str, key: str) -> Any:
        return []


class TestWiringContractLoad:
    def test_wiring_contract_exists_and_metadata(self) -> None:
        assert _CONTRACT_PATH.exists(), f"Missing wiring contract: {_CONTRACT_PATH}"
        metadata = _CONTRACT.get("metadata", {})
        assert metadata.get("module_id") == "orchestrator"
        assert _CONTRACT.get("contract_version") == 1


class TestRequiredFilesFromContract:
    @pytest.mark.parametrize("rel_path", _REQUIRED_FILES)
    def test_required_file_exists_or_explicit_contract_drift(self, rel_path: str) -> None:
        full = _REPO_ROOT / rel_path
        assert full.is_file(), f"Declared required file missing: {rel_path}"


class TestPortProtocolSignatures:
    @pytest.mark.parametrize("port_symbol,required_methods", _PORT_METHODS.items())
    def test_port_methods_declared(self, port_symbol: str, required_methods: list[str]) -> None:
        orch = importlib.import_module("k1.orchestrator")
        port_cls = getattr(orch, port_symbol)
        for method in required_methods:
            assert hasattr(port_cls, method), f"{port_symbol} missing method '{method}'"


class TestProductionAdaptersImplementProtocols:
    def test_prod_mailbox_adapter(self) -> None:
        from k1.orchestrator import IMailboxPort
        from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter

        assert isinstance(MailboxAdapter(), IMailboxPort)

    def test_prod_fabric_gateway_adapter(self) -> None:
        from k1.orchestrator import IFabricGatewayPort
        from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter

        assert isinstance(FabricGatewayAdapter(cast(Any, SimpleNamespace())), IFabricGatewayPort)

    def test_prod_planner_adapter(self) -> None:
        from k1.fabric.circuit_breaker.breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )
        from k1.orchestrator import IPlannerPort
        from k1.orchestrator.adapters.planner_adapter import PlannerAdapter

        cb = CircuitBreaker("planner", CircuitBreakerConfig())
        assert isinstance(PlannerAdapter(_DummyPlannerMailbox(), cb), IPlannerPort)

    def test_prod_state_read_adapter(self) -> None:
        from k1.orchestrator import IStateReadPort
        from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter

        assert isinstance(StateReadAdapter(_DummyStateReader()), IStateReadPort)

    def test_prod_delta_emit_adapter(self) -> None:
        from k1.orchestrator import IDeltaEmitPort
        from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter

        assert isinstance(DeltaEmitAdapter(_DummyEventPort(), _DummyDeltaBus()), IDeltaEmitPort)

    def test_prod_bridge_write_adapter(self) -> None:
        from k1.orchestrator import IBridgeWritePort
        from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter

        assert isinstance(BridgeWriteAdapter(_DummyBridgeClient()), IBridgeWritePort)

    def test_prod_event_subscription_adapter(self) -> None:
        from k1.orchestrator import IEventSubscriptionPort
        from k1.orchestrator.adapters.event_subscription_adapter import (
            EventSubscriptionAdapter,
        )

        assert isinstance(EventSubscriptionAdapter(_DummyEventPort()), IEventSubscriptionPort)


class TestTestAdaptersImplementProtocols:
    def test_test_mailbox_adapter(self) -> None:
        from k1.orchestrator import IMailboxPort
        from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter

        assert isinstance(TestMailboxAdapter(), IMailboxPort)

    def test_mock_fabric_adapter(self) -> None:
        from k1.orchestrator import IFabricGatewayPort
        from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter

        assert isinstance(MockFabricAdapter(), IFabricGatewayPort)

    def test_mock_planner_adapter(self) -> None:
        from k1.orchestrator import IPlannerPort
        from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter

        assert isinstance(MockPlannerAdapter(), IPlannerPort)

    def test_mock_state_read_adapter(self) -> None:
        from k1.orchestrator import IStateReadPort
        from k1.orchestrator.adapters.mock_state_read_adapter import (
            MockStateReadAdapter,
        )

        assert isinstance(MockStateReadAdapter(), IStateReadPort)

    def test_test_delta_adapter(self) -> None:
        from k1.orchestrator import IDeltaEmitPort
        from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter

        assert isinstance(TestDeltaAdapter(), IDeltaEmitPort)

    def test_mock_bridge_adapter(self) -> None:
        from k1.orchestrator import IBridgeWritePort
        from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter

        assert isinstance(MockBridgeAdapter(), IBridgeWritePort)

    def test_test_event_adapter(self) -> None:
        from k1.orchestrator import IEventSubscriptionPort
        from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter

        assert isinstance(TestEventAdapter(), IEventSubscriptionPort)

    def test_test_workflow_storage_adapter(self) -> None:
        from k1.orchestrator import IWorkflowStoragePort
        from k1.orchestrator.adapters.test_workflow_storage_adapter import (
            TestWorkflowStorageAdapter,
        )

        assert isinstance(TestWorkflowStorageAdapter(), IWorkflowStoragePort)


class TestFactoryWiring:
    @pytest.mark.asyncio
    async def test_create_for_testing_wires_all_ports(self) -> None:
        from k1.orchestrator import (
            IBridgeWritePort,
            IDeltaEmitPort,
            IEventSubscriptionPort,
            IFabricGatewayPort,
            IMailboxPort,
            IPlannerPort,
            IStateReadPort,
        )
        from k1.orchestrator.factory import OrchestratorFactory
        from k1.orchestrator.orchestration.orchestrator_service import (
            OrchestratorService,
        )

        service = await OrchestratorFactory.create_for_testing()
        assert isinstance(service, OrchestratorService)

        assert isinstance(service._mailbox, IMailboxPort)
        assert isinstance(service._fabric_port, IFabricGatewayPort)
        assert isinstance(service._planner_port, IPlannerPort)
        assert isinstance(service._state_port, IStateReadPort)
        assert isinstance(service._delta_port, IDeltaEmitPort)
        assert isinstance(service._bridge_port, IBridgeWritePort)
        assert isinstance(service._event_port, IEventSubscriptionPort)

        assert service._dag_executor is not None
        assert service._constraint_resolver is not None
        assert service._workflow_engine is not None
        assert service._connector_lifecycle is not None
        assert service._error_router is not None


class TestForbiddenPatterns:
    def test_no_istatewriteport_in_orchestrator_code(self) -> None:
        offenders: list[str] = []
        for py_file in (_REPO_ROOT / "k1" / "orchestrator").rglob("*.py"):
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            if "IStateWritePort" in text:
                offenders.append(str(py_file.relative_to(_REPO_ROOT)))
        assert not offenders, f"ORCH-01 violation: IStateWritePort referenced in {offenders}"

    def test_no_test_or_mock_adapter_imports_in_production_except_allowlist(self) -> None:
        allowlist = {
            "k1/orchestrator/factory.py",
            "k1/orchestrator/adapters/__init__.py",
        }
        pattern = re.compile(
            r"^\s*(from|import)\s+k1\.orchestrator\.adapters\.(test_|mock_)",
            re.MULTILINE,
        )
        offenders: list[str] = []

        for py_file in (_REPO_ROOT / "k1" / "orchestrator").rglob("*.py"):
            rel = str(py_file.relative_to(_REPO_ROOT)).replace("\\", "/")
            if rel in allowlist:
                continue
            if rel.startswith("k1/orchestrator/adapters/test_") or rel.startswith(
                "k1/orchestrator/adapters/mock_"
            ):
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                offenders.append(rel)

        assert not offenders, f"Forbidden test/mock adapter import in production code: {offenders}"


class TestInitExports:
    def test_ports_init_exports_core_8_ports(self) -> None:
        ports = importlib.import_module("k1.orchestrator.ports")
        expected = {
            "IMailboxPort",
            "IFabricGatewayPort",
            "IPlannerPort",
            "IStateReadPort",
            "IDeltaEmitPort",
            "IBridgeWritePort",
            "IEventSubscriptionPort",
            "IWorkflowStoragePort",
        }
        assert expected.issubset(set(getattr(ports, "__all__", [])))

    def test_adapters_init_exports_expected_adapters(self) -> None:
        adapters = importlib.import_module("k1.orchestrator.adapters")
        expected = {
            "MailboxAdapter",
            "FabricGatewayAdapter",
            "PlannerAdapter",
            "StateReadAdapter",
            "DeltaEmitAdapter",
            "BridgeWriteAdapter",
            "EventSubscriptionAdapter",
            "WorkflowStorageAdapter",
            "TestMailboxAdapter",
            "MockFabricAdapter",
            "MockPlannerAdapter",
            "MockStateReadAdapter",
            "TestDeltaAdapter",
            "MockBridgeAdapter",
            "TestEventAdapter",
            "TestWorkflowStorageAdapter",
        }
        assert expected.issubset(set(getattr(adapters, "__all__", [])))


class TestWiringImportsSection:
    def test_required_modules_importable(self) -> None:
        required_modules = (
            _CONTRACT.get("wiring", {}).get("imports", {}).get("required_modules", [])
        )
        for module in required_modules:
            imported = importlib.import_module(f"k1.{module}")
            assert imported is not None

    def test_required_symbols_exist_and_are_referenced(self) -> None:
        required_symbols = (
            _CONTRACT.get("wiring", {}).get("imports", {}).get("required_symbols", [])
        )

        for item in required_symbols:
            module_name = item["from"]
            symbol = item["import"]
            used_files = item.get("used_in_files", [])

            imported_module = importlib.import_module(f"k1.{module_name}")
            assert hasattr(
                imported_module, symbol
            ), f"Missing required symbol: k1.{module_name}.{symbol}"

            for rel_path in used_files:
                target = _REPO_ROOT / rel_path
                assert target.exists(), f"Required used_in_file missing: {rel_path}"
                text = target.read_text(encoding="utf-8", errors="ignore")
                assert (
                    symbol in text
                ), f"Required symbol '{symbol}' not referenced in declared file '{rel_path}'"


class TestRuntimeAssertionsSection:
    def test_on_load_runtime_assertions(self) -> None:
        # Mirrors wiring.contract.yaml runtime_assertions.on_load semantics.
        orch = importlib.import_module("k1.orchestrator")
        for sym in (
            "IMailboxPort",
            "IFabricGatewayPort",
            "IPlannerPort",
            "IStateReadPort",
            "IDeltaEmitPort",
            "IBridgeWritePort",
            "IEventSubscriptionPort",
            "IWorkflowStoragePort",
            "TaskEnvelope",
            "PlanRequest",
            "CommittedPlan",
            "AggregatedResult",
            "StepResult",
            "ProcessingContext",
            "OrchestratorConfig",
        ):
            assert hasattr(orch, sym), f"Missing runtime assertion symbol: {sym}"

    def test_on_load_event_catalog_importable(self) -> None:
        events = importlib.import_module("k1.orchestrator.events")
        assert hasattr(events, "ALL_EMITTED")
        assert hasattr(events, "ALL_CONSUMED")
