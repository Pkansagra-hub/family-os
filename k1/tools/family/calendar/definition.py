"""k1.tools.family.calendar.definition -- declarative spec for the Calendar adapter.

This module exposes a single immutable value, :data:`CALENDAR_DEFINITION`,
which is the source of truth for every consumer of the Calendar surface:

* :func:`k1.fabric.manifest_translator.register_definition` turns each
  :class:`ActionSpec` into a Fabric ``CapabilityContract`` so LLM
  planners and orchestration workflows can discover the actions.
* :func:`k1.tools.family.manifest.ui_manifest` derives a role-filtered
  UI manifest for the web shell.
* :func:`k1.tools.family.manifest.llm_tool_specs` derives both the
  ``calendar.<action>`` and the ``tool.<kind>.calendar.<action>``
  capability names the Concierge LLM uses to invoke actions.
* :class:`CalendarToolService` consumes ``DEFINITION.tables_sql`` to
  bring up its SQLite projection tables at construction time.

The action list intentionally mirrors the M15 whiteboard / plan §E15.1
matrix (10 actions, 3 of which are parent-only).
"""

from __future__ import annotations

import os

from k1.tools.family.definition import (
    ActionSpec,
    FieldSpec,
    LLMHints,
    SSESpec,
    ToolDefinition,
)

# ---------------------------------------------------------------------------
# DDL -- read once at import time so the file is the canonical source.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "tables.sql"), encoding="utf-8") as _f:
    _CALENDAR_DDL: str = _f.read()


# ---------------------------------------------------------------------------
# Reused FieldSpec helpers
# ---------------------------------------------------------------------------

# ``visibility`` is constrained to the four canonical bands.  We surface
# the allowed values to the LLM via the description so the planner can
# pick a sensible default without consulting the policy module.
_VISIBILITY_FIELD = FieldSpec(
    name="visibility",
    type="string",
    required=False,
    description=(
        "Row-level visibility band: one of ``family`` | ``adults`` | "
        "``named`` | ``private``.  Defaults to ``family`` unless the "
        "visibility policy promotes it (e.g. work-source events become "
        "``adults``)."
    ),
)
_VISIBLE_TO_FIELD = FieldSpec(
    name="visible_to",
    type="array",
    required=False,
    description=(
        "Allow-list of ``member_id`` strings consulted when "
        "``visibility`` is ``named``.  Ignored otherwise."
    ),
)
_METADATA_FIELD = FieldSpec(
    name="metadata",
    type="object",
    required=False,
    description=(
        "Opaque structured metadata for coordination. Use ``_semantic`` for "
        "domain-agnostic prep notes, authority boundaries, future-weave hints, "
        "or provenance; keep user-visible notes in ``notes``."
    ),
)


# ---------------------------------------------------------------------------
# CALENDAR_DEFINITION
# ---------------------------------------------------------------------------

