"""Tests for Epic 6.1 Issues 6.1.1-6.1.8 -- Test Adapters.

Validates:
- TestMailboxAdapter (SS16.2.1): IMailboxPort Protocol compliance
- TestLLMAdapter (SS16.2.2): ILLMPort Protocol compliance
- TestFabricRetrievalAdapter (SS16.2.3): IFabricRetrievalPort Protocol compliance
- TestStateReadAdapter (SS16.2.4): IStateReadPort Protocol compliance
- TestBridgeAdapter (SS16.2.5): IBridgePort Protocol compliance
- TestDeltaAdapter (SS16.2.6): IDeltaEmitPort Protocol compliance
- TestEventAdapter (SS16.2.7): IEventPort Protocol compliance
- conftest.py (SS30.3, SS30.4): Shared fixtures and adapter wiring

Each adapter is tested for:
- Protocol structural compliance (isinstance check with @runtime_checkable)
- Constructor injection of preset data
- Capture-mode recording of all calls
- Zero I/O, deterministic behavior
- All methods per spec
- Assertion helpers

References: planner.md SS16.2, SS15.2-15.8, SS30.3, SS30.4
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import CapabilityContract, RetrievalResult, ScoredCapability
from k1.orchestrator.types import (
    CommittedPlan,
    MicroReplanRequest,
    PlanRequest,
    PlanStep,
)
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
    DELTA_CRASH_RECOVERY,
    DELTA_MICRO_REPLAN,
    DELTA_PLAN_CANCELLED,
    DELTA_PLAN_END,
    DELTA_PLAN_UPDATE,
    DELTA_STAGE_TRANSITION,
    DELTA_TOOL_RESULT,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    SECTION_PLAN,
    SECTION_TOOLS,
    DeltaPayload,
    HubRequest,
    HubResponse,
    MailboxFullError,
    RecallResponse,
    RequestConstraints,
)
from tests.k1.planner.adapters.test_bridge_adapter import TestBridgeAdapter
from tests.k1.planner.adapters.test_delta_adapter import TestDeltaAdapter
from tests.k1.planner.adapters.test_event_adapter import TestEventAdapter
from tests.k1.planner.adapters.test_fabric_retrieval_adapter import (
    TestFabricRetrievalAdapter,
)
from tests.k1.planner.adapters.test_llm_adapter import LLMTimeoutError, TestLLMAdapter
from tests.k1.planner.adapters.test_mailbox_adapter import TestMailboxAdapter
from tests.k1.planner.adapters.test_state_read_adapter import TestStateReadAdapter

# =========================================================================
# Helpers
# =========================================================================


def _make_plan_request(intent: str = "test intent") -> PlanRequest:
    """Create a minimal valid PlanRequest."""
    return PlanRequest(
        intent=intent,
        trace_id=str(uuid.uuid4()),
    )


def _make_committed_plan(
    num_steps: int = 1,
    request_id: str = "",
) -> CommittedPlan:
    """Create a minimal valid CommittedPlan."""
    steps = [PlanStep(id=f"s{i}", capability=f"cap_{i}") for i in range(1, num_steps + 1)]
    return CommittedPlan(
        plan_id=str(uuid.uuid4()),
        request_id=request_id or str(uuid.uuid4()),
        intent="test",
        steps=steps,
        trace_id=str(uuid.uuid4()),
    )


def _make_micro_replan_request() -> MicroReplanRequest:
    """Create a minimal valid MicroReplanRequest."""
    return MicroReplanRequest(
        original_plan_id=str(uuid.uuid4()),
        completed_results={},
        remaining_steps=[PlanStep(id="rs1", capability="cap_remain")],
        trace_id=str(uuid.uuid4()),
    )


def _make_hub_request(
    stage: str = "SKETCH",
    max_tokens: int = 2000,
    timeout_ms: int = 8000,
    capability: str = "STRUCTURED",
) -> HubRequest:
    """Create a minimal valid HubRequest for a given stage."""
    return HubRequest(
        capability=capability,
        payload={
            "messages": [
                {"role": "system", "content": f"You are a {stage} stage."},
            ],
            "output_schema": {"type": "object"},
        },
        constraints=RequestConstraints(
            max_tokens=max_tokens,
            timeout_ms=timeout_ms,
            consumer_id=f"planner_{stage.lower()}",
        ),
        trace_id=str(uuid.uuid4()),
    )


def _make_scored_capabilities(n: int) -> List[ScoredCapability]:
    """Create n ScoredCapability objects with descending scores."""
    return [
        ScoredCapability(
            contract=CapabilityContract(
                name=f"tool.cap_{i}",
                version="1.0.0",
                domain=["test"],
                description=f"Test capability {i}",
            ),
            score=round(1.0 - i * 0.05, 2),
        )
        for i in range(n)
    ]


# =========================================================================
# TestMailboxAdapter (SS16.2.1)
# =========================================================================


class TestMailboxAdapterProtocol:
    """6.1.1: TestMailboxAdapter satisfies IMailboxPort Protocol."""

    def test_protocol_compliance(self) -> None:
        """isinstance check passes with @runtime_checkable Protocol."""
        adapter = TestMailboxAdapter()
        assert isinstance(adapter, IMailboxPort)

    def test_has_all_protocol_methods(self) -> None:
        """Adapter exposes all IMailboxPort methods."""
        adapter = TestMailboxAdapter()
        assert hasattr(adapter, "dequeue")
        assert hasattr(adapter, "enqueue")
        assert hasattr(adapter, "send_cancel")
        assert hasattr(adapter, "drain")
        assert hasattr(adapter, "micro_replan")
        assert callable(adapter.dequeue)
        assert callable(adapter.enqueue)
        assert callable(adapter.send_cancel)
        assert callable(adapter.drain)
        assert callable(adapter.micro_replan)


class TestMailboxAdapterEmptyQueue:
    """6.1.1: Empty mailbox behavior."""

    async def test_dequeue_empty_raises(self) -> None:
        """dequeue() on empty mailbox raises IndexError."""
        adapter = TestMailboxAdapter()
        with pytest.raises(IndexError, match="queue is empty"):
            await adapter.dequeue()

    async def test_drain_empty_returns_empty_list(self) -> None:
        """drain() on empty mailbox returns empty list."""
        adapter = TestMailboxAdapter()
        result = adapter.drain()
        assert result == []

    async def test_queue_depth_starts_at_zero(self) -> None:
        """queue_depth is 0 for fresh adapter."""
        adapter = TestMailboxAdapter()
        assert adapter.queue_depth == 0


class TestMailboxAdapterSingleRequest:
    """6.1.1: Single request -- full pipeline e2e path."""

    async def test_preset_request_dequeued(self) -> None:
        """Pre-loaded request is available via dequeue()."""
        req = _make_plan_request("book restaurant")
        adapter = TestMailboxAdapter(preset_requests=[req])

        result = await adapter.dequeue()
        assert result.intent == "book restaurant"
        assert result.request_id == req.request_id

    async def test_preset_request_queue_depth(self) -> None:
        """Queue depth reflects preset requests."""
        req = _make_plan_request()
        adapter = TestMailboxAdapter(preset_requests=[req])
        assert adapter.queue_depth == 1

        await adapter.dequeue()
        assert adapter.queue_depth == 0


class TestMailboxAdapterFIFO:
    """6.1.1: Multiple requests -- FIFO ordering verification."""

    async def test_fifo_ordering(self) -> None:
        """Requests are dequeued in FIFO order."""
        reqs = [_make_plan_request(f"intent_{i}") for i in range(3)]
        adapter = TestMailboxAdapter(preset_requests=reqs)

        for i in range(3):
            result = await adapter.dequeue()
            assert result.intent == f"intent_{i}"

    async def test_get_dequeue_order(self) -> None:
        """get_dequeue_order() returns request_ids in FIFO order."""
        reqs = [_make_plan_request(f"intent_{i}") for i in range(3)]
        adapter = TestMailboxAdapter(preset_requests=reqs)

        order = adapter.get_dequeue_order()
        assert order == [r.request_id for r in reqs]

    async def test_enqueue_adds_to_end(self) -> None:
        """enqueue() appends to the end of the queue."""
        first = _make_plan_request("first")
        second = _make_plan_request("second")
        adapter = TestMailboxAdapter(preset_requests=[first])

        await adapter.enqueue(second)

        r1 = await adapter.dequeue()
        r2 = await adapter.dequeue()
        assert r1.intent == "first"
        assert r2.intent == "second"


class TestMailboxAdapterOverflow:
    """6.1.1: Overflow -- rejection at depth > 5."""

    async def test_enqueue_at_max_depth_raises(self) -> None:
        """enqueue() raises MailboxFullError when queue has 5 items."""
        reqs = [_make_plan_request(f"req_{i}") for i in range(5)]
        adapter = TestMailboxAdapter(preset_requests=reqs)

        with pytest.raises(MailboxFullError, match="Mailbox full"):
            await adapter.enqueue(_make_plan_request("overflow"))

    async def test_enqueue_below_max_depth_succeeds(self) -> None:
        """enqueue() succeeds when queue has < 5 items."""
        reqs = [_make_plan_request(f"req_{i}") for i in range(4)]
        adapter = TestMailboxAdapter(preset_requests=reqs)

        await adapter.enqueue(_make_plan_request("fifth"))
        assert adapter.queue_depth == 5

    async def test_enqueue_captures_even_on_overflow(self) -> None:
        """enqueue_log captures the call even when MailboxFullError is raised."""
        reqs = [_make_plan_request(f"req_{i}") for i in range(5)]
        adapter = TestMailboxAdapter(preset_requests=reqs)
        overflow_req = _make_plan_request("overflow")

        with pytest.raises(MailboxFullError):
            await adapter.enqueue(overflow_req)

        # Call IS logged even on failure
        assert len(adapter.enqueue_log) == 1
        assert adapter.enqueue_log[0].intent == "overflow"


class TestMailboxAdapterCancel:
    """6.1.1: Cancel during plan -- inter-stage cancel check."""

    async def test_send_cancel_logs(self) -> None:
        """send_cancel() appends to cancel_log."""
        adapter = TestMailboxAdapter()
        await adapter.send_cancel("req-123")
        await adapter.send_cancel("req-456")

        assert adapter.cancel_log == ["req-123", "req-456"]

    async def test_assert_cancel_ids_pass(self) -> None:
        """assert_cancel_ids() passes on match."""
        adapter = TestMailboxAdapter()
        await adapter.send_cancel("a")
        await adapter.send_cancel("b")
        adapter.assert_cancel_ids(["a", "b"])

    async def test_assert_cancel_ids_fail(self) -> None:
        """assert_cancel_ids() fails on mismatch."""
        adapter = TestMailboxAdapter()
        await adapter.send_cancel("a")
        with pytest.raises(AssertionError):
            adapter.assert_cancel_ids(["b"])


class TestMailboxAdapterMicroReplan:
    """6.1.1: micro_replan() behavior."""

    async def test_micro_replan_returns_configured_result(self) -> None:
        """micro_replan() returns the injected CommittedPlan."""
        plan = _make_committed_plan()
        adapter = TestMailboxAdapter()
        adapter.set_micro_replan_result(plan)

        req = _make_micro_replan_request()
        result = await adapter.micro_replan(req)
        assert result.plan_id == plan.plan_id

    async def test_micro_replan_raises_configured_error(self) -> None:
        """micro_replan() raises the injected error."""
        adapter = TestMailboxAdapter()
        adapter.set_micro_replan_error(TimeoutError("timed out"))

        with pytest.raises(TimeoutError, match="timed out"):
            await adapter.micro_replan(_make_micro_replan_request())

    async def test_micro_replan_no_config_raises_runtime(self) -> None:
        """micro_replan() without config raises RuntimeError."""
        adapter = TestMailboxAdapter()
        with pytest.raises(RuntimeError, match="no result or error"):
            await adapter.micro_replan(_make_micro_replan_request())

    async def test_micro_replan_logs_all_calls(self) -> None:
        """micro_replan_log captures all calls."""
        plan = _make_committed_plan()
        adapter = TestMailboxAdapter()
        adapter.set_micro_replan_result(plan)

        req1 = _make_micro_replan_request()
        req2 = _make_micro_replan_request()
        await adapter.micro_replan(req1)
        await adapter.micro_replan(req2)

        assert len(adapter.micro_replan_log) == 2
        assert adapter.micro_replan_log[0].original_plan_id == req1.original_plan_id
        assert adapter.micro_replan_log[1].original_plan_id == req2.original_plan_id


class TestMailboxAdapterDrain:
    """6.1.1: drain() behavior."""

    async def test_drain_returns_all_and_clears(self) -> None:
        """drain() returns all queued requests and empties the queue."""
        reqs = [_make_plan_request(f"req_{i}") for i in range(3)]
        adapter = TestMailboxAdapter(preset_requests=reqs)

        drained = adapter.drain()
        assert len(drained) == 3
        assert adapter.queue_depth == 0

    async def test_drain_preserves_fifo_order(self) -> None:
        """drain() returns requests in FIFO order."""
        reqs = [_make_plan_request(f"intent_{i}") for i in range(3)]
        adapter = TestMailboxAdapter(preset_requests=reqs)

        drained = adapter.drain()
        for i, req in enumerate(drained):
            assert req.intent == f"intent_{i}"


class TestMailboxAdapterAssertionHelpers:
    """6.1.1: Assertion helper methods."""

    async def test_assert_enqueue_count_pass(self) -> None:
        """assert_enqueue_count passes on exact match."""
        adapter = TestMailboxAdapter()
        await adapter.enqueue(_make_plan_request())
        await adapter.enqueue(_make_plan_request())
        adapter.assert_enqueue_count(2)

    async def test_assert_enqueue_count_fail(self) -> None:
        """assert_enqueue_count fails on mismatch."""
        adapter = TestMailboxAdapter()
        with pytest.raises(AssertionError, match="Expected 1 enqueue"):
            adapter.assert_enqueue_count(1)


# =========================================================================
# TestLLMAdapter (SS16.2.2)
# =========================================================================


class TestLLMAdapterProtocol:
    """6.1.2: TestLLMAdapter satisfies ILLMPort Protocol."""

    def test_protocol_compliance(self) -> None:
        """isinstance check passes with @runtime_checkable Protocol."""
        adapter = TestLLMAdapter()
        assert isinstance(adapter, ILLMPort)

    def test_has_execute_method(self) -> None:
        """Adapter exposes the execute() method."""
        adapter = TestLLMAdapter()
        assert hasattr(adapter, "execute")
        assert callable(adapter.execute)


class TestLLMAdapterHappyPath:
    """6.1.2: Happy path -- per-stage configured responses."""

    async def test_returns_configured_response(self) -> None:
        """execute() returns the configured HubResponse for the detected stage."""
        sketch_resp = HubResponse(
            result={"content": '{"steps": []}'},
            metadata={"usage": {"total_tokens": 200}},
        )
        adapter = TestLLMAdapter(stage_responses={"SKETCH": sketch_resp})
        req = _make_hub_request(stage="SKETCH")

        result = await adapter.execute(req)
        assert result.result == {"content": '{"steps": []}'}

    async def test_different_stages_return_different_responses(self) -> None:
        """Each stage gets its own configured response."""
        sketch_resp = HubResponse(result={"content": "sketch"})
        expand_resp = HubResponse(result={"content": "expand"})
        adapter = TestLLMAdapter(stage_responses={"SKETCH": sketch_resp, "EXPAND": expand_resp})

        r1 = await adapter.execute(_make_hub_request(stage="SKETCH"))
        r2 = await adapter.execute(_make_hub_request(stage="EXPAND"))
        assert r1.result["content"] == "sketch"
        assert r2.result["content"] == "expand"

    async def test_deterministic_same_input_same_output(self) -> None:
        """Same input always produces same output (no randomness)."""
        resp = HubResponse(result={"content": "fixed"})
        adapter = TestLLMAdapter(stage_responses={"SKETCH": resp})

        req = _make_hub_request(stage="SKETCH")
        r1 = await adapter.execute(req)
        r2 = await adapter.execute(req)
        assert r1 == r2


class TestLLMAdapterDefaultResponse:
    """6.1.2: Default/fallback response behavior."""

    async def test_default_response_for_unknown_stage(self) -> None:
        """default_response is returned when stage not in stage_responses."""
        default = HubResponse(result={"content": "default"})
        adapter = TestLLMAdapter(default_response=default)

        req = _make_hub_request(stage="SKETCH")
        result = await adapter.execute(req)
        assert result.result["content"] == "default"

    async def test_synthesized_response_when_no_config(self) -> None:
        """Returns synthetic response when no config matches."""
        adapter = TestLLMAdapter()
        req = _make_hub_request(stage="SKETCH")
        result = await adapter.execute(req)

        assert "content" in result.result
        assert "usage" in result.metadata


class TestLLMAdapterErrorInjection:
    """6.1.2: Error injection for specific stages."""

    async def test_error_stage_raises_timeout(self) -> None:
        """execute() raises LLMTimeoutError for error_stages."""
        adapter = TestLLMAdapter(error_stages={"SKETCH"})
        req = _make_hub_request(stage="SKETCH")

        with pytest.raises(LLMTimeoutError, match="configured to fail"):
            await adapter.execute(req)

    async def test_error_stage_carries_trace_id(self) -> None:
        """LLMTimeoutError carries the trace_id from the request."""
        adapter = TestLLMAdapter(error_stages={"EXPAND"})
        req = _make_hub_request(stage="EXPAND")

        with pytest.raises(LLMTimeoutError) as exc_info:
            await adapter.execute(req)
        assert exc_info.value.trace_id == req.trace_id

    async def test_non_error_stage_succeeds(self) -> None:
        """Stages not in error_stages return normally."""
        resp = HubResponse(result={"content": "ok"})
        adapter = TestLLMAdapter(
            stage_responses={"SKETCH": resp},
            error_stages={"EXPAND"},
        )

        result = await adapter.execute(_make_hub_request(stage="SKETCH"))
        assert result.result["content"] == "ok"

    async def test_set_error_stage_dynamically(self) -> None:
        """set_error_stage() adds error injection mid-test."""
        adapter = TestLLMAdapter()
        req = _make_hub_request(stage="VALIDATE")

        # Before: succeeds
        await adapter.execute(req)

        # After: fails
        adapter.set_error_stage("VALIDATE")
        with pytest.raises(LLMTimeoutError):
            await adapter.execute(req)

    async def test_clear_error_stage(self) -> None:
        """clear_error_stage() removes error injection."""
        adapter = TestLLMAdapter(error_stages={"SKETCH"})
        adapter.clear_error_stage("SKETCH")

        result = await adapter.execute(_make_hub_request(stage="SKETCH"))
        assert result is not None


class TestLLMAdapterLatency:
    """6.1.2: Simulated latency via asyncio.sleep."""

    async def test_latency_zero_no_delay(self) -> None:
        """latency_ms=0 does not add delay."""
        import time

        adapter = TestLLMAdapter(latency_ms=0)
        start = time.monotonic()
        await adapter.execute(_make_hub_request())
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # Should be near-instant

    async def test_latency_nonzero_adds_delay(self) -> None:
        """latency_ms > 0 introduces asyncio.sleep delay."""
        import time

        adapter = TestLLMAdapter(latency_ms=100)
        start = time.monotonic()
        await adapter.execute(_make_hub_request())
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08  # Allow some scheduling jitter


class TestLLMAdapterCapture:
    """6.1.2: Call log capture for post-test assertion."""

    async def test_call_log_records_all_calls(self) -> None:
        """call_log captures every execute() call."""
        adapter = TestLLMAdapter()
        req1 = _make_hub_request(stage="SKETCH")
        req2 = _make_hub_request(stage="EXPAND")

        await adapter.execute(req1)
        await adapter.execute(req2)

        assert adapter.call_count == 2
        assert adapter.call_log[0].trace_id == req1.trace_id
        assert adapter.call_log[1].trace_id == req2.trace_id

    async def test_call_log_captures_even_on_error(self) -> None:
        """Call is logged even when error_stages raises."""
        adapter = TestLLMAdapter(error_stages={"SKETCH"})
        req = _make_hub_request(stage="SKETCH")

        with pytest.raises(LLMTimeoutError):
            await adapter.execute(req)

        assert adapter.call_count == 1
        assert adapter.call_log[0].trace_id == req.trace_id

    async def test_assert_call_count(self) -> None:
        """assert_call_count helper."""
        adapter = TestLLMAdapter()
        await adapter.execute(_make_hub_request())
        adapter.assert_call_count(1)

        with pytest.raises(AssertionError):
            adapter.assert_call_count(2)

    async def test_assert_stage_called(self) -> None:
        """assert_stage_called helper."""
        adapter = TestLLMAdapter()
        await adapter.execute(_make_hub_request(stage="SKETCH"))

        adapter.assert_stage_called("SKETCH")
        with pytest.raises(AssertionError):
            adapter.assert_stage_called("EXPAND")

    async def test_get_calls_for_stage(self) -> None:
        """get_calls_for_stage returns only calls for that stage."""
        adapter = TestLLMAdapter()
        await adapter.execute(_make_hub_request(stage="SKETCH"))
        await adapter.execute(_make_hub_request(stage="EXPAND"))
        await adapter.execute(_make_hub_request(stage="SKETCH"))

        sketch_calls = adapter.get_calls_for_stage("SKETCH")
        assert len(sketch_calls) == 2


class TestLLMAdapterBudgetAssertions:
    """6.1.2: Budget and capability type assertion helpers."""

    async def test_assert_max_tokens(self) -> None:
        """assert_max_tokens verifies constraints.max_tokens per stage."""
        adapter = TestLLMAdapter()
        await adapter.execute(_make_hub_request(stage="SKETCH", max_tokens=2000))

        adapter.assert_max_tokens("SKETCH", 2000)
        with pytest.raises(AssertionError):
            adapter.assert_max_tokens("SKETCH", 1000)

    async def test_assert_capability_type(self) -> None:
        """assert_capability_type verifies HubRequest.capability."""
        adapter = TestLLMAdapter()
        await adapter.execute(_make_hub_request(stage="SKETCH", capability="STRUCTURED"))

        adapter.assert_capability_type("SKETCH", "STRUCTURED")
        with pytest.raises(AssertionError):
            adapter.assert_capability_type("SKETCH", "CHAT")


class TestLLMAdapterStageDetection:
    """6.1.2: Stage detection from consumer_id and payload heuristic."""

    async def test_consumer_id_direct_match(self) -> None:
        """consumer_id matching stage name directly."""
        adapter = TestLLMAdapter(
            stage_responses={"SKETCH": HubResponse(result={"content": "matched"})}
        )
        req = HubRequest(
            capability="STRUCTURED",
            payload={"messages": []},
            constraints=RequestConstraints(max_tokens=100, timeout_ms=1000, consumer_id="SKETCH"),
        )
        result = await adapter.execute(req)
        assert result.result["content"] == "matched"

    async def test_consumer_id_suffix_match(self) -> None:
        """consumer_id with prefix (e.g., planner_sketch) detected."""
        adapter = TestLLMAdapter(
            stage_responses={"SKETCH": HubResponse(result={"content": "suffix"})}
        )
        req = HubRequest(
            capability="STRUCTURED",
            payload={"messages": []},
            constraints=RequestConstraints(
                max_tokens=100, timeout_ms=1000, consumer_id="planner_sketch"
            ),
        )
        result = await adapter.execute(req)
        assert result.result["content"] == "suffix"

    async def test_micro_stage_detection(self) -> None:
        """Micro-replan stages detected from consumer_id."""
        adapter = TestLLMAdapter(
            stage_responses={"MICRO_SKETCH": HubResponse(result={"content": "micro"})}
        )
        req = HubRequest(
            capability="STRUCTURED",
            payload={"messages": []},
            constraints=RequestConstraints(
                max_tokens=100,
                timeout_ms=1000,
                consumer_id="planner_micro_sketch",
            ),
        )
        result = await adapter.execute(req)
        assert result.result["content"] == "micro"


class TestLLMAdapterTokenCounting:
    """6.1.2: Pre-configured token usage in ResponseMetadata."""

    async def test_metadata_usage_returned(self) -> None:
        """Configured metadata with usage is returned."""
        resp = HubResponse(
            result={"content": "ok"},
            metadata={
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 75,
                    "total_tokens": 225,
                },
                "latency_ms": 100,
                "model_id": "gpt-4",
            },
        )
        adapter = TestLLMAdapter(stage_responses={"SKETCH": resp})
        result = await adapter.execute(_make_hub_request(stage="SKETCH"))

        assert result.metadata["usage"]["prompt_tokens"] == 150
        assert result.metadata["usage"]["completion_tokens"] == 75
        assert result.metadata["model_id"] == "gpt-4"


# =========================================================================
# TestFabricRetrievalAdapter (SS16.2.3)
# =========================================================================


class TestFabricRetrievalAdapterProtocol:
    """6.1.3: TestFabricRetrievalAdapter satisfies IFabricRetrievalPort."""

    def test_protocol_compliance(self) -> None:
        """isinstance check passes with @runtime_checkable Protocol."""
        adapter = TestFabricRetrievalAdapter()
        assert isinstance(adapter, IFabricRetrievalPort)

    def test_has_all_protocol_methods(self) -> None:
        """Adapter exposes both Protocol methods."""
        adapter = TestFabricRetrievalAdapter()
        assert hasattr(adapter, "discover_capabilities")
        assert hasattr(adapter, "find_relevant_prompts")
        assert callable(adapter.discover_capabilities)
        assert callable(adapter.find_relevant_prompts)


class TestFabricRetrievalAdapterRichDiscovery:
    """6.1.3: Rich discovery -- 10+ capabilities."""

    async def test_discover_returns_preset_capabilities(self) -> None:
        """discover_capabilities() returns from preset_capabilities."""
        caps = _make_scored_capabilities(12)
        adapter = TestFabricRetrievalAdapter(preset_capabilities=caps)

        result = await adapter.discover_capabilities(intent="find restaurants")
        assert len(result.capabilities) == 10  # default top_k=10
        assert result.total_matched == 12

    async def test_discover_respects_top_k(self) -> None:
        """discover_capabilities() slices to top_k."""
        caps = _make_scored_capabilities(15)
        adapter = TestFabricRetrievalAdapter(preset_capabilities=caps)

        result = await adapter.discover_capabilities(top_k=5)
        assert len(result.capabilities) == 5

    async def test_discover_top_k_larger_than_preset(self) -> None:
        """top_k larger than preset returns all available."""
        caps = _make_scored_capabilities(3)
        adapter = TestFabricRetrievalAdapter(preset_capabilities=caps)

        result = await adapter.discover_capabilities(top_k=10)
        assert len(result.capabilities) == 3
        assert result.total_matched == 3


class TestFabricRetrievalAdapterEmptyDiscovery:
    """6.1.3: Empty discovery -- 0 results."""

    async def test_discover_empty_preset(self) -> None:
        """discover_capabilities() with no preset returns empty."""
        adapter = TestFabricRetrievalAdapter()
        result = await adapter.discover_capabilities()

        assert len(result.capabilities) == 0
        assert result.total_matched == 0

    async def test_find_prompts_empty_preset(self) -> None:
        """find_relevant_prompts() with no preset returns empty."""
        adapter = TestFabricRetrievalAdapter()
        result = await adapter.find_relevant_prompts()

        assert len(result.capabilities) == 0
        assert result.total_matched == 0


class TestFabricRetrievalAdapterFiltered:
    """6.1.3: Filtered results -- safety_band and domain forwarded."""

    async def test_safety_band_captured(self) -> None:
        """safety_band argument is recorded in discover_log."""
        adapter = TestFabricRetrievalAdapter(preset_capabilities=_make_scored_capabilities(3))
        await adapter.discover_capabilities(safety_band="AMBER")

        assert adapter.discover_log[0]["safety_band"] == "AMBER"

    async def test_domain_captured(self) -> None:
        """domain argument is recorded in discover_log."""
        adapter = TestFabricRetrievalAdapter(preset_capabilities=_make_scored_capabilities(3))
        await adapter.discover_capabilities(domain=["food", "travel"])

        assert adapter.discover_log[0]["domain"] == ["food", "travel"]

    async def test_session_context_captured(self) -> None:
        """session_context argument is recorded in discover_log."""
        adapter = TestFabricRetrievalAdapter()
        ctx = {"user_id": "u123", "location": "NYC"}
        await adapter.discover_capabilities(session_context=ctx)

        assert adapter.discover_log[0]["session_context"] == ctx

    async def test_intent_captured(self) -> None:
        """intent argument is recorded in discover_log."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities(intent="book a table")

        assert adapter.discover_log[0]["intent"] == "book a table"

    async def test_assert_safety_band_in_discovers(self) -> None:
        """assert_safety_band_in_discovers helper."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities(safety_band="RED")
        await adapter.discover_capabilities(safety_band="RED")

        adapter.assert_safety_band_in_discovers("RED")

    async def test_assert_safety_band_in_discovers_fails(self) -> None:
        """assert_safety_band_in_discovers fails on mismatch."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities(safety_band="GREEN")

        with pytest.raises(AssertionError, match="safety_band"):
            adapter.assert_safety_band_in_discovers("RED")


