"""k1.tools.family.reminders.definition -- declarative spec for the Reminders adapter.

Exposes :data:`REMINDERS_DEFINITION`, the single source of truth consumed by
the Fabric manifest translator, UI manifest generator, LLM tool spec builder,
and :class:`RemindersToolService`.

8 actions total:
  Writes (AMBER):  create_reminder, update_reminder, snooze_reminder,
                   dismiss_reminder, fire_reminder, delete_reminder
  Reads (GREEN):   list_reminders, get_reminder

Special notes
-------------
* ``fire_reminder`` is **system-only** (``allowed_roles=["system"]``).
  The K1 scheduler calls it when a trigger fires; the LLM must never call it.
  The SSE envelope it emits carries push-notification payload fields
  (``push_title``, ``push_body``, ``push_recipient_ids``) for APNs/FCM relay.
* ``create_reminder`` cross-member guard: if ``recipient != caller`` the
  caller must be ``guardian`` or higher.  Declared as runtime check (not
  ``min_role``) so self-reminders work for any role.
* ``update_reminder`` is blocked after firing (``status != 'scheduled'``).
* ``snooze_reminder`` / ``dismiss_reminder`` require caller to be the
  recipient, the creator (``actor``), or ``guardian``+.
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

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "tables.sql"), encoding="utf-8") as _f:
    _REMINDERS_DDL: str = _f.read()

# ---------------------------------------------------------------------------
# Shared field helpers
# ---------------------------------------------------------------------------

_REMINDER_ID_FIELD = FieldSpec(
    name="reminder_id",
    type="string",
    required=True,
    description="``Reminder.id``.",
)
_VISIBILITY_FIELD = FieldSpec(
    name="visibility",
    type="string",
    required=False,
    description="Row-level band: ``family`` | ``adults`` | ``named`` | ``private``.",
)

# ---------------------------------------------------------------------------
# Phase 1.1 -- Constitution / Policy / Guide cards / Ontology (Epic 11.1-11.2)
#
# Grounded to the REAL 8-action surface: create / update / snooze / dismiss /
# fire (system-only) / delete / list / get. Reminders are pure notifications --
# distinct from one-shot tasks and recurring gamified chores.
# ---------------------------------------------------------------------------

_REMINDERS_CONSTITUTION: dict[str, Any] = {
    "connector_id": "family.reminders",
    "constitution_id": "family.reminders.v1",
    "schema_version": "1.0.0",
    "execution_phases": ["read", "mutate"],
    "prerequisite_reads": [
        {
            "operation": "list",
            "resource_kind": "reminder",
            "reason": (
                "Check for duplicate reminders (same person + same time + same "
                "message) before creating."
            ),
            "required": True,
            "timeout_ms": 5000,
        },
        {
            "operation": "list",
            "resource_kind": "calendar_event",
            "reason": (
                "If the reminder uses an event_offset trigger, verify the "
                "referenced calendar event still exists. If deleted, the "
                "reminder would fire at a computed time based on nothing -- "
                "warn the user."
            ),
            "required": False,
            "timeout_ms": 3000,
        },
    ],
    "conflict_analysis_rules": [
        {
            "check": "duplicate",
            "with_resource_kinds": ["reminder"],
            "description": (
                "New reminder must not duplicate an existing reminder for the "
                "same recipient at the same time with the same message."
            ),
            "resolution": (
                "Tell the user: '{recipient} already has a reminder "
                "{existing_message} at {time}'. Offer: create anyway or cancel."
            ),
        },
        {
            "check": "invalid_event_ref",
            "with_resource_kinds": ["calendar_event"],
            "description": (
                "The calendar event referenced by an event_offset trigger no "
                "longer exists (deleted or moved)."
            ),
            "resolution": (
                "Warn: 'The event {event_title} was deleted. The reminder will "
                "still fire at {computed_time} but won't reference a valid "
                "event.' Offer: create anyway, pick a different event, or cancel."
            ),
        },
    ],
    "companion_resource_roles": [
        {
            "resource_kind": "calendar_event",
            "role": "dependency",
            "description": (
                "Reminders can fire at event offsets ('30 minutes before "
                "Riley's soccer') via the event_offset trigger. The reminder "
                "depends on the event existing -- if the event is deleted, warn "
                "the user per conflict_analysis_rules above."
            ),
        },
        {
            "resource_kind": "task",
            "role": "distinct_sibling",
            "description": (
                "CRITICAL DISTINCTION: Reminders are PURE NOTIFICATIONS ('remind "
                "Riley to take medicine at 8pm'). Tasks are ONE-SHOT action "
                "items ('pick up Riley today'). If the user says 'remind me to "
                "X', that's a reminder. If the user says 'I need to X' or 'add X "
                "to my list', that's a task. See the 'Reminders vs Tasks' guide "
                "card."
            ),
        },
    ],
    "hil_gates": [
        {
            "trigger": "missing_required_field",
            "field": "trigger_at",
            "prompt": "What time should the reminder fire?",
        },
        {
            "trigger": "missing_required_field",
            "field": "recipient",
            "prompt": "Who is this reminder for?",
        },
        {
            "trigger": "missing_required_field",
            "field": "message",
            "prompt": "What should the reminder say?",
        },
        {
            "trigger": "ambiguous_person",
            "prompt": "Which person did you mean? I found: {candidate_names}.",
        },
    ],
    "mutation_sequencing": [
        {
            "order": 1,
            "phase": "read",
            "operation": "list",
            "description": "Read current reminders + calendar event if event_offset trigger is set.",
        },
        {
            "order": 2,
            "phase": "mutate",
            "operation": "create",
            "description": (
                "Create the reminder if no duplicate detected. Warn about an "
                "invalid event reference if applicable."
            ),
        },
        {
            "order": 3,
            "phase": "read",
            "operation": "list",
            "description": "Verify reminder was created (read_after_write).",
        },
    ],
    "verification_requirements": [
        {
            "method": "read_after_write",
            "description": "Read back the created reminder and confirm all fields match.",
            "required_for_submit": True,
        },
        {
            "method": "output_schema",
            "description": "Validate the returned reminder matches the expected schema.",
        },
    ],
    "precondition_summary": (
        "Before creating a reminder, I MUST list existing reminders for the same "
        "recipient to check for duplicates. If the reminder uses an event_offset "
        "trigger, I SHOULD verify the event still exists. Reminders are pure "
        "notifications -- I do NOT check for calendar scheduling conflicts."
    ),
    "companion_resource_summary": (
        "Reminders can fire at calendar event offsets. Reminders are DISTINCT "
        "from tasks: reminders are pure notifications ('remind me to X at Y "
        "time'), tasks are action items ('I need to do X'). See the 'Reminders "
        "vs Tasks' guide card for the full distinction rules."
    ),
    "hil_trigger_summary": (
        "I need human input when: reminder time, recipient, or message is "
        "missing, or a person reference is ambiguous."
    ),
    "degradation_policy": (
        "If read_after_write verification fails, retry once then submit degraded."
    ),
}

_REMINDERS_POLICY: dict[str, Any] = {
    "operation_role_gates": {
        # Anyone in the household can set/manage their own reminders; the
        # cross-recipient guard (recipient != caller -> guardian+) is enforced
        # at the service layer, not as a static role gate.
        "create_reminder": ["parent", "child", "guardian", "elder"],
        "update_reminder": ["parent", "child", "guardian", "elder"],
        "snooze_reminder": ["parent", "child", "guardian", "elder"],
        "dismiss_reminder": ["parent", "child", "guardian", "elder"],
        "delete_reminder": ["parent", "child", "guardian", "elder"],
        # fire_reminder is the scheduler's mechanism -- system only.
        "fire_reminder": ["system"],
    },
    "operation_safety_bands": {
        "create_reminder": "GREEN",
        "update_reminder": "GREEN",
        "snooze_reminder": "GREEN",
        "dismiss_reminder": "GREEN",
        "delete_reminder": "GREEN",
    },
}

_REMINDERS_GUIDE_CARDS: list[dict[str, Any]] = [
    {
        "guide_id": "family.reminders.guide.01",
        "title": "Reminders vs Tasks -- Know the Difference",
        "content": (
            "REMINDERS are PURE NOTIFICATIONS:\n"
            "  'Remind Riley to take medicine at 8pm'\n"
            "  'Remind me to call the dentist tomorrow at 9am'\n"
            "  'Remind Riley 30 minutes before soccer practice'\n"
            "Reminders fire once, notify, and are done. No tracking, no "
            "completion state, no rewards. They are cheap -- create freely.\n\n"
            "TASKS are ONE-SHOT ACTION ITEMS:\n"
            "  'Pick up Riley from school today'\n"
            "  'I need to finish the report by Friday'\n"
            "Tasks are tracked, have completion state, and may have due dates.\n\n"
            "RED FLAGS that mean TASK not reminder:\n"
            "- 'I need to [do X]' -> task\n"
            "- 'add [X] to my list' -> task\n"
            "- '[X] is due [date]' -> task\n"
            "- 'don't forget to [X]' -> ask if they want a reminder or a task\n\n"
            "If ANY red flag is present, consider family.tasks instead."
        ),
        "relevance": "always",
        "disclosure_phase": "connector_summary",
    },
    {
        "guide_id": "family.reminders.guide.02",
        "title": "Creating Reminders from Calendar Events",
        "content": (
            "Reminders can fire at offsets from calendar events using the "
            "event_offset trigger:\n"
            "- 'Remind Riley 30 minutes before soccer practice'\n"
            "- 'Remind me 1 hour before the dentist appointment'\n\n"
            "Always verify the event still exists before creating the reminder. "
            "If the event is deleted, warn the user but still allow creation."
        ),
        "relevance": "on_conflict",
        "disclosure_phase": "tool_name_selection",
    },
]

_REMINDERS_ONTOLOGY: dict[str, Any] = {
    "domain": "family",
    "concept_aliases": [
        {"alias": "alert", "canonical_concept": "reminder", "weight": 0.9},
        {"alias": "nag", "canonical_concept": "reminder", "weight": 0.7},
        {"alias": "notify", "canonical_concept": "reminder", "weight": 0.8},
        {"alias": "remind me", "canonical_concept": "reminder", "weight": 1.0},
        {"alias": "ping", "canonical_concept": "reminder", "weight": 0.6},
    ],
    "concept_resource_edges": [
        {"concept": "reminder", "resource_family": "reminder", "weight": 1.0},
    ],
    "resource_connector_edges": [
        {
            "resource_family": "reminder",
            "connector_id": "family.reminders",
            "weight": 1.0,
            "role": "primary",
        },
        {
            "resource_family": "calendar_event",
            "connector_id": "family.reminders",
            "weight": 0.5,
            "role": "companion",
        },
    ],
    "operation_aliases": [
        {"alias": "remind", "operation_family": "create", "effect": "write"},
        {"alias": "set", "operation_family": "create", "effect": "write"},
        {"alias": "snooze", "operation_family": "snooze", "effect": "write"},
        {"alias": "notify", "operation_family": "create", "effect": "write"},
    ],
}


# ---------------------------------------------------------------------------
# REMINDERS_DEFINITION
# ---------------------------------------------------------------------------

REMINDERS_DEFINITION = ToolDefinition(
    adapter_id="reminders",
    version="1.0.0",
    category="coordination",
    summary=(
        "Personal and cross-family alert system with time-based, location-based, "
        "and calendar-offset triggers.  The killer feature: any family member can "
        "set a reminder on behalf of another."
    ),
    title="Reminders",
    icon="bell",
    description=(
        "FamilyOS native reminder engine.  Each reminder has a recipient (who gets "
        "alerted) and a trigger (when/where it fires).  Trigger kinds: time, "
        "location_enter, location_leave, event_offset.  Lifecycle: "
        "scheduled → fired → dismissed | snoozed.  Every write fans out via SSE; "
        "fire_reminder SSE carries push-notification payload for APNs/FCM relay."
    ),
    entity_type="reminder",
    views=["list", "timeline"],
    activity_profile="reminders.v1",
    domain_tags=["alerting", "notification", "scheduler"],
    filters=[
        FieldSpec(
            name="recipient",
            type="string",
            required=False,
            description="Filter by recipient ``member_id``.",
        ),
        FieldSpec(
            name="status",
            type="string",
            required=False,
            description="Filter by status: scheduled | fired | dismissed | snoozed.",
        ),
    ],
    can_reference=["calendar_event", "task"],
    feature_flags=["m15_reminders"],
    # ── Phase 1.1 enrichment (Epics 11.1-11.2) ──
    resource_kinds=["reminder"],
    actor_scope=["parent", "admin", "system"],
    snapshot_types=["daily_snapshot", "weekly_overview"],
    back_execution_profile=True,
    constitution=_REMINDERS_CONSTITUTION,
    policy_declarations=_REMINDERS_POLICY,
    guide_cards=_REMINDERS_GUIDE_CARDS,
    ontology=_REMINDERS_ONTOLOGY,
    tables_sql=_REMINDERS_DDL,
    actions=[
        # ------------------------------------------------------------------
        # 1. create_reminder
        # ------------------------------------------------------------------
        ActionSpec(
            name="create_reminder",
            kind="write",
            summary="Create a new reminder for self or another family member.",
            label="New reminder",
            primary=True,
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            idempotent=True,
            params=[
                FieldSpec(
                    name="title",
                    type="string",
                    required=True,
                    description="Short alert text shown on device.",
                ),
                FieldSpec(
                    name="recipient",
                    type="string",
                    required=True,
                    description=(
                        "``member_id`` who receives the alert.  "
                        "Setting this to another member requires ``guardian`` or higher."
                    ),
                ),
                FieldSpec(
                    name="trigger",
                    type="object",
                    required=True,
                    description=(
                        "Trigger spec.  Required keys depend on ``kind``: "
                        "``time`` → ``{kind, fire_at}``; "
                        "``location_enter|leave`` → ``{kind, location:{lat,lon,radius_m}}``; "
                        "``event_offset`` → ``{kind, event_id, offset_minutes?}``."
                    ),
                ),
                FieldSpec(
                    name="message",
                    type="string",
                    required=False,
                    description="Optional longer instruction for the recipient.",
                ),
                FieldSpec(
                    name="linked_event_id",
                    type="string",
                    required=False,
                    description="Cross-tool back-link to ``calendar_events.id``.",
                ),
                _VISIBILITY_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user says 'remind X to Y' — X is the recipient",
                    "user wants a time-triggered alert at a specific moment",
                    "user wants a location-triggered alert ('when dad gets home', 'when you leave work')",
                    "user wants a pre-event or post-event alert N minutes relative to a calendar event",
                    "user wants to remind themselves at a specific time",
                ],
                avoid_when=[
                    "deadline-based to-do with no automatic firing → tasks.create_task",
                    "time-blocked appointment with start+end time → calendar.create_event",
                    "recurring household duty → chores.create_template",
                    "user wants to add a shopping item → shopping.add_item",
                ],
                examples=[
                    "Remind dad to grab milk when he leaves work → create_reminder(title='Grab milk', recipient=dad_id, trigger={kind:'location_leave', location:{name:'work', lat:..., lon:..., radius_m:200}})",
                    "Remind Riley to take medication at 8pm → create_reminder(title='Take medication', recipient=riley_id, trigger={kind:'time', fire_at:'2026-05-12T20:00:00Z'})",
                    "Alert everyone 30 min before the dentist → one create_reminder per member with trigger={kind:'event_offset', event_id:'...', offset_minutes:-30}",
                ],
            ),
            sse=SSESpec(emits=["family.reminders.create_reminder.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 2. update_reminder
        # ------------------------------------------------------------------
        ActionSpec(
            name="update_reminder",
            kind="write",
            summary="Change the title, message, or trigger of a scheduled reminder.",
            label="Edit reminder",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                _REMINDER_ID_FIELD,
                FieldSpec(name="title", type="string", required=False),
                FieldSpec(name="message", type="string", required=False),
                FieldSpec(
                    name="trigger",
                    type="object",
                    required=False,
                    description="Replace the trigger spec entirely.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants to change when or where a reminder fires before it has fired",
                    "user wants to change the reminder title or message",
                ],
                avoid_when=[
                    "reminder has already fired or been dismissed — immutable at that point",
                    "user wants to delay a fired reminder → snooze_reminder",
                ],
                examples=[
                    "Change the medication reminder to 9pm → get_reminder(reminder_id) first, then update_reminder(reminder_id, trigger={kind:'time', fire_at:'...T21:00:00Z'})",
                    "Update the 'grab milk' reminder message → update_reminder(reminder_id, message='Also grab bread')",
                ],
            ),
            sse=SSESpec(emits=["family.reminders.update_reminder.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 3. snooze_reminder
        # ------------------------------------------------------------------
        ActionSpec(
            name="snooze_reminder",
            kind="write",
            summary="Re-arm a fired reminder to fire again at a new time.",
            label="Snooze",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                _REMINDER_ID_FIELD,
                FieldSpec(
                    name="snooze_until",
                    type="datetime",
                    required=True,
                    description="ISO 8601 time when the reminder should re-fire.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder_id", type="string", required=True),
                FieldSpec(name="snoozed_until", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "reminder fired and recipient says 'remind me again in X minutes'",
                    "user wants to defer an alert that already appeared",
                ],
                avoid_when=[
                    "reminder has not fired yet — use update_reminder to shift the trigger instead",
                ],
                examples=[
                    "Snooze the medication alert for 30 minutes → snooze_reminder(reminder_id, snooze_until=now+30min)",
                    "Remind me again at 10pm → snooze_reminder(reminder_id, snooze_until='...T22:00:00Z')",
                ],
            ),
            sse=SSESpec(emits=["family.reminders.snooze_reminder.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 4. dismiss_reminder
        # ------------------------------------------------------------------
        ActionSpec(
            name="dismiss_reminder",
            kind="write",
            summary="Acknowledge a fired reminder — no further action needed.",
            label="Dismiss",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[_REMINDER_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "recipient acknowledged the alert and no further action is needed",
                    "user says 'got it', 'ok', 'done' in response to a reminder notification",
                ],
                examples=[
                    "Riley says 'got it' after the homework alert → dismiss_reminder(reminder_id)",
                    "Mark the dentist reminder as done → dismiss_reminder(reminder_id)",
                ],
            ),
            sse=SSESpec(emits=["family.reminders.dismiss_reminder.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 5. fire_reminder  — SYSTEM ONLY
        # ------------------------------------------------------------------
        ActionSpec(
            name="fire_reminder",
            kind="write",
            summary=(
                "SYSTEM ONLY — called by K1 scheduler when a trigger condition is met.  "
                "LLM must never call this action."
            ),
            label="Fire reminder",
            min_band="GREEN",
            allowed_roles=["system"],
            tool_instructions=(
                "Scheduler-only reminder lifecycle action. LLM callers must not invoke "
                "this action; user-facing reminder work should use create/update/snooze/"
                "dismiss/delete contracts as permitted by schema and policy."
            ),
            params=[_REMINDER_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder_id", type="string", required=True),
                FieldSpec(name="fired_at", type="string", required=True),
                # Push-notification payload carried in SSE envelope:
                FieldSpec(name="push_title", type="string", required=False),
                FieldSpec(name="push_body", type="string", required=False),
                FieldSpec(name="push_recipient_ids", type="array", required=False),
            ],
            llm=LLMHints(
                use_when=["SYSTEM ONLY — do not use; the scheduler calls this automatically"],
                avoid_when=["any LLM-initiated scenario — this is scheduler-only"],
            ),
            sse=SSESpec(
                emits=["family.reminders.fire_reminder.write.v1"],
                redact_fields=[],
            ),
        ),
        # ------------------------------------------------------------------
        # 6. delete_reminder
        # ------------------------------------------------------------------
        ActionSpec(
            name="delete_reminder",
            kind="delete",
            summary="Cancel and soft-delete a reminder before it fires.",
            label="Delete reminder",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[_REMINDER_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to cancel a reminder that hasn't fired yet"],
                avoid_when=[
                    "reminder already fired — use dismiss_reminder to acknowledge instead",
                ],
                examples=[
                    "Cancel the 'take out trash' reminder → get_reminder(reminder_id) to confirm status=scheduled, then delete_reminder(reminder_id)",
                    "Remove the pickup reminder → list_reminders(recipient, status=scheduled) to find id, then delete_reminder(reminder_id)",
                ],
            ),
            sse=SSESpec(emits=["family.reminders.delete_reminder.delete.v1"]),
        ),
        # ------------------------------------------------------------------
        # 7. list_reminders
        # ------------------------------------------------------------------
        ActionSpec(
            name="list_reminders",
            kind="read",
            summary="Return reminders in the family space, ACL-filtered for the caller.",
            label="List reminders",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[
                FieldSpec(
                    name="recipient",
                    type="string",
                    required=False,
                    description="Filter to a specific recipient ``member_id``.",
                ),
                FieldSpec(
                    name="status",
                    type="string",
                    required=False,
                    description="Filter by status: scheduled | fired | dismissed | snoozed.",
                ),
                FieldSpec(
                    name="due_before",
                    type="datetime",
                    required=False,
                    description="Return only time-based reminders whose ``fire_at`` ≤ this value.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminders", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "planner checking existing reminders before creating a duplicate",
                    "user asks 'what reminders do I have today?'",
                    "user asks what reminders are set for a specific family member",
                ],
                examples=[
                    "Check for duplicate before creating → list_reminders(recipient=member_id, status='scheduled')",
                    "What reminders does Riley have? → list_reminders(recipient=riley_id)",
                    "Show all pending alerts → list_reminders(status='scheduled')",
                ],
            ),
        ),
        # ------------------------------------------------------------------
        # 8. get_reminder
        # ------------------------------------------------------------------
        ActionSpec(
            name="get_reminder",
            kind="read",
            summary="Fetch a single reminder by id (ACL-filtered).",
            label="Get reminder",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[_REMINDER_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="reminder", type="object", required=True),
            ],
            llm=LLMHints(
                use_when=["user asks about the details of a specific reminder"],
                examples=[
                    "Read current state before mutating → get_reminder(reminder_id)",
                    "Verify the snooze landed → get_reminder(reminder_id) after write",
                ],
            ),
        ),
    ],
)