CALENDAR_DEFINITION = ToolDefinition(
    adapter_id="calendar",
    version="1.0.0",
    category="coordination",
    summary=(
        "Family-shared calendar with per-event visibility, optional "
        "external feed imports, and cross-family live sync."
    ),
    title="Family Calendar",
    icon="calendar",
    description=(
        "FamilyOS native calendar.  Stores events authored locally and "
        "(later) imported from Google/Outlook/Classroom feeds.  Every "
        "write produces a WAL envelope plus an SSE fan-out so all "
        "household devices stay in sync within seconds."
    ),
    entity_type="calendar_event",
    views=["month", "week", "day", "list"],
    activity_profile="calendar.v1",
    filters=[
        FieldSpec(
            name="member",
            type="array",
            required=False,
            description="Filter events whose attendees include any of these member_ids.",
        ),
        FieldSpec(
            name="source",
            type="array",
            required=False,
            description="Filter by provenance: native | google | outlook | classroom | apple.",
        ),
        FieldSpec(
            name="visibility",
            type="array",
            required=False,
            description="Filter by visibility band: family | adults | named | private.",
        ),
    ],
    can_reference=["task", "reminder", "shopping_item"],
    feature_flags=["m15_calendar"],
    domain_tags=["scheduling", "availability", "external_calendar"],
    tables_sql=_CALENDAR_DDL,
    actions=[
        # ------------------------------------------------------------------
        # 1. create_event
        # ------------------------------------------------------------------
        ActionSpec(
            name="create_event",
            kind="write",
            summary="Create a new calendar event.",
            label="New event",
            primary=True,
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            idempotent=True,
            params=[
                FieldSpec(
                    name="title", type="string", required=True, description="Short event name."
                ),
                FieldSpec(
                    name="start",
                    type="datetime",
                    required=True,
                    description="Event start (ISO 8601).",
                ),
                FieldSpec(
                    name="end",
                    type="datetime",
                    required=True,
                    description="Event end (ISO 8601, strictly > start).",
                ),
                FieldSpec(
                    name="attendees",
                    type="array",
                    required=False,
                    description="List of attending member_ids.",
                ),
                FieldSpec(name="location", type="string", required=False),
                FieldSpec(name="notes", type="string", required=False),
                _METADATA_FIELD,
                FieldSpec(
                    name="rrule",
                    type="string",
                    required=False,
                    description="Optional iCal RRULE; recurrence expansion is M17.",
                ),
                _VISIBILITY_FIELD,
                _VISIBLE_TO_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants to schedule an appointment, meeting, or activity",
                    "user mentions a fixed-time event with start and end on a date",
                ],
                avoid_when=[
                    "user wants a recurring family chore -> use chores.create_chore",
                    "user wants a one-off to-do without fixed time -> use tasks.create_task",
                    "user wants a time/location alert -> use reminders.create_reminder",
                ],
                examples=[
                    "Add Riley's soccer game Saturday 10am to 11:30am",
                    "Schedule a dentist appointment for Jordan next Tuesday 2pm",
                ],
            ),
            sse=SSESpec(emits=["family.calendar.create_event.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 2. update_event
        # ------------------------------------------------------------------
        ActionSpec(
            name="update_event",
            kind="write",
            summary="Patch fields of an existing calendar event.",
            label="Update event",
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(
                    name="expected_version",
                    type="integer",
                    required=False,
                    description="Optimistic-concurrency token; reject on mismatch.",
                ),
                FieldSpec(name="title", type="string", required=False),
                FieldSpec(name="start", type="datetime", required=False),
                FieldSpec(name="end", type="datetime", required=False),
                FieldSpec(name="attendees", type="array", required=False),
                FieldSpec(name="location", type="string", required=False),
                FieldSpec(name="notes", type="string", required=False),
                _METADATA_FIELD,
                FieldSpec(name="rrule", type="string", required=False),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to reschedule or edit an existing event"],
                examples=[
                    "Move Riley's soccer game to Sunday 11am → get_event(event_id) first, then update_event(event_id, start, end)",
                    "Add Jordan to the dentist appointment → update_event(event_id, attendees=[...existing..., jordan_id])",
                ],
            ),
            sse=SSESpec(emits=["family.calendar.update_event.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 3. delete_event
        # ------------------------------------------------------------------
        ActionSpec(
            name="delete_event",
            kind="delete",
            summary="Soft-delete a calendar event.",
            label="Delete event",
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                FieldSpec(name="event_id", type="string", required=True),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="event_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to cancel or remove an event"],
                examples=[
                    "Cancel Riley's dentist appointment → get_event(event_id) to confirm, then delete_event(event_id)",
                    "Remove the school trip event → list_events(start, end) to find id, then delete_event(event_id)",
                ],
            ),
            sse=SSESpec(emits=["family.calendar.delete_event.delete.v1"]),
        ),
        # ------------------------------------------------------------------
        # 4. list_events
        # ------------------------------------------------------------------
        ActionSpec(
            name="list_events",
            kind="read",
            summary="Return events in a time window, ACL-filtered for the caller.",
            label="List events",
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[
                FieldSpec(
                    name="start",
                    type="datetime",
                    required=False,
                    description="Window start (inclusive).",
                ),
                FieldSpec(
                    name="end",
                    type="datetime",
                    required=False,
                    description="Window end (inclusive).",
                ),
                FieldSpec(
                    name="member_filter",
                    type="array",
                    required=False,
                    description="Only include events whose attendees overlap this list.",
                ),
                FieldSpec(
                    name="source_filter",
                    type="array",
                    required=False,
                    description="Only include events whose ``source`` is in this list.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="events", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user asks what's on the calendar for a day or week",
                    "planner needs to read existing events before scheduling",
                ],
                examples=[
                    "What's on the calendar this weekend? → list_events(start=Friday, end=Sunday)",
                    "Do we have anything Tuesday afternoon? → list_events(start=Tuesday 12:00, end=Tuesday 23:59)",
                    "Check for duplicate events before creating → list_events(start=proposed_start-1d, end=proposed_start+1d)",
                ],
            ),
        ),
        # ------------------------------------------------------------------
        # 5. get_event
        # ------------------------------------------------------------------
        ActionSpec(
            name="get_event",
            kind="read",
            summary="Fetch a single event by id (ACL-filtered).",
            label="Get event",
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[FieldSpec(name="event_id", type="string", required=True)],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="event", type="object", required=True),
            ],
            llm=LLMHints(
                use_when=["user asks about the details of a specific event"],
                examples=[
                    "Get the dentist appointment details → get_event(event_id)",
                    "Read current state before updating → get_event(event_id) to retrieve version and fields",
                ],
            ),
        ),
        # ------------------------------------------------------------------
        # 6. respond_to_invite
        # ------------------------------------------------------------------
        ActionSpec(
            name="respond_to_invite",
            kind="write",
            summary="Record the caller's RSVP for an event they attend.",
            label="Respond to invite",
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(
                    name="response",
                    type="string",
                    required=True,
                    description="One of: yes | no | maybe | tentative.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(name="response", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to RSVP yes/no/maybe to an event"],
                examples=[
                    "Accept the school play invite → get_event(event_id) first, then respond_to_invite(event_id, response='yes')",
                    "Decline the work party → respond_to_invite(event_id, response='no')",
                ],
            ),
            sse=SSESpec(emits=["family.calendar.respond_to_invite.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 7. set_visibility (parent-only)
        # ------------------------------------------------------------------
        ActionSpec(
            name="set_visibility",
            kind="write",
            summary="Change the visibility band of an existing event.",
            label="Change visibility",
            context=["entity_detail_gear"],
            min_band="GREEN",
            min_role="parent",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "guardian", "system"],
            params=[
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(
                    name="visibility",
                    type="string",
                    required=True,
                    description="One of: family | adults | named | private.",
                ),
                FieldSpec(
                    name="visible_to",
                    type="array",
                    required=False,
                    description="Allow-list of member_ids when visibility=named.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="event_id", type="string", required=True),
                FieldSpec(name="visibility", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["a parent wants to restrict who can see an event"],
                avoid_when=["caller is a child -- the role gate will reject"],
                examples=[
                    "Make the surprise party private → set_visibility(event_id, visibility='private')",
                    "Share the work trip only with adults → set_visibility(event_id, visibility='adults')",
                ],
            ),
            sse=SSESpec(emits=["family.calendar.set_visibility.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 8. connect_feed (parent-only)
        # ------------------------------------------------------------------
        ActionSpec(
            name="connect_feed",
            kind="write",
            summary="Bind an external calendar account (Google/Outlook/...).",
            label="Connect external calendar",
            min_band="GREEN",
            min_role="parent",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "guardian", "system"],
            idempotent=True,
            params=[
                FieldSpec(
                    name="feed_source",
                    type="string",
                    required=True,
                    description="One of: google | outlook | teams | classroom | apple.",
                ),
                FieldSpec(
                    name="account",
                    type="string",
                    required=True,
                    description="External account identifier (usually an e-mail).",
                ),
                FieldSpec(
                    name="member_id",
                    type="string",
                    required=False,
                    description="Family member who owns the account (defaults to caller).",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="feed_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["a parent wants to import events from Google/Outlook/Classroom"],
                examples=["Connect my Google work calendar"],
            ),
            sse=SSESpec(emits=["family.calendar.connect_feed.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 9. disconnect_feed (parent-only)
        # ------------------------------------------------------------------
        ActionSpec(
            name="disconnect_feed",
            kind="write",
            summary="Remove a previously connected external feed binding.",
            label="Disconnect feed",
            min_band="GREEN",
            min_role="parent",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "guardian", "system"],
            params=[FieldSpec(name="feed_id", type="string", required=True)],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="feed_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["a parent wants to remove a connected feed"],
                examples=[
                    "Remove the Outlook feed → list_feeds() first, then disconnect_feed(feed_id)",
                ],
            ),
            sse=SSESpec(emits=["family.calendar.disconnect_feed.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 10. list_feeds
        # ------------------------------------------------------------------
        ActionSpec(
            name="list_feeds",
            kind="read",
            summary="List currently-bound external feeds (ACL-filtered).",
            label="List feeds",
            min_band="GREEN",
            prompt_template="calendar_activity_v1",
            allowed_roles=["parent", "guardian", "elder", "system"],
            params=[
                FieldSpec(
                    name="member_id",
                    type="string",
                    required=False,
                    description="Optional filter: feeds owned by this member.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="feeds", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to see which external calendars are connected"],
                examples=[
                    "Which calendars are synced? → list_feeds()",
                    "Check existing feeds before connecting a new one → list_feeds()",
                ],
            ),
        ),
    ],
)