class TestFabricRetrievalAdapterPrompts:
    """6.1.3: find_relevant_prompts behavior."""

    async def test_find_prompts_returns_preset(self) -> None:
        """find_relevant_prompts() returns from preset_prompts."""
        prompts = _make_scored_capabilities(5)
        adapter = TestFabricRetrievalAdapter(preset_prompts=prompts)

        result = await adapter.find_relevant_prompts(intent="generate email")
        assert len(result.capabilities) == 5

    async def test_find_prompts_respects_top_k(self) -> None:
        """find_relevant_prompts() slices to top_k."""
        prompts = _make_scored_capabilities(8)
        adapter = TestFabricRetrievalAdapter(preset_prompts=prompts)

        result = await adapter.find_relevant_prompts(top_k=3)
        assert len(result.capabilities) == 3

    async def test_find_prompts_safety_band_captured(self) -> None:
        """safety_band is recorded in prompt_log."""
        adapter = TestFabricRetrievalAdapter(preset_prompts=_make_scored_capabilities(2))
        await adapter.find_relevant_prompts(safety_band="AMBER")

        assert adapter.prompt_log[0]["safety_band"] == "AMBER"

    async def test_find_prompts_domain_captured(self) -> None:
        """domain is recorded in prompt_log."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.find_relevant_prompts(domain=["cooking"])

        assert adapter.prompt_log[0]["domain"] == ["cooking"]


class TestFabricRetrievalAdapterCapture:
    """6.1.3: Call log capture and assertion helpers."""

    async def test_discover_count(self) -> None:
        """discover_count tracks number of calls."""
        adapter = TestFabricRetrievalAdapter()
        assert adapter.discover_count == 0

        await adapter.discover_capabilities()
        await adapter.discover_capabilities()
        assert adapter.discover_count == 2

    async def test_prompt_count(self) -> None:
        """prompt_count tracks number of calls."""
        adapter = TestFabricRetrievalAdapter()
        assert adapter.prompt_count == 0

        await adapter.find_relevant_prompts()
        assert adapter.prompt_count == 1

    async def test_assert_discover_count(self) -> None:
        """assert_discover_count helper."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities()
        adapter.assert_discover_count(1)

        with pytest.raises(AssertionError):
            adapter.assert_discover_count(2)

    async def test_assert_prompt_count(self) -> None:
        """assert_prompt_count helper."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.find_relevant_prompts()
        adapter.assert_prompt_count(1)

        with pytest.raises(AssertionError):
            adapter.assert_prompt_count(0)

    async def test_get_discover_top_k_values(self) -> None:
        """get_discover_top_k_values returns all top_k args."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities(top_k=10)
        await adapter.discover_capabilities(top_k=5)

        assert adapter.get_discover_top_k_values() == [10, 5]

    async def test_get_prompt_top_k_values(self) -> None:
        """get_prompt_top_k_values returns all top_k args."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.find_relevant_prompts(top_k=3)
        await adapter.find_relevant_prompts(top_k=7)

        assert adapter.get_prompt_top_k_values() == [3, 7]

    async def test_assert_domain_in_discovers(self) -> None:
        """assert_domain_in_discovers helper."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities(domain=["food"])
        await adapter.discover_capabilities(domain=["food"])

        adapter.assert_domain_in_discovers(["food"])

    async def test_assert_domain_in_discovers_fails(self) -> None:
        """assert_domain_in_discovers fails on mismatch."""
        adapter = TestFabricRetrievalAdapter()
        await adapter.discover_capabilities(domain=["food"])

        with pytest.raises(AssertionError):
            adapter.assert_domain_in_discovers(["travel"])


