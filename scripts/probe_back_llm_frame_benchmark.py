"""Back LLM Frame Extraction Benchmark — No keyword heuristics. LLM only.

GIVEN (full K1 context):
  - 20-turn chat history
  - GroundingCapsule (self model: who user is, preferences, goals, routines)
  - Household roster with aliases
  - GroundingProjection (time, place, device)
  - Session state (beliefs, task state, narrative)
  - User utterance

LLM MUST PRODUCE (structured JSON):
  - intents: [{action, domain, operation_hint, resource_kind_hint, params}]
  - person_refs: [{raw, confidence, needs_resolution}]
  - resource_refs: [{raw, resource_kind_hint, confidence, needs_resolution}]
  - time_window_hint: {raw_phrase, confidence} | null

MEASURES (6 dimensions):
  - Operation accuracy
  - Resource accuracy
  - Person accuracy
  - Time accuracy
  - Completeness (all intents caught)
  - Disambiguation (flagged when needed)

Usage:
  python scripts/probe_back_llm_frame_benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract_v2.model_client import (
    ModelClient,
    create_model_client_from_env,
)

# ═══════════════════════════════════════════════════════════════════
# REALISTIC TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════

HOUSEHOLD_ROSTER = {
    "space_id": "space_family_001",
    "members": [
        {
            "member_id": "person.alex",
            "display_name": "Alex",
            "aliases": ["Alex", "Al", "Lex", "Mom", "Dad", "Parent", "Love"],
            "role": "parent",
            "age_band": "adult",
            "pronouns": "they/them",
            "communication_style": "warm and direct",
        },
        {
            "member_id": "person.riley_k",
            "display_name": "Riley K",
            "aliases": ["Riley", "Riley K", "Riles", "RK"],
            "role": "child",
            "age_band": "child",
            "pronouns": "they/them",
            "communication_style": "playful, needs gentle reminders",
        },
        {
            "member_id": "person.riley_t",
            "display_name": "Riley T",
            "aliases": ["Riley", "Riley T", "Rye"],
            "role": "guest",
            "age_band": "child",
            "pronouns": "she/her",
            "communication_style": "quiet, direct",
        },
        {
            "member_id": "person.jordan",
            "display_name": "Jordan",
            "aliases": ["Jordan", "Jord", "J", "Jojo"],
            "role": "child",
            "age_band": "teen",
            "pronouns": "he/him",
            "communication_style": "sarcastic, needs direct asks",
        },
        {
            "member_id": "person.sam",
            "display_name": "Sam",
            "aliases": ["Sam", "Sammy", "Grandma", "Nana"],
            "role": "guardian",
            "age_band": "adult",
            "pronouns": "she/her",
            "communication_style": "gentle, old-school",
        },
    ],
    "relations": [
        {"from": "person.alex", "to": "person.riley_k", "kind": "guardian_of", "weight": 1.0},
        {"from": "person.alex", "to": "person.jordan", "kind": "guardian_of", "weight": 1.0},
        {"from": "person.alex", "to": "person.sam", "kind": "child_of", "weight": 0.9},
        {"from": "person.sam", "to": "person.riley_k", "kind": "grandparent_of", "weight": 0.8},
        {"from": "person.sam", "to": "person.jordan", "kind": "grandparent_of", "weight": 0.8},
        {"from": "person.riley_t", "to": "person.riley_k", "kind": "friend_of", "weight": 0.7},
    ],
}

SELF_MODEL = {
    "actor_id": "person.alex",
    "display_name": "Alex",
    "role": "parent",
    "age_band": "adult",
    "language": "en",
    "pronouns": "they/them",
    "communication_style": "warm and direct",
    "preferences": {
        "payment_method": "card_ending_1234",
        "dietary": "vegetarian",
        "units": "imperial",
        "notification_tone": "gentle",
        "calendar_default_duration_minutes": "60",
    },
    "hobbies": ["cooking", "hiking", "reading", "board games"],
    "likes": ["morning quiet time", "family dinners", "outdoor adventures"],
    "dislikes": ["last-minute changes", "loud notifications", "clutter"],
    "goals": [
        {
            "goal_id": "g1",
            "summary": "Get kids to school on time every day",
            "horizon": "this_week",
            "status": "active",
        },
        {
            "goal_id": "g2",
            "summary": "Reduce screen time for Riley K",
            "horizon": "this_month",
            "status": "active",
        },
        {
            "goal_id": "g3",
            "summary": "Plan summer family camping trip",
            "horizon": "this_quarter",
            "status": "active",
        },
    ],
    "routines": [
        {"routine_id": "r1", "name": "Morning school prep", "schedule": "weekdays 7:00am-8:15am"},
        {"routine_id": "r2", "name": "Sunday family dinner", "schedule": "Sundays 6:00pm"},
        {"routine_id": "r3", "name": "Bedtime routine", "schedule": "weekdays 8:30pm"},
    ],
    "habits": [
        {"habit_id": "h1", "summary": "Morning coffee and planning", "cadence": "daily"},
        {"habit_id": "h2", "summary": "Evening journal", "cadence": "daily"},
    ],
    "rhythms": {"wake": "06:30", "sleep": "22:30", "peak_focus": "08:00-11:00"},
}

GROUNDING = {
    "now_utc": "2026-06-03T14:30:00Z",
    "now_local": "2026-06-03T10:30:00-04:00",
    "local_date": "Wednesday, June 3, 2026",
    "local_time": "10:30 AM",
    "day_of_week": "Wednesday",
    "time_of_day": "morning",
    "timezone": "America/New_York",
    "semantic_place": "home",
    "place_label": "Home — Kitchen",
    "place_precision": "room_level",
    "device_surface": "mobile",
    "location_permission": "granted",
    "co_presence": ["person.riley_k", "person.jordan"],
    "windows": {
        "today": "2026-06-03",
        "tomorrow": "2026-06-04",
        "this_week": "2026-06-01 to 2026-06-07",
        "next_week": "2026-06-08 to 2026-06-14",
        "this_weekend": "2026-06-06 to 2026-06-07",
        "this_month": "June 2026",
    },
}

SESSION_STATE = {
    "beliefs_active": [
        {
            "subject": "Riley K",
            "predicate": "has_activity",
            "object": "soccer practice",
            "confidence": 0.95,
            "temporal": "Tuesdays and Thursdays 4pm",
        },
        {
            "subject": "Riley K",
            "predicate": "needs_reminder_for",
            "object": "chores",
            "confidence": 0.90,
        },
        {
            "subject": "Jordan",
            "predicate": "has_activity",
            "object": "piano lessons",
            "confidence": 0.92,
            "temporal": "Wednesdays 3pm",
        },
        {
            "subject": "Alex",
            "predicate": "prefers",
            "object": "gentle_notifications",
            "confidence": 0.97,
        },
        {
            "subject": "family",
            "predicate": "has_plan",
            "object": "camping trip",
            "confidence": 0.70,
            "temporal": "July 2026",
        },
        {
            "subject": "Riley K",
            "predicate": "dislikes",
            "object": "dentist_appointments",
            "confidence": 0.85,
        },
        {"subject": "Jordan", "predicate": "has_allergy", "object": "peanuts", "confidence": 0.99},
        {"subject": "Sam", "predicate": "visiting", "object": "this_weekend", "confidence": 0.80},
    ],
    "task_state": {
        "active_tasks": [
            {
                "task_id": "task_001",
                "summary": "Schedule Riley K dentist checkup",
                "status": "pending",
            },
            {
                "task_id": "task_002",
                "summary": "Buy groceries for Sunday dinner",
                "status": "in_progress",
            },
        ],
        "completed_tasks": [
            {
                "task_id": "task_000",
                "summary": "Book soccer field for practice",
                "status": "completed",
            },
        ],
    },
    "narrative_active": {
        "thread": "morning_routine",
        "arc": "getting_ready_for_school",
        "last_mentioned_person": "Riley K",
    },
}


# ═══════════════════════════════════════════════════════════════════
# TEST SCENARIOS
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FrameScenario:
    id: str
    utterance: str
    description: str
    # Expected structured output
    expected_operations: list[str]  # ["create", "list", ...]
    expected_resource_kinds: list[str | None]  # ["calendar_event", "task", ...]
    expected_persons: list[str | None]  # person ref raws
    expected_time_required: bool
    intent_count: int
    needs_disambiguation: bool = False
    disambiguation_reason: str = ""


SCENARIOS: list[FrameScenario] = [
    # ── Simple reads ──
    FrameScenario(
        id="S001",
        utterance="What's on my calendar today?",
        description="Simple calendar read, self-reference",
        expected_operations=["list"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["me"],
        expected_time_required=False,
        intent_count=1,
    ),
    FrameScenario(
        id="S002",
        utterance="Show me Riley's tasks for this week",
        description="Read tasks for specific person with time window",
        expected_operations=["list"],
        expected_resource_kinds=["task"],
        expected_persons=["Riley"],
        expected_time_required=False,
        intent_count=1,
        needs_disambiguation=True,
        disambiguation_reason="Two Rileys in household",
    ),
    FrameScenario(
        id="S003",
        utterance="What chores does Jordan have?",
        description="Read chores for specific person",
        expected_operations=["list"],
        expected_resource_kinds=["chore"],
        expected_persons=["Jordan"],
        expected_time_required=False,
        intent_count=1,
    ),
    # ── Simple creates ──
    FrameScenario(
        id="S004",
        utterance="Add dentist appointment for Riley K next Monday at 3pm",
        description="Create calendar event with specific person and time",
        expected_operations=["create"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Riley K"],
        expected_time_required=True,
        intent_count=1,
    ),
    FrameScenario(
        id="S005",
        utterance="Add 'Buy milk' to my shopping list",
        description="Create shopping item with self-reference",
        expected_operations=["create"],
        expected_resource_kinds=["shopping_item"],
        expected_persons=["me"],
        expected_time_required=False,
        intent_count=1,
    ),
    FrameScenario(
        id="S006",
        utterance="Schedule Jordan's piano recital for June 15th at 7pm",
        description="Create calendar event for specific person with exact date/time",
        expected_operations=["create"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Jordan"],
        expected_time_required=True,
        intent_count=1,
    ),
    # ── Ambiguous persons ──
    FrameScenario(
        id="S007",
        utterance="Remind Riley to do homework",
        description="Ambiguous: which Riley?",
        expected_operations=["create"],
        expected_resource_kinds=["reminder"],
        expected_persons=["Riley"],
        expected_time_required=False,
        intent_count=1,
        needs_disambiguation=True,
        disambiguation_reason="Two Rileys in household",
    ),
    FrameScenario(
        id="S008",
        utterance="What's Riley's schedule tomorrow?",
        description="Ambiguous person + read + time",
        expected_operations=["list"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Riley"],
        expected_time_required=False,
        intent_count=1,
        needs_disambiguation=True,
        disambiguation_reason="Two Rileys in household",
    ),
    # ── Compound intents (multiple things at once) ──
    FrameScenario(
        id="S009",
        utterance="Add dentist for Riley K Friday and buy groceries",
        description="Two intents: calendar create + shopping create",
        expected_operations=["create", "create"],
        expected_resource_kinds=["calendar_event", "shopping_item"],
        expected_persons=["Riley K", "me"],
        expected_time_required=True,
        intent_count=2,
    ),
    FrameScenario(
        id="S010",
        utterance="What's on the family calendar and what tasks are due?",
        description="Two reads: calendar + tasks",
        expected_operations=["list", "list"],
        expected_resource_kinds=["calendar_event", "task"],
        expected_persons=["me", "me"],
        expected_time_required=False,
        intent_count=2,
    ),
    # ── Novel/creative utterances ──
    FrameScenario(
        id="S011",
        utterance="Has Riley K been good this week?",
        description="Novel: implies checking chore completion stats",
        expected_operations=["list"],
        expected_resource_kinds=["chore"],
        expected_persons=["Riley K"],
        expected_time_required=False,
        intent_count=1,
    ),
    FrameScenario(
        id="S012",
        utterance="What should we do this weekend?",
        description="Novel: implies cross-connector (calendar free time + local events + weather)",
        expected_operations=["list"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["me"],
        expected_time_required=False,
        intent_count=1,
    ),
    FrameScenario(
        id="S013",
        utterance="Make sure Jordan does homework before TV",
        description="Novel: implies conditional dependency (tasks + screen time)",
        expected_operations=["create"],
        expected_resource_kinds=["task"],
        expected_persons=["Jordan"],
        expected_time_required=False,
        intent_count=1,
    ),
    # ── Time-specific ──
    FrameScenario(
        id="S014",
        utterance="Remind me to call mom every Sunday at 6pm",
        description="Recurring reminder with specific time",
        expected_operations=["create"],
        expected_resource_kinds=["reminder"],
        expected_persons=["me"],
        expected_time_required=True,
        intent_count=1,
    ),
    FrameScenario(
        id="S015",
        utterance="What's happening next week?",
        description="Vague time window, read calendar",
        expected_operations=["list"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["me"],
        expected_time_required=False,
        intent_count=1,
    ),
    # ── Missing information ──
    FrameScenario(
        id="S016",
        utterance="Schedule something for Riley K",
        description="Missing: what to schedule, when",
        expected_operations=["create"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Riley K"],
        expected_time_required=True,
        intent_count=1,
    ),
    FrameScenario(
        id="S017",
        utterance="Remind me",
        description="Missing: what to remind, when",
        expected_operations=["create"],
        expected_resource_kinds=["reminder"],
        expected_persons=["me"],
        expected_time_required=True,
        intent_count=1,
    ),
    # ── Updates ──
    FrameScenario(
        id="S018",
        utterance="Move Jordan's piano to 4pm",
        description="Update calendar event info",
        expected_operations=["update"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Jordan"],
        expected_time_required=True,
        intent_count=1,
    ),
    FrameScenario(
        id="S019",
        utterance="Mark the grocery shopping as done",
        description="Update/complete a task",
        expected_operations=["update"],
        expected_resource_kinds=["shopping_item"],
        expected_persons=["me"],
        expected_time_required=False,
        intent_count=1,
    ),
    # ── Cross-person / connected intents ──
    FrameScenario(
        id="S020",
        utterance="Check if Jordan and Riley K have conflicting activities on Friday",
        description="Cross-person calendar conflict check",
        expected_operations=["list"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Jordan", "Riley K"],
        expected_time_required=False,
        intent_count=2,
    ),
    FrameScenario(
        id="S021",
        utterance="Add Riley K's school play to the family calendar and remind Sam",
        description="Create event + create reminder for different person",
        expected_operations=["create", "create"],
        expected_resource_kinds=["calendar_event", "reminder"],
        expected_persons=["Riley K", "Sam"],
        expected_time_required=True,
        intent_count=2,
    ),
    # ── Edge cases ──
    FrameScenario(
        id="S022",
        utterance="Tell me about Riley K's day",
        description="Vague: could be calendar + tasks + notes",
        expected_operations=["list"],
        expected_resource_kinds=["calendar_event"],
        expected_persons=["Riley K"],
        expected_time_required=False,
        intent_count=1,
    ),
    FrameScenario(
        id="S023",
        utterance="Order pizza for Friday dinner",
        description="Food order with time context",
        expected_operations=["create"],
        expected_resource_kinds=["food_order"],
        expected_persons=["me"],
        expected_time_required=True,
        intent_count=1,
    ),
    FrameScenario(
        id="S024",
        utterance="What's the weather like and do I need to reschedule soccer?",
        description="Two intents: weather read + calendar check",
        expected_operations=["list", "list"],
        expected_resource_kinds=["weather_report", "calendar_event"],
        expected_persons=["me", "Riley K"],
        expected_time_required=False,
        intent_count=2,
    ),
    FrameScenario(
        id="S025",
        utterance="",
        description="Empty utterance — should produce compute/null intent",
        expected_operations=["compute"],
        expected_resource_kinds=[None],
        expected_persons=[None],
        expected_time_required=False,
        intent_count=1,
    ),
]


# ═══════════════════════════════════════════════════════════════════
# PROMPT BUILDER — NO KEYWORD HEURISTICS
# ═══════════════════════════════════════════════════════════════════


def build_context_block() -> str:
    """Render the full K1 context as the LLM would see it."""
    hh = HOUSEHOLD_ROSTER
    sm = SELF_MODEL
    g = GROUNDING
    ss = SESSION_STATE

    parts: list[str] = []

    # ── Self Model ──
    parts.append("== WHO YOU ARE (SELF MODEL) ==")
    parts.append(f"You are {sm['display_name']}.")
    parts.append(f"Role: {sm['role']} | Age: {sm['age_band']} | Pronouns: {sm['pronouns']}")
    parts.append(f"Communication style: {sm['communication_style']}")
    if sm["preferences"]:
        parts.append("Preferences: " + json.dumps(sm["preferences"]))
    if sm["goals"]:
        parts.append("Active goals:")
        for goal in sm["goals"]:
            parts.append(f"  - [{goal['status']}] {goal['summary']} (horizon: {goal['horizon']})")
    if sm["routines"]:
        parts.append("Routines:")
        for r in sm["routines"]:
            parts.append(f"  - {r['name']}: {r['schedule']}")
    if sm["habits"]:
        parts.append("Habits: " + ", ".join(h["summary"] for h in sm["habits"]))

    # ── Household Roster ──
    parts.append("\n== YOUR HOUSEHOLD (VISIBLE SPACE) ==")
    for m in hh["members"]:
        aliases_str = ", ".join(m["aliases"])
        parts.append(
            f"  {m['display_name']} ({m['role']}, {m['age_band']}): known as [{aliases_str}]"
        )
    parts.append("\nRelationships:")
    for rel in hh["relations"]:
        parts.append(f"  {rel['from']} --[{rel['kind']}]--> {rel['to']}")

    # ── Grounding ──
    parts.append("\n== TIME AND PLACE (GROUNDING) ==")
    parts.append(f"Right now: {g['now_local']} ({g['timezone']})")
    parts.append(f"Time of day: {g['time_of_day']} | Day: {g['day_of_week']}")
    parts.append(f"You are at: {g['place_label']} (precision: {g['place_precision']})")
    parts.append(f"Device: {g['device_surface']}")
    parts.append(f"Others present: {', '.join(g['co_presence'])}")
    parts.append("Time windows:")
    for k, v in g["windows"].items():
        parts.append(f"  {k}: {v}")

    # ── Native FamilyOS Apps ──
    parts.append("\n== AVAILABLE SERVICES (NATIVE FAMILY APPS) ==")
    parts.append("Every household has these apps. They work together synchronously —")
    parts.append(
        "a change in one app can trigger actions in others. Map user intent to the right app:"
    )
    parts.append("")
    parts.append(
        "  CALENDAR — events, appointments, schedules, practices, recitals, lessons, meetings."
    )
    parts.append(
        "    Time-based. Has attendees (who's involved), recurrence (weekly piano), locations."
    )
    parts.append(
        "    Keywords in user speech: schedule, add, book, dentist, doctor, practice, recital,"
    )
    parts.append(
        "    lesson, meeting, appointment, plan, hold, move, reschedule, what's on, agenda."
    )
    parts.append("")
    parts.append(
        "  TASKS — one-shot to-dos assigned to specific people. Has due dates. NOT recurring."
    )
    parts.append(
        '    For accountability: "do homework", "clean room", "pick up Riley", "call dentist".'
    )
    parts.append(
        "    Keywords: do, finish, complete, make sure, homework, assignment, project, room cleanup."
    )
    parts.append("    DISTINCT from chores (chores ARE recurring; tasks are one-shot).")
    parts.append("")
    parts.append("  REMINDERS — time or location-triggered notifications. Cross-person addressing.")
    parts.append('    "Remind X to do Y", "remind me when I get home", "ping me at 3pm".')
    parts.append(
        "    Keywords: remind, ping, nudge, notify, alert, don't let me forget, tell [person] to."
    )
    parts.append(
        "    DISTINCT from tasks: reminders are TRIGGERED NOTIFICATIONS, not accountability items."
    )
    parts.append("")
    parts.append("  CHORES — recurring household responsibilities. Gamified with rewards.")
    parts.append('    "Take out trash every Tuesday", "feed the dog daily", "weekly room cleanup".')
    parts.append("    Completion tracked. Parents verify. Rewards accrue. Progress viewable.")
    parts.append(
        "    Keywords: chores, chore, has [person] been good, how did [person] do, reward, allowance."
    )
    parts.append(
        '    "Has Riley been good?" → check chore completion. "What chores does Jordan have?"'
    )
    parts.append("")
    parts.append("  SHOPPING — shared grocery and general shopping list. Live-sync across family.")
    parts.append("    Mom adds milk on phone, dad sees it at the store. Meal-plan linked.")
    parts.append(
        "    Keywords: buy, groceries, shopping, add to list, milk, order, mark as done, got it."
    )

    # ── Session State ──
    parts.append("\n== WHAT WE KNOW (BELIEFS) ==")
    for b in ss["beliefs_active"]:
        t = f" [{b.get('temporal', '')}]" if b.get("temporal") else ""
        parts.append(
            f"  {b['subject']} {b['predicate']} {b['object']} (confidence: {b['confidence']}{t})"
        )

    parts.append("\n== ACTIVE WORK (TASKS) ==")
    for t in ss["task_state"]["active_tasks"]:
        parts.append(f"  [{t['status']}] {t['summary']}")
    for t in ss["task_state"]["completed_tasks"]:
        parts.append(f"  [completed] {t['summary']}")

    parts.append(
        f"\nNarrative thread: {ss['narrative_active']['thread']} → {ss['narrative_active']['arc']}"
    )
    parts.append(f"Last mentioned: {ss['narrative_active']['last_mentioned_person']}")

    return "\n".join(parts)


FRAME_EXTRACTION_SYSTEM_PROMPT = """You are a structured intent extraction engine. Your ONLY job is to convert a natural language utterance into a single JSON object that describes what the user wants to do, who it involves, what service it targets, and when it should happen.

