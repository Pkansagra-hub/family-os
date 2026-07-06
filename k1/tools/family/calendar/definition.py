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
from typing import Any

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
# Phase 1.1 -- Constitution / Policy / Guide cards / Ontology (Epic 9.3-9.6)
#
# These dicts are projected into GlobalProjectionStore by
# ``register_definition_to_store`` so the situated resolver can enforce
# prerequisite reads, conflict analysis, HIL gates, role/safety policy,
# and typed (graph) resolution for the Calendar connector.
# ---------------------------------------------------------------------------

_CALENDAR_CONSTITUTION: dict[str, Any] = {
    "connector_id": "family.calendar",
    "constitution_id": "family.calendar.v1",
    "schema_version": "1.0.0",
    "execution_phases": ["read", "mutate"],
    "prerequisite_reads": [
        {
            "operation": "list",
            "resource_kind": "event",
            "reason": (
                "Check for time-window conflicts with existing events "
                "before creating or updating."
            ),
            "required": True,
            "timeout_ms": 5000,
        },
        {
            "operation": "list",
            "resource_kind": "chore",
            "reason": "Assigned chores in the same time window may conflict -- warn the user.",
            "required": False,
            "timeout_ms": 3000,
        },
        {
            "operation": "list",
            "resource_kind": "task",
            "reason": "Due tasks in the same time window may conflict -- warn the user.",
            "required": False,
            "timeout_ms": 3000,
        },
    ],
    "conflict_analysis_rules": [
        {
            "check": "time_overlap",
            "with_resource_kinds": ["event"],
            "description": "Two events at overlapping times for the same attendees.",
            "resolution": (
                "Present the conflict to the user with these options: create "
                "anyway, pick a different time, or cancel. Do NOT silently "
                "overwrite."
            ),
        },
        {
            "check": "time_overlap",
            "with_resource_kinds": ["chore"],
            "description": "An assigned chore is due during this event's time window.",
            "resolution": (
                "Warn: '{child} has chore {chore_title} due at {due_time}'. "
                "Offer: create event anyway, reschedule the chore, or cancel "
                "this event."
            ),
        },
        {
            "check": "time_overlap",
            "with_resource_kinds": ["task"],
            "description": "A task is due during this event's time window.",
            "resolution": (
                "Warn: '{assignee} has task {task_title} due'. Offer: create "
                "event anyway or cancel."
            ),
        },
        {
            "check": "participant_availability",
            "description": "All attendees must be free in the target time window.",
            "resolution": (
                "If any participant has a conflicting event, list the conflict "
                "and ask whether to proceed."
            ),
        },
    ],
    "companion_resource_roles": [
        {
            "resource_kind": "chore",
            "role": "conflict_source",
            "description": (
                "Calendar events may conflict with assigned chores in the same "
                "time window. When the user says 'assign kitchen cleanup to "
                "Riley weekly', that is a CHORE, not a calendar event -- use "
                "family.chores."
            ),
        },
        {
            "resource_kind": "task",
            "role": "conflict_source",
            "description": "Calendar events may conflict with due tasks.",
        },
        {
            "resource_kind": "reminder",
            "role": "dependency",
            "description": "Events can trigger reminders via event_offset triggers.",
        },
        {
            "resource_kind": "item",
            "role": "suggestion_source",
            "description": (
                "Events like 'birthday party Saturday' may suggest shopping "
                "items ('order cake?')."
            ),
        },
    ],
    "hil_gates": [
        {
            "trigger": "missing_required_field",
            "field": "title",
            "prompt": "What should this event be called?",
        },
        {
            "trigger": "missing_required_field",
            "field": "start",
            "prompt": "What time does this event start?",
        },
        {
            "trigger": "missing_required_field",
            "field": "end",
            "prompt": "What time does this event end? (I'll default to 1 hour if not sure.)",
        },
        {
            "trigger": "missing_required_field",
            "field": "resource_id",
            "prompt": "Which calendar should I add this to?",
        },
        {
            "trigger": "time_conflict_detected",
            "prompt": "This time conflicts with: {conflict_summary}. What should I do?",
            "options": ["Create anyway", "Pick a different time", "Cancel"],
        },
        {
            "trigger": "ambiguous_person",
            "prompt": "Which person did you mean? I found: {candidate_names}.",
        },
        {
            "trigger": "child_creates_event",
            "prompt": "{child_name} is creating an event. Notify parents?",
            "options": ["Yes, notify parents", "Just create it"],
        },
    ],
    "mutation_sequencing": [
        {
            "order": 1,
            "phase": "read",
            "operation": "list",
            "description": "Read current calendar + chores + tasks for the target time window.",
        },
        {
            "order": 2,
            "phase": "mutate",
            "operation": "create",
            "description": (
                "Create the event if no blocking conflicts. If a soft conflict "
                "exists, present it to the user per conflict_analysis_rules "
                "resolution guidance above."
            ),
        },
        {
            "order": 3,
            "phase": "read",
            "operation": "list",
            "description": "Verify event was created (read_after_write).",
        },
    ],
    "verification_requirements": [
        {
            "method": "read_after_write",
            "description": "Read back the created event and confirm all fields match.",
            "required_for_submit": True,
        },
        {
            "method": "output_schema",
            "description": "Validate the returned event matches the expected schema.",
        },
    ],
    "precondition_summary": (
        "Before creating or updating an event, I MUST list the calendar for the "
        "target time window. I SHOULD also check chores and tasks for soft "
        "conflicts. I present all conflicts to the user -- I never silently "
        "overwrite."
    ),
    "companion_resource_summary": (
        "Calendar events conflict with chores and tasks in the same time window. "
        "Events can trigger reminders. Recurring events like birthdays can "
        "suggest shopping items. If the user describes something recurring with "
        "reward tracking, that is a CHORE (family.chores), not a calendar event."
    ),
    "hil_trigger_summary": (
        "I need human input when: title/start/end/calendar are missing, a time "
        "conflict is detected, a person reference is ambiguous, or a child is "
        "creating an event that should notify parents."
    ),
    "degradation_policy": (
        "If read_after_write verification fails, retry once. If still failing, "
        "submit degraded with the created event_id but flag verification=failed."
    ),
    # ── RES-017: Teaching surface fields (2026-06-17) ──────────────
    "how_to_sequence": [
        "1. Read current calendar + chores + tasks for the target time window.",
        "2. Create the event if no blocking conflicts. If a soft conflict "
        "exists, present it to the user per conflict resolution guidance.",
        "3. Verify event was created (read_after_write).",
    ],
    "what_to_verify": [
        "After create/update: Read back the event and confirm all fields "
        "match the submitted values.",
        "Validate the returned event matches the expected output schema.",
    ],
    "when_to_ask_human": [
        {
            "trigger": "missing_required_field",
            "reason": "Event title is required.",
            "prompt": "What should this event be called?",
        },
        {
            "trigger": "missing_required_field",
            "reason": "Start time is required.",
            "prompt": "What time does this event start?",
        },
        {
            "trigger": "missing_required_field",
            "reason": "End time is required.",
            "prompt": "What time does this event end? (I'll default to 1 hour if not sure.)",
        },
        {
            "trigger": "missing_required_field",
            "reason": "Target calendar must be selected.",
            "prompt": "Which calendar should I add this to?",
        },
        {
            "trigger": "time_conflict_detected",
            "reason": "This time conflicts with an existing event, chore, or task.",
            "prompt": "This time conflicts with: {conflict_summary}. What should I do?",
        },
        {
            "trigger": "ambiguous_person",
            "reason": "Person reference could not be resolved to a single member.",
            "prompt": "Which person did you mean? I found: {candidate_names}.",
        },
        {
            "trigger": "child_creates_event",
            "reason": "A child is creating an event — parent notification may be required.",
            "prompt": "{child_name} is creating an event. Notify parents?",
        },
    ],
    "companion_connectors": [
        {
            "connector_id": "family.chores",
            "role": "conflict_source",
            "description": (
                "Calendar events may conflict with assigned chores in the "
                "same time window. When the user describes something "
                "recurring with reward tracking, route to family.chores."
            ),
        },
        {
            "connector_id": "family.tasks",
            "role": "conflict_source",
            "description": "Calendar events may conflict with due tasks.",
        },
        {
            "connector_id": "family.reminders",
            "role": "dependency",
            "description": "Events can trigger reminders via event_offset triggers.",
        },
        {
            "connector_id": "family.shopping",
            "role": "suggestion_source",
            "description": (
                "Events like 'birthday party Saturday' may suggest shopping "
                "items ('order cake?')."
            ),
        },
    ],
    "conflict_rules": [
        (
            "If time_overlap with events: Two events at overlapping times "
            "for the same attendees. Resolution: Present the conflict to "
            "the user with options — create anyway, pick a different time, "
            "or cancel. Do NOT silently overwrite."
        ),
        (
            "If time_overlap with chores: An assigned chore is due during "
            "this event's time window. Resolution: Warn that the child has "
            "a chore due, offer to create event anyway, reschedule the "
            "chore, or cancel."
        ),
        (
            "If time_overlap with tasks: A task is due during this event's "
            "time window. Resolution: Warn that the assignee has a task "
            "due, offer to create event anyway or cancel."
        ),
        (
            "If participant_availability: All attendees must be free in the "
            "target time window. Resolution: If any participant has a "
            "conflicting event, list the conflict and ask whether to proceed."
        ),
    ],
}

