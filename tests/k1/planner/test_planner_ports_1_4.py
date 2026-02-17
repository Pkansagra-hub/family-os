"""Tests for Epic 1.4 -- Port Definitions.

Validates all 7 hexagonal port Protocols:
- @runtime_checkable Protocol classes
- Method signatures (names, parameters, defaults)
- isinstance checks with conforming/non-conforming adapters
- Import paths (individual modules + ports/__init__.py + k1.planner)
- Layer 1 import rules (no service/adapter/agent imports)
- Method bodies are protocol stubs (no implementation logic)
- New types: HubRequest, HubResponse, RecallResponse
- __all__ completeness

References: planner.md SS15 (Port Architecture), SS30.5.2 (F11-F18)
"""

from __future__ import annotations

import ast
import inspect
import os
from typing import Any, Callable, Dict, Protocol

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanRequest
from k1.planner.ports import (
    IBridgePort,
    IDeltaEmitPort,
    IEventPort,
    IFabricRetrievalPort,
    ILLMPort,
    IMailboxPort,
    IStateReadPort,
)
from k1.planner.types import (
    DeltaPayload,
    HubRequest,
    HubResponse,
    RecallResponse,
    RequestConstraints,
)

# =========================================================================
# Section 1: File existence
# =========================================================================


class TestFileExistence:
    """Epic 1.4 Done When: 8 files exist in k1/planner/ports/ (F11-F18)."""

    PORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "k1", "planner", "ports")

    EXPECTED_FILES = [
        "__init__.py",
        "mailbox_port.py",
        "llm_port.py",
        "fabric_retrieval_port.py",
        "state_read_port.py",
        "bridge_port.py",
        "delta_emit_port.py",
        "event_port.py",
    ]

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_port_file_exists(self, filename: str) -> None:
        path = os.path.join(self.PORTS_DIR, filename)
        assert os.path.isfile(path), f"Missing port file: {filename}"

    def test_exactly_8_files(self) -> None:
        py_files = [f for f in os.listdir(self.PORTS_DIR) if f.endswith(".py")]
        assert len(py_files) == 8, f"Expected 8 .py files, got {py_files}"


# =========================================================================
# Section 2: All 7 are @runtime_checkable Protocol
# =========================================================================


ALL_PORTS = [
    IMailboxPort,
    ILLMPort,
    IFabricRetrievalPort,
    IStateReadPort,
    IBridgePort,
    IDeltaEmitPort,
    IEventPort,
]


class TestRuntimeCheckable:
    """All 7 port classes are @runtime_checkable typing.Protocol."""

    @pytest.mark.parametrize("port_cls", ALL_PORTS, ids=lambda p: p.__name__)
    def test_is_protocol(self, port_cls: type) -> None:
        assert issubclass(port_cls, Protocol)

    @pytest.mark.parametrize("port_cls", ALL_PORTS, ids=lambda p: p.__name__)
    def test_runtime_checkable_isinstance(self, port_cls: type) -> None:
        """Verify isinstance works (which proves @runtime_checkable)."""

        # Build a conforming class dynamically
        class Conforming:
            pass

        for name, method in inspect.getmembers(port_cls, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue
            setattr(Conforming, name, lambda self, *a, **kw: None)

        assert isinstance(Conforming(), port_cls)


# =========================================================================
# Section 3: IMailboxPort method signatures (SS15.2)
# =========================================================================


class TestIMailboxPort:
    """IMailboxPort: enqueue(), send_cancel(), micro_replan() match SS15.2."""

    def test_has_enqueue(self) -> None:
        sig = inspect.signature(IMailboxPort.enqueue)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "request" in params

    def test_has_send_cancel(self) -> None:
        sig = inspect.signature(IMailboxPort.send_cancel)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "request_id" in params

    def test_has_micro_replan(self) -> None:
        sig = inspect.signature(IMailboxPort.micro_replan)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "request" in params

    def test_enqueue_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IMailboxPort.enqueue)

    def test_send_cancel_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IMailboxPort.send_cancel)

    def test_micro_replan_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IMailboxPort.micro_replan)

    def test_isinstance_conforming(self) -> None:
        class Adapter:
            async def dequeue(self) -> PlanRequest:
                raise NotImplementedError

            async def enqueue(self, request: PlanRequest) -> None:
                pass

            async def send_cancel(self, request_id: str) -> None:
                pass

            def drain(self) -> list:
                return []

            async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
                return CommittedPlan()  # type: ignore[call-arg]

        assert isinstance(Adapter(), IMailboxPort)

    def test_isinstance_non_conforming(self) -> None:
        class Missing:
            async def enqueue(self, request: PlanRequest) -> None:
                pass

        assert not isinstance(Missing(), IMailboxPort)


# =========================================================================
# Section 4: ILLMPort method signatures (SS15.3)
# =========================================================================


