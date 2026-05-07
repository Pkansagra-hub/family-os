"""Tests for SketchService skeleton & constructor (Issue 3.1.1).

Tests cover:
  - Constructor with valid dependencies (3 params)
  - Constructor None-rejection for each dependency
  - __slots__ verification (no __dict__)
  - Read-only property accessors
  - execute() / micro_execute() signature and async verification
  - Statelessness: no mutable instance state
  - Dependency layer validation (Layer 2 imports only)
  - ToolCallRouterLike protocol structural check
  - HILCoordinatorLike protocol structural check
  - SketchService does NOT hold PipelineController reference

References
----------
- planner.md Section 6 (Stage 1 SKETCH Deep Dive)
- planner.md Section 30.6 (Dependency Layers)
- docs/plans/planner-implementation-plan.md Issue 3.1.1
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from k1.planner.stages.sketch_service import SketchService, ToolCallRouterLike
from k1.planner.types import StageContext

# ---------------------------------------------------------------------------
# Test helpers -- minimal Protocol implementations
# ---------------------------------------------------------------------------


class FakeLLMPort:
    """Minimal ILLMPort implementation for constructor tests."""

    async def execute(self, request: Any) -> Any:
        return None


class FakeToolRouter:
    """Minimal ToolCallRouterLike implementation for constructor tests."""

    def __init__(self) -> None:
        self._tool_call_count: int = 0

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    def reset(self) -> None:
        self._tool_call_count = 0

    async def discover(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> Any:
        return None

    async def read_context(
        self,
        session_id: str,
        sections: list[str],
    ) -> Dict[str, Any]:
        return {}

    async def recall_memory(
        self,
        query: str,
        trace_id: str,
    ) -> Any:
        return None

    async def find_prompts(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        top_k: int = 5,
    ) -> Any:
        return None


class FakeHILCoordinator:
    """E5: minimal IHILPort fake (renamed from FakeHILCoordinator).

    Exposes the unified k1.kernel.ports.hil_port.IHILPort surface.
    Default behaviour: ask_clarification times out; request_approval
    auto-approves. Tests that need other behaviour replace the
    `_clar_response` / `_approval_response` attributes.
    """

    def __init__(self) -> None:
        from k1.hil.types import ApprovalResponse, ClarificationResponse

        self._budget: dict[str, int] = {}
        self.clarification_calls: list = []
        self.approval_calls: list = []
        self.reset_calls: list[str] = []
        self._clar_response = ClarificationResponse(
            hil_request_id="fake",
            answer=None,
            timed_out=True,
            round_budget_exhausted=False,
        )
        self._approval_response = ApprovalResponse(
            hil_request_id="fake",
            decision="approve",
            modifications=None,
            timed_out=False,
        )

    async def ask_clarification(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import ClarificationResponse

        self.clarification_calls.append(req)
        used = self._budget.get(req.caller_key, 0)
        if used >= 2:
            return ClarificationResponse(
                hil_request_id="",
                answer=None,
                timed_out=False,
                round_budget_exhausted=True,
            )
        self._budget[req.caller_key] = used + 1
        return self._clar_response

    async def request_approval(self, req):  # type: ignore[no-untyped-def]
        self.approval_calls.append(req)
        return self._approval_response

    async def needs_human(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import NeedsHumanResponse

        return NeedsHumanResponse(
            hil_request_id="fake",
            decision="timeout",
            resolution={},
            raw_user_text=None,
            timed_out=True,
        )

    async def request_override(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import OverrideResponse

        return OverrideResponse(
            hil_request_id="fake",
            choice="abort",
            selected_alternative=None,
            fallback_action=None,
            timed_out=True,
        )

    async def gate_capability(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import GateDecision, GateOutcome

        return GateDecision(
            outcome=GateOutcome.ALLOW,
            hil_request_id=None,
            reason="fake_allow",
            user_approved=None,
            audit_only=False,
        )

    def reset_round_budget(self, caller_key: str) -> None:
        self.reset_calls.append(caller_key)
        self._budget.pop(caller_key, None)

    async def shutdown(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_port() -> FakeLLMPort:
    return FakeLLMPort()


@pytest.fixture
def tool_router() -> FakeToolRouter:
    return FakeToolRouter()


@pytest.fixture
def hil_coord() -> FakeHILCoordinator:
    return FakeHILCoordinator()


@pytest.fixture
def sketch_svc(
    llm_port: FakeLLMPort,
    tool_router: FakeToolRouter,
    hil_coord: FakeHILCoordinator,
) -> SketchService:
    return SketchService(
        llm_port=llm_port,
        tool_router=tool_router,
        hil_port=hil_coord,
    )


def _make_ctx() -> StageContext:
    """Construct a minimal valid StageContext for stub tests."""
    return StageContext(
        request_id="req-001",
        trace_id="trace-abc",
        timeout_remaining_ms=30000,
        token_budget_remaining=4096,
        cancel_check=lambda: False,
    )


@dataclass
class FakePlanRequest:
    """Minimal stand-in for PlanRequest (from k1.orchestrator.types)."""

    request_id: str = "req-001"
    trace_id: str = "trace-abc"
    intent: str = "test intent"


@dataclass
class FakeMicroReplanRequest:
    """Minimal stand-in for MicroReplanRequest."""

    original_plan_id: str = "plan-001"
    trace_id: str = "trace-micro"
    request_id: str = "req-micro-001"


# ===========================================================================
# 1. Constructor -- valid dependencies
# ===========================================================================


class TestConstructorValid:
    """SketchService constructor stores all 3 dependencies."""

    def test_constructor_stores_llm_port(
        self, sketch_svc: SketchService, llm_port: FakeLLMPort
    ) -> None:
        assert sketch_svc.llm_port is llm_port

    def test_constructor_stores_tool_router(
        self, sketch_svc: SketchService, tool_router: FakeToolRouter
    ) -> None:
        assert sketch_svc.tool_router is tool_router

    def test_constructor_stores_hil_coord(
        self, sketch_svc: SketchService, hil_coord: FakeHILCoordinator
    ) -> None:
        assert sketch_svc.hil_port is hil_coord

    def test_constructor_keyword_only(self) -> None:
        """Constructor params must be passed as keywords (positional also OK)."""
        svc = SketchService(
            llm_port=FakeLLMPort(),
            tool_router=FakeToolRouter(),
            hil_port=FakeHILCoordinator(),
        )
        assert svc.llm_port is not None
        assert svc.tool_router is not None
        assert svc.hil_port is not None


# ===========================================================================
# 2. Constructor -- None rejection
# ===========================================================================


class TestConstructorNoneRejection:
    """Constructor rejects None for each dependency with TypeError."""

    def test_none_llm_port_raises(self) -> None:
        with pytest.raises(TypeError, match="llm_port must not be None"):
            SketchService(
                llm_port=None,  # type: ignore[arg-type]
                tool_router=FakeToolRouter(),
                hil_port=FakeHILCoordinator(),
            )

    def test_none_tool_router_raises(self) -> None:
        with pytest.raises(TypeError, match="tool_router must not be None"):
            SketchService(
                llm_port=FakeLLMPort(),
                tool_router=None,  # type: ignore[arg-type]
                hil_port=FakeHILCoordinator(),
            )

    def test_none_hil_coord_raises(self) -> None:
        with pytest.raises(TypeError, match="hil_port must not be None"):
            SketchService(
                llm_port=FakeLLMPort(),
                tool_router=FakeToolRouter(),
                hil_port=None,  # type: ignore[arg-type]
            )


# ===========================================================================
# 3. __slots__ verification
# ===========================================================================


class TestSlots:
    """SketchService uses __slots__ -- no __dict__ allowed."""

    def test_has_slots(self) -> None:
        assert hasattr(SketchService, "__slots__")

    def test_no_dict(self, sketch_svc: SketchService) -> None:
        assert not hasattr(sketch_svc, "__dict__")

    def test_slots_contain_expected_names(self) -> None:
        expected = {"_llm_port", "_tool_router", "_hil_port"}
        assert set(SketchService.__slots__) == expected

    def test_slots_exactly_three(self) -> None:
        """Stateless between calls -- only 3 dependency slots, no mutable state."""
        assert len(SketchService.__slots__) == 3

    def test_cannot_add_arbitrary_attribute(self, sketch_svc: SketchService) -> None:
        with pytest.raises(AttributeError):
            sketch_svc.unexpected_field = "bad"  # type: ignore[attr-defined]


# ===========================================================================
# 4. Read-only property accessors
# ===========================================================================


class TestProperties:
    """Properties expose dependencies as read-only."""

    def test_llm_port_property_type(self, sketch_svc: SketchService) -> None:
        assert sketch_svc.llm_port is not None

    def test_tool_router_property_type(self, sketch_svc: SketchService) -> None:
        assert sketch_svc.tool_router is not None

    def test_hil_coord_property_type(self, sketch_svc: SketchService) -> None:
        assert sketch_svc.hil_port is not None

    def test_llm_port_property_same_instance(
        self, sketch_svc: SketchService, llm_port: FakeLLMPort
    ) -> None:
        assert sketch_svc.llm_port is llm_port

    def test_tool_router_property_same_instance(
        self, sketch_svc: SketchService, tool_router: FakeToolRouter
    ) -> None:
        assert sketch_svc.tool_router is tool_router

    def test_hil_coord_property_same_instance(
        self, sketch_svc: SketchService, hil_coord: FakeHILCoordinator
    ) -> None:
        assert sketch_svc.hil_port is hil_coord


# ===========================================================================
# 5. execute() -- signature and async verification
# ===========================================================================


class TestExecuteSignature:
    """execute() is async with correct signature (now implemented in 3.1.2+)."""

    def test_execute_is_async(self) -> None:
        """execute() must be an async method (coroutine function)."""
        assert inspect.iscoroutinefunction(SketchService.execute)

    def test_execute_signature_params(self) -> None:
        """execute() signature: (self, request: PlanRequest, ctx: StageContext) -> SketchResult."""
        sig = inspect.signature(SketchService.execute)
        param_names = list(sig.parameters.keys())
        assert param_names == ["self", "request", "ctx"]


# ===========================================================================
# 6. micro_execute() -- signature and async verification
# ===========================================================================


class TestMicroExecuteSignature:
    """micro_execute() is async with correct signature (now implemented in 3.1.2+)."""

    def test_micro_execute_is_async(self) -> None:
        """micro_execute() must be an async method (coroutine function)."""
        assert inspect.iscoroutinefunction(SketchService.micro_execute)

    def test_micro_execute_signature_params(self) -> None:
        """micro_execute() signature: (self, request, ctx) -> SketchResult."""
        sig = inspect.signature(SketchService.micro_execute)
        param_names = list(sig.parameters.keys())
        assert param_names == ["self", "request", "ctx"]


# ===========================================================================
# 7. Statelessness -- no mutable instance state
# ===========================================================================


class TestStatelessness:
    """SketchService is stateless between calls (all state via params)."""

    def test_no_counter_slot(self) -> None:
        """No _retry_count, _call_count, or similar mutable slots."""
        for slot in SketchService.__slots__:
            assert not slot.startswith("_count")
            assert not slot.startswith("_retry")

    def test_only_dependency_slots(self) -> None:
        """All slots are dependency references (prefixed with _)."""
        for slot in SketchService.__slots__:
            assert slot.startswith("_"), f"Slot {slot!r} is not a private dependency"

    def test_no_pipeline_controller_reference(self) -> None:
        """SketchService does NOT hold a reference to PipelineController."""
        assert "_pipeline_ctrl" not in SketchService.__slots__
        assert "_controller" not in SketchService.__slots__


# ===========================================================================
# 8. Protocol structural checks -- ToolCallRouterLike
# ===========================================================================


class TestToolCallRouterLikeProtocol:
    """ToolCallRouterLike protocol defines the expected interface."""

    def test_is_runtime_checkable(self) -> None:
        """ToolCallRouterLike is @runtime_checkable."""
        assert isinstance(FakeToolRouter(), ToolCallRouterLike)

    def test_non_conforming_rejected(self) -> None:
        """Objects missing required methods are NOT ToolCallRouterLike."""
        assert not isinstance(object(), ToolCallRouterLike)

    def test_has_tool_call_count_property(self) -> None:
        """Protocol declares tool_call_count property."""
        assert hasattr(ToolCallRouterLike, "tool_call_count")

    def test_has_reset_method(self) -> None:
        """Protocol declares reset() method."""
        assert hasattr(ToolCallRouterLike, "reset")
        assert callable(getattr(ToolCallRouterLike, "reset", None))

    def test_has_discover_method(self) -> None:
        """Protocol declares discover() async method."""
        assert hasattr(ToolCallRouterLike, "discover")
        assert inspect.iscoroutinefunction(getattr(ToolCallRouterLike, "discover", None))

    def test_has_read_context_method(self) -> None:
        """Protocol declares read_context() async method."""
        assert hasattr(ToolCallRouterLike, "read_context")
        assert inspect.iscoroutinefunction(getattr(ToolCallRouterLike, "read_context", None))

    def test_has_recall_memory_method(self) -> None:
        """Protocol declares recall_memory() async method."""
        assert hasattr(ToolCallRouterLike, "recall_memory")
        assert inspect.iscoroutinefunction(getattr(ToolCallRouterLike, "recall_memory", None))


# ===========================================================================
# 9. HILCoordinatorLike protocol checks REMOVED in E5 (HIL Unification).
# Planner stages now consume the unified IHILPort directly; the legacy
# planner-local HILCoordinatorLike protocol has been deleted.
# ===========================================================================


# ===========================================================================
# 10. Dependency layer validation (Layer 2)
# ===========================================================================


class TestDependencyLayer:
    """SketchService is Layer 2 -- imports only Layer 0 types and Layer 1 ports."""

    def test_imports_ilmport_from_layer1(self) -> None:
        """ILLMPort imported from k1.planner.ports.llm_port (Layer 1)."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        assert "from k1.planner.ports.llm_port import ILLMPort" in source

    def test_imports_types_from_layer0(self) -> None:
        """Layer 0 types imported from k1.planner.types."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        assert "from k1.planner.types import" in source

    def test_imports_orchestrator_types_from_layer0(self) -> None:
        """Shared types imported from k1.orchestrator.types (Layer 0)."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        assert "from k1.orchestrator.types import" in source

    def test_no_layer3_imports(self) -> None:
        """Layer 2 must NOT import Layer 3 (PlannerAgent) -- AST check."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    "planner_agent" not in node.module
                ), f"Layer 2 must not import PlannerAgent: {node.module}"
                if node.names:
                    for alias in node.names:
                        assert alias.name != "PlannerAgent", "Layer 2 must not import PlannerAgent"

    def test_no_pipeline_controller_import(self) -> None:
        """SketchService must NOT import PipelineController (AST check)."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    "pipeline_controller" not in node.module
                ), f"Layer 2 must not import PipelineController: {node.module}"
                if node.names:
                    for alias in node.names:
                        assert (
                            alias.name != "PipelineController"
                        ), "Layer 2 must not import PipelineController"

    def test_no_adapter_imports(self) -> None:
        """Layer 2 must NOT import adapters directly."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                assert (
                    "adapter" not in module.lower()
                ), f"Layer 2 must not import adapters: {module}"

    def test_no_circular_stage_imports(self) -> None:
        """SketchService must NOT import other stage services."""
        source = Path(inspect.getfile(SketchService)).read_text(encoding="utf-8")
        assert "expand_service" not in source
        assert "validate_service" not in source
        assert "commit_service" not in source


# ===========================================================================
# 11. Module exports
# ===========================================================================


class TestModuleExports:
    """sketch_service module exports the expected symbols."""

    def test_sketch_service_importable(self) -> None:
        from k1.planner.stages.sketch_service import SketchService as _S

        assert _S is SketchService

    def test_tool_call_router_like_importable(self) -> None:
        from k1.planner.stages.sketch_service import ToolCallRouterLike as _T

        assert _T is ToolCallRouterLike


# ===========================================================================
# 12. Multiple instances -- isolation
# ===========================================================================


class TestInstanceIsolation:
    """Multiple SketchService instances do not share state."""

    def test_different_llm_ports(self) -> None:
        llm_a, llm_b = FakeLLMPort(), FakeLLMPort()
        svc_a = SketchService(
            llm_port=llm_a,
            tool_router=FakeToolRouter(),
            hil_port=FakeHILCoordinator(),
        )
        svc_b = SketchService(
            llm_port=llm_b,
            tool_router=FakeToolRouter(),
            hil_port=FakeHILCoordinator(),
        )
        assert svc_a.llm_port is llm_a
        assert svc_b.llm_port is llm_b
        assert svc_a.llm_port is not svc_b.llm_port

    def test_different_tool_routers(self) -> None:
        tr_a, tr_b = FakeToolRouter(), FakeToolRouter()
        svc_a = SketchService(
            llm_port=FakeLLMPort(),
            tool_router=tr_a,
            hil_port=FakeHILCoordinator(),
        )
        svc_b = SketchService(
            llm_port=FakeLLMPort(),
            tool_router=tr_b,
            hil_port=FakeHILCoordinator(),
        )
        assert svc_a.tool_router is tr_a
        assert svc_b.tool_router is tr_b
        assert svc_a.tool_router is not svc_b.tool_router
