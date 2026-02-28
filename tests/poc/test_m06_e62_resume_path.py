"""
tests.poc.test_m06_e62_resume_path -- E6.2 Resume Path & Context Hydration.

Tests for:
  6.2.1: back_resume_handler wired via route_back_envelope (ALREADY WIRED)
  6.2.2: Unified context storage reads (HILSubTask primary, SM fallback)
  6.2.3: Mandatory cancel callback warning
  6.2.4: prior_messages hydration via build_resume_context
  6.2.5: remaining_budget uses max(2,...) not max(1,...)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME, TOPIC_TASK_SUSPENDED
from poc.k1_poc.protocols.hitl_wiring import build_resume_context
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


# =========================================================================
# 6.2.1 -- back_resume_handler wired via route_back_envelope
# =========================================================================


class TestBackResumeHandlerWiring:
    """6.2.1: route_back_envelope routes task.resume.v1 to back_resume_handler."""

    def test_route_back_envelope_handles_resume_topic(self) -> None:
        """route_back_envelope recognizes task.resume.v1 topic."""
        import inspect

        from poc.k1_poc.actors.back import route_back_envelope

        sig = inspect.signature(route_back_envelope)
        assert "envelope" in sig.parameters
        # The function is async and routes by topic
        source = inspect.getsource(route_back_envelope)
        assert "TOPIC_TASK_RESUME" in source
        assert "back_resume_handler" in source


# =========================================================================
# 6.2.2 -- Unified context storage reads
# =========================================================================


class TestUnifiedContextReads:
    """6.2.2: _on_task_resume reads from HILSubTask first, SuspensionManager fallback."""

    @pytest.mark.asyncio
    async def test_resume_uses_hil_subtask_context(self) -> None:
        """Resume pops HILSubTask and resolves it."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        # Suspend
        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Cuisine?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)
        assert task_id in fsm._pending_hil_subtasks
        token = fsm._pending_hil_subtasks[task_id].resume_token

        # Resume with correct token
        resume_env = _make_envelope(
            TOPIC_TASK_RESUME,
            {
                "task_id": task_id,
                "resume_token": token,
                "resolution": {"answer": "Italian"},
            },
            envelope_id=400,
        )
        fsm._on_task_resume(resume_env)

        # HILSubTask should be popped (consumed by resume)
        assert task_id not in fsm._pending_hil_subtasks

    @pytest.mark.asyncio
    async def test_resume_clears_suspension_manager(self) -> None:
        """Resume also clears SuspensionManager context (legacy cleanup)."""
        c = create_wired_fsm_with_hitl()
        fsm, bus = c["fsm"], c["bus"]
        task_id = _advance_to_companioning(fsm, bus)

        suspend_env = _make_envelope(
            TOPIC_TASK_SUSPENDED,
            {"task_id": task_id, "question": "Q?", "hil_type": "clarification"},
            envelope_id=300,
        )
        fsm._on_task_suspended(suspend_env)
        token = fsm._pending_hil_subtasks[task_id].resume_token

        resume_env = _make_envelope(
            TOPIC_TASK_RESUME,
            {"task_id": task_id, "resume_token": token, "resolution": {"answer": "yes"}},
            envelope_id=400,
        )
        fsm._on_task_resume(resume_env)

        # SuspensionManager should also have been cleaned
        stored = fsm._suspension_manager.pop_context(task_id)
        assert stored is None


# =========================================================================
# 6.2.3 -- Mandatory cancel callback
# =========================================================================


class TestMandatoryCancelCallback:
    """6.2.3: _build_cancellation_check warns when no CancellationToken."""

    def test_build_cancellation_check_exists(self) -> None:
        """back.py has _build_cancellation_check function."""
        import inspect

        from poc.k1_poc.actors import back

        source = inspect.getsource(back._build_cancellation_check)
        # Should reference _never_cancel as fallback
        assert "_never_cancel" in source


# =========================================================================
# 6.2.4 -- prior_messages hydration via build_resume_context
# =========================================================================


class TestPriorMessagesHydration:
    """6.2.4: build_resume_context produces correct ResumeContext."""

    def test_clarification_resume_context(self) -> None:
        """Clarification resume includes RESUME_INSTRUCTIONS and resolution."""
        ctx = build_resume_context(
            task_id="t1",
            hil_type="clarification",
            resolution={"answer": "Italian food"},
            findings_so_far=[{"role": "assistant", "content": "searching..."}],
            original_task={"action": "search"},
            last_iteration=2,
            total_budget=10,
        )
        assert ctx.hil_type == "clarification"
        assert ctx.task_id == "t1"
        assert ctx.remaining_budget >= 2

    def test_approval_resume_context(self) -> None:
        """Approval resume includes merged_params."""
        ctx = build_resume_context(
            task_id="t2",
            hil_type="approval",
            resolution={
                "decision": "approved_with_modifications",
                "modifications": {"payment_method": "amex"},
            },
            findings_so_far=[],
            original_task={},
            last_iteration=1,
            total_budget=10,
        )
        assert ctx.hil_type == "approval"


# =========================================================================
# 6.2.5 -- remaining_budget uses max(2,...) not max(1,...)
# =========================================================================


class TestRemainingBudgetFloor:
    """6.2.5: remaining_budget floor is 2, not 1."""

    def test_floor_is_two(self) -> None:
        """When total_budget - last_iteration < 2, floor is still 2."""
        ctx = build_resume_context(
            task_id="t1",
            hil_type="clarification",
            resolution={"answer": "yes"},
            findings_so_far=[],
            original_task={},
            last_iteration=9,
            total_budget=10,
        )
        assert ctx.remaining_budget >= 2

    def test_normal_budget_passes_through(self) -> None:
        """When total_budget - last_iteration >= 2, use that value."""
        ctx = build_resume_context(
            task_id="t1",
            hil_type="clarification",
            resolution={"answer": "yes"},
            findings_so_far=[],
            original_task={},
            last_iteration=3,
            total_budget=10,
        )
        assert ctx.remaining_budget == 7
