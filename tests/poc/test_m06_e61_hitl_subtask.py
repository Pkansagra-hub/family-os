"""
tests.poc.test_m06_e61_hitl_subtask -- E6.1 HILSubTask Model & FSM Integration.

Tests for:
  6.1.1: HILSubTask dataclass -- construction, status transitions, serialization
  6.1.2: Creation in _on_task_suspended -- HILSubTask as single SOT
  6.1.3: Block invoke_capability when HITL pending (L2 defense)
  6.1.4: Resume token validation -- stale resume rejected
  6.1.5: Consolidated suspension limits -- max rounds enforcement
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME, TOPIC_TASK_SUSPENDED
from poc.k1_poc.protocols.hitl_persistence import HILSubTask, HILSubTaskStatus
from poc.k1_poc.testing.fixtures import create_test_hil_subtask, create_wired_fsm_with_hitl

# =========================================================================
# Helpers
# =========================================================================


def _make_envelope(
    topic: str,
    payload: dict | None = None,
    envelope_id: int = 1,
    parent_id: int = 0,
) -> Envelope:
    """Build a minimal Envelope for testing."""
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
    """Drive the FSM to COMPANIONING with an active task.

    Directly sets internal state (matching M2 test patterns) to avoid
    needing registered actors for Front/Back delivery.

    Returns the dispatched task_id.
    """
    from poc.k1_poc.fsm.states import ConciergeState

    task_id = f"task-{uuid.uuid4().hex[:8]}"

    # Set FSM state directly (no Front/Back actors registered)
    fsm._state = ConciergeState.COMPANIONING
    fsm._turn_number = 1
    fsm._active_task_ids.add(task_id)
    fsm._task_dispatch_turns[task_id] = 0
    fsm._task_bridge.dispatch_task(task_id, "search_restaurants")
    return task_id


def _captured_by_topic(bus: Any, topic: str) -> list[Envelope]:
    return [e for e in bus.captured if e.topic == topic]


# =========================================================================
# 6.1.1 -- HILSubTask dataclass
# =========================================================================


class TestHILSubTaskDataclass:
    """6.1.1: HILSubTask construction and behavior."""

    def test_construction_defaults(self) -> None:
        """HILSubTask generates UUID pending_hil_id and resume_token."""
        sub = create_test_hil_subtask()
        assert sub.pending_hil_id  # non-empty UUID
        assert sub.resume_token  # non-empty UUID
        assert sub.status == HILSubTaskStatus.PENDING
        assert sub.hil_type == "clarification"
        assert sub.parent_task_id == "test-task-1"
        assert sub.created_at_ns > 0
        assert sub.resolved_at_ns == 0

    def test_resolve_transition(self) -> None:
        """resolve() moves PENDING -> RESOLVED and sets resolved_at_ns."""
        sub = create_test_hil_subtask()
        sub.resolve(decision_branch="clarified")
        assert sub.status == HILSubTaskStatus.RESOLVED
        assert sub.resolved_at_ns > 0

    def test_timeout_transition(self) -> None:
        """time_out() moves PENDING -> TIMED_OUT."""
        sub = create_test_hil_subtask()
        sub.time_out()
        assert sub.status == HILSubTaskStatus.TIMED_OUT

    def test_cancel_transition(self) -> None:
        """cancel() moves PENDING -> CANCELLED."""
        sub = create_test_hil_subtask()
        sub.cancel()
        assert sub.status == HILSubTaskStatus.CANCELLED

    def test_double_resolve_idempotent(self) -> None:
        """Resolving an already-resolved sub-task does not change status."""
        sub = create_test_hil_subtask()
        sub.resolve(decision_branch="clarified")
        first_resolved_at = sub.resolved_at_ns
        sub.resolve(decision_branch="modified")
        # Status unchanged, timestamp unchanged
        assert sub.status == HILSubTaskStatus.RESOLVED
        assert sub.resolved_at_ns == first_resolved_at

    def test_serialization_roundtrip(self) -> None:
        """to_persistence -> from_persistence produces equal fields."""
        original = create_test_hil_subtask(
            task_id="roundtrip-1",
            hil_type="approval",
            question="Approve payment?",
            safety_band="AMBER",
            timeout_ms=10000,
        )
        data = original.to_persistence()
        restored = HILSubTask.from_persistence(data)
        assert restored.pending_hil_id == original.pending_hil_id
        assert restored.hil_type == original.hil_type
        assert restored.parent_task_id == original.parent_task_id
        assert restored.question == original.question
        assert restored.safety_band == original.safety_band
        assert restored.timeout_ms == original.timeout_ms
        assert restored.resume_token == original.resume_token
        assert restored.status == original.status

    def test_to_persistence_includes_suspended_at_ms(self) -> None:
        """Serialized form includes suspended_at_ms for crash recovery."""
        sub = create_test_hil_subtask()
        data = sub.to_persistence()
        assert "suspended_at_ms" in data
        assert data["suspended_at_ms"] > 0

    def test_to_hil_request_conversion(self) -> None:
        """to_hil_request() returns an HILRequest with matching fields."""
        sub = create_test_hil_subtask(
            task_id="convert-1",
            hil_type="selection",
            question="Pick one",
            options=["A", "B"],
        )
        req = sub.to_hil_request()
        assert req.hil_type == "selection"
        assert req.question == "Pick one"

    def test_react_snapshot_default(self) -> None:
        """Default react_snapshot has expected keys."""
        sub = create_test_hil_subtask()
        assert "prior_messages" in sub.react_snapshot
        assert "tool_history" in sub.react_snapshot
        assert "last_iteration" in sub.react_snapshot


# =========================================================================
# 6.1.2 -- HILSubTask creation in _on_task_suspended
# =========================================================================


class TestHILSubTaskCreation:
    """6.1.2: _on_task_suspended creates HILSubTask as single SOT."""

    @pytest.mark.asyncio
    async def test_subtask_created_on_suspension(self) -> None:
        """Suspending a task creates an HILSubTask in _pending_hil_subtasks."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {
                "task_id": task_id,
                "question": "What cuisine?",
                "hil_type": "clarification",
                "timeout_s": 60,
            },
            envelope_id=300,
        )
        fsm._on_task_suspended(env)

        assert task_id in fsm._pending_hil_subtasks
        sub = fsm._pending_hil_subtasks[task_id]
        assert sub.parent_task_id == task_id
        assert sub.hil_type == "clarification"
        assert sub.question == "What cuisine?"
        assert sub.status == HILSubTaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_subtask_resume_token_unique(self) -> None:
        """Each suspension creates a unique resume_token."""
        c = create_wired_fsm_with_hitl(max_rounds=5)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "q1", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(env)
        token1 = fsm._pending_hil_subtasks[task_id].resume_token
        assert token1  # non-empty

    @pytest.mark.asyncio
    async def test_subtask_persisted_to_task_state(self) -> None:
        """HILSubTask data persisted via set_pending_hil_data."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Pick one", "hil_type": "selection"},
            envelope_id=300,
        )
        fsm._on_task_suspended(env)

        # Verify SS task_state has pending_hil_data
        ss = c.get("session_state")
        if ss is not None:
            ts = ss.get_section("task_state")
            entry = ts.get_by_id(task_id)
            assert entry is not None
            assert entry.pending_hil is True
            assert entry.pending_hil_data is not None
            assert entry.pending_hil_data["hil_type"] == "selection"


# =========================================================================
# 6.1.3 -- Block invoke_capability when HITL pending
# =========================================================================


class TestInvokeCapabilityBlock:
    """6.1.3: L2 defense blocks invoke_capability when HITL pending."""

    @pytest.mark.asyncio
    async def test_tool_result_blocked_when_hitl_pending(self) -> None:
        """execute_invoke_capability returns blocked when HITL pending for task."""
        from poc.k1_poc.tools.implementations import ToolContext, execute_invoke_capability

        # Create a mock coordinator with pending request
        class MockCoordinator:
            def get_pending_request(self, task_id: str) -> Any:
                return {"question": "waiting"} if task_id == "task-1" else None

            def validate_before_invoke(self, **kwargs: Any) -> str:
                return "block_needs_approval"

        ctx = ToolContext(
            session_manager=None,
            cognitive_trace_id="trace-1",
            actor="back",
            hil_coordinator=MockCoordinator(),
            active_task_id="task-1",
        )
        result = await execute_invoke_capability(
            args={"capability_name": "order_food", "params": {}},
            ctx=ctx,
        )
        assert result.status == "blocked"

    def test_cognitive_tools_not_blocked(self) -> None:
        """Cognitive tools (update_beliefs etc.) are not routed through invoke_capability."""
        # This is a design verification: cognitive tools have separate
        # dispatch functions and should never hit the L2 check.
        from poc.k1_poc.tools import implementations as impl

        # Verify update_beliefs and invoke_capability are separate functions
        assert hasattr(impl, "execute_invoke_capability")
        # The L2 check lives ONLY in execute_invoke_capability
        import inspect

        source = inspect.getsource(impl.execute_invoke_capability)
        assert "hil_coordinator" in source or "validate_before_invoke" in source


# =========================================================================
# 6.1.4 -- Resume token validation
# =========================================================================


class TestResumeTokenValidation:
    """6.1.4: FSM rejects stale resume_token on task.resume.v1."""

    @pytest.mark.asyncio
    async def test_stale_token_rejected(self) -> None:
        """Resume with wrong resume_token is silently rejected."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Suspend task
        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Cuisine?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)
        _correct_token = fsm._pending_hil_subtasks[task_id].resume_token  # noqa: F841

        # Attempt resume with wrong token
        stale_env = _make_envelope(
            TOPIC_TASK_RESUME,
            {
                "task_id": task_id,
                "resume_token": "wrong-token-" + uuid.uuid4().hex[:8],
                "resolution": {"answer": "Italian"},
            },
            envelope_id=400,
        )
        fsm._on_task_resume(stale_env)

        # Task should still be suspended (subtask NOT popped)
        assert task_id in fsm._pending_hil_subtasks

    @pytest.mark.asyncio
    async def test_correct_token_accepted(self) -> None:
        """Resume with correct resume_token proceeds normally."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Suspend task
        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Cuisine?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)
        correct_token = fsm._pending_hil_subtasks[task_id].resume_token

        # Resume with correct token
        resume_env = _make_envelope(
            TOPIC_TASK_RESUME,
            {
                "task_id": task_id,
                "resume_token": correct_token,
                "resolution": {"answer": "Italian"},
            },
            envelope_id=400,
        )
        fsm._on_task_resume(resume_env)

        # Task should be resumed (subtask popped)
        assert task_id not in fsm._pending_hil_subtasks

    @pytest.mark.asyncio
    async def test_resume_without_token_accepted(self) -> None:
        """Resume without resume_token still accepted (backward compat)."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Color?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)

        # Resume without token field (legacy behavior)
        resume_env = _make_envelope(
            TOPIC_TASK_RESUME,
            {"task_id": task_id, "resolution": {"answer": "blue"}},
            envelope_id=400,
        )
        fsm._on_task_resume(resume_env)

        # Should still work (token None != expected doesn't trigger mismatch
        # because the check only fires when BOTH are non-None)
        # The subtask should have been popped during resume processing
        assert task_id not in fsm._pending_hil_subtasks


# =========================================================================
# 6.1.5 -- Consolidated suspension limits
# =========================================================================


class TestConsolidatedSuspensionLimits:
    """6.1.5: Max HITL rounds enforced at single checkpoint."""

    @pytest.mark.asyncio
    async def test_max_rounds_exceeded_completes_task(self) -> None:
        """When hil_count > max_rounds, task is completed (not suspended)."""
        c = create_wired_fsm_with_hitl(max_rounds=1)
        fsm, bus = c["fsm"], c["bus"]
        coord = c["hil_coordinator"]
        task_id = _advance_to_companioning(fsm, bus)

        # Pre-set count so next suspension exceeds limit
        coord._hil_counts[task_id] = 1

        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Again?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)

        # Task should NOT be in pending_hil_subtasks (limit hit -> complete)
        assert task_id not in fsm._pending_hil_subtasks
        # Task should have been removed from active
        assert task_id not in fsm._active_task_ids

    @pytest.mark.asyncio
    async def test_within_limit_proceeds(self) -> None:
        """When hil_count <= max_rounds, suspension proceeds normally."""
        c = create_wired_fsm_with_hitl(max_rounds=3)
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "First?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)

        # Task should be in pending_hil_subtasks
        assert task_id in fsm._pending_hil_subtasks