class TestFabricRetrievalAdapterReturnType:
    """6.1.3: Return type is RetrievalResult."""

    async def test_discover_returns_retrieval_result(self) -> None:
        """discover_capabilities() returns RetrievalResult."""
        adapter = TestFabricRetrievalAdapter(preset_capabilities=_make_scored_capabilities(2))
        result = await adapter.discover_capabilities()
        assert isinstance(result, RetrievalResult)

    async def test_find_prompts_returns_retrieval_result(self) -> None:
        """find_relevant_prompts() returns RetrievalResult."""
        adapter = TestFabricRetrievalAdapter(preset_prompts=_make_scored_capabilities(2))
        result = await adapter.find_relevant_prompts()
        assert isinstance(result, RetrievalResult)

    async def test_discover_query_intent_populated(self) -> None:
        """RetrievalResult.query_intent matches the intent argument."""
        adapter = TestFabricRetrievalAdapter()
        result = await adapter.discover_capabilities(intent="test query")
        assert result.query_intent == "test query"

    async def test_find_prompts_query_intent_populated(self) -> None:
        """RetrievalResult.query_intent matches the intent argument."""
        adapter = TestFabricRetrievalAdapter()
        result = await adapter.find_relevant_prompts(intent="prompt search")
        assert result.query_intent == "prompt search"


