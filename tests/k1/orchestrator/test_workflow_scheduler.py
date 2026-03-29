"""
Tests for k1.orchestrator.workflows.workflow_scheduler (Issue 4.2.1).

Verifies:
  - compute_next_fire() for CRON, EVENT, MANUAL trigger types.
  - WorkflowScheduler lifecycle (start/stop).
  - _tick() fires due triggers and enqueues WorkflowRunRequest.
  - _tick() updates trigger state after successful enqueue.
  - MailboxFullError is caught and trigger state is NOT updated.
  - Inactive/missing workflows are skipped gracefully.
  - Crash recovery: missed fires dispatched on first tick.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.ports.mailbox_port import MailboxFullError, MailboxMessage
from k1.orchestrator.types import PlanStep, TriggerSpec, TriggerType, WorkflowRunRequest
from k1.orchestrator.workflows.system_clock import FrozenClock
from k1.orchestrator.workflows.workflow_scheduler import (
    MAX_FLOAT,
    WorkflowScheduler,
    compute_next_fire,
)
from k1.orchestrator.workflows.workflow_types import WorkflowSpec

# ===========================================================================
# Helpers / Fakes
# ===========================================================================


def _make_step(step_id: str = "s1", capability: str = "test.cap") -> PlanStep:
    """Minimal PlanStep for WorkflowSpec construction."""
    return PlanStep(id=step_id, capability=capability)


def _make_spec(
    workflow_id: str = "wf-1",
    version: str = "1.0.0",
    active: bool = True,
    trigger_type: TriggerType = TriggerType.CRON,
    schedule: Optional[str] = "*/5 * * * *",
) -> WorkflowSpec:
    """Build a minimal valid WorkflowSpec."""
    trigger = TriggerSpec(type=trigger_type, schedule=schedule)
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=f"test-workflow-{workflow_id}",
        source_plan_id="plan-001",
        version=version,
        trigger=trigger,
        steps=[_make_step()],
        dependencies={},
        active=active,
    )


class FakeMailbox:
    """In-memory mailbox that records enqueue calls."""

    def __init__(self, *, raise_full: bool = False) -> None:
        self.messages: List[Tuple[MailboxMessage, str]] = []
        self._raise_full = raise_full

    def enqueue(self, message: MailboxMessage, priority: str = "INTERACTIVE") -> int:
        if self._raise_full:
            raise MailboxFullError("mailbox full")
        self.messages.append((message, priority))
        return len(self.messages) - 1

    def dequeue(self) -> Optional[MailboxMessage]:
        if self.messages:
            return self.messages.pop(0)[0]
        return None

    def depth(self) -> int:
        return len(self.messages)

    def peek_priority(self) -> Optional[str]:
        if self.messages:
            return self.messages[0][1]
        return None


class FakeStorage:
    """In-memory storage that backs scheduler tests."""

    def __init__(self) -> None:
        self._workflows: Dict[str, WorkflowSpec] = {}
        self._due_triggers: List[Tuple[str, TriggerSpec]] = []
        self._trigger_updates: List[Tuple[str, float, float]] = []

    def set_due_triggers(self, due: List[Tuple[str, TriggerSpec]]) -> None:
        self._due_triggers = list(due)

    def add_workflow(self, spec: WorkflowSpec) -> None:
        self._workflows[spec.workflow_id] = spec

    # -- IWorkflowStoragePort methods used by scheduler --

    async def get_due_triggers(self, now: float) -> List[Tuple[str, TriggerSpec]]:
        return self._due_triggers

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        self._trigger_updates.append((workflow_id, next_fire, last_fire))

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]:
        return self._workflows.get(workflow_id)

    # -- Unused stubs required by Protocol shape --

    async def save_workflow(self, spec: Any) -> None:
        pass

    async def list_workflows(self, active_only: bool = True) -> List[Any]:
        return []

    async def delete_workflow(self, workflow_id: str) -> None:
        pass

    async def purge_workflow(self, workflow_id: str) -> None:
        pass

    async def save_trigger(self, workflow_id: str, trigger: Any) -> None:
        pass

    async def save_run(self, manifest: Any) -> None:
        pass

    async def get_runs(self, workflow_id: str, limit: int = 10) -> List[Any]:
        return []

    async def save_gap(self, gap: Any) -> None:
        pass

    async def get_pending_gaps(self) -> List[Any]:
        return []


class FakeStatePort:
    """Stub IStateReadPort (not exercised in scheduler V1 tests)."""

    async def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return None

    async def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]:
        return {}

    async def get_snapshot(self, session_id: str) -> Any:
        return None


# ===========================================================================
# compute_next_fire tests
# ===========================================================================


class TestComputeNextFireCron:
    """compute_next_fire for CRON triggers uses croniter."""

    def test_every_5_minutes(self) -> None:
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        # Base time: 2023-11-14 22:13:20 UTC
        now = 1700000000.0
        result = compute_next_fire(trigger, now)
        # Must be in the future
        assert result > now
        # Must be within 5 minutes
        assert result <= now + 5 * 60

    def test_hourly(self) -> None:
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="0 * * * *")
        now = 1700000000.0
        result = compute_next_fire(trigger, now)
        assert result > now
        assert result <= now + 3600

    def test_respects_timezone(self) -> None:
        trigger = TriggerSpec(
            type=TriggerType.CRON,
            schedule="0 9 * * *",
            timezone="US/Eastern",
        )
        now = 1700000000.0
        result = compute_next_fire(trigger, now)
        assert result > now

    def test_missing_schedule_raises(self) -> None:
        """CRON trigger with no schedule is rejected at TriggerSpec construction."""
        with pytest.raises(ValueError, match="schedule"):
            TriggerSpec(type=TriggerType.CRON, schedule=None)


class TestComputeNextFireEvent:
    """EVENT triggers return MAX_FLOAT (no schedule)."""

    def test_returns_max_float(self) -> None:
        trigger = TriggerSpec(type=TriggerType.EVENT, event_topic="cap.updated")
        result = compute_next_fire(trigger, 1700000000.0)
        assert result == MAX_FLOAT


class TestComputeNextFireManual:
    """MANUAL triggers return MAX_FLOAT."""

    def test_returns_max_float(self) -> None:
        trigger = TriggerSpec(type=TriggerType.MANUAL)
        result = compute_next_fire(trigger, 1700000000.0)
        assert result == MAX_FLOAT


# ===========================================================================
# WorkflowScheduler lifecycle tests
# ===========================================================================


class TestSchedulerLifecycle:
    """start() / stop() / running property."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        storage = FakeStorage()
        mailbox = FakeMailbox()
        clock = FrozenClock(1700000000.0)
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), clock)
        await scheduler.start()
        assert scheduler.running is True
        await scheduler.stop()
        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        storage = FakeStorage()
        mailbox = FakeMailbox()
        clock = FrozenClock(1700000000.0)
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), clock)
        await scheduler.start()
        await scheduler.start()  # no-op
        assert scheduler.running is True
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        scheduler = WorkflowScheduler(
            FakeStorage(), FakeMailbox(), FakeStatePort(), FrozenClock(1.0)
        )
        await scheduler.stop()  # no-op when not started
        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        storage = FakeStorage()
        mailbox = FakeMailbox()
        clock = FrozenClock(1700000000.0)
        scheduler = WorkflowScheduler(
            storage, mailbox, FakeStatePort(), clock, tick_interval_s=0.01
        )
        await scheduler.start()
        assert scheduler._task is not None
        await scheduler.stop()
        assert scheduler._task is None