class TestILLMPort:
    """ILLMPort: execute(HubRequest) -> HubResponse matches SS15.3."""

    def test_has_execute(self) -> None:
        sig = inspect.signature(ILLMPort.execute)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "request" in params

    def test_execute_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(ILLMPort.execute)

    def test_isinstance_conforming(self) -> None:
        class Adapter:
            async def execute(self, request: HubRequest) -> HubResponse:
                return HubResponse()

        assert isinstance(Adapter(), ILLMPort)

    def test_no_other_methods(self) -> None:
        """CommitService must NOT have access (PLAN-03). Only execute."""
        public_methods = [
            m for m in dir(ILLMPort) if not m.startswith("_") and callable(getattr(ILLMPort, m))
        ]
        assert public_methods == ["execute"]


# =========================================================================
# Section 5: IFabricRetrievalPort method signatures (SS15.4)
# =========================================================================


class TestIFabricRetrievalPort:
    """IFabricRetrievalPort: discover + find_relevant -- PLAN-06 enforced."""

    def test_has_discover_capabilities(self) -> None:
        sig = inspect.signature(IFabricRetrievalPort.discover_capabilities)
        params = list(sig.parameters.keys())
        assert "domain" in params
        assert "intent" in params
        assert "safety_band" in params
        assert "session_context" in params
        assert "top_k" in params

    def test_has_find_relevant_prompts(self) -> None:
        sig = inspect.signature(IFabricRetrievalPort.find_relevant_prompts)
        params = list(sig.parameters.keys())
        assert "intent" in params
        assert "domain" in params
        assert "safety_band" in params
        assert "top_k" in params

    def test_discover_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IFabricRetrievalPort.discover_capabilities)

    def test_find_prompts_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IFabricRetrievalPort.find_relevant_prompts)

    def test_plan06_no_execute_method(self) -> None:
        """PLAN-06: no invoke or execute method on this port."""
        public = [m for m in dir(IFabricRetrievalPort) if not m.startswith("_")]
        assert "invoke_capability" not in public
        assert "execute" not in public
        assert "invoke" not in public

    def test_discover_defaults(self) -> None:
        sig = inspect.signature(IFabricRetrievalPort.discover_capabilities)
        assert sig.parameters["domain"].default is None
        assert sig.parameters["intent"].default == ""
        assert sig.parameters["safety_band"].default == "GREEN"
        assert sig.parameters["session_context"].default is None
        assert sig.parameters["top_k"].default == 10


# =========================================================================
# Section 6: IStateReadPort method signatures (SS15.5)
# =========================================================================


class TestIStateReadPort:
    """IStateReadPort: read_sections() -- PLAN-01 enforced."""

    def test_has_read_sections(self) -> None:
        sig = inspect.signature(IStateReadPort.read_sections)
        params = list(sig.parameters.keys())
        assert "sections" in params
        assert "trace_id" in params

    def test_read_sections_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IStateReadPort.read_sections)

    def test_plan01_no_write_methods(self) -> None:
        """PLAN-01: NO write/update/set/delete methods."""
        public = [m for m in dir(IStateReadPort) if not m.startswith("_")]
        forbidden = ["write", "update", "set", "delete", "put", "store"]
        for method_name in public:
            for word in forbidden:
                assert (
                    word not in method_name.lower()
                ), f"PLAN-01 violation: {method_name} contains '{word}'"

    def test_trace_id_default(self) -> None:
        sig = inspect.signature(IStateReadPort.read_sections)
        assert sig.parameters["trace_id"].default == ""


# =========================================================================
# Section 7: IBridgePort method signatures (SS15.6)
# =========================================================================


class TestIBridgePort:
    """IBridgePort: recall(), persist_plan() match SS15.6."""

    def test_has_recall(self) -> None:
        sig = inspect.signature(IBridgePort.recall)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "selectors" in params
        assert "trace_id" in params

    def test_has_persist_plan(self) -> None:
        sig = inspect.signature(IBridgePort.persist_plan)
        params = list(sig.parameters.keys())
        assert "plan" in params
        assert "trace_id" in params

    def test_recall_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IBridgePort.recall)

    def test_persist_plan_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(IBridgePort.persist_plan)

    def test_recall_defaults(self) -> None:
        sig = inspect.signature(IBridgePort.recall)
        assert sig.parameters["selectors"].default is None
        assert sig.parameters["trace_id"].default == ""


# =========================================================================
# Section 8: IDeltaEmitPort method signatures (SS15.7)
# =========================================================================