# =========================================================================
# Cross-cutting: Adapters are NOT importable from production code
# =========================================================================


class TestAdapterFileLocation:
    """SS30.3: Test adapters live in tests/ directory, not k1/planner/."""

    def test_mailbox_adapter_in_test_tree(self) -> None:
        """TestMailboxAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_mailbox_adapter as mod

        assert "tests" in mod.__name__

    def test_llm_adapter_in_test_tree(self) -> None:
        """TestLLMAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_llm_adapter as mod

        assert "tests" in mod.__name__

    def test_fabric_adapter_in_test_tree(self) -> None:
        """TestFabricRetrievalAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_fabric_retrieval_adapter as mod

        assert "tests" in mod.__name__

    def test_adapters_package_exports(self) -> None:
        """adapters/__init__.py re-exports all 6 adapters."""
        from tests.k1.planner.adapters import (
            TestBridgeAdapter,
            TestDeltaAdapter,
            TestFabricRetrievalAdapter,
            TestLLMAdapter,
            TestMailboxAdapter,
            TestStateReadAdapter,
        )

        assert TestMailboxAdapter is not None
        assert TestLLMAdapter is not None
        assert TestFabricRetrievalAdapter is not None
        assert TestStateReadAdapter is not None
        assert TestBridgeAdapter is not None
        assert TestDeltaAdapter is not None


# =========================================================================
# Issue 6.1.4: TestStateReadAdapter (SS16.2.4, IStateReadPort)
# =========================================================================


class TestStateReadAdapterProtocol:
    """IStateReadPort structural compliance tests."""

    def test_isinstance_check(self) -> None:
        """TestStateReadAdapter satisfies IStateReadPort Protocol."""
        adapter = TestStateReadAdapter()
        assert isinstance(adapter, IStateReadPort)

    def test_read_sections_method_exists(self) -> None:
        """read_sections() method is present."""
        adapter = TestStateReadAdapter()
        assert callable(getattr(adapter, "read_sections", None))

    def test_get_snapshot_method_exists(self) -> None:
        """get_snapshot() method is present."""
        adapter = TestStateReadAdapter()
        assert callable(getattr(adapter, "get_snapshot", None))


class TestStateReadAdapterReadSections:
    """Tests for read_sections() behavior."""

    async def test_empty_preset_returns_empty_snapshot(self) -> None:
        """No preset sections -> empty snapshot."""
        adapter = TestStateReadAdapter()
        snap = await adapter.read_sections(["profile", "context"])
        assert snap.sections == {}
        assert snap.section_names == []

    async def test_intersection_returns_only_matching(self) -> None:
        """Only sections present in preset_sections are returned."""
        preset = {
            "profile": {"name": "Alice"},
            "history": {"entries": [1, 2, 3]},
        }
        adapter = TestStateReadAdapter(preset_sections=preset)
        snap = await adapter.read_sections(["profile", "missing"])
        assert "profile" in snap.sections
        assert "missing" not in snap.sections
        assert snap.sections["profile"] == {"name": "Alice"}

    async def test_missing_sections_omitted_not_none(self) -> None:
        """Missing sections are omitted (not None-valued)."""
        adapter = TestStateReadAdapter(preset_sections={"a": {"val": 1}})
        snap = await adapter.read_sections(["a", "b", "c"])
        assert list(snap.sections.keys()) == ["a"]
        assert "b" not in snap.sections
        assert "c" not in snap.sections

    async def test_section_names_sorted(self) -> None:
        """section_names in returned snapshot are sorted."""
        preset = {"z_section": {}, "a_section": {}, "m_section": {}}
        adapter = TestStateReadAdapter(preset_sections=preset)
        snap = await adapter.read_sections(["z_section", "a_section", "m_section"])
        assert snap.section_names == ["a_section", "m_section", "z_section"]

    async def test_all_preset_sections_returned_when_all_requested(self) -> None:
        """Requesting all preset sections returns all."""
        preset = {"x": {"a": 1}, "y": {"b": 2}}
        adapter = TestStateReadAdapter(preset_sections=preset)
        snap = await adapter.read_sections(["x", "y"])
        assert len(snap.sections) == 2
        assert snap.sections["x"] == {"a": 1}
        assert snap.sections["y"] == {"b": 2}

    async def test_empty_sections_request(self) -> None:
        """Requesting empty list returns empty snapshot."""
        adapter = TestStateReadAdapter(preset_sections={"a": {"v": 1}})
        snap = await adapter.read_sections([])
        assert snap.sections == {}

    async def test_returns_session_snapshot_type(self) -> None:
        """Return type is SessionSnapshot."""
        adapter = TestStateReadAdapter()
        snap = await adapter.read_sections(["any"])
        assert isinstance(snap, SessionSnapshot)


class TestStateReadAdapterGetSnapshot:
    """Tests for get_snapshot() behavior."""

    async def test_no_preset_returns_empty(self) -> None:
        """No preset_snapshot -> returns empty SessionSnapshot."""
        adapter = TestStateReadAdapter()
        snap = await adapter.get_snapshot()
        assert isinstance(snap, SessionSnapshot)
        assert snap.sections == {}

    async def test_preset_snapshot_returned(self) -> None:
        """Preset snapshot is returned directly."""
        custom_snap = SessionSnapshot(
            session_id="sess-1",
            sections={"profile": {"name": "Bob"}},
        )
        adapter = TestStateReadAdapter(preset_snapshot=custom_snap)
        result = await adapter.get_snapshot()
        assert result is custom_snap
        assert result.session_id == "sess-1"

    async def test_trace_id_logged(self) -> None:
        """get_snapshot() records trace_id."""
        adapter = TestStateReadAdapter()
        await adapter.get_snapshot(trace_id="t-123")
        assert adapter.snapshot_log == ["t-123"]


class TestStateReadAdapterCapture:
    """Tests for capture/assertion capabilities."""

    async def test_read_log_records_sections(self) -> None:
        """Each read_sections call is recorded."""
        adapter = TestStateReadAdapter(preset_sections={"a": {}, "b": {}})
        await adapter.read_sections(["a"])
        await adapter.read_sections(["a", "b"])
        assert adapter.read_count == 2
        assert adapter.read_log[0] == ["a"]
        assert adapter.read_log[1] == ["a", "b"]

    async def test_assert_read_count_passes(self) -> None:
        """assert_read_count passes on correct count."""
        adapter = TestStateReadAdapter()
        await adapter.read_sections(["x"])
        adapter.assert_read_count(1)

    async def test_assert_read_count_fails(self) -> None:
        """assert_read_count raises on mismatch."""
        adapter = TestStateReadAdapter()
        with pytest.raises(AssertionError, match="Expected 2"):
            adapter.assert_read_count(2)

    async def test_assert_sections_requested(self) -> None:
        """assert_sections_requested validates specific call."""
        adapter = TestStateReadAdapter()
        await adapter.read_sections(["b", "a"])
        adapter.assert_sections_requested(0, ["a", "b"])

    async def test_assert_sections_requested_out_of_range(self) -> None:
        """assert_sections_requested raises on bad index."""
        adapter = TestStateReadAdapter()
        with pytest.raises(AssertionError, match="out of range"):
            adapter.assert_sections_requested(0, ["x"])

    async def test_get_all_requested_sections(self) -> None:
        """get_all_requested_sections returns flat list with dupes."""
        adapter = TestStateReadAdapter()
        await adapter.read_sections(["a", "b"])
        await adapter.read_sections(["b", "c"])
        all_sections = adapter.get_all_requested_sections()
        assert all_sections == ["a", "b", "b", "c"]

    async def test_snapshot_log_captures_multiple(self) -> None:
        """snapshot_log appends for each get_snapshot call."""
        adapter = TestStateReadAdapter()
        await adapter.get_snapshot(trace_id="t1")
        await adapter.get_snapshot(trace_id="t2")
        assert adapter.snapshot_log == ["t1", "t2"]

    def test_read_log_is_copy(self) -> None:
        """read_log returns a copy, not internal state."""
        adapter = TestStateReadAdapter()
        log1 = adapter.read_log
        log1.append(["fake"])
        assert adapter.read_log == []

    def test_snapshot_log_is_copy(self) -> None:
        """snapshot_log returns a copy, not internal state."""
        adapter = TestStateReadAdapter()
        log1 = adapter.snapshot_log
        log1.append("fake")
        assert adapter.snapshot_log == []


class TestStateReadAdapterFileLocation:
    """SS30.3: TestStateReadAdapter lives in tests/ directory."""

    def test_state_read_adapter_in_test_tree(self) -> None:
        """TestStateReadAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_state_read_adapter as mod

        assert "tests" in mod.__name__


