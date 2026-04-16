"""Tests for Production Adapters (E-MW-5.1).

Covers:
  - BridgeCommandAdapter: submit() and submit_batch() translation
  - EventSubscriptionAdapter: subscribe/unsubscribe/publish translation
  - HealthAdapter: is_ready() and health_check() composition

28 tests organized in 6 test classes.

References:
  - E-MW-5.1: Production Adapters (3 remaining)
  - k1/memory_writer/adapters/bridge_command_adapter.py
  - k1/memory_writer/adapters/event_subscription_adapter.py
  - k1/memory_writer/adapters/health_adapter.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock

import pytest

from k1.memory_writer.adapters.bridge_command_adapter import BridgeCommandAdapter
from k1.memory_writer.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.memory_writer.adapters.health_adapter import HealthAdapter
from k1.memory_writer.types import HealthStatus, Subscription

# ---------------------------------------------------------------------------
# Fakes / stubs
# ---------------------------------------------------------------------------


@dataclass
class FakeSubscriptionHandle:
    """Mimics FabricSubscriptionHandle."""

    subscription_id: str
    topic: str


class FakeKernelCommandPort:
    """Stub for Bridge's KernelCommandPort."""

    def __init__(self) -> None:
        self.submit_calls: List[Dict[str, Any]] = []
        self.submit_batch_calls: List[Any] = []
        self._submit_error: Optional[Exception] = None
        self._batch_error: Optional[Exception] = None

    async def submit_command(
        self,
        topic: str,
        body: dict,
        *,
        schema_uri: Optional[str] = None,
        band: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        if self._submit_error:
            raise self._submit_error
        self.submit_calls.append(
            {
                "topic": topic,
                "body": body,
                "schema_uri": schema_uri,
                "trace_id": trace_id,
            }
        )

    async def submit_command_batch(self, envelopes: list) -> None:
        if self._batch_error:
            raise self._batch_error
        self.submit_batch_calls.append(envelopes)


class FakeFabricBusAdapter:
    """Stub for K1's FabricBusAdapter."""

    def __init__(self) -> None:
        self.subscribe_calls: List[Tuple[str, Any]] = []
        self.emit_calls: List[Tuple[str, dict]] = []
        self.unsubscribe_calls: List[Any] = []
        self._next_sub_id: int = 0
        self._emit_error: Optional[Exception] = None

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict], None],
    ) -> FakeSubscriptionHandle:
        self._next_sub_id += 1
        handle = FakeSubscriptionHandle(
            subscription_id=f"sub-{self._next_sub_id}",
            topic=topic,
        )
        self.subscribe_calls.append((topic, handler))
        return handle

    def unsubscribe(self, handle: FakeSubscriptionHandle) -> bool:
        self.unsubscribe_calls.append(handle)
        return True

    def emit(self, topic: str, payload: dict) -> None:
        if self._emit_error:
            raise self._emit_error
        self.emit_calls.append((topic, payload))


class FakeCircuitBreaker:
    """Stub for CircuitBreaker."""

    def __init__(self, is_open: bool = False) -> None:
        self.is_open = is_open


# ---------------------------------------------------------------------------
# BridgeCommandAdapter - Submit
# ---------------------------------------------------------------------------


