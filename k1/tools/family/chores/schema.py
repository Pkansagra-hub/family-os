"""k1.tools.family.chores.schema -- Chore entity types.

Two entities:

* :class:`ChoreTemplate` -- a reusable chore definition with a recurrence
  schedule, base point value, and default assignee.  Templates are created
  by parents; individual occurrences (``ChoreOccurrence``) are generated
  by the scheduler or on-demand.

* :class:`ChoreOccurrence` -- a single due instance of a chore.  Has its
  own lifecycle: ``pending → done | skipped``.  Records who completed it
  and timestamps for points calculation.

Design notes
------------
* Chores are **recurring by design** — that is the key distinction from
  Tasks (one-shot) and Reminders (time/location triggered alerts).
* ``points`` on the template sets the default reward; the occurrence may
  override with ``points_awarded`` after completion (parent can adjust).
* ``frequency`` drives the scheduler that stamps ``next_due_at``;
  recurrence math lives in the scheduler module, not here.
* Both models are immutable (``frozen=True``) and ``extra="forbid"`` per
  the M15 convention.  Mutations go through ``model_copy(update=...)`` or
  :meth:`BaseEntity.bump`.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from k1.tools.family.base import BaseEntity

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ChoreFrequency = Literal["daily", "weekly", "monthly", "once"]
ChoreStatus = Literal["pending", "done", "skipped"]


# ---------------------------------------------------------------------------
# ChoreTemplate
# ---------------------------------------------------------------------------


class ChoreTemplate(BaseEntity):
    """A reusable chore pattern owned by the family space.

    Attributes
    ----------
    title:
        Short human-readable name, e.g. "Vacuum living room".
    description:
        Optional longer instructions.
    assigned_to:
        Default assignee ``member_id``; individual occurrences may override.
    frequency:
        Recurrence cadence.  ``once`` creates a single occurrence and
        marks the template complete after it is done.
    base_points:
        Base gamification reward for completing this chore.  Zero means
        no points awarded.
    is_active:
        Soft-disable without deleting; inactive templates don't generate
        new occurrences.
    """

    title: str = Field(..., min_length=1, description="Short name of the chore.")
    description: Optional[str] = Field(default=None, description="Optional extended instructions.")
    assigned_to: Optional[str] = Field(
        default=None,
        description="Default assignee ``member_id``.  ``None`` = unassigned pool.",
    )
    frequency: ChoreFrequency = Field(
        default="weekly",
        description="Recurrence cadence: daily | weekly | monthly | once.",
    )
    base_points: int = Field(
        default=0,
        ge=0,
        description="Default gamification points awarded on completion.",
    )
    is_active: bool = Field(
        default=True,
        description="``False`` pauses new occurrence generation.",
    )


# ---------------------------------------------------------------------------
# ChoreOccurrence
# ---------------------------------------------------------------------------


class ChoreOccurrence(BaseEntity):
    """A single scheduled instance of a :class:`ChoreTemplate`.

    Attributes
    ----------
    template_id:
        FK reference to the parent :class:`ChoreTemplate`.
    title:
        Denormalized copy of the template title so the occurrence is
        self-describing without a JOIN.
    assigned_to:
        Assignee for this specific occurrence — may differ from the
        template default (e.g. "swap week").
    due_at:
        ISO 8601 UTC timestamp when this occurrence is due.
    completed_at:
        Stamped when ``status`` transitions to ``"done"``.
    completed_by:
        ``member_id`` of whoever marked it done (may differ from ``assigned_to``).
    skipped_at:
        Stamped when ``status`` transitions to ``"skipped"``.
    skip_reason:
        Optional human note explaining why it was skipped.
    points_awarded:
        Final points awarded for this specific occurrence; defaults to
        ``template.base_points`` at creation time and may be adjusted
        by a parent.
    status:
        Lifecycle: ``pending`` → ``done`` | ``skipped``.
    """

    template_id: str = Field(..., description="Parent ChoreTemplate.id.")
    title: str = Field(..., min_length=1, description="Denormalized chore title.")
    assigned_to: Optional[str] = Field(
        default=None, description="Assignee member_id for this occurrence."
    )
    due_at: Optional[str] = Field(default=None, description="ISO 8601 UTC due timestamp.")
    completed_at: Optional[str] = Field(default=None)
    completed_by: Optional[str] = Field(
        default=None, description="member_id who completed the chore."
    )
    skipped_at: Optional[str] = Field(default=None)
    skip_reason: Optional[str] = Field(default=None)
    points_awarded: int = Field(
        default=0,
        ge=0,
        description="Points awarded for this instance.",
    )
    status: ChoreStatus = Field(
        default="pending",
        description="pending | done | skipped.",
    )

    @model_validator(mode="after")
    def _check_status_coherence(self) -> "ChoreOccurrence":
        if self.status == "done":
            if not self.completed_at:
                raise ValueError("completed_at is required when status='done'")
        if self.status == "skipped":
            if not self.skipped_at:
                raise ValueError("skipped_at is required when status='skipped'")
        if self.status != "skipped" and self.skipped_at is not None:
            raise ValueError("skipped_at must be None when status is not 'skipped'")
        if self.status != "done" and self.completed_at is not None:
            raise ValueError("completed_at must be None when status is not 'done'")
        return self