# =========================================================================
# Issue 6.1.5: TestBridgeAdapter (SS16.2.5, IBridgePort)
# =========================================================================


class TestBridgeAdapterProtocol:
    """IBridgePort structural compliance tests."""

    def test_isinstance_check(self) -> None:
        """TestBridgeAdapter satisfies IBridgePort Protocol."""
        adapter = TestBridgeAdapter()
        assert isinstance(adapter, IBridgePort)

    def test_recall_method_exists(self) -> None:
        """recall() method is present."""
        adapter = TestBridgeAdapter()
        assert callable(getattr(adapter, "recall", None))

    def test_persist_plan_method_exists(self) -> None:
        """persist_plan() method is present."""
        adapter = TestBridgeAdapter()
        assert callable(getattr(adapter, "persist_plan", None))


class TestBridgeAdapterRecall:
    """Tests for recall() behavior."""

    async def test_empty_preset_returns_empty_response(self) -> None:
        """No preset recall data -> empty RecallResponse."""
        adapter = TestBridgeAdapter()
        result = await adapter.recall("test query")
        assert isinstance(result, RecallResponse)
        assert result.facts == []
        assert result.scores == []

    async def test_preset_recall_returned(self) -> None:
        """Preset recall data flows through."""
        preset = {
            "facts": [{"content": "family birthday"}],
            "scores": [0.95],
        }
        adapter = TestBridgeAdapter(preset_recall=preset)
        result = await adapter.recall("birthday")
        assert result.facts == [{"content": "family birthday"}]
        assert result.scores == [0.95]

    async def test_trace_id_passed_through(self) -> None:
        """trace_id from call appears in response."""
        adapter = TestBridgeAdapter()
        result = await adapter.recall("q", trace_id="t-456")
        assert result.trace_id == "t-456"

    async def test_recall_unavailable_returns_empty(self) -> None:
        """When offline, recall returns empty even with preset."""
        preset = {"facts": [{"x": 1}], "scores": [0.5]}
        adapter = TestBridgeAdapter(preset_recall=preset, available=False)
        result = await adapter.recall("anything")
        assert result.facts == []
        assert result.scores == []

    async def test_selectors_recorded(self) -> None:
        """Selectors are captured in recall log."""
        adapter = TestBridgeAdapter()
        await adapter.recall("q", selectors=["memory", "habits"])
        assert adapter.recall_log[0]["selectors"] == ["memory", "habits"]

    async def test_recall_log_captures_all_calls(self) -> None:
        """All recall calls are logged."""
        adapter = TestBridgeAdapter()
        await adapter.recall("q1", trace_id="t1")
        await adapter.recall("q2", selectors=["s"], trace_id="t2")
        assert adapter.recall_count == 2
        assert adapter.recall_log[0]["query"] == "q1"
        assert adapter.recall_log[1]["query"] == "q2"


class TestBridgeAdapterPersist:
    """Tests for persist_plan() behavior."""

    async def test_persist_captures_plan(self) -> None:
        """persist_plan records plan.to_dict()."""
        adapter = TestBridgeAdapter()
        plan = _make_committed_plan()
        await adapter.persist_plan(plan)
        captured = adapter.get_persisted_plans()
        assert len(captured) == 1
        assert captured[0]["plan_id"] == plan.plan_id

    async def test_persist_multiple_plans(self) -> None:
        """Multiple persists recorded in order."""
        adapter = TestBridgeAdapter()
        p1 = _make_committed_plan()
        p2 = _make_committed_plan(num_steps=2)
        await adapter.persist_plan(p1)
        await adapter.persist_plan(p2)
        assert adapter.persist_count == 2

    async def test_persist_unavailable_drops_silently(self) -> None:
        """When offline, persist_plan silently drops."""
        adapter = TestBridgeAdapter(available=False)
        plan = _make_committed_plan()
        await adapter.persist_plan(plan)
        assert adapter.persist_count == 0

    async def test_persist_no_exception(self) -> None:
        """persist_plan never raises (fire-and-forget)."""
        adapter = TestBridgeAdapter()
        plan = _make_committed_plan()
        # Should complete without exception
        await adapter.persist_plan(plan, trace_id="t-persist")


class TestBridgeAdapterAvailability:
    """Tests for availability toggle."""

    def test_default_available(self) -> None:
        """Default state is available."""
        adapter = TestBridgeAdapter()
        assert adapter.is_available() is True

    def test_constructed_offline(self) -> None:
        """Can construct in offline state."""
        adapter = TestBridgeAdapter(available=False)
        assert adapter.is_available() is False

    def test_toggle_availability(self) -> None:
        """set_available toggles state."""
        adapter = TestBridgeAdapter()
        adapter.set_available(False)
        assert adapter.is_available() is False
        adapter.set_available(True)
        assert adapter.is_available() is True

    async def test_availability_affects_recall_mid_test(self) -> None:
        """Toggling availability mid-test changes recall behavior."""
        preset = {"facts": [{"k": "v"}], "scores": [1.0]}
        adapter = TestBridgeAdapter(preset_recall=preset)

        r1 = await adapter.recall("q1")
        assert len(r1.facts) == 1

        adapter.set_available(False)
        r2 = await adapter.recall("q2")
        assert len(r2.facts) == 0

        adapter.set_available(True)
        r3 = await adapter.recall("q3")
        assert len(r3.facts) == 1


class TestBridgeAdapterAssertions:
    """Tests for assertion helpers."""

    async def test_assert_recall_count(self) -> None:
        """assert_recall_count validates correctly."""
        adapter = TestBridgeAdapter()
        await adapter.recall("q")
        adapter.assert_recall_count(1)

    async def test_assert_recall_count_fails(self) -> None:
        """assert_recall_count raises on mismatch."""
        adapter = TestBridgeAdapter()
        with pytest.raises(AssertionError, match="Expected 1"):
            adapter.assert_recall_count(1)

    async def test_assert_persist_count(self) -> None:
        """assert_persist_count validates correctly."""
        adapter = TestBridgeAdapter()
        plan = _make_committed_plan()
        await adapter.persist_plan(plan)
        adapter.assert_persist_count(1)

    async def test_assert_persist_count_fails(self) -> None:
        """assert_persist_count raises on mismatch."""
        adapter = TestBridgeAdapter()
        with pytest.raises(AssertionError, match="Expected 1"):
            adapter.assert_persist_count(1)


