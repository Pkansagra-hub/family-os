"""
tests.poc.test_m06_e64_crash_recovery -- E6.4 Crash Recovery.

Tests for:
  6.4.1: HILSubTask persisted via set_pending_hil_data (SS roundtrip)
  6.4.2: scan_for_recovery categorizes SUSPENDED tasks
  6.4.3: _recover_hitl_on_startup re-presents recoverable tasks
  6.4.4: _recover_hitl_on_startup auto-cancels expired tasks
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import TOPIC_TASK_SUSPENDED
from poc.k1_poc.protocols.hitl_persistence import HILSubTask, HILSubTaskStatus, scan_for_recovery
from poc.k1_poc.testing.fixtures import create_test_hil_subtask, create_wired_fsm_with_hitl

# =========================================================================
# Helpers
# =========================================================================


def _now_ms() -> int:
    return int(time.monotonic_ns() / 1_000_000)


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
# 6.4.1 -- HILSubTask persisted via set_pending_hil_data (SS roundtrip)
# =========================================================================


class TestHILSubTaskPersistence:
    """6.4.1: HILSubTask serialized and stored in TaskStateEntry.pending_hil_data."""

    @pytest.mark.asyncio
    async def test_persist_on_suspension(self) -> None:
        """_on_task_suspended persists HILSubTask to task_state via set_pending_hil_data."""
        c = create_wired_fsm_with_hitl(with_ss_binding=True)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "clarification"},
            envelope_id=100,
        )
        fsm._on_task_suspended(env)

        # Read back from task_bridge
        entry = fsm._task_bridge.get_task(task_id)
        assert entry is not None
        assert entry.pending_hil_data is not None
        assert entry.pending_hil_data["hil_type"] == "clarification"
        assert "resume_token" in entry.pending_hil_data
        assert "pending_hil_id" in entry.pending_hil_data

    @pytest.mark.asyncio
    async def test_persistence_roundtrip(self) -> None:
        """HILSubTask.from_persistence(to_persistence()) recovers same state."""
        subtask = create_test_hil_subtask(
            task_id="t-round",
            hil_type="approval",
            question="Approve purchase?",
            timeout_ms=30_000,
        )
        data = subtask.to_persistence()
        recovered = HILSubTask.from_persistence(data)

        assert recovered.pending_hil_id == subtask.pending_hil_id
        assert recovered.hil_type == subtask.hil_type
        assert recovered.resume_token == subtask.resume_token
        assert recovered.question == subtask.question
        assert recovered.timeout_ms == subtask.timeout_ms
        assert recovered.status == HILSubTaskStatus.PENDING


# =========================================================================
# 6.4.2 -- scan_for_recovery categorizes SUSPENDED tasks
# =========================================================================


class TestScanForRecovery:
    """6.4.2: scan_for_recovery correctly triages SUSPENDED tasks."""

    def test_no_suspended_tasks(self) -> None:
        """Empty task_state returns empty report."""
        report = scan_for_recovery({})
        assert report.total_scanned == 0
        assert report.recovered_count == 0
        assert report.timed_out_count == 0

    def test_active_tasks_skipped(self) -> None:
        """Tasks with status != SUSPENDED are skipped."""
        state = {
            "t1": {"status": "ACTIVE", "pending_hil": None},
            "t2": {"status": "COMPLETED", "pending_hil": None},
        }
        report = scan_for_recovery(state)
        assert report.skipped_count == 2
        assert report.recovered_count == 0

    def test_expired_task_timed_out(self) -> None:
        """SUSPENDED task past its deadline is marked timed_out."""
        now = _now_ms()
        state = {
            "t1": {
                "status": "SUSPENDED",
                "pending_hil": {
                    "suspended_at_ms": now - 120_000,
                    "timeout_ms": 60_000,
                },
            },
        }
        report = scan_for_recovery(state, now_ms=now)
        assert "t1" in report.timed_out_task_ids
        assert report.timed_out_count == 1

    def test_recoverable_task(self) -> None:
        """SUSPENDED task within its deadline is marked recovered."""
        now = _now_ms()
        state = {
            "t1": {
                "status": "SUSPENDED",
                "pending_hil": {
                    "suspended_at_ms": now - 10_000,
                    "timeout_ms": 60_000,
                },
            },
        }
        report = scan_for_recovery(state, now_ms=now)
        assert "t1" in report.recovered_task_ids
        assert report.recovered_count == 1

    def test_mixed_tasks(self) -> None:
        """Mix of expired, recoverable, and active tasks."""
        now = _now_ms()
        state = {
            "t_expired": {
                "status": "SUSPENDED",
                "pending_hil": {
                    "suspended_at_ms": now - 200_000,
                    "timeout_ms": 60_000,
                },
            },
            "t_ok": {
                "status": "SUSPENDED",
                "pending_hil": {
                    "suspended_at_ms": now - 5_000,
                    "timeout_ms": 60_000,
                },
            },
            "t_active": {
                "status": "ACTIVE",
                "pending_hil": None,
            },
        }
        report = scan_for_recovery(state, now_ms=now)
        assert report.total_scanned == 3
        assert report.timed_out_count == 1
        assert report.recovered_count == 1
        assert report.skipped_count == 1


# =========================================================================
# 6.4.3 -- _recover_hitl_on_startup re-presents recoverable
# =========================================================================


class TestRecoverRePresent:
    """6.4.3: _recover_hitl_on_startup reconstructs HILSubTask for recoverable tasks."""

    @pytest.mark.asyncio
    async def test_recover_repopulates_pending_subtasks(self) -> None:
        """Recoverable tasks get their HILSubTask reconstructed in _pending_hil_subtasks."""
        c = create_wired_fsm_with_hitl(with_ss_binding=True)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Suspend to create pending_hil_data
        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {
                "task_id": task_id,
                "question": "Cuisine?",
                "hil_type": "clarification",
                "timeout_s": 300,
            },
            envelope_id=200,
        )
        fsm._on_task_suspended(env)

        # Capture the persisted data and original resume token
        entry = fsm._task_bridge.get_task(task_id)
        assert entry is not None
        original_token = fsm._pending_hil_subtasks[task_id].resume_token

        # Simulate restart: clear in-memory state
        fsm._pending_hil_subtasks.clear()

        # Re-run recovery
        fsm._recover_hitl_on_startup()

        # Should have recovered the subtask
        assert task_id in fsm._pending_hil_subtasks
        recovered = fsm._pending_hil_subtasks[task_id]
        assert recovered.resume_token == original_token
        assert recovered.hil_type == "clarification"


# =========================================================================
# 6.4.4 -- _recover_hitl_on_startup auto-cancels expired
# =========================================================================


class TestRecoverAutoCancel:
    """6.4.4: _recover_hitl_on_startup auto-cancels expired HITL tasks."""

    @pytest.mark.asyncio
    async def test_expired_task_emits_timed_out(self) -> None:
        """Expired tasks get hitl.timed_out.v1 emitted during recovery."""
        c = create_wired_fsm_with_hitl(with_ss_binding=True)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Suspend with very short timeout
        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {
                "task_id": task_id,
                "question": "Q?",
                "hil_type": "clarification",
                "timeout_s": 0.001,
            },
            envelope_id=300,
        )
        fsm._on_task_suspended(env)

        # Manually expire the persisted data by setting suspended_at_ms far in the past
        entry = fsm._task_bridge.get_task(task_id)
        if entry and entry.pending_hil_data:
            entry.pending_hil_data["suspended_at_ms"] = _now_ms() - 999_999
            entry.pending_hil_data["timeout_ms"] = 1  # 1ms timeout
            fsm._task_bridge.set_pending_hil_data(task_id, entry.pending_hil_data)

        # Clear in-memory state (simulate restart)
        fsm._pending_hil_subtasks.clear()
        # Cancel existing timeout watcher to avoid double-fire
        for t in list(fsm._suspension_manager._timeout_tasks.values()):
            t.cancel()
        fsm._suspension_manager._timeout_tasks.clear()

        # Clear captured before recovery to isolate recovery events
        bus.captured.clear()

        # Run recovery
        fsm._recover_hitl_on_startup()

        from poc.k1_poc.bus.topics import TOPIC_HITL_TIMED_OUT

        found = _captured_by_topic(bus, TOPIC_HITL_TIMED_OUT)
        assert len(found) >= 1, f"Expected timed_out event, got {len(found)}"
        payload = json.loads(found[0].payload)
        assert payload["task_id"] == task_id
        assert payload.get("recovery") is True

    @pytest.mark.asyncio
    async def test_expired_not_in_pending_subtasks(self) -> None:
        """Expired tasks do not get reconstructed in _pending_hil_subtasks."""
        c = create_wired_fsm_with_hitl(with_ss_binding=True)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "clarification", "timeout_s": 0.001},
            envelope_id=400,
        )
        fsm._on_task_suspended(env)

        entry = fsm._task_bridge.get_task(task_id)
        if entry and entry.pending_hil_data:
            entry.pending_hil_data["suspended_at_ms"] = _now_ms() - 999_999
            entry.pending_hil_data["timeout_ms"] = 1
            fsm._task_bridge.set_pending_hil_data(task_id, entry.pending_hil_data)

        fsm._pending_hil_subtasks.clear()
        for t in list(fsm._suspension_manager._timeout_tasks.values()):
            t.cancel()
        fsm._suspension_manager._timeout_tasks.clear()

        fsm._recover_hitl_on_startup()

        assert task_id not in fsm._pending_hil_subtasks