_CALENDAR_POLICY: dict[str, Any] = {
    "operation_role_gates": {
        "create_event": ["parent", "child", "guardian"],
        "update_event": ["parent", "guardian"],
        "delete_event": ["parent", "guardian"],
        "set_visibility": ["parent"],
        "connect_feed": ["parent"],
        "disconnect_feed": ["parent"],
        "list_feeds": ["parent", "guardian"],
        "respond_to_invite": ["parent", "child", "guardian"],
    },
    "operation_safety_bands": {
        "create_event": "GREEN",
        "update_event": "GREEN",
        "delete_event": "AMBER",
        "set_visibility": "AMBER",
        "connect_feed": "AMBER",
        "disconnect_feed": "AMBER",
    },
    "protected_resources": [
        {
            "resource_id_pattern": "cal_parent_*",
            "reason": "Parent calendar may contain sensitive appointments.",
            "required_role": "parent",
        },
    ],
    "hil_triggers": [
        {
            "condition": "write_operation AND actor_role == 'child'",
            "prompt": "Ask a parent to confirm this calendar change.",
        },
    ],
}

_CALENDAR_GUIDE_CARDS: list[dict[str, Any]] = [
    {
        "guide_id": "family.calendar.guide.01",
        "title": "How to Schedule Events",
        "content": (
            "When creating a calendar event:\n"
            "1. Always LIST the calendar first to check for conflicts.\n"
            "2. Check the person's chores and tasks in the same time window.\n"
            "3. If the person is a child, their parent's calendar may have "
            "related events.\n"
            "4. Provide clear titles -- 'Dentist - Riley' not just 'Appointment'.\n"
            "5. Set appropriate durations -- default 60 min if unsure."
        ),
        "relevance": "always",
        "disclosure_phase": "connector_summary",
    },
    {
        "guide_id": "family.calendar.guide.02",
        "title": "Conflict Resolution",
        "content": (
            "When the constitution reports a time conflict:\n"
            "- Tell the user WHAT conflicts (event name + time).\n"
            "- Offer: 'Create anyway', 'Pick a different time', or 'Cancel'.\n"
            "- Do NOT silently overwrite or skip the conflict."
        ),
        "relevance": "on_conflict",
        "disclosure_phase": "tool_name_selection",
    },
]