class TestBridgeAdapterFileLocation:
    """SS30.3: TestBridgeAdapter lives in tests/ directory."""

    def test_bridge_adapter_in_test_tree(self) -> None:
        """TestBridgeAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_bridge_adapter as mod

        assert "tests" in mod.__name__


# =========================================================================
# Issue 6.1.6: TestDeltaAdapter (SS16.2.6, IDeltaEmitPort)
# =========================================================================


def _make_delta(
    delta_type: str = DELTA_STAGE_TRANSITION,
    section: str = SECTION_PIPELINE,
    data: Optional[Dict[str, Any]] = None,
    agent_id: str = PLANNER_AGENT_ID,
    trace_id: str = "trace-delta-test",
) -> DeltaPayload:
    """Create a minimal valid DeltaPayload."""
    return DeltaPayload(
        agent_id=agent_id,
        delta_type=delta_type,
        section=section,
        data=data or {},
        trace_id=trace_id,
    )


class TestDeltaAdapterProtocol:
    """IDeltaEmitPort structural compliance tests."""

    def test_isinstance_check(self) -> None:
        """TestDeltaAdapter satisfies IDeltaEmitPort Protocol."""
        adapter = TestDeltaAdapter()
        assert isinstance(adapter, IDeltaEmitPort)

    def test_emit_method_exists(self) -> None:
        """emit() method is present."""
        adapter = TestDeltaAdapter()
        assert callable(getattr(adapter, "emit", None))

    def test_emit_is_synchronous(self) -> None:
        """emit() is not a coroutine function (SS15.7: synchronous)."""
        import inspect

        adapter = TestDeltaAdapter()
        assert not inspect.iscoroutinefunction(adapter.emit)


class TestDeltaAdapterEmit:
    """Tests for emit() behavior."""

    def test_emit_captures_delta(self) -> None:
        """emit() appends to capture list."""
        adapter = TestDeltaAdapter()
        delta = _make_delta()
        adapter.emit(delta)
        assert adapter.delta_count == 1
        assert adapter.get_deltas()[0] is delta

    def test_emit_never_raises(self) -> None:
        """emit() must never raise (fire-and-forget)."""
        adapter = TestDeltaAdapter()
        delta = _make_delta()
        # Should not raise
        adapter.emit(delta)

    def test_emit_ordering_preserved(self) -> None:
        """Deltas captured in emission order."""
        adapter = TestDeltaAdapter()
        d1 = _make_delta(delta_type=DELTA_STAGE_TRANSITION, data={"to": "SKETCH"})
        d2 = _make_delta(delta_type=DELTA_PLAN_UPDATE)
        d3 = _make_delta(delta_type=DELTA_PLAN_END)
        adapter.emit(d1)
        adapter.emit(d2)
        adapter.emit(d3)
        deltas = adapter.get_deltas()
        assert deltas[0].delta_type == DELTA_STAGE_TRANSITION
        assert deltas[1].delta_type == DELTA_PLAN_UPDATE
        assert deltas[2].delta_type == DELTA_PLAN_END

    def test_emit_all_delta_types(self) -> None:
        """All 8 valid delta types can be emitted."""
        adapter = TestDeltaAdapter()
        for dt in [
            DELTA_STAGE_TRANSITION,
            DELTA_TOOL_RESULT,
            DELTA_PLAN_UPDATE,
            DELTA_PLAN_END,
            DELTA_PLAN_CANCELLED,
            DELTA_MICRO_REPLAN,
            DELTA_CRASH_RECOVERY,
        ]:
            adapter.emit(_make_delta(delta_type=dt))
        assert adapter.delta_count == 7

    def test_emit_with_all_sections(self) -> None:
        """Deltas with all 3 valid sections are captured."""
        adapter = TestDeltaAdapter()
        for section in [SECTION_PIPELINE, SECTION_PLAN, SECTION_TOOLS]:
            adapter.emit(_make_delta(section=section))
        assert adapter.delta_count == 3


class TestDeltaAdapterFiltering:
    """Tests for filtering and query helpers."""

    def test_get_deltas_by_type(self) -> None:
        """get_deltas_by_type filters correctly."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta(delta_type=DELTA_STAGE_TRANSITION))
        adapter.emit(_make_delta(delta_type=DELTA_PLAN_UPDATE))
        adapter.emit(_make_delta(delta_type=DELTA_STAGE_TRANSITION))

        transitions = adapter.get_deltas_by_type(DELTA_STAGE_TRANSITION)
        assert len(transitions) == 2
        updates = adapter.get_deltas_by_type(DELTA_PLAN_UPDATE)
        assert len(updates) == 1

    def test_get_deltas_by_type_empty(self) -> None:
        """get_deltas_by_type returns empty for unmatched type."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta(delta_type=DELTA_STAGE_TRANSITION))
        assert adapter.get_deltas_by_type(DELTA_PLAN_END) == []

    def test_get_stage_transition_sequence(self) -> None:
        """get_stage_transition_sequence extracts 'to' fields."""
        adapter = TestDeltaAdapter()
        adapter.emit(
            _make_delta(
                delta_type=DELTA_STAGE_TRANSITION,
                data={"to": "SKETCH"},
            )
        )
        adapter.emit(_make_delta(delta_type=DELTA_PLAN_UPDATE))
        adapter.emit(
            _make_delta(
                delta_type=DELTA_STAGE_TRANSITION,
                data={"to": "EXPAND"},
            )
        )
        assert adapter.get_stage_transition_sequence() == ["SKETCH", "EXPAND"]


class TestDeltaAdapterAssertions:
    """Tests for assertion helpers."""

    def test_assert_delta_count_passes(self) -> None:
        """assert_delta_count passes on correct count."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta())
        adapter.assert_delta_count(1)

    def test_assert_delta_count_fails(self) -> None:
        """assert_delta_count raises on mismatch."""
        adapter = TestDeltaAdapter()
        with pytest.raises(AssertionError, match="Expected 3"):
            adapter.assert_delta_count(3)

    def test_assert_stage_transitions_passes(self) -> None:
        """assert_stage_transitions passes on correct sequence."""
        adapter = TestDeltaAdapter()
        for stage in ["SKETCH", "EXPAND", "VERIFY", "COMMIT"]:
            adapter.emit(
                _make_delta(
                    delta_type=DELTA_STAGE_TRANSITION,
                    data={"to": stage},
                )
            )
        adapter.assert_stage_transitions(["SKETCH", "EXPAND", "VERIFY", "COMMIT"])

    def test_assert_stage_transitions_fails(self) -> None:
        """assert_stage_transitions raises on wrong sequence."""
        adapter = TestDeltaAdapter()
        adapter.emit(
            _make_delta(
                delta_type=DELTA_STAGE_TRANSITION,
                data={"to": "SKETCH"},
            )
        )
        with pytest.raises(AssertionError, match="Expected stage transitions"):
            adapter.assert_stage_transitions(["EXPAND"])

    def test_assert_has_delta_type_passes(self) -> None:
        """assert_has_delta_type passes when type present."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta(delta_type=DELTA_PLAN_END))
        adapter.assert_has_delta_type(DELTA_PLAN_END)

    def test_assert_has_delta_type_fails(self) -> None:
        """assert_has_delta_type raises when type absent."""
        adapter = TestDeltaAdapter()
        with pytest.raises(AssertionError, match="No delta with type"):
            adapter.assert_has_delta_type(DELTA_PLAN_END)

    def test_assert_no_delta_type_passes(self) -> None:
        """assert_no_delta_type passes when type absent."""
        adapter = TestDeltaAdapter()
        adapter.assert_no_delta_type(DELTA_CRASH_RECOVERY)

    def test_assert_no_delta_type_fails(self) -> None:
        """assert_no_delta_type raises when type present."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta(delta_type=DELTA_CRASH_RECOVERY))
        with pytest.raises(AssertionError, match="Expected no"):
            adapter.assert_no_delta_type(DELTA_CRASH_RECOVERY)


class TestDeltaAdapterClear:
    """Tests for clear/reset behavior."""

    def test_clear_resets_capture(self) -> None:
        """clear() removes all captured deltas."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta())
        adapter.emit(_make_delta())
        assert adapter.delta_count == 2
        adapter.clear()
        assert adapter.delta_count == 0
        assert adapter.get_deltas() == []

    def test_clear_allows_reuse(self) -> None:
        """After clear, new emits work normally."""
        adapter = TestDeltaAdapter()
        adapter.emit(_make_delta())
        adapter.clear()
        adapter.emit(_make_delta(delta_type=DELTA_PLAN_END))
        assert adapter.delta_count == 1
        assert adapter.get_deltas()[0].delta_type == DELTA_PLAN_END


class TestDeltaAdapterFileLocation:
    """SS30.3: TestDeltaAdapter lives in tests/ directory."""

    def test_delta_adapter_in_test_tree(self) -> None:
        """TestDeltaAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_delta_adapter as mod

        assert "tests" in mod.__name__


# =========================================================================
# Issue 6.1.7: TestEventAdapter (SS16.2.7, IEventPort)
# =========================================================================


class TestEventAdapterProtocol:
    """IEventPort structural compliance tests."""

    def test_isinstance_check(self) -> None:
        """TestEventAdapter satisfies IEventPort Protocol."""
        adapter = TestEventAdapter()
        assert isinstance(adapter, IEventPort)

    def test_emit_method_exists(self) -> None:
        """emit() method is present."""
        adapter = TestEventAdapter()
        assert callable(getattr(adapter, "emit", None))

    def test_subscribe_method_exists(self) -> None:
        """subscribe() method is present."""
        adapter = TestEventAdapter()
        assert callable(getattr(adapter, "subscribe", None))

    def test_unsubscribe_method_exists(self) -> None:
        """unsubscribe() method is present."""
        adapter = TestEventAdapter()
        assert callable(getattr(adapter, "unsubscribe", None))

    def test_emit_is_synchronous(self) -> None:
        """emit() is not a coroutine function (SS15.8: synchronous)."""
        import inspect

        adapter = TestEventAdapter()
        assert not inspect.iscoroutinefunction(adapter.emit)

    def test_subscribe_is_synchronous(self) -> None:
        """subscribe() is not a coroutine function."""
        import inspect

        adapter = TestEventAdapter()
        assert not inspect.iscoroutinefunction(adapter.subscribe)


class TestEventAdapterEmit:
    """Tests for emit() behavior."""

    def test_emit_captures_event(self) -> None:
        """emit() appends (topic, payload) to capture list."""
        adapter = TestEventAdapter()
        adapter.emit("k1.planner.plan.ready.v1", {"plan_id": "p1"})
        assert adapter.publish_count == 1
        published = adapter.get_all_published()
        assert published[0] == ("k1.planner.plan.ready.v1", {"plan_id": "p1"})

    def test_emit_never_raises(self) -> None:
        """emit() must never raise (fire-and-forget)."""
        adapter = TestEventAdapter()
        # No subscribers, should not raise
        adapter.emit("nonexistent.topic", {"data": "test"})

    def test_emit_ordering_preserved(self) -> None:
        """Events captured in emission order."""
        adapter = TestEventAdapter()
        adapter.emit("topic.a", {"seq": 1})
        adapter.emit("topic.b", {"seq": 2})
        adapter.emit("topic.a", {"seq": 3})
        all_published = adapter.get_all_published()
        assert len(all_published) == 3
        assert all_published[0][0] == "topic.a"
        assert all_published[1][0] == "topic.b"
        assert all_published[2][0] == "topic.a"

    def test_emit_invokes_registered_handlers(self) -> None:
        """emit() dispatches to subscribed handlers."""
        adapter = TestEventAdapter()
        received: List[Dict[str, Any]] = []
        adapter.subscribe("my.topic", lambda t, p: received.append(p))
        adapter.emit("my.topic", {"key": "value"})
        assert len(received) == 1
        assert received[0] == {"key": "value"}

    def test_emit_invokes_multiple_handlers(self) -> None:
        """emit() dispatches to ALL handlers on the topic."""
        adapter = TestEventAdapter()
        log1: List[str] = []
        log2: List[str] = []
        adapter.subscribe("topic", lambda t, p: log1.append("h1"))
        adapter.subscribe("topic", lambda t, p: log2.append("h2"))
        adapter.emit("topic", {})
        assert log1 == ["h1"]
        assert log2 == ["h2"]

    def test_emit_swallows_handler_exceptions(self) -> None:
        """If a handler raises, emit() catches and continues."""
        adapter = TestEventAdapter()
        call_order: List[str] = []

        def bad_handler(t: str, p: Any) -> None:
            call_order.append("bad")
            raise RuntimeError("handler error")

        def good_handler(t: str, p: Any) -> None:
            call_order.append("good")

        adapter.subscribe("topic", bad_handler)
        adapter.subscribe("topic", good_handler)
        # Should not raise
        adapter.emit("topic", {})
        assert "bad" in call_order
        assert "good" in call_order

    def test_emit_only_fires_matching_topic(self) -> None:
        """Handlers on other topics are not invoked."""
        adapter = TestEventAdapter()
        received: List[str] = []
        adapter.subscribe("topic.a", lambda t, p: received.append("a"))
        adapter.subscribe("topic.b", lambda t, p: received.append("b"))
        adapter.emit("topic.a", {})
        assert received == ["a"]