# ===========================================================================
# _tick() behaviour tests
# ===========================================================================


class TestSchedulerTick:
    """Direct _tick() invocations for deterministic testing."""

    @pytest.mark.asyncio
    async def test_no_due_triggers_is_noop(self) -> None:
        storage = FakeStorage()
        mailbox = FakeMailbox()
        clock = FrozenClock(1700000000.0)
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), clock)
        await scheduler._tick()
        assert len(mailbox.messages) == 0
        assert len(storage._trigger_updates) == 0

    @pytest.mark.asyncio
    async def test_fires_due_cron_trigger(self) -> None:
        now = 1700000000.0
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _make_spec(workflow_id="wf-cron", trigger_type=TriggerType.CRON)
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-cron", trigger)])
        mailbox = FakeMailbox()
        clock = FrozenClock(now)
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), clock)

        await scheduler._tick()

        # One message enqueued
        assert len(mailbox.messages) == 1
        msg, priority = mailbox.messages[0]
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.workflow_id == "wf-cron"
        assert msg.version == "1.0.0"
        assert msg.trigger_type == TriggerType.CRON
        assert priority == "INTERACTIVE"
        assert msg.trigger_context["triggered_at"] == now

        # Trigger state updated
        assert len(storage._trigger_updates) == 1
        wf_id, next_fire, last_fire = storage._trigger_updates[0]
        assert wf_id == "wf-cron"
        assert last_fire == now
        assert next_fire > now

    @pytest.mark.asyncio
    async def test_fires_multiple_triggers(self) -> None:
        now = 1700000000.0
        t1 = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        t2 = TriggerSpec(type=TriggerType.CRON, schedule="0 * * * *")
        spec1 = _make_spec(workflow_id="wf-a")
        spec2 = _make_spec(workflow_id="wf-b")
        storage = FakeStorage()
        storage.add_workflow(spec1)
        storage.add_workflow(spec2)
        storage.set_due_triggers([("wf-a", t1), ("wf-b", t2)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(now))

        await scheduler._tick()

        assert len(mailbox.messages) == 2
        assert len(storage._trigger_updates) == 2

    @pytest.mark.asyncio
    async def test_skips_missing_workflow(self) -> None:
        """Trigger references a workflow_id not in storage."""
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        storage = FakeStorage()
        # Do NOT add the workflow
        storage.set_due_triggers([("wf-ghost", trigger)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(1700000000.0))

        await scheduler._tick()

        assert len(mailbox.messages) == 0
        assert len(storage._trigger_updates) == 0

    @pytest.mark.asyncio
    async def test_skips_inactive_workflow(self) -> None:
        """Trigger references an inactive workflow."""
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _make_spec(workflow_id="wf-off", active=False)
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-off", trigger)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(1700000000.0))

        await scheduler._tick()

        assert len(mailbox.messages) == 0
        assert len(storage._trigger_updates) == 0


class TestSchedulerMailboxFull:
    """On MailboxFullError: log + retry, do NOT update trigger state."""

    @pytest.mark.asyncio
    async def test_mailbox_full_skips_trigger_update(self) -> None:
        now = 1700000000.0
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _make_spec(workflow_id="wf-full")
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-full", trigger)])
        mailbox = FakeMailbox(raise_full=True)
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(now))

        await scheduler._tick()

        # Message was NOT enqueued
        assert len(mailbox.messages) == 0
        # Trigger state was NOT updated (retry on next tick)
        assert len(storage._trigger_updates) == 0

    @pytest.mark.asyncio
    async def test_mailbox_full_does_not_block_other_triggers(self) -> None:
        """Even if one trigger fails, others proceed."""
        now = 1700000000.0
        t1 = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        t2 = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec1 = _make_spec(workflow_id="wf-ok")
        spec2 = _make_spec(workflow_id="wf-ok2")
        storage = FakeStorage()
        storage.add_workflow(spec1)
        storage.add_workflow(spec2)
        storage.set_due_triggers([("wf-ok", t1), ("wf-ok2", t2)])

        # Mailbox that fails only on first enqueue
        call_count = 0

        class FailFirstMailbox(FakeMailbox):
            def enqueue(self, message: MailboxMessage, priority: str = "INTERACTIVE") -> int:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise MailboxFullError("first call fails")
                return super().enqueue(message, priority)

        mailbox = FailFirstMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(now))

        await scheduler._tick()

        # Second trigger succeeded
        assert len(mailbox.messages) == 1
        msg, _ = mailbox.messages[0]
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.workflow_id == "wf-ok2"

        # Only the successful trigger's state was updated
        assert len(storage._trigger_updates) == 1
        assert storage._trigger_updates[0][0] == "wf-ok2"