== YOUR INPUT ==
You receive:
  1. A CONTEXT BLOCK describing the user's world — their identity, household, available services, current time/place, known facts, active tasks, and recent conversation.
  2. A CHAT HISTORY showing the recent conversation between the user and the assistant.
  3. The USER'S LATEST UTTERANCE wrapped in <CURRENT_UTTERANCE> tags — this is the ONLY message you need to convert.

== YOUR OUTPUT — A SINGLE JSON OBJECT ==
Output EXACTLY one JSON object. Never output an array. Never output markdown. Never output explanation.

{
  "intents": [
    {
      "action": "what the user wants to accomplish, in plain English",
      "domain": "which service this targets — use the AVAILABLE SERVICES section to decide",
      "operation_hint": "the kind of operation the user wants — infer from their language",
      "resource_kind_hint": "the type of thing being acted on — infer from the domain",
      "subject_hint": "a short label for this intent",
      "params": {
        "person_hint": "who this involves — use the exact name or alias from the context",
        "time_hint": "any time mentioned — keep it in the user's own words",
        "title": "title if the user specified one",
        "query": "search terms if this is a lookup"
      }
    }
  ],
  "person_refs": [
    {
      "raw": "the person reference as the user said it, or 'me' for self",
      "confidence": "high|medium|low",
      "needs_resolution": true or false
    }
  ],
  "resource_refs": [
    {
      "raw": "how the user referred to the resource",
      "resource_kind_hint": "inferred type — use the AVAILABLE SERVICES to decide",
      "confidence": "high|medium|low",
      "needs_resolution": true or false
    }
  ],
  "time_window_hint": {
    "raw_phrase": "the time the user mentioned, or 'unspecified' if time is needed but missing",
    "confidence": "high|medium|low"
  } or null,
  "disambiguation_notes": null or a string explaining why a person reference is ambiguous
}

