"""Tests for ``ReminderTrigger`` and ``Reminder`` Pydantic schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k1.tools.family.reminders.schema import Reminder, ReminderTrigger

# ---------------------------------------------------------------------------
# ReminderTrigger validators
# ---------------------------------------------------------------------------


def test_trigger_time_requires_fire_at() -> None:
    with pytest.raises(ValidationError, match="fire_at"):
        ReminderTrigger(kind="time")


def test_trigger_time_valid() -> None:
    t = ReminderTrigger(kind="time", fire_at="2026-05-12T20:00:00Z")
    assert t.fire_at == "2026-05-12T20:00:00Z"


def test_trigger_location_enter_requires_location() -> None:
    with pytest.raises(ValidationError, match="location"):
        ReminderTrigger(kind="location_enter")


def test_trigger_location_requires_lat_lon_radius() -> None:
    with pytest.raises(ValidationError, match="lat"):
        ReminderTrigger(kind="location_leave", location={"lat": 37.0})


def test_trigger_location_valid() -> None:
    t = ReminderTrigger(
        kind="location_leave",
        location={"lat": 37.77, "lon": -122.41, "radius_m": 200, "name": "work"},
    )
    assert t.kind == "location_leave"


def test_trigger_event_offset_requires_event_id() -> None:
    with pytest.raises(ValidationError, match="event_id"):
        ReminderTrigger(kind="event_offset")


def test_trigger_event_offset_valid() -> None:
    t = ReminderTrigger(kind="event_offset", event_id="ev1", offset_minutes=-30)
    assert t.offset_minutes == -30


def test_trigger_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z", oops="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Reminder entity validators
# ---------------------------------------------------------------------------


def test_reminder_minimal_construction() -> None:
    r = Reminder(
        id="r1",
        actor="u1",
        title="Pick up milk",
        recipient="u2",
        trigger=ReminderTrigger(kind="time", fire_at="2026-05-12T20:00:00Z"),
    )
    assert r.status == "scheduled"
    assert r.snoozed_until is None
    assert r.fired_at is None


def test_reminder_snoozed_requires_snoozed_until() -> None:
    with pytest.raises(ValidationError, match="snoozed_until"):
        Reminder(
            id="r1",
            actor="u1",
            title="X",
            recipient="u2",
            trigger=ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z"),
            status="snoozed",
            fired_at="2026-01-01T00:00:00Z",
            # snoozed_until missing
        )


def test_reminder_snoozed_requires_fired_at() -> None:
    with pytest.raises(ValidationError, match="fired_at"):
        Reminder(
            id="r1",
            actor="u1",
            title="X",
            recipient="u2",
            trigger=ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z"),
            status="snoozed",
            snoozed_until="2026-01-01T00:10:00Z",
            # fired_at missing
        )


def test_reminder_fired_requires_fired_at() -> None:
    with pytest.raises(ValidationError, match="fired_at"):
        Reminder(
            id="r1",
            actor="u1",
            title="X",
            recipient="u2",
            trigger=ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z"),
            status="fired",
        )


def test_reminder_snoozed_until_must_be_none_when_not_snoozed() -> None:
    with pytest.raises(ValidationError, match="snoozed_until must be None"):
        Reminder(
            id="r1",
            actor="u1",
            title="X",
            recipient="u2",
            trigger=ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z"),
            status="scheduled",
            snoozed_until="2026-01-02T00:00:00Z",
        )


def test_reminder_is_frozen() -> None:
    r = Reminder(
        id="r1",
        actor="u1",
        title="X",
        recipient="u2",
        trigger=ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z"),
    )
    with pytest.raises(ValidationError):
        r.title = "changed"  # type: ignore[misc]


def test_reminder_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Reminder(
            id="r1",
            actor="u1",
            title="X",
            recipient="u2",
            trigger=ReminderTrigger(kind="time", fire_at="2026-01-01T00:00:00Z"),
            oops="extra",  # type: ignore[call-arg]
        )