class TestSchedulerCrashRecovery:
    """Crash recovery: missed triggers fire on first tick."""

    @pytest.mark.asyncio
    async def test_missed_fire_dispatched(self) -> None:
        """If next_fire < now (missed), trigger still appears in due list and fires."""
        # Simulate: a trigger was due at 1699999900 but scheduler was down.
        # Now it's 1700000000. Storage returns it as due.
        now = 1700000000.0
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _make_spec(workflow_id="wf-missed")
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-missed", trigger)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(now))

        await scheduler._tick()

        assert len(mailbox.messages) == 1
        # next_fire advanced to future (not stuck at old time)
        _, next_fire, _ = storage._trigger_updates[0]
        assert next_fire > now


class TestSchedulerPriority:
    """All enqueues use INTERACTIVE priority (SEM-3)."""

    @pytest.mark.asyncio
    async def test_priority_is_interactive(self) -> None:
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _make_spec(workflow_id="wf-prio")
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-prio", trigger)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(1700000000.0))

        await scheduler._tick()

        _, priority = mailbox.messages[0]
        assert priority == "INTERACTIVE"


class TestSchedulerEventAndManualTriggers:
    """EVENT and MANUAL triggers: next_fire = MAX_FLOAT after firing."""

    @pytest.mark.asyncio
    async def test_event_trigger_next_fire_max(self) -> None:
        trigger = TriggerSpec(type=TriggerType.EVENT, event_topic="cap.updated")
        spec = WorkflowSpec(
            workflow_id="wf-evt",
            name="test-evt",
            source_plan_id="plan-001",
            version="1.0.0",
            trigger=trigger,
            steps=[_make_step()],
            dependencies={},
        )
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-evt", trigger)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(1700000000.0))

        await scheduler._tick()

        assert len(mailbox.messages) == 1
        _, next_fire, _ = storage._trigger_updates[0]
        assert next_fire == MAX_FLOAT

    @pytest.mark.asyncio
    async def test_manual_trigger_next_fire_max(self) -> None:
        trigger = TriggerSpec(type=TriggerType.MANUAL)
        spec = _make_spec(
            workflow_id="wf-manual",
            trigger_type=TriggerType.MANUAL,
            schedule=None,
        )
        storage = FakeStorage()
        storage.add_workflow(spec)
        storage.set_due_triggers([("wf-manual", trigger)])
        mailbox = FakeMailbox()
        scheduler = WorkflowScheduler(storage, mailbox, FakeStatePort(), FrozenClock(1700000000.0))

        await scheduler._tick()

        assert len(mailbox.messages) == 1
        _, next_fire, _ = storage._trigger_updates[0]
        assert next_fire == MAX_FLOAT
