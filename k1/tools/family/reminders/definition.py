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
            prompt_template="reminders_activity_v1",
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
                    "recurring household duty → chores.create_chore",
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
            prompt_template="reminders_activity_v1",
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
            prompt_template="reminders_activity_v1",
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
            prompt_template="reminders_activity_v1",
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
            prompt_template="reminders_activity_v1",
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
            prompt_template="reminders_activity_v1",
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
            prompt_template="reminders_activity_v1",
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
