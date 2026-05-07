"""
tests.poc.test_m04_e41_ss_binding -- E4.1 FSM/SessionState Binding.

Validates the 2 issues of Epic 4.1:
  4.1.1 -- TaskBridge.rebind() wires real SS task_state + task_artifacts
  4.1.2 -- ConciergeControlExtension.bind_control_section() mirrors FSM
           state into SS control section overlay

Test count target: ~25 tests.
"""

from __future__ import annotations

import pytest

from poc.k1_poc.fsm.control_extension import ConciergeControlExtension
from poc.k1_poc.fsm.states import ConciergeState
from poc.k1_poc.fsm.task_bridge import TaskBridge
from poc.k1_poc.sessionstate.sections.control import ControlSection
from poc.k1_poc.sessionstate.sections.task_artifacts import TaskArtifactsSection
from poc.k1_poc.sessionstate.sections.task_state import TaskStateSection, TaskStatus

# =========================================================================
# 4.1.1 -- TaskBridge.rebind()
# =========================================================================


class TestTaskBridgeRebind:
    """TaskBridge.rebind() replaces local fallback sections with real SS."""

    def test_initial_bridge_uses_local_sections(self) -> None:
        """Before rebind, TaskBridge creates its own local sections."""
        bridge = TaskBridge()
        local_ts = bridge.task_state
        assert isinstance(local_ts, TaskStateSection)
        assert not bridge.is_rebound

    def test_rebind_replaces_task_state(self) -> None:
        """After rebind, task_state points to the provided section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)
        assert bridge.task_state is real_ts
        assert bridge.is_rebound

    def test_rebind_replaces_task_artifacts(self) -> None:
        """After rebind, task_artifacts points to the provided section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)
        assert bridge.task_artifacts is real_ta

    def test_dispatch_after_rebind_visible_in_real_section(self) -> None:
        """Tasks dispatched after rebind are visible in the real section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        bridge.dispatch_task("task-1", "Book flight")
        entry = real_ts.get_by_id("task-1")
        assert entry is not None
        assert entry.action == "Book flight"
        assert entry.status == TaskStatus.DISPATCHED

    def test_complete_after_rebind_visible_in_real_section(self) -> None:
        """Task completion after rebind updates the real section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        bridge.dispatch_task("task-1", "Book flight")
        bridge.complete_task("task-1")
        entry = real_ts.get_by_id("task-1")
        assert entry is not None
        assert entry.status == TaskStatus.COMPLETED

    def test_artifact_after_rebind_visible_in_real_section(self) -> None:
        """Artifacts added after rebind are visible in the real section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        bridge.add_artifact("task-1", content="Confirmation ABC123")
        artifacts = real_ta.get_all()
        assert len(artifacts) == 1
        assert artifacts[0].content == "Confirmation ABC123"

    def test_rebind_copies_preexisting_tasks(self) -> None:
        """Tasks dispatched before rebind are copied to the real section."""
        bridge = TaskBridge()
        bridge.dispatch_task("pre-task", "Pre-rebind task")

        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        entry = real_ts.get_by_id("pre-task")
        assert entry is not None
        assert entry.action == "Pre-rebind task"

    def test_rebind_copies_preexisting_artifacts(self) -> None:
        """Artifacts added before rebind are copied to the real section."""
        bridge = TaskBridge()
        bridge.add_artifact("task-1", content="early artifact")

        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        artifacts = real_ta.get_all()
        assert len(artifacts) == 1
        assert artifacts[0].content == "early artifact"

    def test_rebind_rejects_active_tasks(self) -> None:
        """Cannot rebind while tasks are in ACTIVE state."""
        bridge = TaskBridge()
        bridge.dispatch_task("task-1", "Running")
        bridge.activate_task("task-1")

        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        with pytest.raises(RuntimeError, match="ACTIVE"):
            bridge.rebind(real_ts, real_ta)

    def test_rebind_allows_dispatched_tasks(self) -> None:
        """Rebind is allowed when tasks are only DISPATCHED (not ACTIVE)."""
        bridge = TaskBridge()
        bridge.dispatch_task("task-1", "Pending")

        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)
        assert bridge.is_rebound
        assert real_ts.get_by_id("task-1") is not None

    def test_rebind_preserves_counters(self) -> None:
        """Rebind does not reset dispatch/complete counters."""
        bridge = TaskBridge()
        bridge.dispatch_task("t1", "A")
        assert bridge.total_dispatched == 1

        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)
        assert bridge.total_dispatched == 1

    def test_rebind_no_duplicate_copy(self) -> None:
        """If real section already has the task, rebind does not duplicate."""
        bridge = TaskBridge()
        bridge.dispatch_task("t1", "Already there")

        real_ts = TaskStateSection()
        real_ts.add_task(task_id="t1", action="Already there", status=TaskStatus.DISPATCHED)
        real_ta = TaskArtifactsSection()

        bridge.rebind(real_ts, real_ta)
        # Should still be exactly 1, not 2
        all_tasks = real_ts.get_all()
        matching = [t for t in all_tasks if t.task_id == "t1"]
        assert len(matching) == 1

    def test_suspend_after_rebind_visible(self) -> None:
        """Task suspension after rebind is visible in the real section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        bridge.dispatch_task("t1", "HITL task")
        bridge.suspend_task("t1")
        entry = real_ts.get_by_id("t1")
        assert entry is not None
        assert entry.status == TaskStatus.SUSPENDED

    def test_cancel_after_rebind_visible(self) -> None:
        """Task cancellation after rebind is visible in the real section."""
        bridge = TaskBridge()
        real_ts = TaskStateSection()
        real_ta = TaskArtifactsSection()
        bridge.rebind(real_ts, real_ta)

        bridge.dispatch_task("t1", "Cancel me")
        bridge.cancel_task("t1")
        entry = real_ts.get_by_id("t1")
        assert entry is not None
        assert entry.status == TaskStatus.CANCELLED


