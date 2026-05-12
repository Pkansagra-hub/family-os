"""Tests for ``CalendarEvent`` and ``ExternalFeed`` Pydantic schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k1.tools.family.calendar.schema import CalendarEvent, ExternalFeed


def test_calendar_event_minimal_construction() -> None:
    ev = CalendarEvent(
        id="e1",
        actor="u1",
        title="Soccer",
        start="2026-05-15T10:00:00+00:00",
        end="2026-05-15T11:30:00+00:00",
    )
    assert ev.title == "Soccer"
    assert ev.attendees == []
    assert ev.visibility == "family"
    assert ev.version == 1
    assert ev.is_deleted is False


def test_calendar_event_start_must_be_before_end() -> None:
    with pytest.raises(ValidationError):
        CalendarEvent(
            id="e1",
            actor="u1",
            title="x",
            start="2026-05-15T11:00:00+00:00",
            end="2026-05-15T10:00:00+00:00",
        )


def test_calendar_event_attendees_are_stripped_and_filtered() -> None:
    ev = CalendarEvent(
        id="e2",
        actor="u1",
        title="x",
        start="2026-05-15T10:00:00+00:00",
        end="2026-05-15T11:00:00+00:00",
        attendees=["  alice  ", "", "bob"],
    )
    assert ev.attendees == ["alice", "bob"]


def test_calendar_event_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        CalendarEvent(
            id="e3",
            actor="u1",
            title="x",
            start="2026-05-15T10:00:00+00:00",
            end="2026-05-15T11:00:00+00:00",
            mystery_field="oops",  # type: ignore[call-arg]
        )


def test_calendar_event_is_frozen() -> None:
    ev = CalendarEvent(
        id="e4",
        actor="u1",
        title="x",
        start="2026-05-15T10:00:00+00:00",
        end="2026-05-15T11:00:00+00:00",
    )
    with pytest.raises(ValidationError):
        ev.title = "new"  # type: ignore[misc]


def test_external_feed_defaults() -> None:
    feed = ExternalFeed(
        id="f1",
        actor="u1",
        member_id="u1",
        feed_source="google",
        account="alice@example.com",
    )
    assert feed.enabled is False
    assert feed.sync_token is None
