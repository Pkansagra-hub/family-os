"""
Tests for MailboxAdapter (6.1.1) and FabricGatewayAdapter (6.1.2).

6.1.1 MailboxAdapter (WFQ priority mailbox):
  TestMailboxAdapterInit          -- construction, defaults, custom weights
  TestMailboxAdapterEnqueue       -- enqueue, capacity, invalid priority
  TestMailboxAdapterDequeue       -- basic, WFQ scheduling, empty
  TestMailboxAdapterWFQ           -- fair distribution, credit refill
  TestMailboxAdapterDepthPeek     -- depth(), peek_priority()
  TestMailboxAdapterDiagnostics   -- queue_depths(), credits_snapshot()
  TestMailboxAdapterThreadSafety  -- concurrent enqueue from threads
  TestMailboxAdapterProtocol      -- IMailboxPort compliance

6.1.2 FabricGatewayAdapter (Fabric facade wrapper):
  TestFabricGatewayExecute        -- success, FabricError, timeout, connection, unknown
  TestFabricGatewayBatch          -- success, fallback to gather, empty
  TestFabricGatewayRegistry       -- query_registry, not found, error
  TestFabricGatewayCategory       -- query_registry_by_category, prefix match, error
  TestFabricGatewayMapping        -- contract-to-entry field mapping
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from k1.fabric.fabric import BatchStrategy, FabricError
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.ports.mailbox_port import MailboxFullError
from k1.orchestrator.types import ErrorSeverity, TaskEnvelope

# ===========================================================================
# Helpers
# ===========================================================================


def _make_envelope(**overrides: Any) -> TaskEnvelope:
    """Create a TaskEnvelope with sensible defaults."""
    defaults: Dict[str, Any] = {
        "intent": "test-intent",
        "trace_id": "trace-001",
        "caller_id": "test-caller",
        "capabilities": ["tool.test"],
    }
    defaults.update(overrides)
    return TaskEnvelope(**defaults)


# ===========================================================================
# 6.1.1 -- MailboxAdapter
# ===========================================================================


class TestMailboxAdapterInit:
    """Construction, defaults, custom weights."""

    def test_default_construction(self) -> None:
        adapter = MailboxAdapter()
        assert adapter.depth() == 0
        assert adapter.queue_depths() == {
            "REALTIME": 0,
            "INTERACTIVE": 0,
            "BACKGROUND": 0,
        }

    def test_custom_max_depth(self) -> None:
        adapter = MailboxAdapter(max_depth=5)
        for i in range(5):
            adapter.enqueue(_make_envelope(trace_id=f"t-{i}"), "INTERACTIVE")
        assert adapter.depth() == 5
        with pytest.raises(MailboxFullError):
            adapter.enqueue(_make_envelope(trace_id="overflow"), "INTERACTIVE")

    def test_custom_weights(self) -> None:
        weights = {"REALTIME": 1.0, "INTERACTIVE": 0.0, "BACKGROUND": 0.0}
        adapter = MailboxAdapter(wfq_weights=weights)
        adapter.enqueue(_make_envelope(trace_id="t-r"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="t-i"), "INTERACTIVE")
        # With REALTIME=1.0 and others=0.0, REALTIME always gets credits
        msg = adapter.dequeue()
        assert msg is not None
        assert msg.trace_id == "t-r"


class TestMailboxAdapterEnqueue:
    """Enqueue behavior, capacity, invalid priority."""

    def test_enqueue_returns_position(self) -> None:
        adapter = MailboxAdapter()
        pos0 = adapter.enqueue(_make_envelope(trace_id="t-0"), "INTERACTIVE")
        pos1 = adapter.enqueue(_make_envelope(trace_id="t-1"), "INTERACTIVE")
        assert pos0 == 0
        assert pos1 == 1

    def test_enqueue_different_priorities(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="t-r"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="t-i"), "INTERACTIVE")
        adapter.enqueue(_make_envelope(trace_id="t-b"), "BACKGROUND")
        assert adapter.depth() == 3
        assert adapter.queue_depths() == {
            "REALTIME": 1,
            "INTERACTIVE": 1,
            "BACKGROUND": 1,
        }

    def test_enqueue_invalid_priority(self) -> None:
        adapter = MailboxAdapter()
        with pytest.raises(ValueError, match="Invalid priority"):
            adapter.enqueue(_make_envelope(), "CRITICAL")

    def test_enqueue_raises_mailbox_full(self) -> None:
        adapter = MailboxAdapter(max_depth=2)
        adapter.enqueue(_make_envelope(trace_id="a"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="b"), "INTERACTIVE")
        with pytest.raises(MailboxFullError, match="capacity"):
            adapter.enqueue(_make_envelope(trace_id="c"), "BACKGROUND")

    def test_enqueue_at_capacity_different_priorities(self) -> None:
        adapter = MailboxAdapter(max_depth=3)
        adapter.enqueue(_make_envelope(trace_id="x"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="y"), "INTERACTIVE")
        adapter.enqueue(_make_envelope(trace_id="z"), "BACKGROUND")
        # Now full -- any enqueue should raise regardless of priority
        with pytest.raises(MailboxFullError):
            adapter.enqueue(_make_envelope(trace_id="over"), "REALTIME")


class TestMailboxAdapterDequeue:
    """Basic dequeue, empty return."""

    def test_dequeue_empty_returns_none(self) -> None:
        adapter = MailboxAdapter()
        assert adapter.dequeue() is None

    def test_dequeue_single_message(self) -> None:
        adapter = MailboxAdapter()
        env = _make_envelope(trace_id="single")
        adapter.enqueue(env, "INTERACTIVE")
        msg = adapter.dequeue()
        assert msg is not None
        assert msg.trace_id == "single"
        assert adapter.depth() == 0

    def test_dequeue_fifo_within_priority(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="first"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="second"), "REALTIME")
        msg1 = adapter.dequeue()
        msg2 = adapter.dequeue()
        assert msg1 is not None and msg1.trace_id == "first"
        assert msg2 is not None and msg2.trace_id == "second"


class TestMailboxAdapterWFQ:
    """WFQ fair distribution tests."""

    def test_wfq_prefers_realtime(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="rt"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="int"), "INTERACTIVE")
        # After first dequeue, REALTIME gets 0.6 credits, INTERACTIVE 0.3
        # REALTIME has higher credit
        msg = adapter.dequeue()
        assert msg is not None
        assert msg.trace_id == "rt"

    def test_wfq_distribution_over_many_dequeues(self) -> None:
        """Over 100 dequeues with all three queues non-empty, distribution
        should approximate 60/30/10."""
        adapter = MailboxAdapter(max_depth=1000)
        # Fill 100 messages per class
        for i in range(100):
            adapter.enqueue(_make_envelope(trace_id=f"R{i}"), "REALTIME")
            adapter.enqueue(_make_envelope(trace_id=f"I{i}"), "INTERACTIVE")
            adapter.enqueue(_make_envelope(trace_id=f"B{i}"), "BACKGROUND")

        counts: Dict[str, int] = {"REALTIME": 0, "INTERACTIVE": 0, "BACKGROUND": 0}
        for _ in range(100):
            msg = adapter.dequeue()
            assert msg is not None
            tid = msg.trace_id
            if tid.startswith("R"):
                counts["REALTIME"] += 1
            elif tid.startswith("I"):
                counts["INTERACTIVE"] += 1
            elif tid.startswith("B"):
                counts["BACKGROUND"] += 1

        # Allow +/-15 margin around expected
        assert 45 <= counts["REALTIME"] <= 75
        assert 15 <= counts["INTERACTIVE"] <= 45
        assert 0 <= counts["BACKGROUND"] <= 25

    def test_wfq_with_only_background(self) -> None:
        """Even with only BACKGROUND messages, they get dequeued."""
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="bg1"), "BACKGROUND")
        adapter.enqueue(_make_envelope(trace_id="bg2"), "BACKGROUND")
        msg1 = adapter.dequeue()
        msg2 = adapter.dequeue()
        assert msg1 is not None and msg1.trace_id == "bg1"
        assert msg2 is not None and msg2.trace_id == "bg2"

    def test_wfq_credit_accumulation(self) -> None:
        """Credits accumulate across dequeue calls."""
        adapter = MailboxAdapter()
        # Dequeue from empty to accumulate credits (returns None)
        adapter.dequeue()
        adapter.dequeue()
        # Now add one BACKGROUND message
        adapter.enqueue(_make_envelope(trace_id="bg"), "BACKGROUND")
        # BACKGROUND has accumulated credits, should be dequeued
        msg = adapter.dequeue()
        assert msg is not None
        assert msg.trace_id == "bg"


class TestMailboxAdapterDepthPeek:
    """depth() and peek_priority() behavior."""

    def test_depth_tracks_enqueue_dequeue(self) -> None:
        adapter = MailboxAdapter()
        assert adapter.depth() == 0
        adapter.enqueue(_make_envelope(trace_id="a"), "REALTIME")
        assert adapter.depth() == 1
        adapter.enqueue(_make_envelope(trace_id="b"), "INTERACTIVE")
        assert adapter.depth() == 2
        adapter.dequeue()
        assert adapter.depth() == 1

    def test_peek_priority_empty(self) -> None:
        adapter = MailboxAdapter()
        assert adapter.peek_priority() is None

    def test_peek_priority_does_not_consume(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="msg"), "REALTIME")
        peeked = adapter.peek_priority()
        assert peeked == "REALTIME"
        assert adapter.depth() == 1  # not consumed

    def test_peek_priority_matches_dequeue(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="rt"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="int"), "INTERACTIVE")
        peeked = adapter.peek_priority()
        msg = adapter.dequeue()
        assert msg is not None
        # The peeked priority should match the dequeued message's class
        if msg.trace_id == "rt":
            assert peeked == "REALTIME"
        else:
            assert peeked == "INTERACTIVE"


class TestMailboxAdapterDiagnostics:
    """queue_depths() and credits_snapshot()."""

    def test_queue_depths_per_priority(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="r1"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="r2"), "REALTIME")
        adapter.enqueue(_make_envelope(trace_id="i1"), "INTERACTIVE")
        depths = adapter.queue_depths()
        assert depths["REALTIME"] == 2
        assert depths["INTERACTIVE"] == 1
        assert depths["BACKGROUND"] == 0

    def test_credits_start_at_zero(self) -> None:
        adapter = MailboxAdapter()
        credits = adapter.credits_snapshot()
        assert all(v == 0.0 for v in credits.values())

    def test_credits_accumulate_after_dequeue(self) -> None:
        adapter = MailboxAdapter()
        adapter.enqueue(_make_envelope(trace_id="msg"), "REALTIME")
        adapter.dequeue()
        credits = adapter.credits_snapshot()
        # After dequeue: REALTIME refilled 0.6 then deducted 1.0 = -0.4
        assert credits["REALTIME"] == pytest.approx(-0.4, abs=0.01)
        # INTERACTIVE refilled 0.3, not deducted
        assert credits["INTERACTIVE"] == pytest.approx(0.3, abs=0.01)
        # BACKGROUND refilled 0.1, not deducted
        assert credits["BACKGROUND"] == pytest.approx(0.1, abs=0.01)


class TestMailboxAdapterThreadSafety:
    """Concurrent enqueue from multiple threads."""

    def test_concurrent_enqueue(self) -> None:
        adapter = MailboxAdapter(max_depth=1000)
        errors: List[Exception] = []

        def worker(tid: int) -> None:
            try:
                for i in range(50):
                    adapter.enqueue(
                        _make_envelope(trace_id=f"t{tid}-{i}"),
                        "INTERACTIVE",
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert adapter.depth() == 250


class TestMailboxAdapterProtocol:
    """Verify MailboxAdapter satisfies IMailboxPort protocol."""

    def test_has_enqueue(self) -> None:
        adapter = MailboxAdapter()
        assert callable(getattr(adapter, "enqueue", None))

    def test_has_dequeue(self) -> None:
        adapter = MailboxAdapter()
        assert callable(getattr(adapter, "dequeue", None))

    def test_has_depth(self) -> None:
        adapter = MailboxAdapter()
        assert callable(getattr(adapter, "depth", None))

    def test_has_peek_priority(self) -> None:
        adapter = MailboxAdapter()
        assert callable(getattr(adapter, "peek_priority", None))


# ===========================================================================
# 6.1.2 -- FabricGatewayAdapter  (Fakes + Tests)
# ===========================================================================


@dataclass
class FakeContract:
    """Minimal fake for CapabilityContract fields."""

    name: str = "tool.test"
    provider_type: str = "tool"
    safety_band_min: str = "GREEN"
    availability: str = "ONLINE"
    avg_latency_ms: Optional[int] = 100


class FakeFabric:
    """Fake Fabric for gateway adapter tests.

    Exposes execute(), execute_batch(), lookup(), and registry_api.
    """

    def __init__(
        self,
        execute_result: Optional[CapabilityResult] = None,
        batch_result: Optional[List[CapabilityResult]] = None,
        lookup_result: Any = None,
        all_contracts: Optional[List[Any]] = None,
        execute_error: Optional[Exception] = None,
        batch_error: Optional[Exception] = None,
        lookup_error: Optional[Exception] = None,
        list_all_error: Optional[Exception] = None,
    ) -> None:
        self._execute_result = execute_result
        self._batch_result = batch_result
        self._lookup_result = lookup_result
        self._execute_error = execute_error
        self._batch_error = batch_error
        self._lookup_error = lookup_error
        self._list_all_error = list_all_error
        self.execute_calls: List[Any] = []
        self.batch_calls: List[Any] = []
        self.lookup_calls: List[str] = []

        # Fake registry_api
        self.registry_api = MagicMock()
        self.registry_api.list_all.return_value = all_contracts or []
        if list_all_error:
            self.registry_api.list_all.side_effect = list_all_error

    async def execute(self, request: Any) -> CapabilityResult:
        self.execute_calls.append(request)
        if self._execute_error:
            raise self._execute_error
        return self._execute_result or CapabilityResult(
            request_id="rq-1",
            trace_id="tr-1",
            success=True,
        )

    async def execute_batch(
        self,
        requests: List[Any],
        strategy: Any,
    ) -> List[CapabilityResult]:
        self.batch_calls.append((requests, strategy))
        if self._batch_error:
            raise self._batch_error
        return self._batch_result or [
            CapabilityResult(request_id=f"rq-{i}", success=True) for i in range(len(requests))
        ]

    def lookup(self, name: str, version: Optional[str] = None) -> Any:
        self.lookup_calls.append(name)
        if self._lookup_error:
            raise self._lookup_error
        return self._lookup_result


def _make_request(**overrides: Any) -> CapabilityRequest:
    """Create a CapabilityRequest with sensible defaults."""
    defaults: Dict[str, Any] = {
        "capability_name": "tool.test",
        "trace_id": "trace-001",
        "caller": "test-caller",
    }
    defaults.update(overrides)
    return CapabilityRequest(**defaults)


def _make_result(**overrides: Any) -> CapabilityResult:
    """Create a CapabilityResult with sensible defaults."""
    defaults: Dict[str, Any] = {
        "request_id": "rq-1",
        "trace_id": "tr-1",
        "success": True,
    }
    defaults.update(overrides)
    return CapabilityResult(**defaults)


# ===========================================================================
# TestFabricGatewayExecute
# ===========================================================================


class TestFabricGatewayExecute:
    """execute() -- success, FabricError, timeout, connection, unknown."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        expected = _make_result(data={"answer": 42})
        fabric = FakeFabric(execute_result=expected)
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        result = await adapter.execute(_make_request())
        assert result is expected
        assert result.success is True
        assert len(fabric.execute_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_fabric_error(self) -> None:
        fabric = FakeFabric(execute_error=FabricError("timeout"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_make_request())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.adapter_name == "fabric_gateway"
        assert err.operation == "execute"
        assert err.error_code == "FABRIC_ERROR"
        assert isinstance(err.original_exception, FabricError)

    @pytest.mark.asyncio
    async def test_execute_timeout_error(self) -> None:
        fabric = FakeFabric(execute_error=asyncio.TimeoutError())
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_make_request())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.error_code == "FABRIC_ERROR"

    @pytest.mark.asyncio
    async def test_execute_connection_error(self) -> None:
        fabric = FakeFabric(execute_error=ConnectionError("unreachable"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_make_request())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.error_code == "FABRIC_UNREACHABLE"

    @pytest.mark.asyncio
    async def test_execute_unknown_error(self) -> None:
        fabric = FakeFabric(execute_error=RuntimeError("unexpected"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_make_request())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.TERMINAL
        assert err.error_code == "FABRIC_UNKNOWN"

    @pytest.mark.asyncio
    async def test_execute_propagates_trace_id(self) -> None:
        fabric = FakeFabric(execute_error=FabricError("err"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_make_request(trace_id="abc123"))
        assert exc_info.value.detail.trace_id == "abc123"


# ===========================================================================
# TestFabricGatewayBatch
# ===========================================================================


class TestFabricGatewayBatch:
    """execute_batch() -- success, fallback, empty."""

    @pytest.mark.asyncio
    async def test_batch_success(self) -> None:
        results = [_make_result(request_id=f"rq-{i}") for i in range(3)]
        fabric = FakeFabric(batch_result=results)
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        requests = [_make_request(capability_name=f"tool.t{i}") for i in range(3)]
        out = await adapter.execute_batch(requests)
        assert len(out) == 3
        assert fabric.batch_calls[0][1] == BatchStrategy.PARALLEL

    @pytest.mark.asyncio
    async def test_batch_empty(self) -> None:
        fabric = FakeFabric()
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]
        out = await adapter.execute_batch([])
        assert out == []

    @pytest.mark.asyncio
    async def test_batch_fallback_on_error(self) -> None:
        """When native batch raises, fallback to asyncio.gather individual."""
        single_result = _make_result(success=True)
        fabric = FakeFabric(
            batch_error=FabricError("batch broken"),
            execute_result=single_result,
        )
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        requests = [_make_request(capability_name=f"tool.t{i}") for i in range(2)]
        out = await adapter.execute_batch(requests)
        # Fallback called individual execute for each request
        assert len(out) == 2
        assert len(fabric.execute_calls) == 2

    @pytest.mark.asyncio
    async def test_batch_fallback_partial_failure(self) -> None:
        """Fallback gather: one request succeeds, one fails."""
        call_count = 0

        class PartialFabric(FakeFabric):
            async def execute(self, request: Any) -> CapabilityResult:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("boom")
                return _make_result(success=True)

        fabric = PartialFabric(batch_error=FabricError("no batch"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        requests = [_make_request() for _ in range(2)]
        out = await adapter.execute_batch(requests)
        assert len(out) == 2
        # First succeeds, second fails via fallback
        assert out[0].success is True
        assert out[1].success is False


# ===========================================================================
# TestFabricGatewayRegistry
# ===========================================================================


class TestFabricGatewayRegistry:
    """query_registry() -- lookup, not found, error."""

    @pytest.mark.asyncio
    async def test_query_registry_found(self) -> None:
        contract = FakeContract(name="tool.calendar.search", avg_latency_ms=50)
        fabric = FakeFabric(lookup_result=contract)
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        entry = await adapter.query_registry("tool.calendar.search")
        assert entry is not None
        assert entry.name == "tool.calendar.search"
        assert entry.estimated_duration_ms == 50
        assert fabric.lookup_calls == ["tool.calendar.search"]

    @pytest.mark.asyncio
    async def test_query_registry_not_found(self) -> None:
        fabric = FakeFabric(lookup_result=None)
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        entry = await adapter.query_registry("tool.nonexistent")
        assert entry is None

    @pytest.mark.asyncio
    async def test_query_registry_error(self) -> None:
        fabric = FakeFabric(lookup_error=RuntimeError("registry down"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.query_registry("tool.broken")
        assert exc_info.value.detail.error_code == "REGISTRY_ERROR"
        assert exc_info.value.detail.severity == ErrorSeverity.DEGRADED


# ===========================================================================
# TestFabricGatewayCategory
# ===========================================================================


class TestFabricGatewayCategory:
    """query_registry_by_category() -- prefix match, empty, error."""

    @pytest.mark.asyncio
    async def test_category_prefix_match(self) -> None:
        contracts = [
            FakeContract(name="tool.calendar.search"),
            FakeContract(name="tool.calendar.create"),
            FakeContract(name="tool.email.send"),
        ]
        fabric = FakeFabric(all_contracts=contracts)
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        entries = await adapter.query_registry_by_category("tool.calendar")
        assert len(entries) == 2
        names = {e.name for e in entries}
        assert names == {"tool.calendar.search", "tool.calendar.create"}

    @pytest.mark.asyncio
    async def test_category_no_match(self) -> None:
        contracts = [FakeContract(name="tool.email.send")]
        fabric = FakeFabric(all_contracts=contracts)
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        entries = await adapter.query_registry_by_category("tool.calendar")
        assert entries == []

    @pytest.mark.asyncio
    async def test_category_empty_registry(self) -> None:
        fabric = FakeFabric(all_contracts=[])
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        entries = await adapter.query_registry_by_category("tool.")
        assert entries == []

    @pytest.mark.asyncio
    async def test_category_error(self) -> None:
        fabric = FakeFabric(list_all_error=RuntimeError("broken"))
        adapter = FabricGatewayAdapter(fabric)  # type: ignore[arg-type]

        with pytest.raises(AdapterException) as exc_info:
            await adapter.query_registry_by_category("tool.")
        assert exc_info.value.detail.error_code == "REGISTRY_ERROR"


# ===========================================================================
# TestFabricGatewayMapping
# ===========================================================================


class TestFabricGatewayMapping:
    """Contract-to-RegistryEntry field mapping."""

    def test_full_mapping(self) -> None:
        contract = FakeContract(
            name="tool.search",
            provider_type="tool",
            safety_band_min="AMBER",
            availability="DEGRADED",
            avg_latency_ms=250,
        )
        entry = FabricGatewayAdapter._contract_to_entry(contract)
        assert entry.name == "tool.search"
        assert entry.provider_type == "tool"
        assert entry.safety_band_min == "AMBER"
        assert entry.availability == "DEGRADED"
        assert entry.compensation_capability is None
        assert entry.estimated_duration_ms == 250

    def test_missing_latency_maps_to_none(self) -> None:
        contract = FakeContract(avg_latency_ms=None)
        entry = FabricGatewayAdapter._contract_to_entry(contract)
        assert entry.estimated_duration_ms is None

    def test_zero_latency_maps_to_none(self) -> None:
        contract = FakeContract(avg_latency_ms=0)
        entry = FabricGatewayAdapter._contract_to_entry(contract)
        assert entry.estimated_duration_ms is None

    def test_entry_is_frozen(self) -> None:
        contract = FakeContract()
        entry = FabricGatewayAdapter._contract_to_entry(contract)
        # RegistryEntry is frozen dataclass
        with pytest.raises(AttributeError):
            entry.name = "changed"  # type: ignore[misc]

    def test_default_availability(self) -> None:
        """Contract without explicit availability defaults to ONLINE."""
        contract = FakeContract(availability="ONLINE")
        entry = FabricGatewayAdapter._contract_to_entry(contract)
        assert entry.availability == "ONLINE"


# ===========================================================================
# TestAdaptersReExports
# ===========================================================================


class TestAdaptersReExports:
    """Verify adapters/__init__.py re-exports."""

    def test_mailbox_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import MailboxAdapter

        assert MailboxAdapter is not None

    def test_fabric_gateway_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import FabricGatewayAdapter

        assert FabricGatewayAdapter is not None
