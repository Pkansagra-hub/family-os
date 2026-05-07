"""
C2-prep Issue 4.3 — NullEventSubscriptionAdapter tests.

Validates null adapter satisfies IEventSubscriptionPort and routes nothing.
"""

from __future__ import annotations

from k1.concierge.adapters.null_event_subscription import NullEventSubscriptionAdapter
from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort


class TestNullEventSubscriptionProtocol:
    def test_satisfies_ieventsubscriptionport(self) -> None:
        assert isinstance(NullEventSubscriptionAdapter(), IEventSubscriptionPort)


class TestNullEventSubscriptionBehaviour:
    def test_subscribe_returns_handle(self) -> None:
        adapter = NullEventSubscriptionAdapter()
        handle = adapter.subscribe("k1.test.v1", lambda t, p: None)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "k1.test.v1"

    def test_unsubscribe_returns_false(self) -> None:
        adapter = NullEventSubscriptionAdapter()
        handle = SubscriptionHandle(subscription_id="x", topic="t")
        assert adapter.unsubscribe(handle) is False

    def test_emit_does_not_raise(self) -> None:
        adapter = NullEventSubscriptionAdapter()
        adapter.emit("k1.test.v1", {"key": "val"})

    def test_emit_does_not_call_handler(self) -> None:
        calls: list = []
        adapter = NullEventSubscriptionAdapter()
        adapter.subscribe("k1.test.v1", lambda t, p: calls.append((t, p)))
        adapter.emit("k1.test.v1", {"data": 1})
        # Null adapter does NOT route — handler must NOT be called
        assert calls == []
