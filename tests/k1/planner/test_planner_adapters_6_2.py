"""Epic 6.2 -- Production adapter tests.

Tests for all 7 production adapters in k1/planner/adapters/:
    1. MailboxAdapter          [F28]  -- asyncio.Queue-backed mailbox
    2. LLMGatewayAdapter       [F29]  -- V2 LLM routing (ILLMRequestBus)
    3. FabricRetrievalAdapter  [F30]  -- capability discovery (FabricRetrieval)
    4. SessionStateReadAdapter [F31]  -- pre-bound session reader
    5. BridgeAdapter           [F32]  -- K0 recall + persist via Bridge
    6. DeltaBusAdapter         [F33]  -- fire-and-forget delta emission
    7. EventBusAdapter         [F34]  -- event pub/sub passthrough

Each adapter gets:
    - Happy-path test(s)
    - Error/degraded-path test(s)
    - Protocol/contract validation test(s)

Run: pytest tests/test_planner_adapters_6_2.py -v
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Type imports
# ---------------------------------------------------------------------------
from k1.fabric.ports.bridge_port import BridgeCommandResult
from k1.fabric.ports.event_port import SubscriptionHandle
from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import RetrievalResult, ScoredCapability
from k1.orchestrator.types import (
    CommittedPlan,
    MicroReplanRequest,
    PlanRequest,
    PlanStep,
)

# ---------------------------------------------------------------------------
# Adapter imports
# ---------------------------------------------------------------------------
from k1.planner.adapters import (
    BridgeAdapter,
    DeltaBusAdapter,
    EventBusAdapter,
    FabricRetrievalAdapter,
    LLMGatewayAdapter,
    MailboxAdapter,
    SessionStateReadAdapter,
)
from k1.planner.adapters.llm_gateway_adapter import ILLMRequestBus
from k1.planner.types import (
    AdapterException,
    DeltaPayload,
    HubRequest,
    HubResponse,
    LLMTimeoutError,
    MailboxFullError,
    RequestConstraints,
    ShutdownError,
)

# ===================================================================
# Helper factories
# ===================================================================


def _make_plan_request(intent: str = "test intent", trace_id: str = "t-001") -> PlanRequest:
    return PlanRequest(intent=intent, trace_id=trace_id)


def _make_plan_step(step_id: str = "s1", capability: str = "do") -> PlanStep:
    return PlanStep(id=step_id, capability=capability)


def _make_committed_plan(
    plan_id: str = "p-1",
    request_id: str = "r-1",
    intent: str = "test",
    trace_id: str = "t-cp",
) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent=intent,
        steps=[_make_plan_step()],
        trace_id=trace_id,
    )


def _make_micro_replan_request(
    original_plan_id: str = "p-orig",
    trace_id: str = "t-mr",
) -> MicroReplanRequest:
    return MicroReplanRequest(
        original_plan_id=original_plan_id,
        completed_results={},
        remaining_steps=[_make_plan_step("s-remain", "adjust")],
        trace_id=trace_id,
    )


def _make_hub_request(
    capability: str = "CHAT",
    max_tokens: int = 100,
    timeout_ms: int = 5000,
) -> HubRequest:
    return HubRequest(
        capability=capability,
        payload={"messages": [{"role": "user", "content": "hello"}]},
        constraints=RequestConstraints(max_tokens=max_tokens, timeout_ms=timeout_ms),
        trace_id="t-hub-001",
    )


def _make_delta_payload(
    delta_type: str = "stage_transition",
    section: str = "pipeline",
) -> DeltaPayload:
    return DeltaPayload(
        agent_id="planner",
        delta_type=delta_type,
        section=section,
        data={"stage": "SKETCH"},
        trace_id="t-delta-001",
    )


# ===================================================================
# 1. MailboxAdapter [F28]
# ===================================================================


class TestMailboxAdapterHappyPath:
    """Happy-path tests for MailboxAdapter."""

    async def test_enqueue_dequeue_fifo(self):
        """Enqueue 3 requests, dequeue in FIFO order."""
        adapter = MailboxAdapter(max_depth=5)
        r1 = _make_plan_request("first", "t1")
        r2 = _make_plan_request("second", "t2")
        r3 = _make_plan_request("third", "t3")

        await adapter.enqueue(r1)
        await adapter.enqueue(r2)
        await adapter.enqueue(r3)

        assert adapter.depth == 3
        assert await adapter.dequeue() is r1
        assert await adapter.dequeue() is r2
        assert await adapter.dequeue() is r3
        assert adapter.depth == 0

    async def test_depth_property(self):
        adapter = MailboxAdapter(max_depth=3)
        assert adapter.depth == 0
        await adapter.enqueue(_make_plan_request())
        assert adapter.depth == 1

    async def test_max_depth_property(self):
        adapter = MailboxAdapter(max_depth=7)
        assert adapter.max_depth == 7

    async def test_priority_class_property(self):
        adapter = MailboxAdapter()
        assert adapter.priority_class == "INTERACTIVE"

    async def test_send_cancel(self):
        adapter = MailboxAdapter()
        assert not adapter.is_cancel_requested("req-1")
        await adapter.send_cancel("req-1")
        assert adapter.is_cancel_requested("req-1")

    async def test_clear_cancel(self):
        adapter = MailboxAdapter()
        await adapter.send_cancel("req-1")
        adapter.clear_cancel("req-1")
        assert not adapter.is_cancel_requested("req-1")

    async def test_drain(self):
        adapter = MailboxAdapter(max_depth=5)
        r1 = _make_plan_request("a", "t1")
        r2 = _make_plan_request("b", "t2")
        await adapter.enqueue(r1)
        await adapter.enqueue(r2)
        drained = adapter.drain()
        assert len(drained) == 2
        assert drained[0] is r1
        assert drained[1] is r2
        assert adapter.depth == 0

    async def test_drain_empty(self):
        adapter = MailboxAdapter()
        assert adapter.drain() == []


class TestMailboxAdapterErrorPath:
    """Error and boundary tests for MailboxAdapter."""

    async def test_enqueue_full_raises_mailbox_full_error(self):
        adapter = MailboxAdapter(max_depth=1)
        await adapter.enqueue(_make_plan_request("first"))
        with pytest.raises(MailboxFullError):
            await adapter.enqueue(_make_plan_request("second"))

    async def test_enqueue_after_shutdown_raises(self):
        adapter = MailboxAdapter()
        adapter.begin_shutdown()
        with pytest.raises(ShutdownError):
            await adapter.enqueue(_make_plan_request())

    async def test_micro_replan_without_controller_raises(self):
        adapter = MailboxAdapter()
        req = _make_micro_replan_request()
        with pytest.raises(RuntimeError, match="PipelineController not set"):
            await adapter.micro_replan(req)

    async def test_micro_replan_after_shutdown_raises(self):
        adapter = MailboxAdapter()
        adapter.begin_shutdown()
        req = _make_micro_replan_request()
        with pytest.raises(ShutdownError):
            await adapter.micro_replan(req)


class TestMailboxAdapterMicroReplan:
    """micro_replan delegation tests."""

    async def test_micro_replan_delegates_to_controller(self):
        adapter = MailboxAdapter()
        plan = _make_committed_plan(plan_id="p-1", request_id="mr-1", intent="adjusted")

        class FakeController:
            async def micro_replan(self, request):
                return plan

        adapter.set_pipeline_controller(FakeController())
        req = _make_micro_replan_request()
        result = await adapter.micro_replan(req)
        assert result is plan

    async def test_micro_replan_returns_none_raises(self):
        adapter = MailboxAdapter()

        class FakeController:
            async def micro_replan(self, request):
                return None

        adapter.set_pipeline_controller(FakeController())
        req = _make_micro_replan_request()
        with pytest.raises(RuntimeError, match="returned None"):
            await adapter.micro_replan(req)


# ===================================================================
# 2. LLMGatewayAdapter [F29]
# ===================================================================


class FakeLLMBus:
    """Fake ILLMRequestBus for testing."""

    def __init__(self, response: Any = None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.last_request: Any = None

    async def request(self, hub_request: Any) -> Any:
        self.last_request = hub_request
        if self._error:
            raise self._error
        return self._response


class TestLLMGatewayAdapterHappyPath:
    """Happy-path tests for LLMGatewayAdapter."""

    async def test_execute_returns_hub_response(self):
        response = HubResponse(result={"content": "hello"}, metadata={"model_id": "gpt-4"})
        bus = FakeLLMBus(response=response)
        adapter = LLMGatewayAdapter(bus, consumer_id="planner")

        result = await adapter.execute(_make_hub_request())
        assert result is response

    async def test_execute_backfills_content_from_model_hub_chat_string(self):
        response = SimpleNamespace(result="hello from chat", metadata={"model_id": "gpt-4"})
        bus = FakeLLMBus(response=response)
        adapter = LLMGatewayAdapter(bus, consumer_id="planner")

        result = await adapter.execute(_make_hub_request())
        assert result.result["content"] == "hello from chat"

    async def test_stamps_consumer_id(self):
        """Verify consumer_id is stamped on constraints (MH-11)."""
        response = HubResponse()
        bus = FakeLLMBus(response=response)
        adapter = LLMGatewayAdapter(bus, consumer_id="test-consumer")

        req = _make_hub_request()
        await adapter.execute(req)

        stamped = bus.last_request
        assert stamped.constraints.consumer_id == "test-consumer"

    async def test_satisfies_llm_request_bus_protocol(self):
        """FakeLLMBus satisfies ILLMRequestBus protocol."""
        bus = FakeLLMBus()
        assert isinstance(bus, ILLMRequestBus)


class TestLLMGatewayAdapterErrorPath:
    """Error mapping tests for LLMGatewayAdapter."""

    async def test_timeout_maps_to_llm_timeout_error(self):
        bus = FakeLLMBus(error=asyncio.TimeoutError())
        adapter = LLMGatewayAdapter(bus)

        with pytest.raises(LLMTimeoutError):
            await adapter.execute(_make_hub_request())

    async def test_generic_error_maps_to_adapter_exception(self):
        bus = FakeLLMBus(error=ConnectionError("connection refused"))
        adapter = LLMGatewayAdapter(bus)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_make_hub_request())
        assert exc_info.value.degraded is True


# ===================================================================
# 3. FabricRetrievalAdapter [F30]
# ===================================================================


class FakeFabricRetrieval:
    """Fake FabricRetrieval for testing."""

    def __init__(
        self,
        capabilities_result: RetrievalResult | None = None,
        prompts_result: RetrievalResult | None = None,
        error: Exception | None = None,
    ):
        self._cap = capabilities_result or RetrievalResult()
        self._prom = prompts_result or RetrievalResult()
        self._error = error

    async def discover_capabilities(self, **kwargs) -> RetrievalResult:
        if self._error:
            raise self._error
        return self._cap

    async def find_relevant_prompts(self, **kwargs) -> RetrievalResult:
        if self._error:
            raise self._error
        return self._prom


class TestFabricRetrievalAdapterHappyPath:
    """Happy-path tests for FabricRetrievalAdapter."""

    async def test_discover_capabilities_returns_result(self):
        result = RetrievalResult(
            capabilities=[ScoredCapability(score=0.9), ScoredCapability(score=0.8)],
            total_matched=2,
        )
        fake = FakeFabricRetrieval(capabilities_result=result)
        adapter = FabricRetrievalAdapter(fake, timeout_ms=5000)

        out = await adapter.discover_capabilities(intent="lights")
        assert out is result
        assert len(out.capabilities) == 2

    async def test_find_relevant_prompts_returns_result(self):
        result = RetrievalResult(
            capabilities=[ScoredCapability(score=0.95)],
            total_matched=1,
        )
        fake = FakeFabricRetrieval(prompts_result=result)
        adapter = FabricRetrievalAdapter(fake, timeout_ms=5000)

        out = await adapter.find_relevant_prompts(intent="greet")
        assert out is result
        assert len(out.capabilities) == 1


class TestFabricRetrievalAdapterDegradedPath:
    """Degraded/error-path tests for FabricRetrievalAdapter."""

    async def test_discover_capabilities_error_returns_empty(self):
        fake = FakeFabricRetrieval(error=RuntimeError("kaboom"))
        adapter = FabricRetrievalAdapter(fake, timeout_ms=5000, max_retries=0)

        out = await adapter.discover_capabilities()
        assert isinstance(out, RetrievalResult)
        assert out.capabilities == []

    async def test_find_relevant_prompts_error_returns_empty(self):
        fake = FakeFabricRetrieval(error=RuntimeError("kaboom"))
        adapter = FabricRetrievalAdapter(fake, timeout_ms=5000, max_retries=0)

        out = await adapter.find_relevant_prompts()
        assert isinstance(out, RetrievalResult)
        assert out.capabilities == []

    async def test_retries_on_failure(self):
        """Adapter retries max_retries times after initial failure."""
        call_count = 0

        class FailThenSucceed:
            async def discover_capabilities(self, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise RuntimeError("temporary failure")
                return RetrievalResult(capabilities=[ScoredCapability(score=0.7)])

            async def find_relevant_prompts(self, **kwargs):
                return RetrievalResult()

        adapter = FabricRetrievalAdapter(FailThenSucceed(), timeout_ms=5000, max_retries=1)
        result = await adapter.discover_capabilities()
        assert len(result.capabilities) == 1
        assert result.capabilities[0].score == 0.7
        assert call_count == 2


# ===================================================================
# 4. SessionStateReadAdapter [F31]
# ===================================================================


class FakeStateReader:
    """Fake ISessionStateReader for testing."""

    def __init__(
        self,
        sections_data: Dict[str, Any] | None = None,
        snapshot: SessionSnapshot | None = None,
        error: Exception | None = None,
    ):
        self._data = sections_data or {}
        self._snapshot = snapshot
        self._error = error
        self.last_session_id: str = ""
        self.last_sections: List[str] = []

    def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]:
        self.last_session_id = session_id
        self.last_sections = names
        if self._error:
            raise self._error
        return {k: v for k, v in self._data.items() if k in names}

    def get_snapshot(self, session_id: str) -> SessionSnapshot:
        self.last_session_id = session_id
        if self._error:
            raise self._error
        if self._snapshot:
            return self._snapshot
        return SessionSnapshot(session_id=session_id, sections=dict(self._data))


class TestSessionStateReadAdapterHappyPath:
    """Happy-path tests for SessionStateReadAdapter."""

    async def test_read_sections_delegates_with_session_id(self):
        data = {
            "affective_now": {"emotion": "happy", "intensity": 0.8},
            "cognitive": {"complexity": "low"},
        }
        reader = FakeStateReader(sections_data=data)
        adapter = SessionStateReadAdapter(reader, session_id="sess-42")

        result = await adapter.read_sections(["affective_now", "cognitive"], trace_id="t-1")

        assert isinstance(result, SessionSnapshot)
        assert result.session_id == "sess-42"
        assert "affective_now" in result.sections
        assert "cognitive" in result.sections
        assert reader.last_session_id == "sess-42"

    async def test_read_sections_missing_section_omitted(self):
        data = {"affective_now": {"emotion": "calm"}}
        reader = FakeStateReader(sections_data=data)
        adapter = SessionStateReadAdapter(reader, session_id="sess-1")

        result = await adapter.read_sections(["affective_now", "missing_section"])
        assert "missing_section" not in result.sections
        assert "affective_now" in result.sections

    async def test_read_sections_returns_snapshot_if_reader_returns_snapshot(self):
        """If the reader returns a SessionSnapshot directly, pass it through."""
        snap = SessionSnapshot(
            session_id="sess-7",
            sections={"beliefs_active": {"key": "val"}},
        )

        class DirectSnapshotReader:
            def read_sections(self, session_id, names):
                return snap

        adapter = SessionStateReadAdapter(DirectSnapshotReader(), session_id="sess-7")
        result = await adapter.read_sections(["beliefs_active"])
        assert result is snap

    async def test_get_snapshot_returns_all_sections(self):
        """get_snapshot delegates to _reader.get_snapshot(session_id)."""
        data = {
            "affective_now": {"emotion": "focused"},
            "cognitive": {"load": "medium"},
            "control": {"safety_band": "GREEN"},
        }
        snap = SessionSnapshot(session_id="sess-snap", sections=data)
        reader = FakeStateReader(snapshot=snap)
        adapter = SessionStateReadAdapter(reader, session_id="sess-snap")

        result = await adapter.get_snapshot(trace_id="t-snap")
        assert result is snap
        assert reader.last_session_id == "sess-snap"

    async def test_get_snapshot_wraps_dict_return(self):
        """If get_snapshot returns a dict, wrap in SessionSnapshot."""

        class DictSnapshotReader:
            def get_snapshot(self, session_id):
                return {"beliefs_active": {"key": "val"}}

            def read_sections(self, session_id, names):
                return {}

        adapter = SessionStateReadAdapter(DictSnapshotReader(), session_id="sess-d")
        result = await adapter.get_snapshot()
        assert isinstance(result, SessionSnapshot)
        assert result.session_id == "sess-d"
        assert "beliefs_active" in result.sections


class TestSessionStateReadAdapterErrorPath:
    """Error-path tests for SessionStateReadAdapter."""

    async def test_reader_error_returns_empty_snapshot(self):
        reader = FakeStateReader(error=RuntimeError("db down"))
        adapter = SessionStateReadAdapter(reader, session_id="sess-x")

        result = await adapter.read_sections(["anything"])
        assert isinstance(result, SessionSnapshot)
        assert result.session_id == "sess-x"
        assert result.sections == {}

    async def test_get_snapshot_error_returns_empty_snapshot(self):
        reader = FakeStateReader(error=RuntimeError("snapshot failed"))
        adapter = SessionStateReadAdapter(reader, session_id="sess-err")

        result = await adapter.get_snapshot(trace_id="t-err")
        assert isinstance(result, SessionSnapshot)
        assert result.session_id == "sess-err"
        assert result.sections == {}


# ===================================================================
# 5. BridgeAdapter [F32]
# ===================================================================


class FakeBridge:
    """Fake Fabric IBridgePort for testing."""

    def __init__(
        self,
        available: bool = True,
        query_result: BridgeCommandResult | None = None,
        command_result: BridgeCommandResult | None = None,
        query_error: Exception | None = None,
        command_error: Exception | None = None,
    ):
        self._available = available
        self._query_result = query_result or BridgeCommandResult.ok()
        self._command_result = command_result or BridgeCommandResult.ok()
        self._query_error = query_error
        self._command_error = command_error
        self.last_query_op: str = ""
        self.last_query_selectors: Dict[str, Any] = {}
        self.last_command_op: str = ""
        self.last_command_payload: Dict[str, Any] = {}

    def is_available(self) -> bool:
        return self._available

    async def query(self, operation, selectors, *, trace_id="", timeout_ms=0):
        self.last_query_op = operation
        self.last_query_selectors = selectors
        if self._query_error:
            raise self._query_error
        return self._query_result

    async def send_command(self, operation, payload, *, trace_id="", timeout_ms=0):
        self.last_command_op = operation
        self.last_command_payload = payload
        if self._command_error:
            raise self._command_error
        return self._command_result


class TestBridgeAdapterHappyPath:
    """Happy-path tests for BridgeAdapter."""

    async def test_recall_returns_populated_response(self):
        result = BridgeCommandResult.ok(
            data={"facts": [{"text": "user likes jazz"}], "scores": [0.95]},
            trace_id="t-1",
        )
        bridge = FakeBridge(query_result=result)
        adapter = BridgeAdapter(bridge)

        resp = await adapter.recall("what music?", trace_id="t-1")
        assert resp.facts == [{"text": "user likes jazz"}]
        assert resp.scores == [0.95]
        assert bridge.last_query_op == "memory.recall"

    async def test_recall_passes_selectors(self):
        bridge = FakeBridge()
        adapter = BridgeAdapter(bridge)

        await adapter.recall("query", selectors=["preferences", "outcomes"], trace_id="t-2")
        assert bridge.last_query_selectors["selectors"] == ["preferences", "outcomes"]

    async def test_persist_plan_sends_command(self):
        bridge = FakeBridge()
        adapter = BridgeAdapter(bridge)
        plan = _make_committed_plan(plan_id="p-1", request_id="r-1", intent="do stuff")

        await adapter.persist_plan(plan, trace_id="t-3")
        assert bridge.last_command_op == "memory.store"

    def test_is_available_when_online(self):
        bridge = FakeBridge(available=True)
        adapter = BridgeAdapter(bridge)
        assert adapter.is_available() is True

    def test_is_available_when_offline(self):
        bridge = FakeBridge(available=False)
        adapter = BridgeAdapter(bridge)
        assert adapter.is_available() is False


class TestBridgeAdapterOfflinePath:
    """Offline/error-path tests for BridgeAdapter."""

    async def test_recall_offline_returns_empty(self):
        bridge = FakeBridge(available=False)
        adapter = BridgeAdapter(bridge)

        resp = await adapter.recall("what?", trace_id="t-off")
        assert resp.facts == []
        assert resp.scores == []
        assert resp.trace_id == "t-off"

    async def test_persist_plan_offline_drops_silently(self):
        bridge = FakeBridge(available=False)
        adapter = BridgeAdapter(bridge)
        plan = _make_committed_plan(plan_id="p-2", request_id="r-2", intent="offline")

        # Should not raise
        await adapter.persist_plan(plan, trace_id="t-off")
        assert bridge.last_command_op == ""  # never called

    async def test_recall_query_failure_returns_empty(self):
        result = BridgeCommandResult.fail("internal", "db error")
        bridge = FakeBridge(query_result=result)
        adapter = BridgeAdapter(bridge)

        resp = await adapter.recall("query", trace_id="t-fail")
        assert resp.facts == []

    async def test_recall_exception_returns_empty(self):
        bridge = FakeBridge(query_error=ConnectionError("timeout"))
        adapter = BridgeAdapter(bridge)

        resp = await adapter.recall("query", trace_id="t-exc")
        assert resp.facts == []
        assert resp.trace_id == "t-exc"

    async def test_persist_plan_exception_drops_silently(self):
        bridge = FakeBridge(command_error=RuntimeError("boom"))
        adapter = BridgeAdapter(bridge)
        plan = _make_committed_plan(plan_id="p-3", request_id="r-3", intent="boom")

        # Should not raise (fire-and-forget)
        await adapter.persist_plan(plan, trace_id="t-boom")


# ===================================================================
# 6. DeltaBusAdapter [F33]
# ===================================================================


class FakeDeltaBus:
    """Fake IDeltaBusPort for testing."""

    def __init__(self, error: Exception | None = None):
        self._error = error
        self.emitted: List[tuple] = []

    def emit_delta(self, agent_id, delta_type, section, data):
        if self._error:
            raise self._error
        self.emitted.append((agent_id, delta_type, section, data))


class TestDeltaBusAdapterHappyPath:
    """Happy-path tests for DeltaBusAdapter."""

    def test_emit_delegates_to_bus(self):
        bus = FakeDeltaBus()
        adapter = DeltaBusAdapter(bus, agent_id="planner")
        delta = _make_delta_payload()

        adapter.emit(delta)

        assert len(bus.emitted) == 1
        agent_id, delta_type, section, data = bus.emitted[0]
        assert agent_id == "planner"
        assert delta_type == "stage_transition"
        assert section == "pipeline"
        assert data == {"stage": "SKETCH"}

    def test_emit_uses_stamped_agent_id(self):
        """Agent ID comes from adapter construction, not delta payload."""
        bus = FakeDeltaBus()
        adapter = DeltaBusAdapter(bus, agent_id="custom-agent")
        delta = _make_delta_payload()

        adapter.emit(delta)
        assert bus.emitted[0][0] == "custom-agent"

    def test_emit_is_synchronous(self):
        """emit() is synchronous (not async), matches IDeltaEmitPort contract."""
        bus = FakeDeltaBus()
        adapter = DeltaBusAdapter(bus)
        delta = _make_delta_payload()

        # Should work without await
        result = adapter.emit(delta)
        assert result is None


class TestDeltaBusAdapterFireAndForget:
    """Fire-and-forget tests for DeltaBusAdapter."""

    def test_emit_swallows_bus_exception(self):
        bus = FakeDeltaBus(error=RuntimeError("bus is down"))
        adapter = DeltaBusAdapter(bus)
        delta = _make_delta_payload()

        # Must not raise
        adapter.emit(delta)

    def test_emit_swallows_any_exception_type(self):
        bus = FakeDeltaBus(error=OSError("permission denied"))
        adapter = DeltaBusAdapter(bus)
        delta = _make_delta_payload()

        # Must not raise
        adapter.emit(delta)


# ===================================================================
# 7. EventBusAdapter [F34]
# ===================================================================


class FakeEventBus:
    """Fake Fabric IEventPort for testing."""

    def __init__(self, error_on_emit: Exception | None = None):
        self._error_on_emit = error_on_emit
        self.emitted: List[tuple] = []
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._next_id: int = 0

    def emit(self, topic: str, payload: Any) -> None:
        if self._error_on_emit:
            raise self._error_on_emit
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Callable) -> SubscriptionHandle:
        self._next_id += 1
        handle = SubscriptionHandle(
            subscription_id=f"sub-{self._next_id}",
            topic=topic,
        )
        self._subscriptions.setdefault(topic, []).append(handler)
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return True


class TestEventBusAdapterHappyPath:
    """Happy-path tests for EventBusAdapter."""

    def test_emit_delegates_to_bus(self):
        bus = FakeEventBus()
        adapter = EventBusAdapter(bus)

        adapter.emit("k1.planner.plan.ready.v1", {"plan_id": "p-1"})
        assert len(bus.emitted) == 1
        assert bus.emitted[0] == ("k1.planner.plan.ready.v1", {"plan_id": "p-1"})

    def test_subscribe_returns_handle(self):
        bus = FakeEventBus()
        adapter = EventBusAdapter(bus)

        def handler(topic, payload):
            pass

        handle = adapter.subscribe("k1.hil.clarification_response.v1", handler)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "k1.hil.clarification_response.v1"

    def test_unsubscribe_returns_bool(self):
        bus = FakeEventBus()
        adapter = EventBusAdapter(bus)

        handle = adapter.subscribe("topic", lambda t, p: None)
        result = adapter.unsubscribe(handle)
        assert result is True


class TestEventBusAdapterFireAndForget:
    """Fire-and-forget tests for EventBusAdapter."""

    def test_emit_swallows_bus_exception(self):
        bus = FakeEventBus(error_on_emit=RuntimeError("bus down"))
        adapter = EventBusAdapter(bus)

        # Must not raise
        adapter.emit("k1.planner.plan.failed.v1", {"error": "oops"})


# ===================================================================
# 8. Cross-cutting: __init__.py re-exports
# ===================================================================


class TestAdapterInitReExports:
    """Verify __init__.py re-exports all 7 adapters."""

    def test_all_adapters_importable_from_package(self):
        from k1.planner.adapters import (
            BridgeAdapter,
            DeltaBusAdapter,
            EventBusAdapter,
            FabricRetrievalAdapter,
            LLMGatewayAdapter,
            MailboxAdapter,
            SessionStateReadAdapter,
        )

        assert BridgeAdapter is not None
        assert DeltaBusAdapter is not None
        assert EventBusAdapter is not None
        assert FabricRetrievalAdapter is not None
        assert LLMGatewayAdapter is not None
        assert MailboxAdapter is not None
        assert SessionStateReadAdapter is not None

    def test_all_in_module_all(self):
        import k1.planner.adapters as adapters_mod

        expected = {
            "BridgeAdapter",
            "DeltaBusAdapter",
            "EventBusAdapter",
            "FabricRetrievalAdapter",
            "LLMGatewayAdapter",
            "MailboxAdapter",
            "SessionStateReadAdapter",
        }
        assert expected.issubset(set(adapters_mod.__all__))

    def test_adapter_count_is_eight(self):
        import k1.planner.adapters as adapters_mod

        # Eighth adapter (4.2.2 / P03): FabricRegistryAdapter exposes
        # deterministic O(1) capability lookup distinct from the
        # semantic-search FabricRetrievalAdapter.
        assert len(adapters_mod.__all__) == 8


# ===================================================================
# 9. Protocol conformance (structural typing validation)
# ===================================================================


class TestProtocolConformance:
    """Verify each adapter implements its port Protocol structurally."""

    def test_mailbox_adapter_has_mailbox_port_methods(self):
        adapter = MailboxAdapter()
        assert callable(getattr(adapter, "enqueue", None))
        assert callable(getattr(adapter, "dequeue", None))
        assert callable(getattr(adapter, "send_cancel", None))
        assert callable(getattr(adapter, "drain", None))
        assert callable(getattr(adapter, "micro_replan", None))

    def test_llm_gateway_has_execute(self):
        bus = FakeLLMBus()
        adapter = LLMGatewayAdapter(bus)
        assert callable(getattr(adapter, "execute", None))

    def test_fabric_retrieval_has_discovery_methods(self):
        adapter = FabricRetrievalAdapter(FakeFabricRetrieval())
        assert callable(getattr(adapter, "discover_capabilities", None))
        assert callable(getattr(adapter, "find_relevant_prompts", None))

    def test_session_state_read_has_read_sections_and_get_snapshot(self):
        adapter = SessionStateReadAdapter(FakeStateReader(), session_id="s1")
        assert callable(getattr(adapter, "read_sections", None))
        assert callable(getattr(adapter, "get_snapshot", None))

    def test_bridge_has_recall_persist_and_is_available(self):
        adapter = BridgeAdapter(FakeBridge())
        assert callable(getattr(adapter, "recall", None))
        assert callable(getattr(adapter, "persist_plan", None))
        assert callable(getattr(adapter, "is_available", None))

    def test_delta_bus_has_emit(self):
        adapter = DeltaBusAdapter(FakeDeltaBus())
        assert callable(getattr(adapter, "emit", None))

    def test_event_bus_has_emit_subscribe_unsubscribe(self):
        adapter = EventBusAdapter(FakeEventBus())
        assert callable(getattr(adapter, "emit", None))
        assert callable(getattr(adapter, "subscribe", None))
        assert callable(getattr(adapter, "unsubscribe", None))


# ===================================================================
# 10. Adapter isolation: each wraps exactly ONE port (SS16.3)
# ===================================================================


class TestSinglePortWrapping:
    """Verify each adapter wraps exactly one infrastructure dependency."""

    def test_mailbox_adapter_has_single_slot_queue(self):
        adapter = MailboxAdapter()
        # Internal state: queue, cancel_set, plan_lock, etc. -- but all
        # serve the single IMailboxPort responsibility.
        assert hasattr(adapter, "_queue")

    def test_bridge_adapter_has_single_bridge_slot(self):
        adapter = BridgeAdapter(FakeBridge())
        assert hasattr(adapter, "_bridge")

    def test_delta_bus_adapter_has_single_bus_slot(self):
        adapter = DeltaBusAdapter(FakeDeltaBus())
        assert hasattr(adapter, "_bus")

    def test_event_bus_adapter_has_single_bus_slot(self):
        adapter = EventBusAdapter(FakeEventBus())
        assert hasattr(adapter, "_bus")

    def test_session_state_adapter_has_reader_and_session_id(self):
        adapter = SessionStateReadAdapter(FakeStateReader(), session_id="s")
        assert hasattr(adapter, "_reader")
        assert hasattr(adapter, "_session_id")

    def test_fabric_retrieval_adapter_has_single_fabric_slot(self):
        adapter = FabricRetrievalAdapter(FakeFabricRetrieval())
        assert hasattr(adapter, "_fabric")

    def test_llm_gateway_has_single_bus_slot(self):
        adapter = LLMGatewayAdapter(FakeLLMBus())
        assert hasattr(adapter, "_bus")
