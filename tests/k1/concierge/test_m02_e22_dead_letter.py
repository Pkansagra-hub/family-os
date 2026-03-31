"""
tests.poc.test_m02_e22_dead_letter -- E2.2 Dead-Letter Pipeline Conformance.

Validates:
    2.2.1  TOPIC_DEAD_LETTER constant, build_dead_letter builder, DeadLetterPayload schema
    2.2.2  _publish_dead_letter uses TOPIC_DEAD_LETTER (not state_updated)
    2.2.3  FSMTurnState max-depth overflow and TTL expiry with dead-letter
    2.2.4  DeadLetterConsumer subscription, counting, filtering, snapshot
    2.2.5  WeaveBatcher overflow guard, PendingResultsQueue bounded depth, WeaveAction.DEAD_LETTER
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.builders import build_dead_letter, build_task_cancel, build_tool_started
from k1.concierge.bus.topics import (
    ALL_TOPICS,
    TOPIC_DEAD_LETTER,
    TOPIC_TASK_COMPLETE,
    TOPIC_TOOL_STARTED,
    TOPIC_USER_INPUT,
)
from k1.concierge.fsm.dead_letter import DeadLetterPayload, build_dead_letter_payload
from k1.concierge.fsm.dead_letter_consumer import DeadLetterConsumer
from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.protocols.weave_batcher import WeaveBatcher, WeaveResult
from k1.concierge.protocols.weave_state import PendingResult, PendingResultsQueue, WeaveAction


def _parse_captured_payload(envelope: Envelope) -> dict[str, Any]:
    """Parse JSON payload from a captured envelope."""
    try:
        return json.loads(envelope.payload) if envelope.payload else {}
    except Exception:
        return {}


def _make_stub_envelope(
    topic: str = "k1.test.stub.v1",
    payload: dict[str, Any] | None = None,
    parent_id: int = 0,
) -> Envelope:
    """Build a minimal Envelope for testing."""
    data = payload or {}
    return Envelope(
        topic=topic,
        priority=Priority.INTERACTIVE,
        payload=json.dumps(data, default=str).encode("utf-8"),
        parent_id=parent_id,
        payload_format=PayloadFormat.JSON,
    )


# =============================================================================
# 2.2.1: TOPIC_DEAD_LETTER, build_dead_letter, DeadLetterPayload
# =============================================================================


class TestDeadLetterTopicAndBuilder:
    """Dead-letter topic constant and envelope builder."""

    def test_topic_constant_exists(self) -> None:
        assert TOPIC_DEAD_LETTER == "k1.internal.dead_letter.v1"

    def test_topic_in_all_topics(self) -> None:
        assert TOPIC_DEAD_LETTER in ALL_TOPICS

    def test_build_dead_letter_produces_envelope(self) -> None:
        env = build_dead_letter(
            payload={"reason": "test", "original_topic": "x"},
            parent_id=42,
        )
        assert env.topic == TOPIC_DEAD_LETTER
        assert env.parent_id == 42

    def test_build_dead_letter_payload_serialized(self) -> None:
        env = build_dead_letter(
            payload={"reason": "overflow", "original_topic": "y"},
        )
        data = json.loads(env.payload)
        assert data["reason"] == "overflow"
        assert data["original_topic"] == "y"

    def test_build_dead_letter_priority_is_background(self) -> None:
        env = build_dead_letter(payload={"reason": "test"})
        assert env.priority == Priority.BACKGROUND


class TestDeadLetterPayloadSchema:
    """DeadLetterPayload dataclass and serialization."""

    def test_all_required_fields(self) -> None:
        dl = DeadLetterPayload(
            original_topic="k1.test.v1",
            original_envelope_id=99,
            reason="invalid_transition",
            fsm_state_at_rejection="LISTENING",
        )
        assert dl.original_topic == "k1.test.v1"
        assert dl.original_envelope_id == 99
        assert dl.reason == "invalid_transition"
        assert dl.fsm_state_at_rejection == "LISTENING"

    def test_default_fields(self) -> None:
        dl = DeadLetterPayload(
            original_topic="x",
            original_envelope_id=0,
            reason="test",
            fsm_state_at_rejection="LISTENING",
        )
        assert dl.turn_number == 0
        assert dl.task_id == ""
        assert dl.original_payload_summary == ""
        assert dl.rejected_at_ns > 0

    def test_to_dict_roundtrip(self) -> None:
        dl = DeadLetterPayload(
            original_topic="k1.test.v1",
            original_envelope_id=42,
            reason="overflow",
            fsm_state_at_rejection="COMPANIONING",
            turn_number=3,
            task_id="t-99",
            original_payload_summary='{"key": "value"}',
            rejected_at_ns=123456789,
        )
        d = dl.to_dict()
        dl2 = DeadLetterPayload.from_dict(d)
        assert dl2.original_topic == dl.original_topic
        assert dl2.original_envelope_id == dl.original_envelope_id
        assert dl2.reason == dl.reason
        assert dl2.fsm_state_at_rejection == dl.fsm_state_at_rejection
        assert dl2.turn_number == dl.turn_number
        assert dl2.task_id == dl.task_id
        assert dl2.rejected_at_ns == dl.rejected_at_ns

    def test_build_dead_letter_payload_helper(self) -> None:
        dl = build_dead_letter_payload(
            original_topic="k1.test.v1",
            original_envelope_id=10,
            reason="expired",
            fsm_state="WEAVING",
            turn_number=5,
            task_id="t-5",
            payload_summary="x" * 600,
        )
        assert dl.reason == "expired"
        assert dl.fsm_state_at_rejection == "WEAVING"
        # Truncated to 500 chars
        assert len(dl.original_payload_summary) == 500

    def test_from_dict_with_missing_fields(self) -> None:
        dl = DeadLetterPayload.from_dict({})
        assert dl.original_topic == ""
        assert dl.original_envelope_id == 0
        assert dl.reason == ""


# =============================================================================
# 2.2.2: _publish_dead_letter uses TOPIC_DEAD_LETTER
# =============================================================================


class TestControllerDeadLetterRouting:
    """Controller dead-letter publishes to TOPIC_DEAD_LETTER, not state_updated."""

    def _make_fsm(self):
        from k1.concierge.bus.setup import create_poc_bus, create_poc_router
        from k1.concierge.fsm.controller import ConciergeController

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        return ConciergeController(bus=bus, router=router), bus

    def test_dead_letter_publishes_to_dead_letter_topic(self) -> None:
        fsm, bus = self._make_fsm()
        env = build_tool_started({"task_id": "t1", "tool_name": "x"})
        fsm._publish_dead_letter(env, "test_reason")

        dead_letters = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        assert len(dead_letters) >= 1
        payload = _parse_captured_payload(dead_letters[-1])
        assert payload["reason"] == "test_reason"
        assert payload["original_topic"] == TOPIC_TOOL_STARTED
        assert payload["fsm_state_at_rejection"] == "LISTENING"

    def test_dead_letter_not_on_state_updated(self) -> None:
        """Dead-letter events should no longer go to state_updated topic."""
        fsm, bus = self._make_fsm()
        env = build_tool_started({"task_id": "t1", "tool_name": "x"})
        fsm._publish_dead_letter(env, "test")

        state_updated = [
            e
            for e in bus.captured
            if e.topic == "k1.session.state.updated.v1"
            and _parse_captured_payload(e).get("dead_letter") is True
        ]
        assert (
            len(state_updated) == 0
        ), "Dead-letter should go to TOPIC_DEAD_LETTER, not state_updated"

    def test_dead_letter_contains_payload_schema(self) -> None:
        """Dead-letter payload matches DeadLetterPayload schema fields."""
        fsm, bus = self._make_fsm()
        env = build_tool_started({"task_id": "t1", "tool_name": "x"})
        fsm._publish_dead_letter(env, "invalid_transition")

        dead_letters = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        payload = _parse_captured_payload(dead_letters[-1])
        # Verify all DeadLetterPayload fields are present
        assert "original_topic" in payload
        assert "original_envelope_id" in payload
        assert "reason" in payload
        assert "fsm_state_at_rejection" in payload
        assert "turn_number" in payload
        assert "task_id" in payload
        assert "original_payload_summary" in payload
        assert "rejected_at_ns" in payload

    def test_guard_rejected_produces_dead_letter(self) -> None:
        """When guard returns DEAD_LETTER, handler publishes to TOPIC_DEAD_LETTER."""
        fsm, bus = self._make_fsm()
        # tool_started in LISTENING state = DEAD_LETTER
        env = build_tool_started({"task_id": "t1", "tool_name": "x"})
        fsm._on_tool_started(env)

        dead_letters = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        assert len(dead_letters) >= 1

    def test_cancel_in_listening_dead_letters(self) -> None:
        """task.cancel in LISTENING should dead-letter (incompatible state)."""
        fsm, bus = self._make_fsm()
        env = build_task_cancel({"task_id": "t1"})
        fsm._on_task_cancel(env)

        dead_letters = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        assert len(dead_letters) >= 1
        payload = _parse_captured_payload(dead_letters[-1])
        assert payload["reason"] == "task_cancel_invalid_state"


# =============================================================================
# 2.2.3: FSMTurnState max-depth overflow and TTL expiry
# =============================================================================


class TestFSMTurnStateOverflow:
    """pending_results max-depth eviction."""

    def test_enqueue_below_max_depth_returns_none(self) -> None:
        ts = FSMTurnState(max_depth=4)
        env = _make_stub_envelope(topic=TOPIC_TASK_COMPLETE, payload={"task_id": "t1"})
        evicted = ts.enqueue_result("t1", {"data": "r1"}, env)
        assert evicted is None
        assert ts.depth == 1

    def test_enqueue_at_max_depth_evicts_oldest(self) -> None:
        ts = FSMTurnState(max_depth=2)
        env1 = _make_stub_envelope(payload={"task_id": "t1"})
        env2 = _make_stub_envelope(payload={"task_id": "t2"})
        env3 = _make_stub_envelope(payload={"task_id": "t3"})

        ts.enqueue_result("t1", {"data": "r1"}, env1)
        ts.enqueue_result("t2", {"data": "r2"}, env2)
        evicted = ts.enqueue_result("t3", {"data": "r3"}, env3)

        assert evicted is not None
        assert evicted["task_id"] == "t1"
        assert ts.depth == 2  # oldest evicted, new one added

    def test_enqueue_overflow_multiple(self) -> None:
        ts = FSMTurnState(max_depth=1)
        env1 = _make_stub_envelope(payload={"task_id": "t1"})
        env2 = _make_stub_envelope(payload={"task_id": "t2"})
        env3 = _make_stub_envelope(payload={"task_id": "t3"})

        ts.enqueue_result("t1", {"data": "r1"}, env1)
        evicted1 = ts.enqueue_result("t2", {"data": "r2"}, env2)
        evicted2 = ts.enqueue_result("t3", {"data": "r3"}, env3)

        assert evicted1 is not None
        assert evicted1["task_id"] == "t1"
        assert evicted2 is not None
        assert evicted2["task_id"] == "t2"
        assert ts.depth == 1

    def test_has_pending_results(self) -> None:
        ts = FSMTurnState(max_depth=16)
        assert ts.has_pending_results is False
        env = _make_stub_envelope()
        ts.enqueue_result("t1", {}, env)
        assert ts.has_pending_results is True


class TestFSMTurnStateTTL:
    """pending_results TTL expiry in drain_results."""

    def test_drain_no_expiry(self) -> None:
        ts = FSMTurnState(max_depth=16, ttl_seconds=300)
        env = _make_stub_envelope()
        ts.enqueue_result("t1", {"data": "r1"}, env)
        valid, expired = ts.drain_results()
        assert len(valid) == 1
        assert len(expired) == 0

    def test_drain_with_expired(self) -> None:
        ts = FSMTurnState(max_depth=16, ttl_seconds=1)
        # Manually insert an item with a very old timestamp
        ts.pending_results.append(
            {
                "task_id": "old",
                "result": {},
                "envelope_id": 0,
                "parent_id": 0,
                "queued_at_ns": 1,  # epoch start -- definitely expired
            }
        )
        # Add a fresh item
        env = _make_stub_envelope()
        ts.enqueue_result("fresh", {"data": "new"}, env)

        valid, expired = ts.drain_results()
        assert len(expired) == 1
        assert expired[0]["task_id"] == "old"
        assert len(valid) == 1
        assert valid[0]["task_id"] == "fresh"
        # Queue should be empty after drain
        assert ts.depth == 0

    def test_drain_empty(self) -> None:
        ts = FSMTurnState()
        valid, expired = ts.drain_results()
        assert valid == []
        assert expired == []

    def test_reset_clears_all(self) -> None:
        ts = FSMTurnState(max_depth=16)
        env = _make_stub_envelope()
        ts.enqueue_result("t1", {}, env)
        ts.reset()
        assert ts.depth == 0
        assert ts.has_pending_results is False


# =============================================================================
# 2.2.4: DeadLetterConsumer
# =============================================================================


class TestDeadLetterConsumer:
    """DeadLetterConsumer subscription, counting, filtering."""

    def _make_consumer(self):
        from k1.concierge.bus.setup import create_poc_bus

        bus = create_poc_bus(capture=True)
        consumer = DeadLetterConsumer(bus)
        return consumer, bus

    def test_subscribes_to_dead_letter_topic(self) -> None:
        consumer, _ = self._make_consumer()
        assert consumer._handle is not None

    def test_total_dead_letters_starts_zero(self) -> None:
        consumer, _ = self._make_consumer()
        assert consumer.total_dead_letters == 0

    def test_receives_dead_letter_event(self) -> None:
        consumer, bus = self._make_consumer()
        dl = DeadLetterPayload(
            original_topic="k1.test.v1",
            original_envelope_id=42,
            reason="invalid_transition",
            fsm_state_at_rejection="LISTENING",
            turn_number=1,
        )
        env = build_dead_letter(payload=dl.to_dict())
        bus.publish(env)
        assert consumer.total_dead_letters == 1

    def test_counts_by_reason(self) -> None:
        consumer, bus = self._make_consumer()
        for reason in ["invalid_transition", "overflow", "invalid_transition"]:
            dl = DeadLetterPayload(
                original_topic="x",
                original_envelope_id=0,
                reason=reason,
                fsm_state_at_rejection="LISTENING",
            )
            bus.publish(build_dead_letter(payload=dl.to_dict()))

        assert consumer.total_dead_letters == 3
        by_reason = consumer.get_events_by_reason("invalid_transition")
        assert len(by_reason) == 2
        by_overflow = consumer.get_events_by_reason("overflow")
        assert len(by_overflow) == 1

    def test_counts_by_state(self) -> None:
        consumer, bus = self._make_consumer()
        for state in ["LISTENING", "COMPANIONING", "LISTENING"]:
            dl = DeadLetterPayload(
                original_topic="x",
                original_envelope_id=0,
                reason="test",
                fsm_state_at_rejection=state,
            )
            bus.publish(build_dead_letter(payload=dl.to_dict()))

        by_state = consumer.get_events_by_state("LISTENING")
        assert len(by_state) == 2

    def test_counts_by_topic(self) -> None:
        consumer, bus = self._make_consumer()
        dl = DeadLetterPayload(
            original_topic=TOPIC_USER_INPUT,
            original_envelope_id=0,
            reason="test",
            fsm_state_at_rejection="LISTENING",
        )
        bus.publish(build_dead_letter(payload=dl.to_dict()))

        by_topic = consumer.get_events_by_topic(TOPIC_USER_INPUT)
        assert len(by_topic) == 1

    def test_snapshot(self) -> None:
        consumer, bus = self._make_consumer()
        dl = DeadLetterPayload(
            original_topic="x",
            original_envelope_id=0,
            reason="overflow",
            fsm_state_at_rejection="WEAVING",
        )
        bus.publish(build_dead_letter(payload=dl.to_dict()))

        snap = consumer.snapshot()
        assert snap["total_dead_letters"] == 1
        assert snap["counts_by_reason"] == {"overflow": 1}
        assert snap["counts_by_state"] == {"WEAVING": 1}
        assert snap["stored_events"] == 1

    def test_reset_clears_everything(self) -> None:
        consumer, bus = self._make_consumer()
        dl = DeadLetterPayload(
            original_topic="x",
            original_envelope_id=0,
            reason="test",
            fsm_state_at_rejection="LISTENING",
        )
        bus.publish(build_dead_letter(payload=dl.to_dict()))
        consumer.reset()
        assert consumer.total_dead_letters == 0
        assert consumer.events == []

    def test_max_events_cap(self) -> None:
        consumer, bus = self._make_consumer()
        # Override max_events for testing
        consumer._max_events = 2
        for i in range(5):
            dl = DeadLetterPayload(
                original_topic="x",
                original_envelope_id=i,
                reason="test",
                fsm_state_at_rejection="LISTENING",
            )
            bus.publish(build_dead_letter(payload=dl.to_dict()))

        # Only 2 events stored, but all 5 counted
        assert consumer.total_dead_letters == 5
        assert len(consumer.events) == 2


# =============================================================================
# 2.2.5: WeaveAction.DEAD_LETTER, PendingResultsQueue overflow, WeaveBatcher overflow
# =============================================================================


class TestWeaveActionDeadLetter:
    """WeaveAction enum includes DEAD_LETTER."""

    def test_dead_letter_member_exists(self) -> None:
        assert WeaveAction.DEAD_LETTER == "dead_letter"

    def test_enum_has_5_members(self) -> None:
        assert len(WeaveAction) == 5

    def test_all_members(self) -> None:
        members = {m.value for m in WeaveAction}
        assert members == {"immediate", "queue_weave", "queue", "chain", "dead_letter"}


class TestPendingResultsQueueOverflow:
    """PendingResultsQueue bounded depth with eviction."""

    def test_push_below_max_returns_none(self) -> None:
        q = PendingResultsQueue(max_depth=4)
        r = PendingResult(task_id="t1", task_description="desc", result_data={})
        evicted = q.push(r)
        assert evicted is None
        assert q.count == 1

    def test_push_at_max_evicts_oldest(self) -> None:
        q = PendingResultsQueue(max_depth=2)
        r1 = PendingResult(task_id="t1", task_description="d1", result_data={})
        r2 = PendingResult(task_id="t2", task_description="d2", result_data={})
        r3 = PendingResult(task_id="t3", task_description="d3", result_data={})

        q.push(r1)
        q.push(r2)
        evicted = q.push(r3)

        assert evicted is not None
        assert evicted.task_id == "t1"
        assert q.count == 2

    def test_push_multiple_overflow(self) -> None:
        q = PendingResultsQueue(max_depth=1)
        r1 = PendingResult(task_id="t1", task_description="d1", result_data={})
        r2 = PendingResult(task_id="t2", task_description="d2", result_data={})
        r3 = PendingResult(task_id="t3", task_description="d3", result_data={})

        q.push(r1)
        ev1 = q.push(r2)
        ev2 = q.push(r3)

        assert ev1 is not None and ev1.task_id == "t1"
        assert ev2 is not None and ev2.task_id == "t2"
        assert q.count == 1

    def test_drain_after_overflow(self) -> None:
        q = PendingResultsQueue(max_depth=2)
        for i in range(5):
            q.push(PendingResult(task_id=f"t{i}", task_description=f"d{i}", result_data={}))
        results = q.drain()
        assert len(results) == 2
        assert results[0].task_id == "t3"
        assert results[1].task_id == "t4"

    def test_default_max_depth(self) -> None:
        q = PendingResultsQueue()
        assert q._max_depth == 16


class TestWeaveBatcherOverflow:
    """WeaveBatcher queued list overflow guard."""

    @pytest.mark.asyncio
    async def test_on_task_complete_no_overflow(self) -> None:
        flushed = []

        async def flush_fn(results):
            flushed.extend(results)

        wb = WeaveBatcher(flush_fn=flush_fn, batch_window_ms=500, max_queued_depth=4)
        wb.set_front_busy(True)

        r = WeaveResult(task_id="t1", task_description="d1", result_data={})
        evicted = await wb.on_task_complete(r)
        assert evicted is None
        assert wb.queued_count == 1

    @pytest.mark.asyncio
    async def test_on_task_complete_overflow_evicts(self) -> None:
        flushed = []

        async def flush_fn(results):
            flushed.extend(results)

        wb = WeaveBatcher(flush_fn=flush_fn, batch_window_ms=500, max_queued_depth=2)
        wb.set_front_busy(True)

        r1 = WeaveResult(task_id="t1", task_description="d1", result_data={})
        r2 = WeaveResult(task_id="t2", task_description="d2", result_data={})
        r3 = WeaveResult(task_id="t3", task_description="d3", result_data={})

        await wb.on_task_complete(r1)
        await wb.on_task_complete(r2)
        evicted = await wb.on_task_complete(r3)

        assert evicted is not None
        assert evicted.task_id == "t1"
        assert wb.queued_count == 2

    @pytest.mark.asyncio
    async def test_on_task_complete_not_busy_no_overflow(self) -> None:
        """When Front is not busy, results go to _pending, no overflow check."""
        flushed = []

        async def flush_fn(results):
            flushed.extend(results)

        wb = WeaveBatcher(flush_fn=flush_fn, batch_window_ms=5000, max_queued_depth=2)
        # Front NOT busy
        r = WeaveResult(task_id="t1", task_description="d1", result_data={})
        evicted = await wb.on_task_complete(r)
        assert evicted is None
        assert wb.pending_count == 1

    @pytest.mark.asyncio
    async def test_max_queued_depth_from_config(self) -> None:
        """WeaveBatcher reads max_queued_depth from config when not passed."""
        flushed = []

        async def flush_fn(results):
            flushed.extend(results)

        wb = WeaveBatcher(flush_fn=flush_fn, batch_window_ms=500)
        assert wb._max_queued_depth == 16  # default from config


# =============================================================================
# Cross-cutting: Config integration
# =============================================================================


class TestConfigIntegration:
    """Config flags for dead-letter features."""

    def test_fsm_config_has_dead_letter_enabled(self) -> None:
        from k1.concierge.config import get_config

        cfg = get_config()
        assert hasattr(cfg.fsm, "dead_letter_enabled")
        assert cfg.fsm.dead_letter_enabled is True

    def test_fsm_config_has_pending_results_max_depth(self) -> None:
        from k1.concierge.config import get_config

        cfg = get_config()
        assert cfg.fsm.pending_results_max_depth == 16

    def test_fsm_config_has_pending_results_ttl(self) -> None:
        from k1.concierge.config import get_config

        cfg = get_config()
        assert cfg.fsm.pending_results_ttl_seconds == 300

    def test_protocols_config_has_weave_max_queued_depth(self) -> None:
        from k1.concierge.config import get_config

        cfg = get_config()
        assert cfg.protocols.weave_max_queued_depth == 16
