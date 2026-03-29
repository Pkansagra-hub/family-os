"""
Tests for EventSubscriptionAdapter (6.1.7) and TestMailboxAdapter (6.1.8).

Covers:
  - EventSubscriptionAdapter: subscribe, unsubscribe, emit, shutdown,
    handle tracking, error mapping to AdapterException.
  - TestMailboxAdapter: enqueue, dequeue, depth, peek_priority, inject,
    drain, assert_enqueued, assert_empty, FIFO ordering, unbounded.
  - Re-exports from adapters __init__.

References:
  - Issues 6.1.7 and 6.1.8 in orchestrator-implementation-plan.md
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException

# ===================================================================
# Fakes -- EventSubscriptionAdapter
# ===================================================================


class FakeEventPort:
    """In-memory IEventPort fake for testing EventSubscriptionAdapter."""

    def __init__(
        self,
        *,
        subscribe_fail: bool = False,
        unsubscribe_fail: bool = False,
        emit_fail: bool = False,
    ) -> None:
        self._next_id = 0
        self._subscribe_fail = subscribe_fail
        self._unsubscribe_fail = unsubscribe_fail
        self._emit_fail = emit_fail
        self.subscriptions: Dict[str, SubscriptionHandle] = {}
        self.emitted: List[Tuple[str, Dict[str, Any]]] = []

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        if self._subscribe_fail:
            raise RuntimeError("subscribe boom")
        self._next_id += 1
        handle = SubscriptionHandle(subscription_id=f"sub-{self._next_id}", topic=topic)
        self.subscriptions[handle.subscription_id] = handle
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        if self._unsubscribe_fail:
            raise RuntimeError("unsubscribe boom")
        if handle.subscription_id in self.subscriptions:
            del self.subscriptions[handle.subscription_id]
            return True
        return False

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._emit_fail:
            raise RuntimeError("emit boom")
        self.emitted.append((topic, dict(payload)))


# ===================================================================
# Simple message types for TestMailboxAdapter tests
# ===================================================================


class _MsgA:
    """Dummy message type A."""

    pass


class _MsgB:
    """Dummy message type B."""

    pass


# ===================================================================
# EventSubscriptionAdapter tests
# ===================================================================


class TestEventSubscriptionAdapterSubscribe:
    """Tests for EventSubscriptionAdapter.subscribe()."""

    def test_subscribe_success(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)

        handle = adapter.subscribe("k1.test.v1", lambda t, p: None)

        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "k1.test.v1"
        assert adapter.active_subscriptions == 1

    def test_subscribe_multiple_tracked(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)

        adapter.subscribe("k1.a.v1", lambda t, p: None)
        adapter.subscribe("k1.b.v1", lambda t, p: None)
        adapter.subscribe("k1.c.v1", lambda t, p: None)

        assert adapter.active_subscriptions == 3

    def test_subscribe_failure_raises_adapter_exception(self) -> None:
        ep = FakeEventPort(subscribe_fail=True)
        adapter = EventSubscriptionAdapter(ep)

        with pytest.raises(AdapterException) as exc_info:
            adapter.subscribe("k1.x.v1", lambda t, p: None)

        assert exc_info.value.adapter_name == "event_subscription"
        assert exc_info.value.error_code == "SUBSCRIBE_FAILED"


class TestEventSubscriptionAdapterUnsubscribe:
    """Tests for EventSubscriptionAdapter.unsubscribe()."""

    def test_unsubscribe_success(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)
        handle = adapter.subscribe("k1.test.v1", lambda t, p: None)

        result = adapter.unsubscribe(handle)

        assert result is True
        assert adapter.active_subscriptions == 0

    def test_unsubscribe_unknown_handle(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)

        unknown = SubscriptionHandle(subscription_id="nonexistent", topic="x")
        result = adapter.unsubscribe(unknown)

        assert result is False

    def test_unsubscribe_failure_raises_adapter_exception(self) -> None:
        ep = FakeEventPort(unsubscribe_fail=True)
        adapter = EventSubscriptionAdapter(ep)

        handle = SubscriptionHandle(subscription_id="x", topic="x")
        with pytest.raises(AdapterException) as exc_info:
            adapter.unsubscribe(handle)

        assert exc_info.value.error_code == "UNSUBSCRIBE_FAILED"


class TestEventSubscriptionAdapterEmit:
    """Tests for EventSubscriptionAdapter.emit()."""

    def test_emit_success(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)

        adapter.emit("k1.test.v1", {"key": "val"})

        assert len(ep.emitted) == 1
        assert ep.emitted[0] == ("k1.test.v1", {"key": "val"})

    def test_emit_failure_swallowed(self) -> None:
        ep = FakeEventPort(emit_fail=True)
        adapter = EventSubscriptionAdapter(ep)

        # fire-and-forget -- should NOT raise
        adapter.emit("k1.test.v1", {})


class TestEventSubscriptionAdapterShutdown:
    """Tests for EventSubscriptionAdapter.shutdown()."""

    def test_shutdown_unsubscribes_all(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)

        adapter.subscribe("k1.a.v1", lambda t, p: None)
        adapter.subscribe("k1.b.v1", lambda t, p: None)
        assert adapter.active_subscriptions == 2

        adapter.shutdown()

        assert adapter.active_subscriptions == 0
        # All subscriptions removed from fake event port
        assert len(ep.subscriptions) == 0

    def test_shutdown_tolerates_unsubscribe_failure(self) -> None:
        """If one unsubscribe fails during shutdown, others still proceed."""
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)

        adapter.subscribe("k1.a.v1", lambda t, p: None)
        adapter.subscribe("k1.b.v1", lambda t, p: None)

        # Make unsubscribe fail after initial subscribes
        ep._unsubscribe_fail = True

        # Should not raise
        adapter.shutdown()

        # Handles list cleared even though unsubscribes failed
        assert adapter.active_subscriptions == 0

    def test_shutdown_idempotent(self) -> None:
        ep = FakeEventPort()
        adapter = EventSubscriptionAdapter(ep)
        adapter.subscribe("k1.a.v1", lambda t, p: None)

        adapter.shutdown()
        adapter.shutdown()  # Second call is no-op

        assert adapter.active_subscriptions == 0


class TestEventSubscriptionAdapterSlots:
    """Structural checks."""

    def test_has_slots(self) -> None:
        assert hasattr(EventSubscriptionAdapter, "__slots__")
        assert "_event_port" in EventSubscriptionAdapter.__slots__
        assert "_handles" in EventSubscriptionAdapter.__slots__


# ===================================================================
# TestMailboxAdapter tests
# ===================================================================


class TestMailboxAdapterEnqueueDequeue:
    """Tests for TestMailboxAdapter enqueue/dequeue."""

    def test_enqueue_dequeue_fifo(self) -> None:
        mb = TestMailboxAdapter()
        msg1 = _MsgA()
        msg2 = _MsgB()

        mb.enqueue(msg1, "REALTIME")
        mb.enqueue(msg2, "BACKGROUND")

        # FIFO regardless of priority
        assert mb.dequeue() is msg1
        assert mb.dequeue() is msg2

    def test_dequeue_empty_returns_none(self) -> None:
        mb = TestMailboxAdapter()
        assert mb.dequeue() is None

    def test_enqueue_returns_zero(self) -> None:
        mb = TestMailboxAdapter()
        assert mb.enqueue(_MsgA()) == 0

    def test_enqueue_unbounded(self) -> None:
        """TestMailboxAdapter never raises MailboxFullError."""
        mb = TestMailboxAdapter()
        for i in range(500):
            mb.enqueue(_MsgA())
        assert mb.depth() == 500

    def test_enqueue_logs(self) -> None:
        mb = TestMailboxAdapter()
        msg = _MsgA()
        mb.enqueue(msg, "REALTIME")

        assert len(mb.enqueued_log) == 1
        assert mb.enqueued_log[0] == (msg, "REALTIME")


class TestMailboxAdapterDepth:
    """Tests for TestMailboxAdapter.depth()."""

    def test_depth_empty(self) -> None:
        mb = TestMailboxAdapter()
        assert mb.depth() == 0

    def test_depth_after_enqueue(self) -> None:
        mb = TestMailboxAdapter()
        mb.enqueue(_MsgA())
        mb.enqueue(_MsgB())
        assert mb.depth() == 2

    def test_depth_after_dequeue(self) -> None:
        mb = TestMailboxAdapter()
        mb.enqueue(_MsgA())
        mb.enqueue(_MsgB())
        mb.dequeue()
        assert mb.depth() == 1


class TestMailboxAdapterPeekPriority:
    """Tests for TestMailboxAdapter.peek_priority()."""

    def test_peek_empty(self) -> None:
        mb = TestMailboxAdapter()
        assert mb.peek_priority() is None

    def test_peek_returns_front_priority(self) -> None:
        mb = TestMailboxAdapter()
        mb.enqueue(_MsgA(), "REALTIME")
        mb.enqueue(_MsgB(), "BACKGROUND")

        assert mb.peek_priority() == "REALTIME"


class TestMailboxAdapterHelpers:
    """Tests for TestMailboxAdapter test helpers."""

    def test_inject(self) -> None:
        mb = TestMailboxAdapter()
        msg = _MsgA()
        mb.inject(msg, "BACKGROUND")

        assert mb.depth() == 1
        assert mb.dequeue() is msg

    def test_drain(self) -> None:
        mb = TestMailboxAdapter()
        m1 = _MsgA()
        m2 = _MsgB()
        mb.enqueue(m1)
        mb.enqueue(m2)

        result = mb.drain()

        assert result == [m1, m2]
        assert mb.depth() == 0

    def test_drain_empty(self) -> None:
        mb = TestMailboxAdapter()
        assert mb.drain() == []

    def test_assert_enqueued_pass(self) -> None:
        mb = TestMailboxAdapter()
        mb.enqueue(_MsgA())
        mb.enqueue(_MsgA())
        mb.enqueue(_MsgB())

        mb.assert_enqueued(_MsgA, count=2)
        mb.assert_enqueued(_MsgB, count=1)

    def test_assert_enqueued_fail(self) -> None:
        mb = TestMailboxAdapter()
        mb.enqueue(_MsgA())

        with pytest.raises(AssertionError, match="Expected 2"):
            mb.assert_enqueued(_MsgA, count=2)

    def test_assert_empty_pass(self) -> None:
        mb = TestMailboxAdapter()
        mb.assert_empty()

    def test_assert_empty_fail(self) -> None:
        mb = TestMailboxAdapter()
        mb.enqueue(_MsgA())

        with pytest.raises(AssertionError, match="1 messages remain"):
            mb.assert_empty()


class TestMailboxAdapterSlots:
    """Structural checks."""

    def test_has_slots(self) -> None:
        assert hasattr(TestMailboxAdapter, "__slots__")
        assert "messages" in TestMailboxAdapter.__slots__
        assert "enqueued_log" in TestMailboxAdapter.__slots__


# ===================================================================
# Re-export tests
# ===================================================================


class TestAdaptersReExports:
    """Verify adapters are importable from the package."""

    def test_event_subscription_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import EventSubscriptionAdapter as ESA

        assert ESA is EventSubscriptionAdapter

    def test_test_mailbox_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import TestMailboxAdapter as TMA

        assert TMA is TestMailboxAdapter
