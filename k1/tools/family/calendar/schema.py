"""k1.tools.family.calendar.schema -- Calendar entity types.

The two entities the Calendar adapter persists:

* :class:`CalendarEvent` -- one event on the family calendar.  Inherits the
  universal ``BaseEntity`` ACL/audit columns and adds the
  calendar-specific business fields (``title``, ``start``, ``end`` ...).

* :class:`ExternalFeed` -- a bound external calendar account (Google,
  Outlook, Classroom, ...) used to import events.  In M15 every feed is
  persisted with ``enabled=False``; the actual sync workers are M17.

Both models are immutable (``frozen=True``) and forbid unknown fields,
so callers must produce a new revision via ``model_copy(update=...)``
or :meth:`BaseEntity.bump` -- matching the foundation-wide invariant.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from k1.tools.family.base import BaseEntity

# ---------------------------------------------------------------------------
# CalendarEvent
# ---------------------------------------------------------------------------


# Plan §E15.1 keeps ``start``/``end`` as ISO 8601 strings rather than
# native ``datetime`` objects: SQLite text columns are easier to index
# and lexicographic ordering on ISO strings matches chronological order.
_ISO_DATETIME_DESC = (
    "ISO 8601 datetime string (e.g. ``2026-05-15T10:00:00+00:00``). "
    "Stored verbatim in SQLite so callers must supply a string the "
    "Python ``datetime`` parser can re-hydrate."
)

InviteResponse = Literal["yes", "no", "maybe", "tentative"]


class CalendarEvent(BaseEntity):
    """One event on the family calendar.

    Required fields are ``title``, ``start`` and ``end``; everything
    else has sensible defaults so creators only need to supply the bare
    minimum to schedule an event.  The :pyfunc:`pydantic.model_validator`
    enforces ``start < end`` so callers cannot persist degenerate
    zero/negative-duration events.
    """

    title: str = Field(..., min_length=1, description="Short event name.")
    start: str = Field(..., min_length=1, description=_ISO_DATETIME_DESC)
    end: str = Field(..., min_length=1, description=_ISO_DATETIME_DESC)
    location: str = Field(default="", description="Free-form location string.")
    notes: str = Field(default="", description="Free-form notes / description.")
    attendees: list[str] = Field(
        default_factory=list,
        description="Family ``member_id`` values of attendees.",
    )
    rrule: Optional[str] = Field(
        default=None,
        description="Optional iCal RRULE for recurring events; raw string only in M15.",
    )
    response: Optional[InviteResponse] = Field(
        default=None,
        description="Caller's RSVP, set via the ``respond_to_invite`` action.",
    )

    @field_validator("attendees")
    @classmethod
    def _strip_attendees(cls, v: list[str]) -> list[str]:
        # Plan §E15.1 attendees are member_id strings.  We accept any
        # non-empty strings and normalise (strip).  Invalid ids are the
        # caller's responsibility -- the family profile is the source
        # of truth for membership.
        cleaned: list[str] = []
        for mid in v:
            s = (mid or "").strip()
            if s:
                cleaned.append(s)
        return cleaned

    @model_validator(mode="after")
    def _validate_window(self) -> "CalendarEvent":
        if self.end <= self.start:
            raise ValueError(f"CalendarEvent.end ({self.end!r}) must be > start ({self.start!r}).")
        return self


# ---------------------------------------------------------------------------
# ExternalFeed
# ---------------------------------------------------------------------------


FeedSource = Literal["google", "outlook", "teams", "classroom", "apple"]


class ExternalFeed(BaseEntity):
    """A bound external calendar account.

    In M15 we persist the binding so the family-settings UI can list
    and revoke feeds, but the worker that polls the external service is
    explicitly out-of-scope (M17 -- IFL adapters).  ``enabled`` therefore
    stays ``False`` for every feed connected in M15.
    """

    member_id: str = Field(..., min_length=1, description="Owning family ``member_id``.")
    feed_source: FeedSource = Field(..., description="External calendar provider.")
    account: str = Field(
        ..., min_length=1, description="External account identifier (e.g. e-mail address)."
    )
    sync_token: Optional[str] = Field(
        default=None, description="Opaque cursor handed back to the IFL worker (M17)."
    )
    enabled: bool = Field(
        default=False,
        description="M15 always persists ``False``; real sync is enabled in M17.",
    )
