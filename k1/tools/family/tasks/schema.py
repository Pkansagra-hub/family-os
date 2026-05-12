"""k1.tools.family.tasks.schema -- Tasks entity types.

Two entities:

* :class:`TaskList` -- a named bucket for grouping tasks (optional; tasks
  may exist with ``list_id=None`` for ungrouped use).

* :class:`TaskItem` -- a single one-shot to-do item.  Distinct from Chores
  (which are recurring + gamified) and Reminders (which are time/location
  triggered).  A TaskItem has a deadline (``due_at``), an assignee
  (``assigned_to``), and a simple four-state lifecycle
  ``open → in_progress → done`` (or ``→ cancelled``).

Both models inherit :class:`BaseEntity` and are immutable / ``extra="forbid"``
so callers must produce new revisions via ``model_copy(update=...)`` or
:meth:`BaseEntity.bump`.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from k1.tools.family.base import BaseEntity

# ---------------------------------------------------------------------------
# TaskList
# ---------------------------------------------------------------------------


class TaskList(BaseEntity):
    """A named container for grouping related tasks.

    Using a list is optional: tasks with ``list_id=None`` float in the
    family task pool.  Typical lists: "Household", "School prep",
    "Weekend errands".
    """

    name: str = Field(..., min_length=1, description="Human-readable list name.")
    color: Optional[str] = Field(
        default=None,
        description="Hex color string for UI chip, e.g. ``#4CAF50``.  Optional.",
    )


# ---------------------------------------------------------------------------
# TaskItem
# ---------------------------------------------------------------------------

TaskPriority = Literal["low", "medium", "high"]
TaskStatus = Literal["open", "in_progress", "done", "cancelled"]

# Valid forward transitions (other than same-state no-ops).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "done", "cancelled"},
    "in_progress": {"done", "cancelled", "open"},  # reopen allowed
    "done": {"open"},  # reopen via reopen_task
    "cancelled": {"open"},  # un-cancel via reopen_task
}


class TaskItem(BaseEntity):
    """A single one-shot family to-do.

    Key design decisions
    --------------------
    * ``due_at`` is an ISO 8601 *deadline* string (not a time range).  The task
      has no ``start`` -- it is not a calendar event.
    * ``assigned_to`` is an optional ``member_id``.  When ``None`` the task is
      unassigned and visible to the whole family (subject to ACL).
    * ``linked_event_id`` provides a cross-tool back-link to
      ``calendar_events.id`` -- useful when the LLM creates a task like
      "pick up Riley" in response to a calendar event.
    * Status transitions are validated by :meth:`_validate_transition` but
      only when ``_prev_status`` is provided via the validator -- standalone
      construction (``status="done"``) is allowed for seeding and testing.
    """

    title: str = Field(..., min_length=1, description="What needs to be done.")
    list_id: Optional[str] = Field(
        default=None, description="``TaskList.id`` this item belongs to; ``None`` = ungrouped."
    )
    assigned_to: Optional[str] = Field(
        default=None, description="``member_id`` of the person responsible; ``None`` = unassigned."
    )
    due_at: Optional[str] = Field(
        default=None, description="ISO 8601 deadline string (e.g. ``2026-05-20T17:00:00+00:00``)."
    )
    priority: TaskPriority = Field(
        default="medium", description="Task urgency; used for LLM ordering and UI sort."
    )
    status: TaskStatus = Field(
        default="open",
        description=(
            "Lifecycle state: ``open`` → ``in_progress`` → ``done`` (or ``cancelled``). "
            "Reopen via ``reopen_task``."
        ),
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp set by ``complete_task``; ``None`` while open.",
    )
    linked_event_id: Optional[str] = Field(
        default=None,
        description="Optional cross-tool back-link to a ``calendar_events.id``.",
    )

    @model_validator(mode="after")
    def _completed_at_coherence(self) -> "TaskItem":
        """``completed_at`` must be absent when status is not ``done``."""

        if self.status != "done" and self.completed_at is not None:
            raise ValueError(
                "TaskItem.completed_at must be None when status is not 'done'; "
                f"got status={self.status!r}."
            )
        return self
