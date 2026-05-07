"""
tests.k1.memory_writer.test_session_batch_dispatcher -- SessionBatchDispatcher (Option B).

Covers:
  - subscribes to ``k1.session.turn.completed.v1`` (canonical FSM topic)
  - buffers turns without invoking the LLM per turn
  - flushes on threshold
  - flushes on idle timeout
  - flushes on stop() (session end)
  - dedups duplicate turn_ids
  - never raises from the bus handler
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, List, Optional, Tuple

import pytest

from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.pipeline.pipeline import PipelineResult
from k1.memory_writer.pipeline.session_batch_dispatcher import SessionBatchDispatcher
from k1.memory_writer.types import Subscription


class FakeEventPort:
    def __init__(self) -> None:
        self.subscriptions: List[Tuple[str, Any]] = []
        self.unsubscribed: List[str] = []
        self._next: int = 0

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        self._next += 1
        self.subscriptions.append((topic, handler))
        return Subscription(subscription_id=f"sub-{self._next}", topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        self.unsubscribed.append(subscription_id)

    async def publish(self, topic: str, payload: dict) -> None:  # pragma: no cover
        pass


class FakePipeline:
    def __init__(self, raises: Optional[Exception] = None) -> None:
        self._raises = raises
        self.session_calls: List[List[TurnCompletePayload]] = []
        self.per_turn_calls: List[TurnCompletePayload] = []
        self.flush_count: int = 0

    async def process(self, payload: TurnCompletePayload) -> PipelineResult:
        self.per_turn_calls.append(payload)
        return PipelineResult(trace_id="trace-fake")

    async def process_session(
        self, turns: List[TurnCompletePayload]
    ) -> PipelineResult:
        self.session_calls.append(list(turns))
        if self._raises is not None:
            raise self._raises
        return PipelineResult(
            atoms_extracted=len(turns),
            envelopes_submitted=len(turns),
            trace_id=turns[-1].cognitive_trace_id if turns else "",
        )

    async def flush_pending(self) -> int:
        self.flush_count += 1
        return 0


def _raw(turn_id: str = "t1", turn_number: int = 1, **kw: Any) -> dict:
    base = {
        "turn_id": turn_id,
        "session_id": "sess-1",
        "cognitive_trace_id": f"trace-{turn_id}",
        "user_message": f"msg-{turn_id}",
        "assistant_response": "ok",
        "timestamp_ms": 1700000000000 + turn_number,
        "turn_number": turn_number,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Lifecycle + topic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribes_to_canonical_fsm_topic() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=10, flush_idle_seconds=60)
    await d.start()
    try:
        assert len(ep.subscriptions) == 1
        assert ep.subscriptions[0][0] == "k1.session.turn.completed.v1"
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_stop_unsubscribes_and_clears() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=10, flush_idle_seconds=60)
    await d.start()
    await d.stop()
    assert ep.unsubscribed == ["sub-1"]
    assert d.buffered_count == 0


@pytest.mark.asyncio
async def test_constructor_validates_thresholds() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    with pytest.raises(ValueError):
        SessionBatchDispatcher(p, ep, flush_turn_threshold=0, flush_idle_seconds=10)
    with pytest.raises(ValueError):
        SessionBatchDispatcher(p, ep, flush_turn_threshold=10, flush_idle_seconds=0)


# ---------------------------------------------------------------------------
# Buffering: NO LLM call per turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buffers_without_invoking_pipeline_per_turn() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=20, flush_idle_seconds=600)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        for i in range(5):
            await handler(_raw(turn_id=f"t{i}", turn_number=i))
        assert d.buffered_count == 5
        assert p.session_calls == []  # no flush yet
        assert p.per_turn_calls == []  # legacy per-turn path untouched
    finally:
        await d.stop()


# ---------------------------------------------------------------------------
# Flush on threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flushes_on_threshold() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=3, flush_idle_seconds=600)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        await handler(_raw(turn_id="t1", turn_number=1))
        await handler(_raw(turn_id="t2", turn_number=2))
        assert p.session_calls == []  # below threshold
        await handler(_raw(turn_id="t3", turn_number=3))
        # threshold reached — single flush of 3 turns
        assert len(p.session_calls) == 1
        assert [t.turn_id for t in p.session_calls[0]] == ["t1", "t2", "t3"]
        assert d.buffered_count == 0
    finally:
        await d.stop()


# ---------------------------------------------------------------------------
# Flush on stop (session end)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flushes_on_stop_session_end() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=20, flush_idle_seconds=600)
    await d.start()
    handler = ep.subscriptions[0][1]
    await handler(_raw(turn_id="t1", turn_number=1))
    await handler(_raw(turn_id="t2", turn_number=2))
    assert p.session_calls == []
    await d.stop()
    assert len(p.session_calls) == 1
    assert [t.turn_id for t in p.session_calls[0]] == ["t1", "t2"]
    assert p.flush_count == 1  # pipeline.flush_pending() also called


@pytest.mark.asyncio
async def test_stop_with_empty_buffer_does_not_call_pipeline() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=20, flush_idle_seconds=600)
    await d.start()
    await d.stop()
    assert p.session_calls == []


# ---------------------------------------------------------------------------
# Flush on idle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flushes_on_idle_timeout() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    # Idle = 1 second; check loop runs every max(1.0, 0.25) = 1.0s
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=20, flush_idle_seconds=1)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        await handler(_raw(turn_id="t1", turn_number=1))
        await handler(_raw(turn_id="t2", turn_number=2))
        assert p.session_calls == []
        # Wait long enough for the idle loop to detect inactivity and flush.
        # Loop wakes every ~1s; idle threshold is 1s; give a generous margin.
        for _ in range(40):
            await asyncio.sleep(0.1)
            if p.session_calls:
                break
        assert len(p.session_calls) == 1
        assert [t.turn_id for t in p.session_calls[0]] == ["t1", "t2"]
    finally:
        await d.stop()


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_drops_duplicate_turn_ids() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=20, flush_idle_seconds=600)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        await handler(_raw(turn_id="t1", turn_number=1))
        await handler(_raw(turn_id="t1", turn_number=1))  # duplicate
        await handler(_raw(turn_id="t2", turn_number=2))
        assert d.buffered_count == 2
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_missing_turn_id_is_skipped() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=20, flush_idle_seconds=600)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        await handler({})  # no turn_id
        assert d.buffered_count == 0
    finally:
        await d.stop()


# ---------------------------------------------------------------------------
# Resilience: handler never raises; pipeline errors are swallowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_error_does_not_crash_dispatcher() -> None:
    p = FakePipeline(raises=RuntimeError("boom"))
    ep = FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=2, flush_idle_seconds=600)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        await handler(_raw(turn_id="t1", turn_number=1))
        await handler(_raw(turn_id="t2", turn_number=2))  # triggers flush -> raises
        # Buffer was emptied even though pipeline raised
        assert d.buffered_count == 0
        assert len(p.session_calls) == 1
    finally:
        await d.stop()


@pytest.mark.asyncio
async def test_handler_swallows_deserialization_errors() -> None:
    p, ep = FakePipeline(), FakeEventPort()
    d = SessionBatchDispatcher(p, ep, flush_turn_threshold=2, flush_idle_seconds=600)
    await d.start()
    try:
        handler = ep.subscriptions[0][1]
        # raw with non-int timestamp_ms triggers deserialization error
        await handler({"turn_id": "t1", "timestamp_ms": "not-an-int"})
        assert d.buffered_count == 0
    finally:
        await d.stop()
