"""
tests.k1.memory_writer.test_turn_dispatcher -- 24 tests for TurnDispatcher.

Covers: lifecycle, dedup, deserialization, backpressure, pipeline integration, observability.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, List, Optional, Tuple

import pytest

from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.pipeline.pipeline import PipelineResult
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher
from k1.memory_writer.types import Subscription

# ---------------------------------------------------------------------------
# Fake adapters
# ---------------------------------------------------------------------------


class FakeEventPort:
    """Captures subscribe/unsubscribe/publish calls."""

    def __init__(self) -> None:
        self.subscriptions: List[Tuple[str, Any]] = []
        self.unsubscribed: List[str] = []
        self._next_sub_id: int = 0

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        self._next_sub_id += 1
        sub_id = f"sub-{self._next_sub_id}"
        self.subscriptions.append((topic, handler))
        return Subscription(subscription_id=sub_id, topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        self.unsubscribed.append(subscription_id)

    async def publish(self, topic: str, payload: dict) -> None:
        pass  # Not used by dispatcher directly


class FakePipeline:
    """Captures process() and flush_pending() calls."""

    def __init__(
        self,
        result: Optional[PipelineResult] = None,
        raises: Optional[Exception] = None,
        slow: bool = False,
    ) -> None:
        self._result = result or PipelineResult(trace_id="trace-fake")
        self._raises = raises
        self._slow = slow
        self.process_calls: List[TurnCompletePayload] = []
        self.flush_count: int = 0

    async def process(self, payload: TurnCompletePayload) -> PipelineResult:
        self.process_calls.append(payload)
        if self._raises:
            raise self._raises
        if self._slow:
            # Yield control so queued turns can arrive
            await asyncio.sleep(0)
        return self._result

    async def flush_pending(self) -> int:
        self.flush_count += 1
        return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_payload(
    turn_id: str = "turn-1",
    session_id: str = "sess-1",
    cognitive_trace_id: str = "trace-1",
    user_message: str = "Hello",
    assistant_response: str = "Hi there",
    timestamp_ms: int = 1700000000000,
    turn_number: int = 1,
    **extra: Any,
) -> dict:
    d = {
        "turn_id": turn_id,
        "session_id": session_id,
        "cognitive_trace_id": cognitive_trace_id,
        "user_message": user_message,
        "assistant_response": assistant_response,
        "timestamp_ms": timestamp_ms,
        "turn_number": turn_number,
    }
    d.update(extra)
    return d


def _dispatcher(
    pipeline: Optional[FakePipeline] = None,
    event_port: Optional[FakeEventPort] = None,
) -> Tuple[TurnDispatcher, FakePipeline, FakeEventPort]:
    p = pipeline or FakePipeline()
    ep = event_port or FakeEventPort()
    d = TurnDispatcher(pipeline=p, event_port=ep)
    return d, p, ep


# ===========================================================================
# TestTurnDispatcherLifecycle — 4 tests
# ===========================================================================


class TestTurnDispatcherLifecycle:
    """Start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_subscribes_to_topic(self) -> None:
        d, _, ep = _dispatcher()
        await d.start()
        assert len(ep.subscriptions) == 1
        assert ep.subscriptions[0][0] == "turn.complete.v1"

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self) -> None:
        d, _, ep = _dispatcher()
        await d.start()
        await d.stop()
        assert len(ep.unsubscribed) == 1

    @pytest.mark.asyncio
    async def test_stop_flushes_pending(self) -> None:
        d, p, _ = _dispatcher()
        await d.start()
        await d.stop()
        assert p.flush_count == 1

    @pytest.mark.asyncio
    async def test_stop_clears_dedup_set(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        # Process turn-1
        await handler(_raw_payload(turn_id="t1"))
        assert len(p.process_calls) == 1
        # Stop clears dedup set
        await d.stop()
        p.process_calls.clear()
        # Re-start and process same turn_id — should be accepted
        await d.start()
        handler2 = ep.subscriptions[1][1]
        await handler2(_raw_payload(turn_id="t1"))
        assert len(p.process_calls) == 1


# ===========================================================================
# TestTurnDispatcherDedup — 5 tests
# ===========================================================================


class TestTurnDispatcherDedup:
    """At-most-once dedup by turn_id."""

    @pytest.mark.asyncio
    async def test_first_delivery_processed(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t1"))
        assert len(p.process_calls) == 1

    @pytest.mark.asyncio
    async def test_duplicate_turn_id_skipped(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t1"))
        await handler(_raw_payload(turn_id="t1"))
        assert len(p.process_calls) == 1

    @pytest.mark.asyncio
    async def test_different_turn_ids_both_processed(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t1"))
        await handler(_raw_payload(turn_id="t2"))
        assert len(p.process_calls) == 2

    @pytest.mark.asyncio
    async def test_dedup_cleared_on_stop(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t1"))
        assert len(p.process_calls) == 1
        await d.stop()
        p.process_calls.clear()
        await d.start()
        handler2 = ep.subscriptions[1][1]
        await handler2(_raw_payload(turn_id="t1"))
        assert len(p.process_calls) == 1

    @pytest.mark.asyncio
    async def test_dedup_set_grows(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        for i in range(5):
            await handler(_raw_payload(turn_id=f"t{i}"))
        assert len(d._processed_ids) == 5
        assert len(p.process_calls) == 5


# ===========================================================================
# TestTurnDispatcherDeserialization — 4 tests
# ===========================================================================


class TestTurnDispatcherDeserialization:
    """Raw dict → TurnCompletePayload conversion."""

    @pytest.mark.asyncio
    async def test_full_payload_deserialized(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        raw = _raw_payload(
            turn_id="t-full",
            session_id="s-full",
            cognitive_trace_id="ct-full",
            user_message="What happened?",
            assistant_response="You had dinner.",
            timestamp_ms=1700000001000,
            turn_number=3,
            mentioned_time_raw="last Tuesday",
            mentioned_time_resolved_ms=1699800000000,
            mentioned_time_confidence=0.9,
            mentioned_time_is_relative=True,
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="RESTAURANT",
            mentioned_location_entity_id="place_olive",
            mentioned_location_confidence=0.85,
        )
        await handler(raw)
        payload = p.process_calls[0]
        assert payload.turn_id == "t-full"
        assert payload.session_id == "s-full"
        assert payload.cognitive_trace_id == "ct-full"
        assert payload.user_message == "What happened?"
        assert payload.assistant_response == "You had dinner."
        assert payload.timestamp_ms == 1700000001000
        assert payload.turn_number == 3
        assert payload.mentioned_time_raw == "last Tuesday"
        assert payload.mentioned_time_resolved_ms == 1699800000000
        assert payload.mentioned_time_confidence == 0.9
        assert payload.mentioned_time_is_relative is True
        assert payload.mentioned_location_raw == "Olive Garden"
        assert payload.mentioned_location_type == "RESTAURANT"
        assert payload.mentioned_location_entity_id == "place_olive"
        assert payload.mentioned_location_confidence == 0.85

    @pytest.mark.asyncio
    async def test_missing_optional_fields_use_defaults(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        # Only required-ish fields
        raw = {"turn_id": "t-min", "session_id": "s1", "user_message": "hi"}
        await handler(raw)
        payload = p.process_calls[0]
        assert payload.turn_id == "t-min"
        assert payload.mentioned_time_raw == ""
        assert payload.mentioned_time_resolved_ms == 0
        assert payload.mentioned_time_confidence == 0.0
        assert payload.mentioned_time_is_relative is True
        assert payload.mentioned_location_raw == ""
        assert payload.mentioned_location_type == ""
        assert payload.mentioned_location_entity_id == ""
        assert payload.mentioned_location_confidence == 0.0

    @pytest.mark.asyncio
    async def test_malformed_payload_skipped(self) -> None:
        """Non-dict values that cause int() or str() to fail → skipped."""
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        # timestamp_ms with a non-numeric value
        raw = {"turn_id": "t-bad", "timestamp_ms": "not-a-number"}
        await handler(raw)
        assert len(p.process_calls) == 0

    @pytest.mark.asyncio
    async def test_turn_number_converted_to_int(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        raw = _raw_payload(turn_id="t-str-num", turn_number="5")
        await handler(raw)
        payload = p.process_calls[0]
        assert payload.turn_number == 5
        assert isinstance(payload.turn_number, int)


# ===========================================================================
# TestTurnDispatcherBackpressure — 5 tests
# ===========================================================================


class TestTurnDispatcherBackpressure:
    """Max 1 processing + 1 queued. Newest wins."""

    @pytest.mark.asyncio
    async def test_concurrent_turn_queued(self) -> None:
        """Turn arrives during processing → queued."""
        process_entered = asyncio.Event()
        process_release = asyncio.Event()

        class SlowPipeline:
            def __init__(self) -> None:
                self.process_calls: List[TurnCompletePayload] = []
                self.flush_count: int = 0

            async def process(self, payload: TurnCompletePayload) -> PipelineResult:
                self.process_calls.append(payload)
                process_entered.set()
                await process_release.wait()
                return PipelineResult(trace_id="slow")

            async def flush_pending(self) -> int:
                self.flush_count += 1
                return 0

        sp = SlowPipeline()
        ep = FakeEventPort()
        d = TurnDispatcher(pipeline=sp, event_port=ep)
        await d.start()
        handler = ep.subscriptions[0][1]

        # Start processing turn-1
        task = asyncio.create_task(handler(_raw_payload(turn_id="t1")))
        await process_entered.wait()

        # turn-2 arrives while t1 is processing → queued
        await handler(_raw_payload(turn_id="t2"))
        assert d._queued_payload is not None
        assert d._queued_payload.turn_id == "t2"

        # Release t1
        process_release.set()
        await task

    @pytest.mark.asyncio
    async def test_queued_turn_processed_after(self) -> None:
        """Queued turn processed after current completes."""
        process_entered = asyncio.Event()
        process_release = asyncio.Event()

        class SlowPipeline:
            def __init__(self) -> None:
                self.process_calls: List[TurnCompletePayload] = []
                self.flush_count: int = 0

            async def process(self, payload: TurnCompletePayload) -> PipelineResult:
                self.process_calls.append(payload)
                if len(self.process_calls) == 1:
                    process_entered.set()
                    await process_release.wait()
                return PipelineResult(trace_id="slow")

            async def flush_pending(self) -> int:
                self.flush_count += 1
                return 0

        sp = SlowPipeline()
        ep = FakeEventPort()
        d = TurnDispatcher(pipeline=sp, event_port=ep)
        await d.start()
        handler = ep.subscriptions[0][1]

        task = asyncio.create_task(handler(_raw_payload(turn_id="t1")))
        await process_entered.wait()

        # Queue t2
        await handler(_raw_payload(turn_id="t2"))

        # Release t1 → t2 processes
        process_release.set()
        await task

        assert len(sp.process_calls) == 2
        assert sp.process_calls[0].turn_id == "t1"
        assert sp.process_calls[1].turn_id == "t2"

    @pytest.mark.asyncio
    async def test_queue_replaced_newest_wins(self) -> None:
        """2 turns arrive during processing → only newest processed."""
        process_entered = asyncio.Event()
        process_release = asyncio.Event()

        class SlowPipeline:
            def __init__(self) -> None:
                self.process_calls: List[TurnCompletePayload] = []
                self.flush_count: int = 0

            async def process(self, payload: TurnCompletePayload) -> PipelineResult:
                self.process_calls.append(payload)
                if len(self.process_calls) == 1:
                    process_entered.set()
                    await process_release.wait()
                return PipelineResult(trace_id="slow")

            async def flush_pending(self) -> int:
                self.flush_count += 1
                return 0

        sp = SlowPipeline()
        ep = FakeEventPort()
        d = TurnDispatcher(pipeline=sp, event_port=ep)
        await d.start()
        handler = ep.subscriptions[0][1]

        task = asyncio.create_task(handler(_raw_payload(turn_id="t1")))
        await process_entered.wait()

        # Queue t2, then replace with t3 (newest wins)
        await handler(_raw_payload(turn_id="t2"))
        await handler(_raw_payload(turn_id="t3"))

        process_release.set()
        await task

        assert len(sp.process_calls) == 2
        assert sp.process_calls[0].turn_id == "t1"
        assert sp.process_calls[1].turn_id == "t3"

    @pytest.mark.asyncio
    async def test_queued_turn_dedup_checked(self) -> None:
        """Queued turn_id already processed → skipped when dequeued."""
        process_entered = asyncio.Event()
        process_release = asyncio.Event()

        class SlowPipeline:
            def __init__(self) -> None:
                self.process_calls: List[TurnCompletePayload] = []
                self.flush_count: int = 0

            async def process(self, payload: TurnCompletePayload) -> PipelineResult:
                self.process_calls.append(payload)
                if len(self.process_calls) == 1:
                    process_entered.set()
                    await process_release.wait()
                return PipelineResult(trace_id="slow")

            async def flush_pending(self) -> int:
                self.flush_count += 1
                return 0

        sp = SlowPipeline()
        ep = FakeEventPort()
        d = TurnDispatcher(pipeline=sp, event_port=ep)
        await d.start()
        handler = ep.subscriptions[0][1]

        task = asyncio.create_task(handler(_raw_payload(turn_id="t1")))
        await process_entered.wait()

        # Queue t1 again (duplicate) → should be skipped on dequeue
        await handler(_raw_payload(turn_id="t1"))

        process_release.set()
        await task

        # Only t1 processed once
        assert len(sp.process_calls) == 1

    @pytest.mark.asyncio
    async def test_no_queue_when_idle(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t1"))
        assert d._queued_payload is None
        assert len(p.process_calls) == 1


# ===========================================================================
# TestTurnDispatcherPipelineIntegration — 3 tests
# ===========================================================================


class TestTurnDispatcherPipelineIntegration:
    """Pipeline interaction correctness."""

    @pytest.mark.asyncio
    async def test_pipeline_result_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        result = PipelineResult(
            trace_id="trace-log",
            atoms_extracted=2,
            envelopes_submitted=2,
        )
        d, _, ep = _dispatcher(pipeline=FakePipeline(result=result))
        await d.start()
        handler = ep.subscriptions[0][1]
        with caplog.at_level(logging.INFO):
            await handler(_raw_payload(turn_id="t-log"))
        assert any("turn processed" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_pipeline_exception_caught(self) -> None:
        d, _, ep = _dispatcher(pipeline=FakePipeline(raises=RuntimeError("boom")))
        await d.start()
        handler = ep.subscriptions[0][1]
        # Should NOT raise
        await handler(_raw_payload(turn_id="t-err"))
        # turn_id still marked processed (added before process() call)
        assert "t-err" in d._processed_ids

    @pytest.mark.asyncio
    async def test_pipeline_called_with_typed_payload(self) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t-typed"))
        assert isinstance(p.process_calls[0], TurnCompletePayload)


# ===========================================================================
# TestTurnDispatcherObservability — 3 tests
# ===========================================================================


class TestTurnDispatcherObservability:
    """Logging behaviour for key events."""

    @pytest.mark.asyncio
    async def test_dedup_skip_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        d, _, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        await handler(_raw_payload(turn_id="t-dup"))
        with caplog.at_level(logging.INFO):
            await handler(_raw_payload(turn_id="t-dup"))
        assert any("duplicate turn_id, skipping" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_queue_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        process_entered = asyncio.Event()
        process_release = asyncio.Event()

        class SlowPipeline:
            def __init__(self) -> None:
                self.process_calls: List[TurnCompletePayload] = []
                self.flush_count: int = 0

            async def process(self, payload: TurnCompletePayload) -> PipelineResult:
                self.process_calls.append(payload)
                process_entered.set()
                await process_release.wait()
                return PipelineResult(trace_id="slow")

            async def flush_pending(self) -> int:
                self.flush_count += 1
                return 0

        sp = SlowPipeline()
        ep = FakeEventPort()
        d = TurnDispatcher(pipeline=sp, event_port=ep)
        await d.start()
        handler = ep.subscriptions[0][1]

        task = asyncio.create_task(handler(_raw_payload(turn_id="t1")))
        await process_entered.wait()

        with caplog.at_level(logging.INFO):
            await handler(_raw_payload(turn_id="t2"))
        assert any("turn queued" in r.message for r in caplog.records)

        process_release.set()
        await task

    @pytest.mark.asyncio
    async def test_deserialization_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        d, p, ep = _dispatcher()
        await d.start()
        handler = ep.subscriptions[0][1]
        with caplog.at_level(logging.WARNING):
            await handler({"turn_id": "ok", "timestamp_ms": "not-a-number"})
        assert any("failed to deserialize" in r.message for r in caplog.records)
        assert len(p.process_calls) == 0
