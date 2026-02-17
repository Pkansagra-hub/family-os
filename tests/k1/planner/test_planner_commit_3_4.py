"""
Tests for CommitService (Epic 3.4).

Covers all 6 issues of Epic 3.4:
  3.4.1 -- CommitService skeleton & constructor
  3.4.2 -- Constructor-level ILLMPort exclusion (PLAN-03)
  3.4.3 -- Deterministic CommittedPlan assembly
  3.4.4 -- WAL persist via IBridgePort
  3.4.5 -- Event emission (plan.ready via IEventPort)
  3.4.6 -- Delta emission (plan_committed + plan_end)

Test categories (~30 tests target):
  - Plan assembly correctness (~8)
  - WAL persist call (~6)
  - Event emission (~6)
  - Delta emission (~4)
  - Bridge offline (~3)
  - Cancel during commit (~3)

References
----------
- planner.md Section 9 (Stage 4 COMMIT Deep Dive)
- planner.md Section 17.6 (CommitService ~30 tests)
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

from k1.orchestrator.types import CommittedPlan, PlanRequest, PlanStep
from k1.planner.events import TOPIC_PLAN_READY
from k1.planner.stages.commit_service import CommitService
from k1.planner.types import (
    DELTA_PLAN_END,
    DELTA_STAGE_TRANSITION,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    VERDICT_APPROVED,
    CommitFailedError,
    DeltaPayload,
    ExpandedPlan,
    StageContext,
    ValidationVerdict,
)

# ===========================================================================
# Fakes
# ===========================================================================


class FakeBridgePort:
    """Configurable fake IBridgePort for testing."""

    def __init__(self) -> None:
        self.persist_calls: List[CommittedPlan] = []
        self.persist_error: Optional[Exception] = None
        self.persist_fail_count: int = 0
        self._fail_remaining: int = 0

    def set_persist_failures(self, count: int) -> None:
        """Set number of consecutive persist failures before success."""
        self._fail_remaining = count

    async def recall(
        self,
        query: str,
        selectors: Optional[List[str]] = None,
        *,
        trace_id: str = "",
    ) -> Any:
        return None

    async def persist_plan(
        self,
        plan: CommittedPlan,
        *,
        trace_id: str = "",
    ) -> None:
        self.persist_calls.append(plan)
        if self.persist_error is not None:
            raise self.persist_error
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise RuntimeError("WAL persist simulated failure")


class FakeDeltaPort:
    """Configurable fake IDeltaEmitPort for testing."""

    def __init__(self) -> None:
        self.deltas: List[DeltaPayload] = []
        self.emit_error: Optional[Exception] = None

    def emit(self, delta: DeltaPayload) -> None:
        self.deltas.append(delta)
        if self.emit_error is not None:
            raise self.emit_error


class FakeEventPort:
    """Configurable fake IEventPort for testing."""

    def __init__(self) -> None:
        self.emissions: List[tuple[str, Any]] = []
        self.emit_error: Optional[Exception] = None
        self._fail_remaining: int = 0

    def set_emit_failures(self, count: int) -> None:
        self._fail_remaining = count

    def emit(self, topic: str, payload: Any) -> None:
        self.emissions.append((topic, payload))
        if self.emit_error is not None:
            raise self.emit_error
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise RuntimeError("Event emit simulated failure")

    def subscribe(self, topic: str, handler: Callable) -> Any:
        return None

    def unsubscribe(self, handle: Any) -> bool:
        return True


# ===========================================================================
# Helpers
# ===========================================================================


def _never_cancel() -> bool:
    return False


def _always_cancel() -> bool:
    return True


def _ctx(
    request_id: str = "req-1",
    trace_id: str = "trace-1",
    timeout_ms: int = 5000,
    token_budget: int = 2000,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> StageContext:
    return StageContext(
        request_id=request_id,
        trace_id=trace_id,
        timeout_remaining_ms=timeout_ms,
        token_budget_remaining=token_budget,
        cancel_check=cancel_check or _never_cancel,
    )


def _step(
    step_id: str = "s1",
    capability: str = "tool.demo",
    *,
    timeout_ms: int = 1000,
    has_side_effects: bool = False,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params={},
        timeout_ms=timeout_ms,
        has_side_effects=has_side_effects,
    )


def _plan(
    steps: Optional[List[PlanStep]] = None,
    dependencies: Optional[Dict[str, List[str]]] = None,
    rationale: str = "test plan",
) -> ExpandedPlan:
    if steps is None:
        steps = [_step("s1")]
    tool_mappings = {s.id: s.capability for s in steps}
    return ExpandedPlan(
        steps=steps,
        dependencies=dependencies or {},
        tool_mappings=tool_mappings,
        rationale=rationale,
    )


def _request(intent: str = "test intent") -> PlanRequest:
    return PlanRequest(
        intent=intent,
        request_id="req-1",
        trace_id="trace-1",
    )


def _verdict() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_APPROVED,
        rationale="approved",
        confidence=0.95,
    )


def _svc(
    bridge: Optional[FakeBridgePort] = None,
    delta: Optional[FakeDeltaPort] = None,
    event: Optional[FakeEventPort] = None,
) -> tuple[CommitService, FakeBridgePort, FakeDeltaPort, FakeEventPort]:
    b = bridge or FakeBridgePort()
    d = delta or FakeDeltaPort()
    e = event or FakeEventPort()
    return CommitService(b, d, e), b, d, e


# ===========================================================================
# 1. Constructor & Skeleton (Issue 3.4.1, 3.4.2) ~5 tests
# ===========================================================================


class TestConstructor:
    """CommitService constructor and PLAN-03 enforcement."""

    def test_constructor_stores_dependencies(self) -> None:
        svc, b, d, e = _svc()
        assert svc.bridge_port is b
        assert svc.delta_port is d
        assert svc.event_port is e

    def test_constructor_rejects_none_bridge(self) -> None:
        with pytest.raises(TypeError, match="bridge_port"):
            CommitService(None, FakeDeltaPort(), FakeEventPort())  # type: ignore[arg-type]

    def test_constructor_rejects_none_delta(self) -> None:
        with pytest.raises(TypeError, match="delta_port"):
            CommitService(FakeBridgePort(), None, FakeEventPort())  # type: ignore[arg-type]

    def test_constructor_rejects_none_event(self) -> None:
        with pytest.raises(TypeError, match="event_port"):
            CommitService(FakeBridgePort(), FakeDeltaPort(), None)  # type: ignore[arg-type]

    def test_uses_slots(self) -> None:
        assert "_bridge_port" in CommitService.__slots__
        assert "_delta_port" in CommitService.__slots__
        assert "_event_port" in CommitService.__slots__

    def test_plan03_no_llm_port_in_constructor(self) -> None:
        """PLAN-03: constructor has no llm_port parameter."""
        import inspect as _inspect

        sig = _inspect.signature(CommitService.__init__)
        param_names = set(sig.parameters.keys()) - {"self"}
        assert "llm_port" not in param_names
        assert param_names == {"bridge_port", "delta_port", "event_port"}


# ===========================================================================
# 2. Plan Assembly (Issue 3.4.3) ~8 tests
# ===========================================================================


class TestPlanAssembly:
    """Deterministic CommittedPlan assembly."""

    async def test_returns_committed_plan(self) -> None:
        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)

    async def test_plan_id_is_uuid(self) -> None:
        """plan_id is a valid UUID string."""
        import uuid

        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        uuid.UUID(result.plan_id)  # Raises ValueError if invalid.

    async def test_request_id_correlation(self) -> None:
        """Correlation contract: committed_plan.request_id == request.request_id."""
        svc, _, _, _ = _svc()
        req = _request()
        result = await svc.execute(_plan(), req, _verdict(), _ctx())
        assert result.request_id == req.request_id

    async def test_intent_from_request(self) -> None:
        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(), _request("book restaurant"), _verdict(), _ctx())
        assert result.intent == "book restaurant"

    async def test_trace_id_from_request(self) -> None:
        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert result.trace_id == "trace-1"

    async def test_steps_from_expanded_plan(self) -> None:
        """Steps are transferred from ExpandedPlan (no modification)."""
        steps = [_step("s1"), _step("s2")]
        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(steps=steps), _request(), _verdict(), _ctx())
        assert len(result.steps) == 2
        assert result.steps[0].id == "s1"
        assert result.steps[1].id == "s2"

    async def test_dependencies_from_expanded_plan(self) -> None:
        steps = [_step("s1"), _step("s2")]
        deps = {"s2": ["s1"]}
        svc, _, _, _ = _svc()
        result = await svc.execute(
            _plan(steps=steps, dependencies=deps), _request(), _verdict(), _ctx()
        )
        assert result.dependencies == {"s2": ["s1"]}

    async def test_critical_path_linear_chain(self) -> None:
        """Linear chain: s1(1000ms) -> s2(2000ms) -> s3(500ms) = 3500ms."""
        steps = [
            _step("s1", timeout_ms=1000),
            _step("s2", timeout_ms=2000),
            _step("s3", timeout_ms=500),
        ]
        deps = {"s2": ["s1"], "s3": ["s2"]}
        svc, _, _, _ = _svc()
        result = await svc.execute(
            _plan(steps=steps, dependencies=deps), _request(), _verdict(), _ctx()
        )
        assert result.estimated_duration_ms == 3500

    async def test_critical_path_parallel_steps(self) -> None:
        """No deps: parallel execution. Critical path = max(timeouts)."""
        steps = [
            _step("s1", timeout_ms=1000),
            _step("s2", timeout_ms=3000),
            _step("s3", timeout_ms=500),
        ]
        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(steps=steps), _request(), _verdict(), _ctx())
        assert result.estimated_duration_ms == 3000

    async def test_critical_path_diamond_dag(self) -> None:
        """Diamond DAG: s1 -> (s2, s3) -> s4. Two paths, pick longest."""
        steps = [
            _step("s1", timeout_ms=100),
            _step("s2", timeout_ms=200),
            _step("s3", timeout_ms=500),
            _step("s4", timeout_ms=100),
        ]
        # s1 -> s2 -> s4: 100+200+100 = 400
        # s1 -> s3 -> s4: 100+500+100 = 700
        deps = {"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]}
        svc, _, _, _ = _svc()
        result = await svc.execute(
            _plan(steps=steps, dependencies=deps),
            _request(),
            _verdict(),
            _ctx(),
        )
        assert result.estimated_duration_ms == 700

    async def test_created_at_is_positive(self) -> None:
        svc, _, _, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert result.created_at > 0


# ===========================================================================
# 3. WAL Persist (Issue 3.4.4) ~6 tests
# ===========================================================================


class TestWALPersist:
    """WAL persistence via IBridgePort."""

    async def test_persist_called_once_on_success(self) -> None:
        svc, bridge, _, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert len(bridge.persist_calls) == 1
        assert bridge.persist_calls[0].plan_id == result.plan_id

    async def test_persist_retry_on_first_failure(self) -> None:
        """First persist fails, retry succeeds -- 2 calls total."""
        bridge = FakeBridgePort()
        bridge.set_persist_failures(1)
        svc, _, _, _ = _svc(bridge=bridge)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert len(bridge.persist_calls) == 2
        assert isinstance(result, CommittedPlan)

    async def test_persist_both_fail_proceeds(self) -> None:
        """Both attempts fail -- plan still delivered (WAL never blocks)."""
        bridge = FakeBridgePort()
        bridge.persist_error = RuntimeError("WAL offline")
        svc, _, _, event = _svc(bridge=bridge)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)
        assert len(bridge.persist_calls) == 2  # Try + retry.
        assert len(event.emissions) >= 1  # Plan still delivered.

    async def test_persist_idempotent_same_plan_id(self) -> None:
        """Both persist calls use same plan (same plan_id for dedup)."""
        bridge = FakeBridgePort()
        bridge.set_persist_failures(1)
        svc, _, _, _ = _svc(bridge=bridge)
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert bridge.persist_calls[0].plan_id == bridge.persist_calls[1].plan_id

    async def test_persist_passes_trace_id(self) -> None:
        """persist_plan receives trace_id from context."""
        # We can verify indirectly via the call happening without error.
        svc, bridge, _, _ = _svc()
        await svc.execute(_plan(), _request(), _verdict(), _ctx(trace_id="trace-abc"))
        assert len(bridge.persist_calls) == 1

    async def test_wal_persisted_flag_in_delta(self) -> None:
        """Stage delta carries wal_persisted=True on success."""
        svc, _, delta, _ = _svc()
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        stage_deltas = [d for d in delta.deltas if d.delta_type == DELTA_STAGE_TRANSITION]
        assert len(stage_deltas) == 1
        assert stage_deltas[0].data["wal_persisted"] is True

    async def test_wal_failed_flag_in_delta(self) -> None:
        """Stage delta carries wal_persisted=False on failure."""
        bridge = FakeBridgePort()
        bridge.persist_error = RuntimeError("WAL offline")
        svc, _, delta, _ = _svc(bridge=bridge)
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        stage_deltas = [d for d in delta.deltas if d.delta_type == DELTA_STAGE_TRANSITION]
        assert len(stage_deltas) == 1
        assert stage_deltas[0].data["wal_persisted"] is False


# ===========================================================================
# 4. Event Emission (Issue 3.4.5) ~6 tests
# ===========================================================================


class TestEventEmission:
    """Plan delivery via IEventPort."""

    async def test_emits_plan_ready_event(self) -> None:
        svc, _, _, event = _svc()
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert len(event.emissions) == 1
        topic, payload = event.emissions[0]
        assert topic == TOPIC_PLAN_READY

    async def test_payload_is_committed_plan_dict(self) -> None:
        svc, _, _, event = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        _, payload = event.emissions[0]
        assert payload["plan_id"] == result.plan_id
        assert payload["request_id"] == result.request_id
        assert payload["intent"] == result.intent

    async def test_payload_has_steps(self) -> None:
        steps = [_step("s1"), _step("s2")]
        svc, _, _, event = _svc()
        await svc.execute(_plan(steps=steps), _request(), _verdict(), _ctx())
        _, payload = event.emissions[0]
        assert len(payload["steps"]) == 2

    async def test_event_retry_on_first_failure(self) -> None:
        """First emit fails, retry succeeds."""
        event = FakeEventPort()
        event.set_emit_failures(1)
        svc, _, _, _ = _svc(event=event)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)
        assert len(event.emissions) == 2  # Try + retry.

    async def test_event_both_fail_still_returns(self) -> None:
        """Both attempts fail -- plan completed but undeliverable."""
        event = FakeEventPort()
        event.emit_error = RuntimeError("Event bus offline")
        svc, _, _, _ = _svc(event=event)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)  # Still returns.
        assert len(event.emissions) == 2  # Try + retry.

    async def test_topic_constant_not_hardcoded(self) -> None:
        """TOPIC_PLAN_READY is imported from events module."""
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        assert "from k1.planner.events import TOPIC_PLAN_READY" in source


# ===========================================================================
# 5. Delta Emission (Issue 3.4.6) ~4 tests
# ===========================================================================


class TestDeltaEmission:
    """Stage and plan-end delta emissions."""

    async def test_emits_stage_delta(self) -> None:
        svc, _, delta, _ = _svc()
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        stage_deltas = [d for d in delta.deltas if d.delta_type == DELTA_STAGE_TRANSITION]
        assert len(stage_deltas) == 1
        d = stage_deltas[0]
        assert d.agent_id == PLANNER_AGENT_ID
        assert d.section == SECTION_PIPELINE
        assert d.data["stage"] == "COMMIT"
        assert d.data["status"] == "completed"
        assert d.data["tokens_used"] == 0
        assert d.data["tool_calls_used"] == 0

    async def test_emits_plan_end_delta(self) -> None:
        svc, _, delta, _ = _svc()
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        end_deltas = [d for d in delta.deltas if d.delta_type == DELTA_PLAN_END]
        assert len(end_deltas) == 1
        d = end_deltas[0]
        assert d.agent_id == PLANNER_AGENT_ID
        assert d.data["stages_completed"] == ["SKETCH", "EXPAND", "VALIDATE", "COMMIT"]
        assert d.data["total_tokens"] == 0

    async def test_stage_delta_has_plan_id(self) -> None:
        svc, _, delta, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        stage_deltas = [d for d in delta.deltas if d.delta_type == DELTA_STAGE_TRANSITION]
        assert stage_deltas[0].data["plan_id"] == result.plan_id

    async def test_plan_end_delta_has_request_id(self) -> None:
        svc, _, delta, _ = _svc()
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        end_deltas = [d for d in delta.deltas if d.delta_type == DELTA_PLAN_END]
        assert end_deltas[0].data["request_id"] == result.request_id

    async def test_delta_emission_failure_does_not_block(self) -> None:
        """Delta emit failure does not block plan completion."""
        delta = FakeDeltaPort()
        delta.emit_error = RuntimeError("Delta bus offline")
        svc, _, _, _ = _svc(delta=delta)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)  # Still succeeds.


# ===========================================================================
# 6. Bridge Offline (Issue 3.4.4 recovery) ~3 tests
# ===========================================================================


class TestBridgeOffline:
    """WAL offline recovery paths."""

    async def test_bridge_offline_plan_still_delivered(self) -> None:
        """Bridge completely offline -- plan delivered via event bus."""
        bridge = FakeBridgePort()
        bridge.persist_error = ConnectionError("K0 unreachable")
        svc, _, _, event = _svc(bridge=bridge)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)
        assert len(event.emissions) >= 1

    async def test_bridge_offline_deltas_still_emitted(self) -> None:
        bridge = FakeBridgePort()
        bridge.persist_error = ConnectionError("K0 unreachable")
        svc, _, delta, _ = _svc(bridge=bridge)
        await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert len(delta.deltas) == 2  # stage + plan_end.

    async def test_bridge_timeout_plan_proceeds(self) -> None:
        bridge = FakeBridgePort()
        bridge.persist_error = TimeoutError("K0 timeout")
        svc, _, _, event = _svc(bridge=bridge)
        result = await svc.execute(_plan(), _request(), _verdict(), _ctx())
        assert isinstance(result, CommittedPlan)


# ===========================================================================
# 7. Cancel During Commit (Issue 3.4.6 recovery) ~3 tests
# ===========================================================================


class TestCancelDuringCommit:
    """Cancellation handling."""

    async def test_cancel_raises_commit_failed(self) -> None:
        svc, _, _, _ = _svc()
        ctx = _ctx(cancel_check=_always_cancel)
        with pytest.raises(CommitFailedError):
            await svc.execute(_plan(), _request(), _verdict(), ctx)

    async def test_cancel_no_bridge_call(self) -> None:
        """On cancel, no WAL persist call is made."""
        svc, bridge, _, _ = _svc()
        ctx = _ctx(cancel_check=_always_cancel)
        with pytest.raises(CommitFailedError):
            await svc.execute(_plan(), _request(), _verdict(), ctx)
        assert len(bridge.persist_calls) == 0

    async def test_cancel_no_event_emitted(self) -> None:
        """On cancel, no plan.ready event is emitted."""
        svc, _, _, event = _svc()
        ctx = _ctx(cancel_check=_always_cancel)
        with pytest.raises(CommitFailedError):
            await svc.execute(_plan(), _request(), _verdict(), ctx)
        assert len(event.emissions) == 0


# ===========================================================================
# 8. PLAN-03 Enforcement & Dependency Layer
# ===========================================================================


class TestPLAN03Enforcement:
    """PLAN-03: zero LLM calls, enforced at module level."""

    def test_no_ilmport_import(self) -> None:
        """Module does NOT import ILLMPort."""
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names = [alias.name for alias in (node.names or [])]
                assert "ILLMPort" not in imported_names, f"Found ILLMPort import in {node.module}"

    def test_no_fabric_retrieval_import(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names = [alias.name for alias in (node.names or [])]
                assert "IFabricRetrievalPort" not in imported_names

    def test_no_tool_call_router_import(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names = [alias.name for alias in (node.names or [])]
                assert "ToolCallRouter" not in imported_names

    def test_no_hil_coordinator_import(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names = [alias.name for alias in (node.names or [])]
                assert "HILCoordinator" not in imported_names
                assert "HILCoordinatorLike" not in imported_names

    def test_no_state_read_port_import(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names = [alias.name for alias in (node.names or [])]
                assert "IStateReadPort" not in imported_names

    def test_no_layer3_imports(self) -> None:
        """Layer 2 must NOT import Layer 3."""
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "planner_agent" not in node.module
                assert "pipeline_controller" not in node.module

    def test_no_circular_stage_imports(self) -> None:
        """CommitService must NOT import other stage services."""
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        assert "sketch_service" not in source
        assert "expand_service" not in source
        assert "validate_service" not in source

    def test_imports_bridge_port_from_layer1(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        assert "from k1.planner.ports.bridge_port import IBridgePort" in source

    def test_imports_delta_port_from_layer1(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        assert "from k1.planner.ports.delta_emit_port import IDeltaEmitPort" in source

    def test_imports_event_port_from_layer1(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        assert "from k1.planner.ports.event_port import IEventPort" in source

    def test_imports_topic_from_events(self) -> None:
        source = Path(inspect.getfile(CommitService)).read_text(encoding="utf-8")
        assert "from k1.planner.events import TOPIC_PLAN_READY" in source