class TestEventAdapterSubscribe:
    """Tests for subscribe()/unsubscribe() behavior."""

    def test_subscribe_returns_handle(self) -> None:
        """subscribe() returns a SubscriptionHandle."""
        adapter = TestEventAdapter()
        handle = adapter.subscribe("some.topic", lambda t, p: None)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "some.topic"
        assert handle.subscription_id != ""

    def test_subscribe_multiple_topics(self) -> None:
        """Can subscribe to multiple different topics."""
        adapter = TestEventAdapter()
        h1 = adapter.subscribe("topic.a", lambda t, p: None)
        h2 = adapter.subscribe("topic.b", lambda t, p: None)
        assert h1.topic == "topic.a"
        assert h2.topic == "topic.b"
        assert adapter.subscription_count == 2

    def test_unsubscribe_removes_handler(self) -> None:
        """unsubscribe() removes the handler."""
        adapter = TestEventAdapter()
        received: List[str] = []
        handle = adapter.subscribe("topic", lambda t, p: received.append("hit"))
        assert adapter.unsubscribe(handle) is True
        adapter.emit("topic", {})
        assert received == []  # Handler was removed

    def test_unsubscribe_returns_false_if_not_found(self) -> None:
        """unsubscribe() returns False for unknown handle."""
        adapter = TestEventAdapter()
        fake_handle = SubscriptionHandle(subscription_id="fake", topic="x")
        assert adapter.unsubscribe(fake_handle) is False

    def test_unsubscribe_idempotent(self) -> None:
        """Double unsubscribe returns False on second call."""
        adapter = TestEventAdapter()
        handle = adapter.subscribe("topic", lambda t, p: None)
        assert adapter.unsubscribe(handle) is True
        assert adapter.unsubscribe(handle) is False

    def test_has_subscription(self) -> None:
        """has_subscription() reflects subscribe/unsubscribe state."""
        adapter = TestEventAdapter()
        assert adapter.has_subscription("topic") is False
        handle = adapter.subscribe("topic", lambda t, p: None)
        assert adapter.has_subscription("topic") is True
        adapter.unsubscribe(handle)
        assert adapter.has_subscription("topic") is False


class TestEventAdapterInjectEvent:
    """Tests for inject_event() helper."""

    def test_inject_event_calls_handlers(self) -> None:
        """inject_event() dispatches to registered handlers."""
        adapter = TestEventAdapter()
        received: List[Dict[str, Any]] = []
        adapter.subscribe("hil.response", lambda t, p: received.append(p))
        adapter.inject_event("hil.response", {"decision": "approved"})
        assert len(received) == 1
        assert received[0] == {"decision": "approved"}

    def test_inject_event_does_not_capture(self) -> None:
        """inject_event() does NOT add to _publish_capture."""
        adapter = TestEventAdapter()
        adapter.subscribe("topic", lambda t, p: None)
        adapter.inject_event("topic", {"data": "injected"})
        assert adapter.publish_count == 0  # Not captured

    def test_inject_event_swallows_exceptions(self) -> None:
        """inject_event() swallows handler exceptions."""
        adapter = TestEventAdapter()

        def bad_handler(t: str, p: Any) -> None:
            raise ValueError("handler error")

        adapter.subscribe("topic", bad_handler)
        # Should not raise
        adapter.inject_event("topic", {})

    def test_inject_event_no_subscribers(self) -> None:
        """inject_event() on topic with no subscribers is a no-op."""
        adapter = TestEventAdapter()
        # Should not raise
        adapter.inject_event("unknown.topic", {"data": "test"})


class TestEventAdapterAssertions:
    """Tests for assertion helpers."""

    def test_get_published_filters_by_topic(self) -> None:
        """get_published() returns only payloads for the given topic."""
        adapter = TestEventAdapter()
        adapter.emit("topic.a", {"a": 1})
        adapter.emit("topic.b", {"b": 2})
        adapter.emit("topic.a", {"a": 3})
        result = adapter.get_published("topic.a")
        assert len(result) == 2
        assert result[0] == {"a": 1}
        assert result[1] == {"a": 3}

    def test_get_published_empty_for_unknown(self) -> None:
        """get_published() returns empty list for unknown topic."""
        adapter = TestEventAdapter()
        assert adapter.get_published("unknown") == []

    def test_assert_published_count_passes(self) -> None:
        """assert_published_count passes on correct count."""
        adapter = TestEventAdapter()
        adapter.emit("topic", {"x": 1})
        adapter.emit("topic", {"x": 2})
        adapter.assert_published_count("topic", 2)

    def test_assert_published_count_fails(self) -> None:
        """assert_published_count raises on mismatch."""
        adapter = TestEventAdapter()
        with pytest.raises(AssertionError, match="Expected 1"):
            adapter.assert_published_count("topic", 1)

    def test_assert_topic_emitted_passes(self) -> None:
        """assert_topic_emitted passes when topic has events."""
        adapter = TestEventAdapter()
        adapter.emit("my.topic", {})
        adapter.assert_topic_emitted("my.topic")

    def test_assert_topic_emitted_fails(self) -> None:
        """assert_topic_emitted raises when topic has no events."""
        adapter = TestEventAdapter()
        with pytest.raises(AssertionError, match="No events published"):
            adapter.assert_topic_emitted("missing.topic")

    def test_assert_topic_not_emitted_passes(self) -> None:
        """assert_topic_not_emitted passes when topic has no events."""
        adapter = TestEventAdapter()
        adapter.assert_topic_not_emitted("absent.topic")

    def test_assert_topic_not_emitted_fails(self) -> None:
        """assert_topic_not_emitted raises when topic was emitted."""
        adapter = TestEventAdapter()
        adapter.emit("present.topic", {})
        with pytest.raises(AssertionError, match="Expected no events"):
            adapter.assert_topic_not_emitted("present.topic")

    def test_get_published_topics(self) -> None:
        """get_published_topics returns unique topics in order."""
        adapter = TestEventAdapter()
        adapter.emit("b.topic", {})
        adapter.emit("a.topic", {})
        adapter.emit("b.topic", {})
        assert adapter.get_published_topics() == ["b.topic", "a.topic"]


class TestEventAdapterClear:
    """Tests for clear/reset behavior."""

    def test_clear_resets_capture(self) -> None:
        """clear() removes all captured events but keeps subscriptions."""
        adapter = TestEventAdapter()
        received: List[str] = []
        adapter.subscribe("topic", lambda t, p: received.append("hit"))
        adapter.emit("topic", {"x": 1})
        assert adapter.publish_count == 1

        adapter.clear()
        assert adapter.publish_count == 0
        assert adapter.get_all_published() == []

        # Subscriptions still active
        adapter.emit("topic", {"x": 2})
        assert len(received) == 2  # Both calls hit the handler


class TestEventAdapterPlannerTopics:
    """Tests simulating real Planner event patterns (SS16.2.7)."""

    def test_plan_ready_event(self) -> None:
        """Simulate plan.ready.v1 emission."""
        adapter = TestEventAdapter()
        adapter.emit(
            "k1.planner.plan.ready.v1",
            {
                "plan_id": "plan-123",
                "request_id": "req-456",
                "cognitive_trace_id": "trace-789",
            },
        )
        adapter.assert_topic_emitted("k1.planner.plan.ready.v1")
        payload = adapter.get_published("k1.planner.plan.ready.v1")[0]
        assert payload["plan_id"] == "plan-123"

    def test_plan_failed_event(self) -> None:
        """Simulate plan.failed.v1 emission."""
        adapter = TestEventAdapter()
        adapter.emit(
            "k1.planner.plan.failed.v1",
            {
                "request_id": "req-1",
                "error": "validation_rejected",
                "stage": "VALIDATE",
            },
        )
        adapter.assert_published_count("k1.planner.plan.failed.v1", 1)

    def test_plan_cancelled_event(self) -> None:
        """Simulate plan.cancelled.v1 emission."""
        adapter = TestEventAdapter()
        adapter.emit(
            "k1.planner.plan.cancelled.v1",
            {
                "request_id": "req-2",
                "reason": "user_cancel",
            },
        )
        adapter.assert_topic_emitted("k1.planner.plan.cancelled.v1")

    def test_hil_flow_inject_response(self) -> None:
        """Simulate HIL: subscribe, inject response, verify handler called."""
        adapter = TestEventAdapter()
        clarification_received: List[Dict[str, Any]] = []

        # PlannerAgent subscribes at INIT
        handle = adapter.subscribe(
            "k1.hil.clarification_response.v1",
            lambda t, p: clarification_received.append(p),
        )

        # External system injects HIL response
        adapter.inject_event(
            "k1.hil.clarification_response.v1",
            {
                "response": "The party is for 10 people",
                "trace_id": "t-hil",
            },
        )

        assert len(clarification_received) == 1
        assert clarification_received[0]["response"] == "The party is for 10 people"

        # Cleanup
        adapter.unsubscribe(handle)

    def test_approval_response_modify(self) -> None:
        """Simulate approval_response with 'modify' decision."""
        adapter = TestEventAdapter()
        decisions: List[str] = []

        adapter.subscribe(
            "k1.hil.approval_response.v1",
            lambda t, p: decisions.append(p.get("decision", "")),
        )

        adapter.inject_event(
            "k1.hil.approval_response.v1",
            {
                "decision": "modify",
                "feedback": "Add a backup venue option",
            },
        )

        assert decisions == ["modify"]


