"""
Tests for k1.bus.middleware -- Middleware Protocol + MiddlewareChain.

Also includes LocalBus integration tests verifying that the middleware chain
runs correctly in the publish path.

Covers:
    MiddlewareChain:
        - Empty chain passes through
        - Single middleware applies
        - Multiple middlewares run in order
        - Middleware returning None drops envelope
        - Drop short-circuits (subsequent middlewares not called)
        - append/prepend ordering
        - size/len/repr

    LocalBus + Middleware integration:
        - Middleware runs after stamping
        - Middleware can modify envelope headers
        - Middleware drop prevents handler dispatch
        - Middleware exceptions are caught (envelope dropped)
        - Capture mode records post-middleware envelope
        - Factory creates bus with middleware
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from k1.bus.envelope import Envelope
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.bus.middleware import Middleware, MiddlewareChain

# ---------------------------------------------------------------------------
# Test helpers: concrete middleware implementations
# ---------------------------------------------------------------------------


class PassthroughMiddleware:
    """Always returns the envelope unchanged."""

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        return envelope


class DropMiddleware:
    """Always drops the envelope (returns None)."""

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        return None


class RecordingMiddleware:
    """Records all envelopes it sees."""

    def __init__(self) -> None:
        self.seen: list[Envelope] = []

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        self.seen.append(envelope)
        return envelope


class ModifyTopicMiddleware:
    """Replaces the topic with a fixed value (header-only modification)."""

    def __init__(self, new_topic: str) -> None:
        self._new_topic = new_topic

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        return replace(envelope, topic=self._new_topic)


class ErrorMiddleware:
    """Raises an exception when processing."""

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        raise RuntimeError("middleware failure")


# ---------------------------------------------------------------------------
# MiddlewareChain tests
# ---------------------------------------------------------------------------


class TestMiddlewareChainEmpty:
    """Empty chain is a pass-through."""

    def test_empty_chain_returns_envelope(self) -> None:
        chain = MiddlewareChain()
        env = Envelope(topic="test", payload=b"x")
        assert chain.process(env) is env

    def test_empty_chain_size(self) -> None:
        chain = MiddlewareChain()
        assert chain.size == 0
        assert len(chain) == 0

    def test_empty_chain_repr(self) -> None:
        chain = MiddlewareChain()
        assert "empty" in repr(chain)

    def test_none_middlewares_creates_empty(self) -> None:
        chain = MiddlewareChain(None)
        assert chain.size == 0


class TestMiddlewareChainSingle:
    """Chain with a single middleware."""

    def test_passthrough(self) -> None:
        chain = MiddlewareChain([PassthroughMiddleware()])
        env = Envelope(topic="test", payload=b"x")
        assert chain.process(env) is env

    def test_drop(self) -> None:
        chain = MiddlewareChain([DropMiddleware()])
        env = Envelope(topic="test", payload=b"x")
        assert chain.process(env) is None

    def test_recording(self) -> None:
        recorder = RecordingMiddleware()
        chain = MiddlewareChain([recorder])
        env = Envelope(topic="test", payload=b"x")
        chain.process(env)
        assert len(recorder.seen) == 1
        assert recorder.seen[0] is env


class TestMiddlewareChainMultiple:
    """Chain with multiple middlewares."""

    def test_all_passthrough(self) -> None:
        chain = MiddlewareChain(
            [
                PassthroughMiddleware(),
                PassthroughMiddleware(),
                PassthroughMiddleware(),
            ]
        )
        env = Envelope(topic="test", payload=b"x")
        assert chain.process(env) is env

    def test_order_matters(self) -> None:
        """Middlewares run in insertion order."""
        r1 = RecordingMiddleware()
        r2 = RecordingMiddleware()
        chain = MiddlewareChain([r1, r2])
        env = Envelope(topic="test", payload=b"x")
        chain.process(env)
        assert len(r1.seen) == 1
        assert len(r2.seen) == 1
        assert r1.seen[0] is env
        assert r2.seen[0] is env

    def test_drop_short_circuits(self) -> None:
        """Drop in middleware N prevents middleware N+1 from running."""
        recorder = RecordingMiddleware()
        chain = MiddlewareChain([DropMiddleware(), recorder])
        env = Envelope(topic="test", payload=b"x")
        result = chain.process(env)
        assert result is None
        assert len(recorder.seen) == 0  # Never reached

    def test_modify_propagates(self) -> None:
        """Middleware can modify headers; downstream sees modified envelope."""
        recorder = RecordingMiddleware()
        chain = MiddlewareChain(
            [
                ModifyTopicMiddleware("k1.modified"),
                recorder,
            ]
        )
        env = Envelope(topic="k1.original", payload=b"x")
        result = chain.process(env)
        assert result is not None
        assert result.topic == "k1.modified"
        assert recorder.seen[0].topic == "k1.modified"


class TestMiddlewareChainAppendPrepend:
    """append() and prepend() modify the chain."""

    def test_append(self) -> None:
        chain = MiddlewareChain()
        chain.append(PassthroughMiddleware())
        assert chain.size == 1

    def test_prepend(self) -> None:
        recorder = RecordingMiddleware()
        chain = MiddlewareChain([recorder])
        chain.prepend(DropMiddleware())
        env = Envelope(topic="test", payload=b"x")
        result = chain.process(env)
        assert result is None  # Drop runs first
        assert len(recorder.seen) == 0  # Recorder never reached

    def test_repr_shows_names(self) -> None:
        chain = MiddlewareChain(
            [
                PassthroughMiddleware(),
                RecordingMiddleware(),
            ]
        )
        r = repr(chain)
        assert "PassthroughMiddleware" in r
        assert "RecordingMiddleware" in r


class TestMiddlewareProtocolConformance:
    """All test helpers satisfy the Middleware Protocol."""

    def test_passthrough_is_middleware(self) -> None:
        assert isinstance(PassthroughMiddleware(), Middleware)

    def test_drop_is_middleware(self) -> None:
        assert isinstance(DropMiddleware(), Middleware)

    def test_recording_is_middleware(self) -> None:
        assert isinstance(RecordingMiddleware(), Middleware)

    def test_modify_is_middleware(self) -> None:
        assert isinstance(ModifyTopicMiddleware("t"), Middleware)


# ---------------------------------------------------------------------------
# LocalBus + Middleware integration
# ---------------------------------------------------------------------------


class TestLocalBusMiddlewareIntegration:
    """Middleware chain integrated into LocalBus.publish()."""

    def test_middleware_runs_after_stamping(self) -> None:
        """Middleware sees bus-stamped envelope_id and created_ns.

        Per M7.1.3 / B02: ``sequence`` is a placeholder (0) inside
        middleware and is only allocated after middleware passes, so
        that middleware-dropped envelopes do not consume sequence
        numbers (which would create gaps for STRICT timing chains).
        Handlers downstream still see ``sequence > 0``.
        """
        recorder = RecordingMiddleware()
        delivered: list[Envelope] = []
        chain = MiddlewareChain([recorder])
        bus = LocalBus(capture=True, middleware=chain)
        bus.subscribe("k1.test", delivered.append)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(recorder.seen) == 1
        assert recorder.seen[0].envelope_id > 0
        assert recorder.seen[0].sequence == 0  # placeholder during middleware
        assert recorder.seen[0].created_ns > 0
        # Handler sees the final stamped envelope with real sequence.
        assert len(delivered) == 1
        assert delivered[0].sequence > 0

    def test_middleware_drop_prevents_handler_dispatch(self) -> None:
        """When middleware drops, handlers are NOT called."""
        delivered: list[Envelope] = []
        chain = MiddlewareChain([DropMiddleware()])
        bus = LocalBus(middleware=chain)
        bus.subscribe("k1.test", delivered.append)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(delivered) == 0

    def test_middleware_drop_prevents_capture(self) -> None:
        """Dropped envelopes are NOT captured."""
        chain = MiddlewareChain([DropMiddleware()])
        bus = LocalBus(capture=True, middleware=chain)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(bus.captured) == 0

    def test_middleware_drop_does_not_increment_published(self) -> None:
        """Dropped envelopes are NOT counted as published."""
        chain = MiddlewareChain([DropMiddleware()])
        bus = LocalBus(middleware=chain)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert bus.stats.envelopes_published == 0

    def test_passthrough_middleware_delivers_normally(self) -> None:
        """Passthrough middleware does not interfere with dispatch."""
        delivered: list[Envelope] = []
        chain = MiddlewareChain([PassthroughMiddleware()])
        bus = LocalBus(capture=True, middleware=chain)
        bus.subscribe("k1.test", delivered.append)
        bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(delivered) == 1
        assert len(bus.captured) == 1
        assert bus.stats.envelopes_published == 1

    def test_middleware_exception_drops_envelope(self) -> None:
        """If middleware raises, envelope is dropped (not dispatched)."""
        delivered: list[Envelope] = []
        chain = MiddlewareChain([ErrorMiddleware()])
        bus = LocalBus(capture=True, middleware=chain)
        bus.subscribe("k1.test", delivered.append)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(delivered) == 0
        assert len(bus.captured) == 0

    def test_capture_records_post_middleware_envelope(self) -> None:
        """Capture records the envelope AFTER middleware processing."""
        chain = MiddlewareChain([ModifyTopicMiddleware("k1.modified")])
        bus = LocalBus(capture=True, middleware=chain)
        bus.subscribe("k1.modified", lambda e: None)
        bus.publish(Envelope(topic="k1.original", payload=b"x"))
        assert len(bus.captured) == 1
        assert bus.captured[0].topic == "k1.modified"

    def test_middleware_property(self) -> None:
        chain = MiddlewareChain([PassthroughMiddleware()])
        bus = LocalBus(middleware=chain)
        assert bus.middleware is chain

    def test_no_middleware_property_is_none(self) -> None:
        bus = LocalBus()
        assert bus.middleware is None

    def test_repr_with_middleware(self) -> None:
        chain = MiddlewareChain([PassthroughMiddleware()])
        bus = LocalBus(middleware=chain)
        assert "middleware=1" in repr(bus)


# ---------------------------------------------------------------------------
# BusFactory + Middleware
# ---------------------------------------------------------------------------


class TestBusFactoryMiddleware:
    """BusFactory methods accept middleware parameter."""

    def test_create_local_with_middleware(self) -> None:
        recorder = RecordingMiddleware()
        bus = BusFactory.create_local(middleware=[recorder], backend="python")
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(recorder.seen) == 1

    def test_create_for_testing_with_middleware(self) -> None:
        recorder = RecordingMiddleware()
        bus = BusFactory.create_for_testing(middleware=[recorder], backend="python")
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(recorder.seen) == 1
        assert len(bus.captured) == 1

    def test_create_local_ordered_with_middleware(self) -> None:
        recorder = RecordingMiddleware()
        bus = BusFactory.create_local_ordered(
            capture=True,
            middleware=[recorder],
        )
        bus.publish(Envelope(topic="k1.k0.sse.test", payload=b"x"))
        assert len(recorder.seen) == 1

    def test_create_local_with_chain(self) -> None:
        chain = MiddlewareChain([PassthroughMiddleware()])
        bus = BusFactory.create_local(middleware=chain)
        assert bus.middleware is chain

    def test_create_local_with_empty_list(self) -> None:
        bus = BusFactory.create_local(middleware=[])
        assert bus.middleware is None  # Empty list -> no middleware

    def test_create_local_no_middleware(self) -> None:
        bus = BusFactory.create_local()
        assert bus.middleware is None