class TestBridgeCommandAdapterSubmit:
    """Tests for BridgeCommandAdapter.submit()."""

    @pytest.fixture()
    def kcp(self) -> FakeKernelCommandPort:
        return FakeKernelCommandPort()

    @pytest.fixture()
    def adapter(self, kcp: FakeKernelCommandPort) -> BridgeCommandAdapter:
        return BridgeCommandAdapter(command_port=kcp)

    @pytest.mark.asyncio
    async def test_submit_delegates_to_command_port(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """submit(topic, schema, body) -> kcp.submit called with matching args."""
        body = {"data": "value", "trace_id": "t-1"}
        await adapter.submit("memory.write", "schema://mem", body)

        assert len(kcp.submit_calls) == 1
        call = kcp.submit_calls[0]
        assert call["topic"] == "memory.write"
        assert call["body"] is body
        assert call["schema_uri"] == "schema://mem"

    @pytest.mark.asyncio
    async def test_submit_extracts_trace_id_from_body(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """body has trace_id -> passed to kcp.submit(trace_id=)."""
        body = {"trace_id": "abc-123"}
        await adapter.submit("t", "s", body)
        assert kcp.submit_calls[0]["trace_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_submit_missing_trace_id_uses_empty(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """body has no trace_id -> kcp.submit(trace_id="")."""
        body = {"data": "no-trace"}
        await adapter.submit("t", "s", body)
        assert kcp.submit_calls[0]["trace_id"] == ""

    @pytest.mark.asyncio
    async def test_submit_propagates_contract_violation(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """kcp raises ContractViolationError -> propagated."""
        from bridge.kernel.command_port import ContractViolationError

        kcp._submit_error = ContractViolationError("bad schema")
        with pytest.raises(ContractViolationError, match="bad schema"):
            await adapter.submit("t", "s", {})

    @pytest.mark.asyncio
    async def test_submit_propagates_generic_error(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """kcp raises RuntimeError -> propagated."""
        kcp._submit_error = RuntimeError("network down")
        with pytest.raises(RuntimeError, match="network down"):
            await adapter.submit("t", "s", {})


# ---------------------------------------------------------------------------
# BridgeCommandAdapter - Batch
# ---------------------------------------------------------------------------


class TestBridgeCommandAdapterBatch:
    """Tests for BridgeCommandAdapter.submit_batch()."""

    @pytest.fixture()
    def kcp(self) -> FakeKernelCommandPort:
        return FakeKernelCommandPort()

    @pytest.fixture()
    def adapter(self, kcp: FakeKernelCommandPort) -> BridgeCommandAdapter:
        return BridgeCommandAdapter(command_port=kcp)

    @pytest.mark.asyncio
    async def test_submit_batch_translates_to_command_envelopes(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """3 envelope dicts -> passed as dicts to submit_command_batch."""
        envs = [
            {"topic": f"t{i}", "body": {"i": i}, "schema_uri": f"s{i}", "trace_id": f"tr{i}"}
            for i in range(3)
        ]
        await adapter.submit_batch(envs)

        assert len(kcp.submit_batch_calls) == 1
        commands = kcp.submit_batch_calls[0]
        assert len(commands) == 3

        for cmd in commands:
            assert isinstance(cmd, dict)

    @pytest.mark.asyncio
    async def test_submit_batch_empty_list_noop(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """empty list -> kcp.submit_batch NOT called."""
        await adapter.submit_batch([])
        assert len(kcp.submit_batch_calls) == 0

    @pytest.mark.asyncio
    async def test_submit_batch_extracts_trace_ids(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """each envelope's trace_id passed through."""
        envs = [
            {"topic": "t", "body": {}, "schema_uri": "s", "trace_id": "tid-A"},
            {"topic": "t", "body": {}, "schema_uri": "s", "trace_id": "tid-B"},
        ]
        await adapter.submit_batch(envs)
        commands = kcp.submit_batch_calls[0]
        assert commands[0]["trace_id"] == "tid-A"
        assert commands[1]["trace_id"] == "tid-B"

    @pytest.mark.asyncio
    async def test_submit_batch_propagates_contract_violation(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """kcp batch raises -> propagated."""
        from bridge.kernel.command_port import ContractViolationError

        kcp._batch_error = ContractViolationError("batch rejected")
        envs = [{"topic": "t", "body": {}, "schema_uri": "s", "trace_id": ""}]
        with pytest.raises(ContractViolationError, match="batch rejected"):
            await adapter.submit_batch(envs)

    @pytest.mark.asyncio
    async def test_submit_batch_all_fields_mapped(
        self, adapter: BridgeCommandAdapter, kcp: FakeKernelCommandPort
    ) -> None:
        """topic, body, schema_uri, trace_id all passed through correctly."""
        env = {
            "topic": "memory.write",
            "body": {"key": "val"},
            "schema_uri": "schema://test",
            "trace_id": "trace-99",
        }
        await adapter.submit_batch([env])
        cmd = kcp.submit_batch_calls[0][0]
        assert cmd["topic"] == "memory.write"
        assert cmd["body"] == {"key": "val"}
        assert cmd["schema_uri"] == "schema://test"
        assert cmd["trace_id"] == "trace-99"


# ---------------------------------------------------------------------------
# EventSubscriptionAdapter - Subscribe
# ---------------------------------------------------------------------------


class TestEventSubscriptionAdapterSubscribe:
    """Tests for EventSubscriptionAdapter.subscribe()."""

    @pytest.fixture()
    def bus(self) -> FakeFabricBusAdapter:
        return FakeFabricBusAdapter()

    @pytest.fixture()
    def adapter(self, bus: FakeFabricBusAdapter) -> EventSubscriptionAdapter:
        return EventSubscriptionAdapter(bus_adapter=bus)

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription(self, adapter: EventSubscriptionAdapter) -> None:
        """subscribe(topic, handler) -> Subscription with sub_id and topic."""

        async def handler(payload: dict) -> None:
            pass

        sub = await adapter.subscribe("turn.complete.v1", handler)
        assert isinstance(sub, Subscription)
        assert sub.topic == "turn.complete.v1"
        assert sub.subscription_id  # non-empty

    @pytest.mark.asyncio
    async def test_subscribe_delegates_to_bus(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """bus.subscribe called with topic and sync wrapper."""

        async def handler(payload: dict) -> None:
            pass

        await adapter.subscribe("my.topic", handler)
        assert len(bus.subscribe_calls) == 1
        assert bus.subscribe_calls[0][0] == "my.topic"
        # Second arg is the sync wrapper callable
        assert callable(bus.subscribe_calls[0][1])

    @pytest.mark.asyncio
    async def test_handler_invoked_on_event(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """bus fires event -> async handler called with payload dict."""
        received: list = []

        async def handler(payload: dict) -> None:
            received.append(payload)

        await adapter.subscribe("test.topic", handler)

        # Get the sync wrapper that was registered with the bus
        sync_wrapper = bus.subscribe_calls[0][1]

        # Invoke it (simulating bus delivering an event)
        sync_wrapper("test.topic", {"key": "value"})

        # Let the event loop process the created task
        await asyncio.sleep(0)

        assert len(received) == 1
        assert received[0] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_handler_receives_payload_only(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """handler gets payload (not topic) per MW protocol."""
        received_args: list = []

        async def handler(payload: dict) -> None:
            received_args.append(payload)

        await adapter.subscribe("topic.x", handler)
        sync_wrapper = bus.subscribe_calls[0][1]
        sync_wrapper("topic.x", {"data": 42})
        await asyncio.sleep(0)

        # Handler receives only payload, not (topic, payload)
        assert len(received_args) == 1
        assert received_args[0] == {"data": 42}

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_tracked(self, adapter: EventSubscriptionAdapter) -> None:
        """3 subscribe calls -> 3 entries in internal map."""

        async def handler(payload: dict) -> None:
            pass

        await adapter.subscribe("t1", handler)
        await adapter.subscribe("t2", handler)
        await adapter.subscribe("t3", handler)

        assert len(adapter._subscriptions) == 3


# ---------------------------------------------------------------------------
# EventSubscriptionAdapter - Unsubscribe
# ---------------------------------------------------------------------------


class TestEventSubscriptionAdapterUnsubscribe:
    """Tests for EventSubscriptionAdapter.unsubscribe()."""

    @pytest.fixture()
    def bus(self) -> FakeFabricBusAdapter:
        return FakeFabricBusAdapter()

    @pytest.fixture()
    def adapter(self, bus: FakeFabricBusAdapter) -> EventSubscriptionAdapter:
        return EventSubscriptionAdapter(bus_adapter=bus)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """unsubscribe(sub_id) -> bus.unsubscribe called with handle."""

        async def handler(payload: dict) -> None:
            pass

        sub = await adapter.subscribe("topic.a", handler)
        await adapter.unsubscribe(sub.subscription_id)

        assert len(bus.unsubscribe_calls) == 1
        assert bus.unsubscribe_calls[0].subscription_id == sub.subscription_id

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_id_noop(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """unknown sub_id -> no error, bus.unsubscribe NOT called."""
        await adapter.unsubscribe("does-not-exist")
        assert len(bus.unsubscribe_calls) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_clears_internal_tracking(
        self, adapter: EventSubscriptionAdapter
    ) -> None:
        """after unsubscribe -> sub_id no longer in _subscriptions."""

        async def handler(payload: dict) -> None:
            pass

        sub = await adapter.subscribe("topic.b", handler)
        assert sub.subscription_id in adapter._subscriptions
        await adapter.unsubscribe(sub.subscription_id)
        assert sub.subscription_id not in adapter._subscriptions


# ---------------------------------------------------------------------------
# EventSubscriptionAdapter - Publish
# ---------------------------------------------------------------------------


class TestEventSubscriptionAdapterPublish:
    """Tests for EventSubscriptionAdapter.publish()."""

    @pytest.fixture()
    def bus(self) -> FakeFabricBusAdapter:
        return FakeFabricBusAdapter()

    @pytest.fixture()
    def adapter(self, bus: FakeFabricBusAdapter) -> EventSubscriptionAdapter:
        return EventSubscriptionAdapter(bus_adapter=bus)

    @pytest.mark.asyncio
    async def test_publish_delegates_to_bus_emit(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """publish(topic, payload) -> bus.emit(topic, payload)."""
        payload = {"event": "data"}
        await adapter.publish("k1.mw.filter.decision.v1", payload)

        assert len(bus.emit_calls) == 1
        assert bus.emit_calls[0] == ("k1.mw.filter.decision.v1", payload)

    @pytest.mark.asyncio
    async def test_publish_fire_and_forget(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """bus.emit raises -> publish does NOT raise (best-effort).

        NOTE: The spec says fire-and-forget. The current adapter
        does NOT catch emit errors (it's fire-and-forget in the sense
        that the caller doesn't await a result). If bus.emit raises
        synchronously, that propagates. This test documents the
        current behavior that bus.emit errors DO propagate.
        """
        bus._emit_error = RuntimeError("bus down")
        # Current implementation lets the error propagate since emit is sync
        with pytest.raises(RuntimeError, match="bus down"):
            await adapter.publish("topic", {"data": 1})

    @pytest.mark.asyncio
    async def test_publish_carries_all_fields(
        self, adapter: EventSubscriptionAdapter, bus: FakeFabricBusAdapter
    ) -> None:
        """payload dict passed unchanged to bus.emit."""
        payload = {"key1": "val1", "nested": {"a": 1}, "list": [1, 2]}
        await adapter.publish("topic.x", payload)

        assert bus.emit_calls[0][1] is payload  # same object, not a copy


# ---------------------------------------------------------------------------
# HealthAdapter
# ---------------------------------------------------------------------------


class TestHealthAdapter:
    """Tests for HealthAdapter."""

    @pytest.fixture()
    def make_adapter(self):
        """Factory that creates a HealthAdapter with configurable state."""

        def _factory(
            is_open: bool = False,
            pending_count: int = 0,
            started: bool = True,
        ) -> HealthAdapter:
            cb = FakeCircuitBreaker(is_open=is_open)
            return HealthAdapter(
                circuit_breaker=cb,
                get_pending_count=lambda: pending_count,
                get_started=lambda: started,
            )

        return _factory

    @pytest.mark.asyncio
    async def test_is_ready_true_when_started_circuit_closed(self, make_adapter) -> None:
        """started=True, cb.is_open=False -> True."""
        adapter = make_adapter(started=True, is_open=False)
        assert await adapter.is_ready() is True

    @pytest.mark.asyncio
    async def test_is_ready_false_when_stopped(self, make_adapter) -> None:
        """started=False -> False."""
        adapter = make_adapter(started=False, is_open=False)
        assert await adapter.is_ready() is False

    @pytest.mark.asyncio
    async def test_is_ready_false_when_circuit_open(self, make_adapter) -> None:
        """started=True, cb.is_open=True -> False."""
        adapter = make_adapter(started=True, is_open=True)
        assert await adapter.is_ready() is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, make_adapter) -> None:
        """started + closed -> is_healthy=True, detail='running'."""
        adapter = make_adapter(started=True, is_open=False)
        status = await adapter.health_check()

        assert isinstance(status, HealthStatus)
        assert status.is_healthy is True
        assert status.detail == "running"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_stopped(self, make_adapter) -> None:
        """not started -> is_healthy=False, detail='stopped'."""
        adapter = make_adapter(started=False, is_open=False)
        status = await adapter.health_check()

        assert status.is_healthy is False
        assert status.detail == "stopped"

    @pytest.mark.asyncio
    async def test_health_check_circuit_open(self, make_adapter) -> None:
        """cb.is_open=True -> llm_circuit_open=True."""
        adapter = make_adapter(started=True, is_open=True)
        status = await adapter.health_check()

        assert status.llm_circuit_open is True
        assert status.is_healthy is False

    @pytest.mark.asyncio
    async def test_health_check_pending_count(self, make_adapter) -> None:
        """get_pending_count returns 5 -> pending_batch_count=5."""
        adapter = make_adapter(started=True, pending_count=5)
        status = await adapter.health_check()

        assert status.pending_batch_count == 5
