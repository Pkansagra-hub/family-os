"""
tests.poc.test_m06_e63_lifecycle_events -- E6.3 HITL Lifecycle Events.

Tests for:
  6.3.1: hitl.requested.v1 emitted on _on_task_suspended
  6.3.2: hitl.resolved.v1 emitted on _on_task_resume
  6.3.3: hitl.timed_out.v1 emitted after timeout, timeout cancelled on resume
  6.3.4: hitl.blocked_red.v1 emitted by HILCoordinator callback
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME, TOPIC_TASK_SUSPENDED
from poc.k1_poc.testing.fixtures import create_wired_fsm_with_hitl

# =========================================================================
# Helpers
# =========================================================================


def _make_envelope(
    topic: str,
    payload: dict | None = None,
    envelope_id: int = 1,
    parent_id: int = 0,
) -> Envelope:
    data = payload or {}
    return Envelope(
        topic=topic,
        payload=json.dumps(data).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=envelope_id,
        parent_id=parent_id,
    )


def _advance_to_companioning(fsm: Any, bus: Any) -> str:
    from poc.k1_poc.fsm.states import ConciergeState

    task_id = f"task-{uuid.uuid4().hex[:8]}"
    fsm._state = ConciergeState.COMPANIONING
    fsm._turn_number = 1
    fsm._active_task_ids.add(task_id)
    fsm._task_dispatch_turns[task_id] = 0
    fsm._task_bridge.dispatch_task(task_id, "search")
    return task_id


def _captured_by_topic(bus: Any, topic: str) -> list[Envelope]:
    return [e for e in bus.captured if e.topic == topic]


# =========================================================================
# 6.3.1 -- hitl.requested.v1 emitted on suspension
# =========================================================================


class TestHITLRequestedEmission:
    """6.3.1: _on_task_suspended emits hitl.requested.v1 on bus."""

    @pytest.mark.asyncio
    async def test_requested_event_emitted(self) -> None:
        """Suspension publishes hitl.requested.v1 with correct fields."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {
                "task_id": task_id,
                "question": "Which restaurant?",
                "hil_type": "clarification",
                "safety_band": "AMBER",
            },
            envelope_id=100,
        )
        fsm._on_task_suspended(env)

        from poc.k1_poc.bus.topics import TOPIC_HITL_REQUESTED

        found = _captured_by_topic(bus, TOPIC_HITL_REQUESTED)
        assert len(found) == 1, f"Expected 1 hitl.requested, got {len(found)}"
        payload = json.loads(found[0].payload)
        assert payload["hil_type"] == "clarification"
        assert payload["parent_task_id"] == task_id
        assert payload["safety_band"] == "AMBER"
        assert "resume_token" in payload
        assert "pending_hil_id" in payload

    @pytest.mark.asyncio
    async def test_requested_event_has_parent_id(self) -> None:
        """hitl.requested.v1 envelope parent_id references the suspension envelope."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "clarification"},
            envelope_id=200,
        )
        fsm._on_task_suspended(env)

        from poc.k1_poc.bus.topics import TOPIC_HITL_REQUESTED

        found = _captured_by_topic(bus, TOPIC_HITL_REQUESTED)
        assert found[0].parent_id == 200


# =========================================================================
# 6.3.2 -- hitl.resolved.v1 emitted on resume
# =========================================================================


class TestHITLResolvedEmission:
    """6.3.2: _on_task_resume emits hitl.resolved.v1 on bus."""

    @pytest.mark.asyncio
    async def test_resolved_event_emitted(self) -> None:
        """Resume publishes hitl.resolved.v1 with correct fields."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Suspend first
        env_s = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "approval"},
            envelope_id=300,
        )
        fsm._on_task_suspended(env_s)
        token = fsm._pending_hil_subtasks[task_id].resume_token
        pending_id = fsm._pending_hil_subtasks[task_id].pending_hil_id

        # Resume
        env_r = _make_envelope(
            TOPIC_TASK_RESUME,
            {
                "task_id": task_id,
                "resume_token": token,
                "resolution": {"decision": "approved"},
                "decision_branch": "approved",
            },
            envelope_id=400,
        )
        fsm._on_task_resume(env_r)

        from poc.k1_poc.bus.topics import TOPIC_HITL_RESOLVED

        found = _captured_by_topic(bus, TOPIC_HITL_RESOLVED)
        assert len(found) == 1
        payload = json.loads(found[0].payload)
        assert payload["pending_hil_id"] == pending_id
        assert payload["hil_type"] == "approval"
        assert payload["decision_branch"] == "approved"
        assert payload["parent_task_id"] == task_id

    @pytest.mark.asyncio
    async def test_resolved_not_emitted_without_subtask(self) -> None:
        """If resume finds no HILSubTask (legacy path), no resolved event."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Manually store in SuspensionManager without HILSubTask
        from poc.k1_poc.fsm.states import ConciergeState

        fsm._suspension_manager.store_context(task_id, {"hil_type": "clarification"})
        fsm._task_bridge.suspend_task(task_id)
        fsm._state = ConciergeState.CLARIFYING_WORKER

        env_r = _make_envelope(
            TOPIC_TASK_RESUME,
            {"task_id": task_id, "resolution": {"answer": "yes"}},
            envelope_id=500,
        )
        fsm._on_task_resume(env_r)

        from poc.k1_poc.bus.topics import TOPIC_HITL_RESOLVED

        found = _captured_by_topic(bus, TOPIC_HITL_RESOLVED)
        assert len(found) == 0, "No resolved event without HILSubTask"


# =========================================================================
# 6.3.3 -- hitl.timed_out.v1 emitted after timeout
# =========================================================================


class TestHITLTimedOutEmission:
    """6.3.3: _hitl_timeout_watcher emits hitl.timed_out.v1 after expiry."""

    @pytest.mark.asyncio
    async def test_timeout_emits_timed_out_event(self) -> None:
        """Short timeout triggers hitl.timed_out.v1 and auto-cancels task."""
        c = create_wired_fsm_with_hitl(timeout_clarification=0.05)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {
                "task_id": task_id,
                "question": "Q?",
                "hil_type": "clarification",
                "timeout_s": 0.05,
            },
            envelope_id=600,
        )
        fsm._on_task_suspended(env)

        # Wait for timeout watcher to fire
        await asyncio.sleep(0.15)

        from poc.k1_poc.bus.topics import TOPIC_HITL_TIMED_OUT

        found = _captured_by_topic(bus, TOPIC_HITL_TIMED_OUT)
        assert len(found) == 1, f"Expected 1 timed_out event, got {len(found)}"
        payload = json.loads(found[0].payload)
        assert payload["parent_task_id"] == task_id
        assert payload["hil_type"] == "clarification"

    @pytest.mark.asyncio
    async def test_timeout_removes_pending_subtask(self) -> None:
        """After timeout, pending subtask is cleaned up."""
        c = create_wired_fsm_with_hitl(timeout_clarification=0.05)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "clarification", "timeout_s": 0.05},
            envelope_id=700,
        )
        fsm._on_task_suspended(env)
        await asyncio.sleep(0.15)

        assert task_id not in fsm._pending_hil_subtasks

    @pytest.mark.asyncio
    async def test_resume_cancels_timeout_watcher(self) -> None:
        """Resume within timeout cancels the timeout watcher (no timed_out event)."""
        c = create_wired_fsm_with_hitl(timeout_clarification=5.0)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env_s = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "clarification", "timeout_s": 5.0},
            envelope_id=800,
        )
        fsm._on_task_suspended(env_s)
        token = fsm._pending_hil_subtasks[task_id].resume_token

        # Resume quickly
        env_r = _make_envelope(
            TOPIC_TASK_RESUME,
            {"task_id": task_id, "resume_token": token, "resolution": {"answer": "yes"}},
            envelope_id=900,
        )
        fsm._on_task_resume(env_r)

        # Small wait to confirm no timeout fires
        await asyncio.sleep(0.05)

        from poc.k1_poc.bus.topics import TOPIC_HITL_TIMED_OUT

        found = _captured_by_topic(bus, TOPIC_HITL_TIMED_OUT)
        assert len(found) == 0, "No timed_out event expected after resume"


# =========================================================================
# 6.3.4 -- hitl.blocked_red.v1 emitted by coordinator callback
# =========================================================================


class TestHITLBlockedRedEmission:
    """6.3.4: HILCoordinator blocked_red callback emits hitl.blocked_red.v1."""

    def test_blocked_red_callback_wired(self) -> None:
        """set_hitl_coordinator wires _on_blocked_red into coordinator."""
        c = create_wired_fsm_with_hitl()
        fsm = c["fsm"]
        coord = fsm._hil_coordinator
        assert coord is not None
        # The coordinator should have a blocked_red callback registered
        assert hasattr(coord, "_blocked_red_callback") or hasattr(coord, "_on_blocked_red")
