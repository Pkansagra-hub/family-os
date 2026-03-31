"""
M02 Tests: TaskState Section (Epic 2.1)
=========================================

Tests for TaskStateSection: lifecycle, transitions, read APIs,
prompt generation, pruning, and serialization.
"""

import time

import pytest

from k1.sessionstate.sections.task_state import (
    TaskStateEntry,
    TaskStateSection,
    TaskStatus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> TaskStateSection:
    return TaskStateSection()


@pytest.fixture
def section_with_tasks(section: TaskStateSection) -> TaskStateSection:
    section.add_task("order_food", task_id="t1", status=TaskStatus.PENDING)
    section.add_task("book_ride", task_id="t2", status=TaskStatus.DISPATCHED)
    section.add_task("search_hotels", task_id="t3", status=TaskStatus.PENDING)
    return section


# =============================================================================
# Epic 2.1.1: TaskStatus and TaskStateEntry
# =============================================================================


class TestTaskStatus:
    def test_all_statuses_in_all(self):
        assert len(TaskStatus.ALL) == 7

    def test_active_group(self):
        assert TaskStatus.ACTIVE_GROUP == {"dispatched", "active", "suspended"}

    def test_terminal_group(self):
        assert TaskStatus.TERMINAL == {"completed", "failed", "cancelled"}

    def test_groups_disjoint(self):
        assert not TaskStatus.ACTIVE_GROUP & TaskStatus.TERMINAL

    def test_groups_plus_pending_cover_all(self):
        assert TaskStatus.ACTIVE_GROUP | TaskStatus.TERMINAL | {"pending"} == TaskStatus.ALL


class TestTaskStateEntry:
    def test_default_values(self):
        entry = TaskStateEntry()
        assert entry.task_id == ""
        assert entry.status == TaskStatus.PENDING
        assert entry.dispatched_at_ms == 0
        assert entry.completed_at_ms == 0
        assert entry.depends_on == []
        assert entry.progress_pct == 0
        assert entry.pending_hil is False
        assert entry.hil_suspensions_count == 0
        assert entry.presented_at_turn == 0


# =============================================================================
# Epic 2.1.2: ISection Protocol
# =============================================================================


class TestISection:
    def test_name(self, section):
        assert section.name == "task_state"

    def test_tier(self, section):
        assert section.tier == "hot"

    def test_budget_bytes(self, section):
        assert section.budget_bytes == 4096

    def test_can_evict(self, section):
        assert section.can_evict is False

    def test_get_size_bytes_empty(self, section):
        assert section.get_size_bytes() > 0  # overhead

    def test_clear(self, section_with_tasks):
        assert section_with_tasks.task_count > 0
        section_with_tasks.clear()
        assert section_with_tasks.task_count == 0

    def test_get_metadata(self, section):
        meta = section.get_metadata()
        assert meta["section"] == "task_state"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 4096
        assert "task_count" in meta
        assert "active_count" in meta


# =============================================================================
# Epic 2.1.3: Write Operations
# =============================================================================


class TestWriteOps:
    def test_add_task_default(self, section):
        entry = section.add_task("order_food")
        assert entry.task_id != ""
        assert entry.action == "order_food"
        assert entry.status == TaskStatus.PENDING
        assert entry.dispatched_at_ms == 0

    def test_add_task_with_id(self, section):
        entry = section.add_task("book_ride", task_id="custom-id")
        assert entry.task_id == "custom-id"

    def test_add_task_dispatched(self, section):
        entry = section.add_task("search", status=TaskStatus.DISPATCHED)
        assert entry.dispatched_at_ms > 0

    def test_add_task_with_depends(self, section):
        entry = section.add_task("checkout", depends_on=["t1", "t2"])
        assert entry.depends_on == ["t1", "t2"]

    def test_add_task_invalid_status(self, section):
        with pytest.raises(ValueError, match="Invalid status"):
            section.add_task("bad", status="nonexistent")

    def test_add_task_max_reached(self, section):
        for i in range(20):
            section.add_task(f"task_{i}")
        with pytest.raises(ValueError, match="Max tasks"):
            section.add_task("overflow")

    def test_update_status_valid(self, section):
        section.add_task("order", task_id="t1")
        updated = section.update_status("t1", TaskStatus.DISPATCHED)
        assert updated.status == TaskStatus.DISPATCHED
        assert updated.dispatched_at_ms > 0

    def test_update_status_to_active(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        updated = section.update_status("t1", TaskStatus.ACTIVE)
        assert updated.status == TaskStatus.ACTIVE

    def test_update_status_to_suspended(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        updated = section.update_status("t1", TaskStatus.SUSPENDED)
        assert updated.pending_hil is True
        assert updated.hil_suspensions_count == 1

    def test_update_status_resume_from_suspended(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t1", TaskStatus.SUSPENDED)
        updated = section.update_status("t1", TaskStatus.ACTIVE)
        assert updated.pending_hil is False
        assert updated.hil_suspensions_count == 1

    def test_update_status_to_completed(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        updated = section.update_status("t1", TaskStatus.COMPLETED)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.completed_at_ms > 0

    def test_update_status_invalid_transition(self, section):
        section.add_task("order", task_id="t1")
        with pytest.raises(ValueError, match="Invalid transition"):
            section.update_status("t1", TaskStatus.COMPLETED)

    def test_update_status_not_found(self, section):
        with pytest.raises(KeyError, match="Task not found"):
            section.update_status("nonexistent", TaskStatus.ACTIVE)

    def test_set_progress(self, section):
        section.add_task("order", task_id="t1")
        section.set_progress("t1", 50)
        assert section.get_by_id("t1").progress_pct == 50

    def test_set_progress_invalid(self, section):
        section.add_task("order", task_id="t1")
        with pytest.raises(ValueError, match="progress_pct must be 0-100"):
            section.set_progress("t1", 150)

    def test_set_progress_not_found(self, section):
        with pytest.raises(KeyError):
            section.set_progress("nonexistent", 50)


# =============================================================================
# Epic 2.1.3: Read Operations
# =============================================================================


class TestReadOps:
    def test_get_active(self, section_with_tasks):
        active = section_with_tasks.get_active()
        assert len(active) == 1  # only t2 is dispatched
        assert active[0].task_id == "t2"

    def test_get_all(self, section_with_tasks):
        assert len(section_with_tasks.get_all()) == 3

    def test_get_by_id(self, section_with_tasks):
        t = section_with_tasks.get_by_id("t1")
        assert t is not None
        assert t.action == "order_food"

    def test_get_by_id_missing(self, section_with_tasks):
        assert section_with_tasks.get_by_id("nonexistent") is None

    def test_count_by_status(self, section_with_tasks):
        counts = section_with_tasks.count_by_status()
        assert counts[TaskStatus.PENDING] == 2
        assert counts[TaskStatus.DISPATCHED] == 1

    def test_get_suspended(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t1", TaskStatus.SUSPENDED)
        susp = section.get_suspended()
        assert len(susp) == 1
        assert susp[0].task_id == "t1"

    def test_has_active_tasks(self, section_with_tasks):
        assert section_with_tasks.has_active_tasks() is True

    def test_has_active_tasks_empty(self, section):
        assert section.has_active_tasks() is False

    def test_task_count(self, section_with_tasks):
        assert section_with_tasks.task_count == 3


# =============================================================================
# Epic 2.1.4: Prompt Generation
# =============================================================================


class TestPrompts:
    def test_to_prompt_empty(self, section):
        prompt = section.to_prompt()
        assert "[TASKS]" in prompt
        assert "No active tasks" in prompt

    def test_to_prompt_with_tasks(self, section_with_tasks):
        prompt = section_with_tasks.to_prompt()
        assert "[TASKS]" in prompt
        assert "order_food" in prompt
        assert "book_ride" in prompt

    def test_to_prompt_with_progress(self, section):
        section.add_task("order", task_id="t1")
        section.set_progress("t1", 60)
        prompt = section.to_prompt()
        assert "60%" in prompt

    def test_to_slim_prompt_empty(self, section):
        assert section.to_slim_prompt() == ""

    def test_to_slim_prompt(self, section_with_tasks):
        slim = section_with_tasks.to_slim_prompt()
        assert slim.startswith("tasks=")
        assert "book_ride:dispatched" in slim


# =============================================================================
# Epic 2.1 + 2.6: Serialization & Pruning
# =============================================================================


class TestSerialization:
    def test_roundtrip(self, section_with_tasks):
        data = section_with_tasks.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

        new_section = TaskStateSection()
        new_section.from_flatbuffer(data)
        assert new_section.task_count == 3
        assert new_section.get_by_id("t1").action == "order_food"
        assert new_section.get_by_id("t2").status == TaskStatus.DISPATCHED

    def test_size_after_serialization(self, section_with_tasks):
        section_with_tasks.to_flatbuffer()
        size = section_with_tasks.get_size_bytes()
        assert size < section_with_tasks.BUDGET_BYTES


class TestPruning:
    def test_mark_presented(self, section):
        section.add_task("order", task_id="t1")
        section.mark_presented("t1", turn_number=5)
        assert section.get_by_id("t1").presented_at_turn == 5

    def test_mark_presented_not_found(self, section):
        with pytest.raises(KeyError):
            section.mark_presented("nonexistent", 5)

    def test_prune_completed_not_yet(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t1", TaskStatus.COMPLETED)
        section.mark_presented("t1", 5)
        pruned = section.prune_completed(current_turn=10)  # only 5 turns
        assert pruned == []
        assert section.task_count == 1

    def test_prune_completed_after_10_turns(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t1", TaskStatus.COMPLETED)
        section.mark_presented("t1", 5)
        pruned = section.prune_completed(current_turn=15)  # exactly 10 turns
        assert pruned == ["t1"]
        assert section.task_count == 0

    def test_prune_unpresented_not_pruned(self, section):
        section.add_task("order", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t1", TaskStatus.COMPLETED)
        # Never presented (presented_at_turn == 0)
        pruned = section.prune_completed(current_turn=100)
        assert pruned == []

    def test_prune_stale_dispatched(self, section):
        now_ms = int(time.time() * 1000)
        section.add_task("order", task_id="t1", status=TaskStatus.DISPATCHED)
        # Backdate dispatched_at_ms
        section.get_by_id("t1").dispatched_at_ms = now_ms - 400_000
        stale = section.prune_stale_dispatched(now_ms=now_ms, stale_threshold_ms=300_000)
        assert stale == ["t1"]
        assert section.get_by_id("t1").status == TaskStatus.FAILED

    def test_prune_stale_skips_active(self, section):
        now_ms = int(time.time() * 1000)
        section.add_task("order", task_id="t1", status=TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.get_by_id("t1").dispatched_at_ms = now_ms - 400_000
        stale = section.prune_stale_dispatched(now_ms=now_ms)
        assert stale == []  # ACTIVE, not DISPATCHED


# =============================================================================
# Full Lifecycle
# =============================================================================


class TestLifecycle:
    def test_full_task_lifecycle(self, section):
        """pending -> dispatched -> active -> completed -> pruned."""
        entry = section.add_task("order_food", task_id="t1")
        assert entry.status == TaskStatus.PENDING

        section.update_status("t1", TaskStatus.DISPATCHED)
        assert section.get_by_id("t1").dispatched_at_ms > 0

        section.update_status("t1", TaskStatus.ACTIVE)
        section.set_progress("t1", 50)
        assert section.has_active_tasks()

        section.update_status("t1", TaskStatus.COMPLETED)
        assert section.get_by_id("t1").completed_at_ms > 0
        assert not section.has_active_tasks()

        section.mark_presented("t1", turn_number=5)
        pruned = section.prune_completed(current_turn=15)
        assert pruned == ["t1"]
        assert section.task_count == 0

    def test_hil_suspension_lifecycle(self, section):
        """pending -> dispatched -> active -> suspended -> active -> completed."""
        section.add_task("book_ride", task_id="t1")
        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t1", TaskStatus.SUSPENDED)
        assert section.get_by_id("t1").pending_hil is True
        assert section.get_by_id("t1").hil_suspensions_count == 1

        section.update_status("t1", TaskStatus.ACTIVE)
        assert section.get_by_id("t1").pending_hil is False

        section.update_status("t1", TaskStatus.COMPLETED)
        assert section.get_by_id("t1").hil_suspensions_count == 1