_CALENDAR_ONTOLOGY: dict[str, Any] = {
    "domain": "family",
    "concept_aliases": [
        {"alias": "dentist", "canonical_concept": "appointment", "weight": 0.9},
        {"alias": "doctor", "canonical_concept": "appointment", "weight": 0.9},
        {"alias": "practice", "canonical_concept": "calendar_event", "weight": 0.7},
        {"alias": "game", "canonical_concept": "calendar_event", "weight": 0.7},
        {"alias": "recital", "canonical_concept": "calendar_event", "weight": 0.8},
        {"alias": "calendar event", "canonical_concept": "calendar_event", "weight": 1.0},
    ],
    "concept_resource_edges": [
        {"concept": "appointment", "resource_family": "event", "weight": 1.0},
        {"concept": "calendar_event", "resource_family": "event", "weight": 1.0},
    ],
    "resource_connector_edges": [
        {
            "resource_family": "event",
            "connector_id": "family.calendar",
            "weight": 1.0,
            "role": "primary",
        },
    ],
    "operation_equivalences": [
        {
            "canonical_operation": "list",
            "equivalent_operation": "search",
            "resource_family": "event",
        },
    ],
    "operation_aliases": [
        {"alias": "schedule", "operation_family": "create", "effect": "write"},
        {"alias": "book", "operation_family": "create", "effect": "write"},
        {"alias": "add", "operation_family": "create", "effect": "write"},
    ],
}


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
    can_reference=["task", "reminder", "item"],
    feature_flags=["m15_calendar"],
    domain_tags=["scheduling", "availability", "external_calendar"],
    # ── Phase 1.1 enrichment (Epics 9.2-9.6) ──
    resource_kinds=["calendar_event", "appointment"],
    # ── Phase 2.6 taxonomy (Epic 23.2) ──
    domain_id="family",
    resource_families=["event"],
    actor_scope=["parent", "admin", "system"],
    snapshot_types=["daily_snapshot", "weekly_overview"],
    back_execution_profile=True,
    constitution=_CALENDAR_CONSTITUTION,
    policy_declarations=_CALENDAR_POLICY,
    guide_cards=_CALENDAR_GUIDE_CARDS,
    ontology=_CALENDAR_ONTOLOGY,
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
                    "user wants a recurring family chore -> use chores.create_template",
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
