"""k1.tools.family.reminders.schema -- Reminder entity types.

Two types:

* :class:`ReminderTrigger` -- nested model (NOT a BaseEntity) describing
  *when* or *where* the reminder fires.  Four kinds:

  - ``time``            -- fires at a specific ISO 8601 ``fire_at``
  - ``location_enter``  -- fires when ``recipient`` enters a lat/lon radius
  - ``location_leave``  -- fires when ``recipient`` leaves a lat/lon radius
  - ``event_offset``    -- fires N minutes before/after a calendar event

* :class:`Reminder` -- the actual alert entity.  Key design point:
  ``recipient`` (who receives the alert) is decoupled from ``actor``
  (who created it), enabling cross-person delegation such as
  "remind dad to pick up Riley when he leaves work".

Lifecycle::

    scheduled → fired → dismissed
                fired → snoozed → scheduled (re-arm)
    scheduled → dismissed  (cancelled before firing)

Model validators enforce coherence:
- ``status=snoozed``   → both ``snoozed_until`` and ``fired_at`` required
- ``status=fired|dismissed`` → ``fired_at`` required
- ``status≠snoozed``   → ``snoozed_until`` must be None
- ``kind=time``        → ``fire_at`` required
- ``kind=location_*``  → ``location`` with lat/lon/radius_m required
- ``kind=event_offset``→ ``event_id`` required
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from k1.tools.family.base import BaseEntity

# ---------------------------------------------------------------------------
# ReminderTrigger
# ---------------------------------------------------------------------------

TriggerKind = Literal["time", "location_enter", "location_leave", "event_offset"]


class ReminderTrigger(BaseModel):
    """Describes the condition that causes a Reminder to fire.

    Stored as a JSON blob inside the ``reminders`` table; not a first-class
    SQLite row.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: TriggerKind = Field(
        ...,
        description=(
            "``time`` — fires at ``fire_at``; "
            "``location_enter`` / ``location_leave`` — fires on geofence event; "
            "``event_offset`` — fires N minutes before/after a calendar event."
        ),
    )
    fire_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 datetime.  Required when ``kind='time'``.",
    )
    location: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Geofence spec ``{lat, lon, radius_m, name?}``.  "
            "Required when ``kind`` is ``location_enter`` or ``location_leave``."
        ),
    )
    event_id: Optional[str] = Field(
        default=None,
        description="``calendar_events.id``.  Required when ``kind='event_offset'``.",
    )
    offset_minutes: int = Field(
        default=0,
        description=(
            "Minutes relative to the calendar event. "
            "Negative = before event, positive = after.  "
            "Only meaningful for ``kind='event_offset'``."
        ),
    )

    @model_validator(mode="after")
    def _check_trigger_coherence(self) -> "ReminderTrigger":
        if self.kind == "time":
            if not self.fire_at:
                raise ValueError("trigger.fire_at is required when kind='time'")
        elif self.kind in ("location_enter", "location_leave"):
            if not self.location:
                raise ValueError(
                    "trigger.location ({lat,lon,radius_m}) is required " f"when kind='{self.kind}'"
                )
            for key in ("lat", "lon", "radius_m"):
                if key not in self.location:
                    raise ValueError(f"trigger.location missing required key '{key}'")
        elif self.kind == "event_offset":
            if not self.event_id:
                raise ValueError("trigger.event_id is required when kind='event_offset'")
        return self


# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

ReminderStatus = Literal["scheduled", "fired", "dismissed", "snoozed"]


class Reminder(BaseEntity):
    """A single personal alert that fires once and demands acknowledgment.

    The ``recipient`` field is the family member whose device(s) should
    show the alert.  It may differ from ``actor`` (creator), which is the
    feature that enables "remind dad to pick up Riley".

    Trigger is stored serialized as a JSON string in SQLite and
    deserialized back to :class:`ReminderTrigger` on read.
    """

    title: str = Field(..., min_length=1, description="Short alert text shown on device.")
    recipient: str = Field(..., description="``member_id`` of the person who receives the alert.")
    trigger: ReminderTrigger = Field(..., description="When / where the reminder fires.")
    message: str = Field(
        default="",
        description="Optional longer instruction or context for the recipient.",
    )
    status: ReminderStatus = Field(
        default="scheduled",
        description="Lifecycle state: scheduled → fired → dismissed|snoozed.",
    )
    snoozed_until: Optional[str] = Field(
        default=None,
        description="ISO 8601 re-arm time.  Set only when ``status='snoozed'``.",
    )
    fired_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp when the trigger fired.  Set by ``fire_reminder``.",
    )
    linked_event_id: Optional[str] = Field(
        default=None,
        description=(
            "Cross-tool back-link to ``calendar_events.id``.  "
            "Mirrors ``trigger.event_id`` for ``event_offset`` kind; "
            "convenience field for join-free queries."
        ),
    )

    @model_validator(mode="after")
    def _check_status_coherence(self) -> "Reminder":
        if self.status == "snoozed":
            if not self.snoozed_until:
                raise ValueError("snoozed_until is required when status='snoozed'")
            if not self.fired_at:
                raise ValueError(
                    "fired_at is required when status='snoozed' "
                    "(snooze implies the reminder already fired once)"
                )
        elif self.status in ("fired", "dismissed"):
            if not self.fired_at:
                raise ValueError(f"fired_at is required when status='{self.status}'")
        if self.status != "snoozed" and self.snoozed_until is not None:
            raise ValueError(f"snoozed_until must be None when status='{self.status}'")
        return self