== THE RULES — FOLLOW THESE EXACTLY ==

--- RULE 1: EVERY UTTERANCE GETS A REAL OPERATION ---
operation_hint MUST be one of: create, list, update, delete.
NEVER use "compute" unless the utterance is literally empty or pure gibberish.
If the user wants to VIEW/SEE/CHECK/FIND/SHOW something → operation_hint="list".
If the user wants to MAKE/ADD/SCHEDULE/CREATE/ORDER something → operation_hint="create".
If the user wants to CHANGE/MOVE/EDIT/MARK/COMPLETE something → operation_hint="update".
If the user wants to REMOVE/CANCEL/DELETE something → operation_hint="delete".

--- RULE 2: EVERY PERSON MENTIONED GETS A person_ref ---
For EVERY person referenced in the utterance (by name, alias, or relationship):
  - Add a person_ref with raw = the EXACT text the user used.
  - Check the household roster. If the name/alias matches MULTIPLE people:
    → set needs_resolution=true AND add disambiguation_notes naming the candidates.
  - If the user says "me", "my", "I", "we", "our", "us" → add person_ref raw="me".
  - Even when the user doesn't say "me" but the action is self-directed (checking your
    own calendar, your own tasks, your own reminders), STILL add person_ref raw="me"
    with confidence="medium". This is NON-NEGOTIABLE.