class TestIDeltaEmitPort:
    """IDeltaEmitPort: emit(DeltaPayload) is synchronous (not async)."""

    def test_has_emit(self) -> None:
        sig = inspect.signature(IDeltaEmitPort.emit)
        params = list(sig.parameters.keys())
        assert "delta" in params

    def test_emit_is_NOT_coroutine(self) -> None:
        """Key property: emit() is synchronous per SS15.7."""
        assert not inspect.iscoroutinefunction(IDeltaEmitPort.emit)

    def test_isinstance_conforming(self) -> None:
        class Adapter:
            def emit(self, delta: DeltaPayload) -> None:
                pass

        assert isinstance(Adapter(), IDeltaEmitPort)


# =========================================================================
# Section 9: IEventPort method signatures (SS15.8)
# =========================================================================


class TestIEventPort:
    """IEventPort: emit(), subscribe(), unsubscribe() match SS15.8."""

    def test_has_emit(self) -> None:
        sig = inspect.signature(IEventPort.emit)
        params = list(sig.parameters.keys())
        assert "topic" in params
        assert "payload" in params

    def test_has_subscribe(self) -> None:
        sig = inspect.signature(IEventPort.subscribe)
        params = list(sig.parameters.keys())
        assert "topic" in params
        assert "handler" in params

    def test_has_unsubscribe(self) -> None:
        sig = inspect.signature(IEventPort.unsubscribe)
        params = list(sig.parameters.keys())
        assert "handle" in params

    def test_emit_is_NOT_coroutine(self) -> None:
        """Matches Fabric IEventPort: synchronous emit."""
        assert not inspect.iscoroutinefunction(IEventPort.emit)

    def test_subscribe_is_NOT_coroutine(self) -> None:
        """Matches Fabric IEventPort: synchronous subscribe."""
        assert not inspect.iscoroutinefunction(IEventPort.subscribe)

    def test_unsubscribe_is_NOT_coroutine(self) -> None:
        assert not inspect.iscoroutinefunction(IEventPort.unsubscribe)

    def test_isinstance_conforming(self) -> None:
        class Adapter:
            def emit(self, topic: str, payload: Dict[str, Any]) -> None:
                pass

            def subscribe(
                self,
                topic: str,
                handler: Callable[[str, Dict[str, Any]], None],
            ) -> SubscriptionHandle:
                return SubscriptionHandle()

            def unsubscribe(self, handle: SubscriptionHandle) -> bool:
                return True

        assert isinstance(Adapter(), IEventPort)


# =========================================================================
# Section 10: Method bodies are Ellipsis only (no implementation logic)
# =========================================================================


PORT_FILES = {
    "mailbox_port.py": "IMailboxPort",
    "llm_port.py": "ILLMPort",
    "fabric_retrieval_port.py": "IFabricRetrievalPort",
    "state_read_port.py": "IStateReadPort",
    "bridge_port.py": "IBridgePort",
    "delta_emit_port.py": "IDeltaEmitPort",
    "event_port.py": "IEventPort",
}


class TestMethodBodiesEllipsis:
    """All method bodies are ... (Ellipsis) only -- zero implementation logic."""

    PORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "k1", "planner", "ports")

    @pytest.mark.parametrize(
        "filename,class_name",
        PORT_FILES.items(),
        ids=PORT_FILES.keys(),
    )
    def test_method_bodies_are_ellipsis(self, filename: str, class_name: str) -> None:
        filepath = os.path.join(self.PORTS_DIR, filename)
        with open(filepath) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Body should be docstring + Ellipsis only
                        non_doc_stmts = [
                            s
                            for s in item.body
                            if not (
                                isinstance(s, ast.Expr)
                                and isinstance(s.value, (ast.Constant, ast.Ellipsis))
                            )
                        ]
                        assert not non_doc_stmts, (
                            f"{class_name}.{item.name}() has non-ellipsis " f"implementation logic"
                        )


# =========================================================================
# Section 11: ports/__init__.py re-exports with __all__
# =========================================================================


class TestPortsInit:
    """k1/planner/ports/__init__.py [F11] re-exports all 7 Protocols."""

    def test_all_has_7_entries(self) -> None:
        from k1.planner.ports import __all__ as ports_all

        assert len(ports_all) == 7

    def test_all_entries_match(self) -> None:
        from k1.planner.ports import __all__ as ports_all

        expected = {
            "IMailboxPort",
            "ILLMPort",
            "IFabricRetrievalPort",
            "IStateReadPort",
            "IBridgePort",
            "IDeltaEmitPort",
            "IEventPort",
        }
        assert set(ports_all) == expected

    def test_import_from_package(self) -> None:
        """Consumers import from k1.planner.ports, not individual files."""
        from k1.planner.ports import (
            IBridgePort,
            IDeltaEmitPort,
            IEventPort,
            IFabricRetrievalPort,
            ILLMPort,
            IMailboxPort,
            IStateReadPort,
        )

        assert all(
            p is not None
            for p in [
                IBridgePort,
                IDeltaEmitPort,
                IEventPort,
                IFabricRetrievalPort,
                ILLMPort,
                IMailboxPort,
                IStateReadPort,
            ]
        )