# =========================================================================
# 4.1.2 -- ConciergeControlExtension.bind_control_section()
# =========================================================================


class TestControlExtensionBind:
    """ConciergeControlExtension binding mirrors state into ControlSection."""

    def test_initial_extension_is_unbound(self) -> None:
        """Before binding, extension has no section reference."""
        ext = ConciergeControlExtension()
        assert not ext.is_bound

    def test_bind_sets_is_bound(self) -> None:
        """After bind_control_section, is_bound is True."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)
        assert ext.is_bound

    def test_bind_syncs_initial_state(self) -> None:
        """Binding immediately syncs the current local state to section."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)

        meta = section.get_metadata()
        assert meta["fsm_state"] == ConciergeState.LISTENING.name
        assert meta["active_task_ids"] == []
        # P3.1: complexity_tier no longer synced from wrapper; SS keeps default ""

    def test_set_fsm_state_syncs_to_section(self) -> None:
        """set_fsm_state mirrors the new state into the section overlay."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)

        ext.set_fsm_state(ConciergeState.DISPATCHING)
        meta = section.get_metadata()
        assert meta["fsm_state"] == "DISPATCHING"

    def test_add_active_task_syncs_to_section(self) -> None:
        """add_active_task mirrors the task list into the section overlay."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)

        ext.add_active_task("task-1")
        meta = section.get_metadata()
        assert meta["active_task_ids"] == ["task-1"]

    def test_remove_active_task_syncs_to_section(self) -> None:
        """remove_active_task mirrors the updated list into section overlay."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)

        ext.add_active_task("task-1")
        ext.add_active_task("task-2")
        ext.remove_active_task("task-1")
        meta = section.get_metadata()
        assert meta["active_task_ids"] == ["task-2"]

    def test_set_complexity_tier_syncs_to_section(self) -> None:
        """P3.1: set_complexity_tier removed from ConciergeControlExtension."""
        import pytest

        ext = ConciergeControlExtension()
        assert not hasattr(ext, "set_complexity_tier")

    def test_multiple_mutations_all_sync(self) -> None:
        """Multiple mutations accumulate correctly in the section overlay."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)

        ext.set_fsm_state(ConciergeState.COMPANIONING)
        ext.add_active_task("t1")
        ext.add_active_task("t2")

        meta = section.get_metadata()
        assert meta["fsm_state"] == "COMPANIONING"
        assert meta["active_task_ids"] == ["t1", "t2"]

    def test_unbound_mutations_do_not_crash(self) -> None:
        """Mutations before binding silently skip section sync."""
        ext = ConciergeControlExtension()
        ext.set_fsm_state(ConciergeState.DISPATCHING)
        ext.add_active_task("t1")
        # No crash -- local state updated, no section to sync to
        assert ext.fsm_state == "DISPATCHING"

    def test_reset_clears_section_binding(self) -> None:
        """reset() clears the section reference."""
        ext = ConciergeControlExtension()
        section = ControlSection()
        ext.bind_control_section(section)
        ext.reset()
        assert not ext.is_bound

    def test_fsm_overlay_property_on_section(self) -> None:
        """ControlSection.fsm_overlay returns overlay dict."""
        section = ControlSection()
        section.set_fsm_overlay("PROGRESSING", ["t1", "t2"], "MEDIUM")
        overlay = section.fsm_overlay
        assert overlay["fsm_state"] == "PROGRESSING"
        assert overlay["active_task_ids"] == ["t1", "t2"]
        assert overlay["complexity_tier"] == "MEDIUM"

    def test_section_clear_resets_overlay(self) -> None:
        """ControlSection.clear() resets the FSM overlay to empty."""
        section = ControlSection()
        section.set_fsm_overlay("DISPATCHING", ["t1"], "HIGH")
        section.clear()
        overlay = section.fsm_overlay
        assert overlay["fsm_state"] == ""
        assert overlay["active_task_ids"] == []

    def test_apply_set_fsm_overlay_operation(self) -> None:
        """ControlSection.apply('set_fsm_overlay', ...) dispatches correctly."""
        section = ControlSection()
        section.apply(
            "set_fsm_overlay",
            {
                "fsm_state": "LISTENING",
                "active_task_ids": [],
                "complexity_tier": "LOW",
            },
        )
        overlay = section.fsm_overlay
        assert overlay["fsm_state"] == "LISTENING"