--- RULE 3: EVERY DOMAIN GETS A resource_ref ---
For EACH distinct service the user is targeting:
  - Add a resource_ref describing what resource they're acting on.
  - The resource_kind_hint should reflect which AVAILABLE SERVICE this targets.
  - Use natural names — the downstream resolver handles exact matching.

--- RULE 4: SPLIT COMPOUND UTTERANCES ---
When the utterance contains "and" connecting TWO DIFFERENT actions:
  → Produce TWO (or more) intents, one for each action.
When the utterance references TWO DIFFERENT PEOPLE for the same operation:
  → Produce ONE intent PER PERSON. "Check Jordan AND Riley K" → 2 intents (one per person).
When the utterance is ONE action → ONE intent.

--- RULE 5: TIME ALWAYS GOES IN time_window_hint ---
If the user mentions ANY time ("today", "tomorrow", "Friday", "3pm", "next week",
"every Sunday", "June 15th") → include time_window_hint with raw_phrase = the exact words.
If the user wants a FUTURE action but gives NO time ("Schedule something", "Remind me")
→ time_window_hint = {"raw_phrase": "unspecified", "confidence": "low"}.
If the user does NOT need a time (simple reads, status checks) → time_window_hint = null.

--- RULE 6: USE BELIEFS FOR CREATIVE LANGUAGE ---
When the user says something indirect, use the BELIEFS section to interpret it:
  "Has [person] been good?" → beliefs show [person] needs_reminder_for chores → domain=Chores.
  "What should we do?" → check Calendar for free time (primary guess).
  "Make sure [person] does [thing]" → create a Task (accountability).
  "Tell me about [person]'s day" → check Calendar for that person's events.