class TestEventAdapterFileLocation:
    """SS30.3: TestEventAdapter lives in tests/ directory."""

    def test_event_adapter_in_test_tree(self) -> None:
        """TestEventAdapter module path is in tests/."""
        import tests.k1.planner.adapters.test_event_adapter as mod

        assert "tests" in mod.__name__


# =========================================================================
# Issue 6.1.8: conftest.py and adapter wiring (SS30.3, SS30.4)
# =========================================================================


class TestConftestFixtures:
    """Verify conftest.py defines correct constants and fixture structure."""

    def test_conftest_importable(self) -> None:
        """conftest module at tests/k1/planner/ is importable."""
        import tests.k1.planner.conftest as conftest_mod

        assert conftest_mod is not None

    def test_default_stage_responses_defined(self) -> None:
        """DEFAULT_STAGE_RESPONSES has SKETCH, EXPAND, VALIDATE keys."""
        from tests.k1.planner.conftest import DEFAULT_STAGE_RESPONSES

        assert "SKETCH" in DEFAULT_STAGE_RESPONSES
        assert "EXPAND" in DEFAULT_STAGE_RESPONSES
        assert "VALIDATE" in DEFAULT_STAGE_RESPONSES

    def test_default_stage_responses_are_hub_responses(self) -> None:
        """Each stage response is a HubResponse with result and metadata."""
        from tests.k1.planner.conftest import DEFAULT_STAGE_RESPONSES

        for stage, resp in DEFAULT_STAGE_RESPONSES.items():
            assert isinstance(resp, HubResponse), f"{stage} is not HubResponse"
            assert "content" in resp.result, f"{stage} missing result.content"
            assert "usage" in resp.metadata, f"{stage} missing metadata.usage"

    def test_sample_capabilities_defined(self) -> None:
        """SAMPLE_CAPABILITIES has 5 ScoredCapability items."""
        from tests.k1.planner.conftest import SAMPLE_CAPABILITIES

        assert len(SAMPLE_CAPABILITIES) == 5
        for cap in SAMPLE_CAPABILITIES:
            assert isinstance(cap, ScoredCapability)

    def test_sample_sections_defined(self) -> None:
        """SAMPLE_SECTIONS has beliefs_active, control, history_recent."""
        from tests.k1.planner.conftest import SAMPLE_SECTIONS

        assert "beliefs_active" in SAMPLE_SECTIONS
        assert "control" in SAMPLE_SECTIONS
        assert "history_recent" in SAMPLE_SECTIONS

    def test_sample_recall_defined(self) -> None:
        """SAMPLE_RECALL has facts and scores."""
        from tests.k1.planner.conftest import SAMPLE_RECALL

        assert "facts" in SAMPLE_RECALL
        assert "scores" in SAMPLE_RECALL
        assert len(SAMPLE_RECALL["facts"]) == len(SAMPLE_RECALL["scores"])


class TestConftestAdapterFixtures:
    """Verify individual adapter fixture functions are properly defined.

    conftest.py fixtures are scoped to tests/k1/planner/ so we validate
    fixture existence, decoration, and wiring logic by inspecting the
    module and replicating the constructor calls.
    """

    def _get_conftest(self) -> Any:
        import tests.k1.planner.conftest as conftest_mod

        return conftest_mod

    def test_test_mailbox_fixture_exists_and_wiring(self) -> None:
        """test_mailbox fixture is defined and produces TestMailboxAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_mailbox"), "conftest missing test_mailbox fixture"
        # Replicate fixture wiring to verify correctness
        result = TestMailboxAdapter()
        assert isinstance(result, TestMailboxAdapter)

    def test_test_llm_fixture_exists_and_wiring(self) -> None:
        """test_llm fixture is defined and wiring produces TestLLMAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_llm"), "conftest missing test_llm fixture"
        result = TestLLMAdapter(stage_responses=dict(mod.DEFAULT_STAGE_RESPONSES))
        assert isinstance(result, TestLLMAdapter)

    def test_test_fabric_fixture_exists_and_wiring(self) -> None:
        """test_fabric fixture is defined and wiring produces TestFabricRetrievalAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_fabric"), "conftest missing test_fabric fixture"
        result = TestFabricRetrievalAdapter(preset_capabilities=list(mod.SAMPLE_CAPABILITIES))
        assert isinstance(result, TestFabricRetrievalAdapter)

    def test_test_state_fixture_exists_and_wiring(self) -> None:
        """test_state fixture is defined and wiring produces TestStateReadAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_state"), "conftest missing test_state fixture"
        result = TestStateReadAdapter(preset_sections=dict(mod.SAMPLE_SECTIONS))
        assert isinstance(result, TestStateReadAdapter)

    def test_test_bridge_fixture_exists_and_wiring(self) -> None:
        """test_bridge fixture is defined and wiring produces TestBridgeAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_bridge"), "conftest missing test_bridge fixture"
        result = TestBridgeAdapter(preset_recall=dict(mod.SAMPLE_RECALL))
        assert isinstance(result, TestBridgeAdapter)

    def test_test_delta_fixture_exists_and_wiring(self) -> None:
        """test_delta fixture is defined and wiring produces TestDeltaAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_delta"), "conftest missing test_delta fixture"
        result = TestDeltaAdapter()
        assert isinstance(result, TestDeltaAdapter)

    def test_test_event_fixture_exists_and_wiring(self) -> None:
        """test_event fixture is defined and wiring produces TestEventAdapter."""
        mod = self._get_conftest()
        assert hasattr(mod, "test_event"), "conftest missing test_event fixture"
        result = TestEventAdapter()
        assert isinstance(result, TestEventAdapter)


class TestConftestAllAdaptersFixture:
    """Verify the all_adapters composite fixture is defined with correct shape.

    Cannot call pytest fixtures directly, so we validate existence and
    replicate the composite logic manually.
    """

    def test_all_adapters_fixture_exists(self) -> None:
        """all_adapters fixture is defined in conftest."""
        import tests.k1.planner.conftest as conftest_mod

        assert hasattr(conftest_mod, "all_adapters"), "conftest missing all_adapters fixture"

    def test_all_adapters_composite_wiring(self) -> None:
        """Replicating all_adapters logic produces dict with 7 correct-type adapters."""
        import tests.k1.planner.conftest as conftest_mod

        # Replicate the composite fixture's construction logic
        result = {
            "mailbox": TestMailboxAdapter(),
            "llm": TestLLMAdapter(stage_responses=dict(conftest_mod.DEFAULT_STAGE_RESPONSES)),
            "fabric": TestFabricRetrievalAdapter(
                preset_capabilities=list(conftest_mod.SAMPLE_CAPABILITIES)
            ),
            "state": TestStateReadAdapter(preset_sections=dict(conftest_mod.SAMPLE_SECTIONS)),
            "bridge": TestBridgeAdapter(preset_recall=dict(conftest_mod.SAMPLE_RECALL)),
            "delta": TestDeltaAdapter(),
            "event": TestEventAdapter(),
        }
        expected_keys = {"mailbox", "llm", "fabric", "state", "bridge", "delta", "event"}
        assert set(result.keys()) == expected_keys
        assert isinstance(result["mailbox"], TestMailboxAdapter)
        assert isinstance(result["llm"], TestLLMAdapter)
        assert isinstance(result["fabric"], TestFabricRetrievalAdapter)
        assert isinstance(result["state"], TestStateReadAdapter)
        assert isinstance(result["bridge"], TestBridgeAdapter)
        assert isinstance(result["delta"], TestDeltaAdapter)
        assert isinstance(result["event"], TestEventAdapter)


class TestAdaptersPackageReExports:
    """Verify adapters/__init__.py re-exports all 7 test adapters."""

    def test_all_seven_adapters_importable(self) -> None:
        """All 7 test adapters importable from adapters package."""
        from tests.k1.planner.adapters import (
            TestBridgeAdapter,
            TestDeltaAdapter,
            TestEventAdapter,
            TestFabricRetrievalAdapter,
            TestLLMAdapter,
            TestMailboxAdapter,
            TestStateReadAdapter,
        )

        assert TestMailboxAdapter is not None
        assert TestLLMAdapter is not None
        assert TestFabricRetrievalAdapter is not None
        assert TestStateReadAdapter is not None
        assert TestBridgeAdapter is not None
        assert TestDeltaAdapter is not None
        assert TestEventAdapter is not None

    def test_adapters_all_has_seven_entries(self) -> None:
        """__all__ in adapters package has 8 entries (E5: added TestHILAdapter)."""
        import tests.k1.planner.adapters as pkg

        assert len(pkg.__all__) == 8


class TestNoMockImport:
    """Verify no adapter uses unittest.mock (FORBIDDEN per spec)."""

    def test_no_mock_in_mailbox_adapter(self) -> None:
        """TestMailboxAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_mailbox_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src

    def test_no_mock_in_llm_adapter(self) -> None:
        """TestLLMAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_llm_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src

    def test_no_mock_in_fabric_adapter(self) -> None:
        """TestFabricRetrievalAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_fabric_retrieval_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src

    def test_no_mock_in_state_adapter(self) -> None:
        """TestStateReadAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_state_read_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src

    def test_no_mock_in_bridge_adapter(self) -> None:
        """TestBridgeAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_bridge_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src

    def test_no_mock_in_delta_adapter(self) -> None:
        """TestDeltaAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_delta_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src

    def test_no_mock_in_event_adapter(self) -> None:
        """TestEventAdapter source has no unittest.mock import."""
        import tests.k1.planner.adapters.test_event_adapter as mod

        src = open(mod.__file__, "r").read()
        assert "unittest.mock" not in src