# =========================================================================
# E4.1 Integration -- Controller.set_session_state wiring
# =========================================================================


class TestControllerSessionStateBinding:
    """Controller.set_session_state() rebinds TaskBridge + ControlExtension."""

    def _create_fsm_and_ss(self):
        """Create FSM + in-memory SessionState for integration tests."""
        from poc.k1_poc.bus.setup import create_poc_bus, create_poc_router
        from poc.k1_poc.fsm.controller import ConciergeController
        from poc.k1_poc.sessionstate.factory import SessionStateFactory

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        fsm = ConciergeController(bus=bus, router=router)
        ss = SessionStateFactory.create_for_testing()
        ss.start()
        return fsm, ss, bus

    def test_set_session_state_rebinds_task_bridge(self) -> None:
        """After set_session_state, task_bridge uses real SS sections."""
        fsm, ss, _ = self._create_fsm_and_ss()
        fsm.set_session_state(ss)

        assert fsm.task_bridge.is_rebound
        assert fsm.task_bridge.task_state is ss.get_section("task_state")
        assert fsm.task_bridge.task_artifacts is ss.get_section("task_artifacts")

    def test_set_session_state_binds_control_extension(self) -> None:
        """After set_session_state, control_ext is bound to SS control."""
        fsm, ss, _ = self._create_fsm_and_ss()
        fsm.set_session_state(ss)

        assert fsm.control_ext.is_bound
        control = ss.get_section("control")
        meta = control.get_metadata()
        assert meta["fsm_state"] == ConciergeState.LISTENING.name

    def test_dispatch_task_visible_through_ss(self) -> None:
        """After binding, FSM task dispatch is visible through SS reads."""
        fsm, ss, _ = self._create_fsm_and_ss()
        fsm.set_session_state(ss)

        fsm.task_bridge.dispatch_task("t1", "Book hotel")
        ts = ss.get_section("task_state")
        entry = ts.get_by_id("t1")
        assert entry is not None
        assert entry.action == "Book hotel"

    def test_fsm_state_change_visible_through_ss(self) -> None:
        """After binding, FSM state changes are visible through SS reads."""
        fsm, ss, _ = self._create_fsm_and_ss()
        fsm.set_session_state(ss)

        fsm.control_ext.set_fsm_state(ConciergeState.DISPATCHING)
        control = ss.get_section("control")
        meta = control.get_metadata()
        assert meta["fsm_state"] == "DISPATCHING"

    def test_active_task_ids_visible_through_ss(self) -> None:
        """After binding, active task IDs are visible through SS control."""
        fsm, ss, _ = self._create_fsm_and_ss()
        fsm.set_session_state(ss)

        fsm.control_ext.add_active_task("t1")
        control = ss.get_section("control")
        meta = control.get_metadata()
        assert "t1" in meta["active_task_ids"]
