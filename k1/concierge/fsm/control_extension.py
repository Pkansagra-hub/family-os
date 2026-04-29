"""
k1.concierge.fsm.control_extension -- ConciergeControlExtension.

V2 Design Ref: Section 5 (control HOT section), Section 25.2 (FSM state fields)

Wraps the existing ControlSection with Concierge FSM fields:
  - fsm_state:       Current ConciergeState (written on every transition)
  - active_task_ids:  List of currently active task IDs
  # P3.4a: complexity_tier removed; tier derivation moved to dispatch_task.

The wrapper does NOT modify ControlSection. It uses the FlowState
sub-fields for task tracking and adds fsm_state
as a lightweight in-memory field that is serialized alongside.

Why a wrapper instead of modifying ControlSection directly:
  1. ControlSection is shared across K1 modules (not just Concierge POC).
  2. FlatBuffer schema changes require regeneration (slow, risky for POC).
  3. The POC extension is 3 fields -- not worth schema churn.
  4. Production would add these to the FlatBuffer schema properly.
"""

from __future__ import annotations

import logging
from typing import Any

from k1.concierge.fsm.states import ConciergeState

logger = logging.getLogger(__name__)


class ConciergeControlExtension:
    """POC extension to ControlSection for Concierge FSM state.

    Tracks the 3 FSM-specific fields that the existing ControlSection
    does not have. These are the fields that Front LLM reads to
    understand current system status.

    Thread safety: Single-writer (FSM). No concurrent writes.

    Usage in ConciergeController:
        self._control_ext = ConciergeControlExtension()
        # On every _transition():
        self._control_ext.set_fsm_state(to_state)
        # On task.dispatch:
        self._control_ext.add_active_task(task_id)
        # On task.complete/failed:
        self._control_ext.remove_active_task(task_id)
        # P3.4a: Phase 1 no longer sets complexity_tier; tier derivation
        # moved to dispatch_task.
    """

    def __init__(self) -> None:
        self._fsm_state: str = ConciergeState.LISTENING.name
        self._active_task_ids: list[str] = []
        self._update_count: int = 0
        self._control_section: Any | None = None  # M4 E4.1.2: bound SS ControlSection
        logger.info(
            "ConciergeControlExtension initialized (initial_state=%s)",
            self._fsm_state,
        )

    # ------------------------------------------------------------------
    # SS Binding (M4 E4.1.2)
    # ------------------------------------------------------------------

    def bind_control_section(self, section: Any) -> None:
        """Bind to a real SS ControlSection so mutators mirror state.

        Called by ``ConciergeController.set_session_state()`` after the
        SessionStateManager is attached.  Once bound, every call to
        ``set_fsm_state``, ``add_active_task``, and ``remove_active_task``
        syncs the overlay into the section.

        Args:
            section: A ControlSection instance from the SessionState manager.
        """
        self._control_section = section
        self._sync_to_section()
        logger.info("ConciergeControlExtension bound to ControlSection")

    @property
    def is_bound(self) -> bool:
        """Whether bind_control_section() has been called."""
        return self._control_section is not None

    def _sync_to_section(self) -> None:
        """Push current local state into the bound ControlSection overlay."""
        if self._control_section is not None:
            self._control_section.set_fsm_overlay(
                fsm_state=self._fsm_state,
                active_task_ids=list(self._active_task_ids),
            )

    # ------------------------------------------------------------------
    # FSM State
    # ------------------------------------------------------------------

    @property
    def fsm_state(self) -> str:
        """Current FSM state name."""
        return self._fsm_state

    def set_fsm_state(self, state: ConciergeState) -> None:
        """Update FSM state. Called on every _transition().

        Args:
            state: The new ConciergeState.
        """
        self._fsm_state = state.name
        self._update_count += 1
        self._sync_to_section()
        logger.debug("ControlExtension: fsm_state -> %s", state.name)

    # ------------------------------------------------------------------
    # Active Task IDs
    # ------------------------------------------------------------------

    @property
    def active_task_ids(self) -> list[str]:
        """List of currently active task IDs."""
        return list(self._active_task_ids)

    @property
    def active_task_count(self) -> int:
        """Number of currently active tasks."""
        return len(self._active_task_ids)

    def add_active_task(self, task_id: str) -> None:
        """Register a newly dispatched task.

        Called by FSM on task.dispatch.v1.

        Args:
            task_id: The dispatched task ID.
        """
        if task_id not in self._active_task_ids:
            self._active_task_ids.append(task_id)
            self._update_count += 1
            self._sync_to_section()
            logger.debug(
                "ControlExtension: task added %s (active=%d)",
                task_id,
                len(self._active_task_ids),
            )

    def remove_active_task(self, task_id: str) -> None:
        """Remove a completed/failed/cancelled task.

        Called by FSM on task.complete/failed/cancelled.
        Safe to call with unknown task_id (no-op).

        Args:
            task_id: The task ID to remove.
        """
        if task_id in self._active_task_ids:
            self._active_task_ids.remove(task_id)
            self._update_count += 1
            self._sync_to_section()
            logger.debug(
                "ControlExtension: task removed %s (active=%d)",
                task_id,
                len(self._active_task_ids),
            )

    def has_active_task(self, task_id: str) -> bool:
        """Check if a task ID is currently active."""
        return task_id in self._active_task_ids

    # ------------------------------------------------------------------
    # Complexity Tier -- removed in P3.4a (mirror of POC P3.1).
    # Tier derivation moved to dispatch_task (`plan: bool` + multi-intent
    # + depends_on signals).
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Snapshot / observability
    # ------------------------------------------------------------------

    @property
    def update_count(self) -> int:
        """Total number of updates (for testing)."""
        return self._update_count

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot dict of the extension state.

        Used by observability (state.updated events) and testing.
        """
        return {
            "fsm_state": self._fsm_state,
            "active_task_ids": list(self._active_task_ids),
        }

    def reset(self) -> None:
        """Reset all extension state. Called on teardown."""
        self._fsm_state = ConciergeState.LISTENING.name
        self._active_task_ids.clear()
        self._update_count = 0
        self._control_section = None