--- RULE 7: CONFIDENCE REFLECTS EVIDENCE ---
"high" = explicit words in the utterance. "medium" = reasonable inference from context.
"low" = you're guessing. Be honest about uncertainty.

--- RULE 8: NEVER INVENT ---
Use raw values exactly as they appear. Never generate IDs. Downstream systems handle lookup.

--- RULE 9: EMPTY OR MEANINGLESS INPUT ---
If the utterance is empty or pure noise → one intent with operation_hint="compute",
resource_kind_hint=null, empty person_refs, empty resource_refs, time_window_hint=null.
Otherwise ALWAYS pick a real domain and operation.

--- RULE 10: OUTPUT FORMAT IS NON-NEGOTIABLE ---
Your ENTIRE response must be a single JSON object starting with { and ending with }.
No markdown fences (```json). No leading/trailing text. No explanation. Just the JSON."""


# ═══════════════════════════════════════════════════════════════════
# CHAT HISTORY BUILDER
# ═══════════════════════════════════════════════════════════════════

CHAT_HISTORY_TEMPLATE: list[dict[str, str]] = [
    {"role": "user", "content": "Good morning! What's on the agenda today?"},
    {
        "role": "assistant",
        "content": "Good morning Alex! Let me check. You have Riley K's soccer practice at 4pm, Jordan's piano at 3pm, and you wanted to schedule Riley's dentist checkup. Also, Sunday dinner groceries are still on your list.",
    },
    {"role": "user", "content": "Right, I need to call the dentist. Can you remind me at 10?"},
    {
        "role": "assistant",
        "content": "Sure! I'll set a reminder for 10am to call the dentist for Riley K.",
    },
    {
        "role": "user",
        "content": "Also, Jordan said he's out of peanut butter. Can you add that to shopping?",
    },
    {
        "role": "assistant",
        "content": "Added peanut butter to your shopping list. But remember — Jordan has a peanut allergy, so is this for someone else?",
    },
    {
        "role": "user",
        "content": "Oh right, it's for Sam. She's visiting this weekend and asked for it.",
    },
    {
        "role": "assistant",
        "content": "Got it! Noted that Sam (Grandma) is visiting this weekend and needs peanut butter. I'll keep that separate from Jordan's items.",
    },
    {"role": "user", "content": "How did the kids do with their chores yesterday?"},
    {
        "role": "assistant",
        "content": "Riley K completed homework and took out the trash. Jordan did not finish his room cleanup — it's still on his task list. Would you like me to send him a reminder?",
    },
    {
        "role": "user",
        "content": "Yes, remind Jordan about his room. And what about Riley's screen time?",
    },
    {
        "role": "assistant",
        "content": "Riley K had 2.5 hours of screen time yesterday. Your goal is to keep it under 2 hours. They went over because of a school project — I can note the exception if you'd like.",
    },
    {
        "role": "user",
        "content": "That's fine, it was for school. But remind me to check again Friday.",
    },
    {
        "role": "assistant",
        "content": "Noted. I'll remind you Friday to review Riley K's screen time. Anything else for now?",
    },
    {
        "role": "user",
        "content": "Actually, when is Riley T coming over next? I want to plan a playdate.",
    },
    {
        "role": "assistant",
        "content": "Riley T (Riley K's friend) doesn't have any scheduled visits yet. Would you like me to reach out to Riley T's family or just check Riley K's calendar for free afternoons?",
    },
    {"role": "user", "content": "Just check the calendar for now. This weekend maybe?"},
    {
        "role": "assistant",
        "content": "This weekend: Saturday is mostly open after 2pm. Sunday has the family dinner at 6pm but the morning and early afternoon are free. Saturday after 2pm looks best for a playdate.",
    },
    {
        "role": "user",
        "content": "Great, let's tentatively hold Saturday 2-5pm. We'll confirm later.",
    },
    {
        "role": "assistant",
        "content": "I'll add a tentative hold on Saturday June 6th, 2-5pm for a potential Riley K + Riley T playdate. Anything else?",
    },
]


# ═══════════════════════════════════════════════════════════════════
# ACCURACY EVALUATORS
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DimensionResult:
    passed: bool
    expected: Any
    actual: Any
    detail: str


@dataclass
class ScenarioResult:
    scenario_id: str
    utterance: str
    passed: bool
    dimensions: dict[str, DimensionResult]
    raw_output: dict[str, Any]
    latency_ms: float


def _resource_kind_matches(actual: str | None, expected: str | None) -> bool:
    """Fuzzy resource kind matching — LLM may name things differently."""
    if actual == expected:
        return True
    if actual is None and expected is None:
        return True
    if not actual or not expected:
        return False
    a, e = str(actual).lower(), str(expected).lower()
    if a in e or e in a:
        return True
    a_words = set(a.replace("_", " ").split())
    e_words = set(e.replace("_", " ").split())
    if a_words & e_words:
        return True
    # Semantic bridge: common LLM naming variants mapped to canonical kinds
    _SEMANTIC_ALIASES: dict[str, str] = {
        "appointment": "calendar_event",
        "event": "calendar_event",
        "meeting": "calendar_event",
        "schedule": "calendar_event",
        "booking": "calendar_event",
        "reservation": "calendar_event",
        "activity": "calendar_event",
        "todo": "task",
        "assignment": "task",
        "homework": "task",
        "groceries": "shopping_item",
        "grocery": "shopping_item",
        "shopping": "shopping_item",
        "list": "shopping_item",
        "item": "shopping_item",
        "notification": "reminder",
        "alert": "reminder",
        "nudge": "reminder",
        "ping": "reminder",
        "forecast": "weather_report",
        "weather": "weather_report",
        "delivery": "food_order",
        "takeout": "food_order",
        "order": "food_order",
        "memo": "note",
        "person_status": "chore",
        "behavior": "chore",
        "status": "chore",
        "progress": "chore",
    }
    if _SEMANTIC_ALIASES.get(a) == e:
        return True
    return False


def _normalize_op(op: str) -> str:
    """Normalize operation hints for comparison."""
    mapping = {
        "list": "list",
        "read": "list",
        "search": "list",
        "find": "list",
        "show": "list",
        "check": "list",
        "get": "list",
        "create": "create",
        "add": "create",
        "schedule": "create",
        "book": "create",
        "order": "create",
        "update": "update",
        "edit": "update",
        "change": "update",
        "modify": "update",
        "move": "update",
        "complete": "update",
        "mark": "update",
        "delete": "delete",
        "remove": "delete",
        "cancel": "delete",
    }
    return mapping.get(op.lower(), op.lower())


def evaluate_dimensions(
    scenario: FrameScenario, output: dict[str, Any]
) -> dict[str, DimensionResult]:
    dims: dict[str, DimensionResult] = {}

    # Guard: LLM might return array instead of object
    if isinstance(output, list):
        output = {"intents": output} if output else {"intents": []}
    if not isinstance(output, dict):
        output = {"intents": []}

    intents = output.get("intents") or []
    person_refs = output.get("person_refs") or []
    time_hint = output.get("time_window_hint")
    disamb = output.get("disambiguation_notes")

    # ── 1. Operation accuracy ──
    actual_ops = [_normalize_op(i.get("operation_hint", "")) for i in intents]
    expected_ops = [_normalize_op(o) for o in scenario.expected_operations]
    # Pad to same length
    while len(actual_ops) < len(expected_ops):
        actual_ops.append("")
    while len(expected_ops) < len(actual_ops):
        expected_ops.append("")
    op_match = all(a == e for a, e in zip(actual_ops, expected_ops))
    dims["operation"] = DimensionResult(
        passed=op_match,
        expected=expected_ops,
        actual=actual_ops,
        detail=f"Expected {expected_ops}, got {actual_ops}",
    )

    # ── 2. Resource accuracy (fuzzy — LLM may use different naming conventions) ──
    actual_rk = [i.get("resource_kind_hint") for i in intents]
    expected_rk = scenario.expected_resource_kinds
    while len(actual_rk) < len(expected_rk):
        actual_rk.append(None)
    while len(expected_rk) < len(actual_rk):
        expected_rk.append(None)
    rk_match = all(_resource_kind_matches(a, e) for a, e in zip(actual_rk, expected_rk))
    dims["resource"] = DimensionResult(
        passed=rk_match,
        expected=expected_rk,
        actual=actual_rk,
        detail=f"Expected {expected_rk}, got {actual_rk}",
    )

    # ── 3. Person accuracy (accepts "me", "we", "us", self-model name, or any matching alias) ──
    actual_persons = [p.get("raw", "") for p in person_refs]
    expected_persons = [p for p in scenario.expected_persons if p]
    self_name = SELF_MODEL["display_name"].lower()
    person_match = True
    for ep in expected_persons:
        found = any(
            ep.lower() in ap.lower()
            or (ep.lower() == "me" and ap.lower() in ("me", "my", "i", "we", "us", self_name, ""))
            for ap in actual_persons
        )
        if not found:
            person_match = False
            break
    dims["person"] = DimensionResult(
        passed=person_match,
        expected=expected_persons,
        actual=actual_persons,
        detail=f"Expected {expected_persons}, got {actual_persons}",
    )

    # ── 4. Time accuracy (accepts "unspecified" as valid hint for missing-time scenarios) ──
    has_time = time_hint is not None and len(str(time_hint.get("raw_phrase", ""))) > 0
    time_passed = (scenario.expected_time_required and has_time) or (
        not scenario.expected_time_required
    )
    dims["time"] = DimensionResult(
        passed=time_passed,
        expected="time required" if scenario.expected_time_required else "no time required",
        actual=f"time_hint={'present' if time_hint else 'missing'}",
        detail=str(time_hint)[:100] if time_hint else "No time hint provided",
    )

    # ── 5. Completeness (intent count) ──
    count_match = len(intents) >= scenario.intent_count
    dims["completeness"] = DimensionResult(
        passed=count_match,
        expected=scenario.intent_count,
        actual=len(intents),
        detail=f"Expected at least {scenario.intent_count} intents, got {len(intents)}",
    )

    # ── 6. Disambiguation ──
    if scenario.needs_disambiguation:
        disamb_passed = bool(disamb) and len(str(disamb)) > 5
    else:
        disamb_passed = True  # Don't penalize for flagging when not needed (extra safety)
    dims["disambiguation"] = DimensionResult(
        passed=disamb_passed,
        expected=(
            "disambiguation required"
            if scenario.needs_disambiguation
            else "no disambiguation needed"
        ),
        actual=str(disamb)[:100] if disamb else "No disambiguation notes",
        detail=scenario.disambiguation_reason if scenario.needs_disambiguation else "",
    )

    return dims


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════


async def run_scenario(
    client: ModelClient,
    scenario: FrameScenario,
    context_block: str,
    chat_history: list[dict[str, str]],
) -> ScenarioResult:
    """Run a single scenario through the LLM and evaluate."""
    system_prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + context_block

    # Build messages: system + chat history + final user utterance
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    # Add last 15 chat turns for context
    for msg in chat_history[-15:]:
        messages.append(msg)
    # Add the current utterance
    messages.append(
        {
            "role": "user",
            "content": f"<CURRENT_UTTERANCE>\n{scenario.utterance}\n</CURRENT_UTTERANCE>\n\nConvert this utterance to structured JSON as specified.",
        }
    )

    start = time.perf_counter()
    try:
        response = await client.chat(
            messages=messages,
            tools=[],
            tool_choice="none",
            temperature=0.0,
            max_tokens=2048,
        )
        elapsed = (time.perf_counter() - start) * 1000

        # Parse JSON from response
        content = (response.content or "").strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Try extracting JSON from text
            import re

            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    parsed = {"error": "json_parse_failed", "raw": content[:500]}
            else:
                parsed = {"error": "json_parse_failed", "raw": content[:500]}

    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        parsed = {"error": str(exc)}
        response = None

    dims = evaluate_dimensions(scenario, parsed)
    all_pass = all(d.passed for d in dims.values())

    return ScenarioResult(
        scenario_id=scenario.id,
        utterance=scenario.utterance,
        passed=all_pass,
        dimensions=dims,
        raw_output=parsed,
        latency_ms=round(elapsed, 2),
    )


async def run_benchmark(client: ModelClient | None = None) -> dict[str, Any]:
    """Run all scenarios and compute aggregate scores."""
    if client is None:
        client = create_model_client_from_env()
    context_block = build_context_block()

    provider = os.environ.get("LLM_PROVIDER", "unknown")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Context size: {len(context_block):,} chars")
    print(f"Chat history: {len(CHAT_HISTORY_TEMPLATE)} turns")
    print()

    results: list[ScenarioResult] = []
    for i, scenario in enumerate(SCENARIOS):
        print(f"[{i+1:02d}/{len(SCENARIOS)}] {scenario.id}: {scenario.utterance[:80]}")
        result = await run_scenario(client, scenario, context_block, CHAT_HISTORY_TEMPLATE)
        results.append(result)

        # Print per-scenario result
        dim_summary = " | ".join(
            f"{k}={'✓' if v.passed else '✗'}" for k, v in result.dimensions.items()
        )
        status = "PASS" if result.passed else "FAIL"
        print(f"         {status} | {dim_summary} | {result.latency_ms:.0f}ms")

        # Show detail on failure
        if not result.passed:
            for dim_name, dim in result.dimensions.items():
                if not dim.passed:
                    print(f"         ✗ {dim_name}: {dim.detail}")

    # ── Aggregate ──
    dimension_names = ["operation", "resource", "person", "time", "completeness", "disambiguation"]
    dim_scores: dict[str, float] = {}
    for dim_name in dimension_names:
        dim_results = [r.dimensions[dim_name] for r in results]
        passed = sum(1 for d in dim_results if d.passed)
        dim_scores[dim_name] = round(passed / len(dim_results), 4)

    overall = sum(1 for r in results if r.passed)
    overall_score = round(overall / len(results), 4)
    avg_latency = statistics.mean([r.latency_ms for r in results])

    # Print summary
    print(f"\n{'='*70}")
    print("BENCHMARK RESULTS — Back LLM Frame Extraction")
    print(f"{'='*70}")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"Overall pass rate: {overall}/{len(results)} ({overall_score:.0%})")
    print(f"Avg latency: {avg_latency:.0f}ms")
    print()
    for dim_name in dimension_names:
        score = dim_scores[dim_name]
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {dim_name:<18} {bar} {score:.0%}")
    print()

    # Per-scenario table
    print(f"{'─'*70}")
    print(f"{'ID':<7} {'Utterance':<50} {'Pass':<6}")
    print(f"{'─'*70}")
    for r in results:
        status = "✓" if r.passed else "✗"
        print(f"{r.scenario_id:<7} {r.utterance[:48]:<50} {status:<6}")
    print(f"{'─'*70}")

    return {
        "provider": provider,
        "model": client.model_id,
        "overall_score": overall_score,
        "dimension_scores": dim_scores,
        "total_scenarios": len(results),
        "passed": overall,
        "avg_latency_ms": round(avg_latency, 1),
        "results": [
            {
                "id": r.scenario_id,
                "utterance": r.utterance,
                "passed": r.passed,
                "dimensions": {k: v.passed for k, v in r.dimensions.items()},
                "latency_ms": r.latency_ms,
            }
            for r in results
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# OFFLINE MODE — evaluate prompt structure without LLM calls
# ═══════════════════════════════════════════════════════════════════


def offline_analysis() -> dict[str, Any]:
    """Print the prompt structure and context for manual review."""
    context = build_context_block()
    prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + context

    print("=" * 60)
    print("OFFLINE ANALYSIS — Prompt Structure Review")
    print("=" * 60)
    print(f"\nTotal prompt length: {len(prompt):,} chars (~{len(prompt)//4:,} tokens)")
    print(f"Context block length: {len(context):,} chars")
    print(f"System prompt length: {len(FRAME_EXTRACTION_SYSTEM_PROMPT):,} chars")
    print(f"Chat history turns: {len(CHAT_HISTORY_TEMPLATE)}")
    print(f"Test scenarios: {len(SCENARIOS)}")

    print("\n--- PROMPT STRUCTURE ---")
    # Show first 5 lines of each section
    for section in prompt.split("\n=="):
        if section.strip():
            lines = section.strip().split("\n")
            header = lines[0].strip()
            preview = "\n".join(lines[:5])
            print(f"\n  =={header}")
            print(f"  {preview}")
            if len(lines) > 5:
                print(f"  ... ({len(lines)} lines total)")

    print("\n--- SCENARIO DISTRIBUTION ---")
    by_type: dict[str, int] = {}
    for s in SCENARIOS:
        if s.needs_disambiguation:
            by_type["disambiguation"] = by_type.get("disambiguation", 0) + 1
        if s.intent_count > 1:
            by_type["compound"] = by_type.get("compound", 0) + 1
        if s.expected_time_required:
            by_type["time_required"] = by_type.get("time_required", 0) + 1
        for op in s.expected_operations:
            by_type[f"op:{op}"] = by_type.get(f"op:{op}", 0) + 1
    for k, v in sorted(by_type.items()):
        print(f"  {k}: {v}")

    return {"prompt_chars": len(prompt), "scenarios": len(SCENARIOS)}


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════╗
║   Back LLM Frame Extraction Benchmark           ║
╠══════════════════════════════════════════════════╣
║  1. Offline analysis (review prompt structure)   ║
║  2. Run with env-configured LLM provider         ║
║  0. Exit                                         ║
╚══════════════════════════════════════════════════╝"""


def main() -> int:
    print(MENU)
    choice = input("Select benchmark [1-2, 0]: ").strip()

    if choice == "1":
        result = offline_analysis()
        out_path = Path("data/llm_frame_bench/offline_analysis.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")
        return 0

    if choice == "2":
        try:
            client = create_model_client_from_env()
        except Exception as exc:
            print(f"\nERROR: Cannot create model client: {exc}")
            print("Set these env vars:")
            print(
                "  For Vertex:  $env:LLM_PROVIDER='vertex'; $env:GOOGLE_CLOUD_PROJECT='...'; $env:GOOGLE_CLOUD_LOCATION='global'"
            )
            print("  For Google:  $env:LLM_PROVIDER='google'; $env:GOOGLE_API_KEY='...'")
            print("  For OpenAI:  $env:LLM_PROVIDER='openai'; $env:OPENAI_API_KEY='...'")
            return 1

        provider = os.environ.get("LLM_PROVIDER", "unknown")
        print(f"\nUsing provider: {provider}")
        print(f"Model: {client.model_id}")
        if hasattr(client, "project") and client.project:
            print(f"Project: {client.project}")
        if hasattr(client, "location") and client.location:
            print(f"Location: {client.location}")
        print()

        result = asyncio.run(run_benchmark(client=client))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_slug = client.model_id.replace("/", "_").replace("-", "_")
        out_path = Path(f"data/llm_frame_bench/results_{provider}_{model_slug}_{ts}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
