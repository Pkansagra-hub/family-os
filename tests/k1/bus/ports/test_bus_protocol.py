"""
Tests for k1.bus.ports.bus -- IBus protocol and SubscriptionHandle.

Coverage targets:
    - SubscriptionHandle frozen dataclass
    - IBus structural subtyping (Protocol compliance)
    - isinstance check with @runtime_checkable
    - Minimal conforming implementation satisfies IBus
    - Non-conforming class does NOT satisfy IBus
"""

import pytest

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import BusHandler, IBus, SubscriptionHandle

# ===================================================================
# SubscriptionHandle
# ===================================================================


class TestSubscriptionHandle:
    """SubscriptionHandle frozen dataclass tests."""

    def test_creation(self) -> None:
        handle = SubscriptionHandle(subscription_id="sub-1", pattern="k1.test.*")
        assert handle.subscription_id == "sub-1"
        assert handle.pattern == "k1.test.*"

    def test_frozen(self) -> None:
        handle = SubscriptionHandle(subscription_id="sub-1", pattern="k1.test")
        with pytest.raises(AttributeError):
            handle.subscription_id = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        h1 = SubscriptionHandle(subscription_id="sub-1", pattern="k1.test")
        h2 = SubscriptionHandle(subscription_id="sub-1", pattern="k1.test")
        assert h1 == h2

    def test_inequality(self) -> None:
        h1 = SubscriptionHandle(subscription_id="sub-1", pattern="k1.test")
        h2 = SubscriptionHandle(subscription_id="sub-2", pattern="k1.test")
        assert h1 != h2


# ===================================================================
# IBus Protocol structural subtyping
# ===================================================================


class _ConformingBus:
    """Minimal class that satisfies IBus protocol."""

    def publish(self, envelope: Envelope) -> None:
        pass

    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id="test", pattern=pattern)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return True


class _NonConformingBus:
    """Class that does NOT satisfy IBus -- missing unsubscribe."""

    def publish(self, envelope: Envelope) -> None:
        pass

    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id="test", pattern=pattern)


class TestIBusProtocol:
    """IBus structural subtyping tests."""

    def test_conforming_class_is_instance(self) -> None:
        bus = _ConformingBus()
        assert isinstance(bus, IBus)

    def test_non_conforming_class_is_not_instance(self) -> None:
        bus = _NonConformingBus()
        assert not isinstance(bus, IBus)

    def test_protocol_publish_callable(self) -> None:
        bus = _ConformingBus()
        env = Envelope(topic="k1.test", payload=b"data")
        # Should not raise
        bus.publish(env)

    def test_protocol_subscribe_returns_handle(self) -> None:
        bus = _ConformingBus()
        handle = bus.subscribe("k1.test.*", lambda e: None)
        assert isinstance(handle, SubscriptionHandle)

    def test_protocol_unsubscribe_returns_bool(self) -> None:
        bus = _ConformingBus()
        handle = SubscriptionHandle(subscription_id="x", pattern="k1.test")
        result = bus.unsubscribe(handle)
        assert result is True


# ===================================================================
# BusHandler type alias
# ===================================================================


class TestBusHandler:
    """BusHandler callable type."""

    def test_lambda_is_valid_handler(self) -> None:
        def noop_handler(env: Envelope) -> None:
            pass

        handler: BusHandler = noop_handler
        env = Envelope(topic="k1.test")
        handler(env)  # Should not raise

    def test_function_is_valid_handler(self) -> None:
        def my_handler(envelope: Envelope) -> None:
            pass

        handler: BusHandler = my_handler
        handler(Envelope())  # Should not raise