# =========================================================================
# Section 12: Layer 1 import rules
# =========================================================================


class TestLayer1Imports:
    """Port files import ONLY from Layer 0 types + external type modules."""

    PORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "k1", "planner", "ports")

    # Allowed import prefixes for Layer 1 port files
    ALLOWED_IMPORTS = {
        "k1.orchestrator.types",
        "k1.planner.types",
        "k1.fabric.types",
        "k1.fabric.ports.state_reader",
        "k1.fabric.ports.event_port",
        "k1.planner.ports",  # for __init__.py re-exports
        "typing",
        "typing_extensions",
        "__future__",
    }

    @pytest.mark.parametrize("filename", PORT_FILES.keys())
    def test_no_forbidden_imports(self, filename: str) -> None:
        filepath = os.path.join(self.PORTS_DIR, filename)
        with open(filepath) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_import(alias.name, filename)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._check_import(node.module, filename)

    def _check_import(self, module: str, filename: str) -> None:
        # Check that the import is from an allowed prefix
        allowed = any(
            module == prefix or module.startswith(prefix + ".") for prefix in self.ALLOWED_IMPORTS
        )
        assert allowed, (
            f"{filename} imports from forbidden module '{module}'. "
            f"Layer 1 may only import from: {self.ALLOWED_IMPORTS}"
        )


# =========================================================================
# Section 13: New types (HubRequest, HubResponse, RecallResponse)
# =========================================================================


class TestNewTypes:
    """HubRequest, HubResponse, RecallResponse defined in types.py."""

    def test_hub_request_frozen(self) -> None:
        req = HubRequest(
            capability="CHAT",
            payload={"messages": []},
            constraints=RequestConstraints(max_tokens=100, timeout_ms=5000),
            trace_id="test",
        )
        with pytest.raises(AttributeError):
            req.capability = "STRUCTURED"  # type: ignore[misc]

    def test_hub_request_validates_capability(self) -> None:
        with pytest.raises(ValueError, match="CHAT.*STRUCTURED"):
            HubRequest(
                capability="INVALID",
                payload={},
                constraints=RequestConstraints(max_tokens=100, timeout_ms=5000),
            )

    def test_hub_request_validates_payload_type(self) -> None:
        with pytest.raises(ValueError, match="payload must be a dict"):
            HubRequest(
                capability="CHAT",
                payload="not a dict",  # type: ignore[arg-type]
                constraints=RequestConstraints(max_tokens=100, timeout_ms=5000),
            )

    def test_hub_response_frozen(self) -> None:
        resp = HubResponse(
            result={"content": "hello"},
            metadata={"model_id": "gpt-4"},
        )
        with pytest.raises(AttributeError):
            resp.result = {}  # type: ignore[misc]

    def test_hub_response_defaults(self) -> None:
        resp = HubResponse()
        assert resp.result == {}
        assert resp.metadata == {}

    def test_recall_response_frozen(self) -> None:
        recall = RecallResponse(
            facts=[{"key": "val"}],
            scores=[0.95],
            trace_id="test",
        )
        with pytest.raises(AttributeError):
            recall.trace_id = "other"  # type: ignore[misc]

    def test_recall_response_defaults(self) -> None:
        recall = RecallResponse()
        assert recall.facts == []
        assert recall.scores == []
        assert recall.trace_id == ""

    def test_types_re_exported_from_init(self) -> None:
        from k1.planner import HubRequest, HubResponse, RecallResponse

        assert HubRequest is not None
        assert HubResponse is not None
        assert RecallResponse is not None

    def test_hub_request_structured_capability(self) -> None:
        req = HubRequest(
            capability="STRUCTURED",
            payload={"messages": [], "output_schema": {}},
            constraints=RequestConstraints(max_tokens=500, timeout_ms=3000, temperature=0.2),
        )
        assert req.capability == "STRUCTURED"


# =========================================================================
# Section 14: k1.planner.__init__ re-exports ports
# =========================================================================


class TestPlannerInitPortExports:
    """Ports are re-exported from k1.planner for convenience."""

    def test_all_ports_in_planner_all(self) -> None:
        from k1.planner import __all__ as planner_all

        port_names = {
            "IMailboxPort",
            "ILLMPort",
            "IFabricRetrievalPort",
            "IStateReadPort",
            "IBridgePort",
            "IDeltaEmitPort",
            "IEventPort",
        }
        assert port_names.issubset(set(planner_all))

    def test_new_types_in_planner_all(self) -> None:
        from k1.planner import __all__ as planner_all

        new_types = {"HubRequest", "HubResponse", "RecallResponse"}
        assert new_types.issubset(set(planner_all))
