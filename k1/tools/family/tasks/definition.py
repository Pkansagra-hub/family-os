"""k1.tools.family.tasks.definition -- declarative spec for the Tasks adapter.

Exposes :data:`TASKS_DEFINITION`, the single source of truth consumed by:

* :func:`k1.fabric.manifest_translator.register_definition` -- registers
  each :class:`ActionSpec` as a Fabric ``CapabilityContract``.
* :func:`k1.tools.family.manifest.ui_manifest` -- role-filtered UI manifest
  rendered by the web shell.
* :func:`k1.tools.family.manifest.llm_tool_specs` -- ``tasks.<action>`` /
  ``tool.<kind>.tasks.<action>`` capability names the Concierge LLM uses.
* :class:`TasksToolService` -- consumes ``DEFINITION.tables_sql`` to bring
  up its SQLite projection tables at construction time.

10 actions, 3 read-only (GREEN band) and 7 writes/deletes (AMBER band).
The cross-member reassignment guard (caller ≠ assignee → parent gate) is a
runtime check inside the handler, not a declarative ``min_role``, matching
the pattern established by ``respond_to_invite`` in the Calendar adapter.
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
# DDL
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "tables.sql"), encoding="utf-8") as _f:
    _TASKS_DDL: str = _f.read()


# ---------------------------------------------------------------------------
# Shared field helpers
# ---------------------------------------------------------------------------

_VISIBILITY_FIELD = FieldSpec(
    name="visibility",
    type="string",
    required=False,
    description="Row-level band: ``family`` | ``adults`` | ``named`` | ``private``.",
)
_VISIBLE_TO_FIELD = FieldSpec(
    name="visible_to",
    type="array",
    required=False,
    description="Allow-list of ``member_id`` strings when ``visibility='named'``.",
)
_TASK_ID_FIELD = FieldSpec(
    name="task_id", type="string", required=True, description="``TaskItem.id``."
)

# ---------------------------------------------------------------------------
# Phase 1.1 -- Constitution / Policy / Guide cards / Ontology (Epic 10.1-10.2)
#
# Projected into GlobalProjectionStore by ``register_definition_to_store``.
# Tasks are ONE-SHOT to-do items; the constitution + guide cards teach the
# resolver/LLM the distinction from recurring gamified CHORES.
# ---------------------------------------------------------------------------

_TASKS_CONSTITUTION: dict[str, Any] = {
    "connector_id": "family.tasks",
    "constitution_id": "family.tasks.v1",
    "schema_version": "1.0.0",
    "execution_phases": ["read", "mutate"],
    "prerequisite_reads": [
        {
            "operation": "list",
            "resource_kind": "task",
            "reason": "Check for duplicate tasks (same title + same assignee) before creating.",
            "required": True,
            "timeout_ms": 5000,
        },
        {
            "operation": "list",
            "resource_kind": "calendar_event",
            "reason": (
                "Check for scheduling conflicts -- a task due Friday may " "conflict with an event."
            ),
            "required": False,
            "timeout_ms": 3000,
        },
    ],
    "conflict_analysis_rules": [
        {
            "check": "duplicate",
            "with_resource_kinds": ["task"],
            "description": (
                "New task title must not match an existing open task for the " "same assignee."
            ),
            "resolution": (
                "Tell the user: '{assignee} already has an open task "
                "{existing_title}'. Create anyway or update the existing task?"
            ),
        },
        {
            "check": "due_date_vs_calendar",
            "with_resource_kinds": ["calendar_event"],
            "description": "A task due at a specific time may conflict with a calendar event.",
            "resolution": (
                "Warn the user if the task's due window overlaps a calendar "
                "event for the same assignee. Do not block -- tasks are flexible."
            ),
        },
    ],
    "companion_resource_roles": [
        {
            "resource_kind": "calendar_event",
            "role": "dependency",
            "description": (
                "Calendar events can auto-create tasks ('Riley has soccer at "
                "5pm -- create pack cleats task due 4:30pm')."
            ),
        },
        {
            "resource_kind": "chore",
            "role": "distinct_sibling",
            "description": (
                "CRITICAL DISTINCTION: Tasks are ONE-SHOT ('pick up Riley "
                "today'). Chores are RECURRING + GAMIFIED ('vacuum living room "
                "every Saturday, earn $2'). If the user describes something "
                "recurring with rewards, points, or allowance -- that is a "
                "CHORE, not a task. Use family.chores, not family.tasks. If the "
                "user says 'assign kitchen cleanup to Riley weekly', that is a "
                "chore. If the user says 'remind Riley to do homework tonight', "
                "that is a task."
            ),
        },
    ],
    "hil_gates": [
        {
            "trigger": "missing_required_field",
            "field": "title",
            "prompt": "What should the task be called?",
        },
        {
            "trigger": "missing_required_field",
            "field": "assignee",
            "prompt": "Who should this task be assigned to?",
        },
        {
            "trigger": "ambiguous_person",
            "prompt": "Which person did you mean? I found: {candidate_names}.",
        },
        {
            "trigger": "duplicate_detected",
            "prompt": (
                "{assignee} already has '{existing_title}'. Create anyway or "
                "update the existing one?"
            ),
            "options": ["Create anyway", "Update existing", "Cancel"],
        },
    ],
    "mutation_sequencing": [
        {
            "order": 1,
            "phase": "read",
            "operation": "list",
            "description": "Read current task list + calendar for the assignee.",
        },
        {
            "order": 2,
            "phase": "mutate",
            "operation": "create",
            "description": (
                "Create the task if no duplicate detected. Warn about calendar " "conflicts if any."
            ),
        },
        {
            "order": 3,
            "phase": "read",
            "operation": "list",
            "description": "Verify task was created (read_after_write).",
        },
    ],
    "verification_requirements": [
        {
            "method": "read_after_write",
            "description": "Read back the created task and confirm all fields match.",
            "required_for_submit": True,
        },
        {
            "method": "output_schema",
            "description": "Validate the returned task matches the expected schema.",
        },
    ],
    "precondition_summary": (
        "Before creating a task, I MUST list existing tasks to check for "
        "duplicates (same title + same assignee). I SHOULD check the assignee's "
        "calendar for scheduling awareness. Tasks are flexible -- I warn about "
        "conflicts but don't block."
    ),
    "companion_resource_summary": (
        "Tasks can be auto-created from calendar events. Tasks are DISTINCT from "
        "chores: tasks are one-shot, chores are recurring with reward tracking. "
        "See the 'Tasks vs Chores' guide card for the full distinction rules."
    ),
    "hil_trigger_summary": (
        "I need human input when: task title or assignee is missing, the person "
        "reference is ambiguous, or a duplicate task is detected."
    ),
    "degradation_policy": (
        "If read_after_write verification fails, retry once then submit degraded."
    ),
}

_TASKS_POLICY: dict[str, Any] = {
    "operation_role_gates": {
        "create_task": ["parent", "child", "guardian"],
        "update_task": ["parent", "guardian"],
        "complete_task": ["parent", "child", "guardian"],
        # reopen_task: gates a completed task back to open -- parent/guardian
        # only (the design's policy table omitted it; the action exists).
        "reopen_task": ["parent", "guardian"],
        "reassign_task": ["parent", "guardian"],
        "delete_task": ["parent", "guardian"],
    },
    "operation_safety_bands": {
        "create_task": "GREEN",
        "reassign_task": "AMBER",
        "delete_task": "AMBER",
    },
}

_TASKS_GUIDE_CARDS: list[dict[str, Any]] = [
    {
        "guide_id": "family.tasks.guide.01",
        "title": "Tasks vs Chores -- Know the Difference",
        "content": (
            "TASKS are ONE-SHOT to-do items:\n"
            "  'Pick up Riley from school today'\n"
            "  'Remind Riley to do homework tonight'\n"
            "  'Buy birthday cake for Saturday's party'\n"
            "Tasks have NO rewards, NO recurrence, NO parent verification gate. "
            "When done, just mark complete_task().\n\n"
            "CHORES are RECURRING + GAMIFIED:\n"
            "  'Vacuum living room every Saturday -- earn $2'\n"
            "  'Clean kitchen nightly -- earn $1.50'\n"
            "Chores have rewards, allowance tracking, parent verify_chore() gate, "
            "and redemption via redeem_reward().\n\n"
            "RED FLAGS that mean CHORE not task:\n"
            "- 'every [day/week/Saturday]' -> recurring = chore\n"
            "- 'earn [$amount]' or 'points' or 'allowance' -> reward = chore\n"
            "- 'assign [child] to [recurring duty]' -> chore\n"
            "- Parent needs to 'verify' or 'approve' -> chore\n\n"
            "If ANY red flag is present, use family.chores tools, not family.tasks."
        ),
        "relevance": "always",
        "disclosure_phase": "connector_summary",
    },
    {
        "guide_id": "family.tasks.guide.02",
        "title": "Creating Tasks from Calendar Events",
        "content": (
            "Calendar events often imply tasks:\n"
            "- 'Riley has soccer at 5pm' -> create 'pack cleats' task due 4:30pm\n"
            "- 'Family dinner Saturday' -> create 'buy groceries' task due Friday\n"
            "- 'Doctor appointment Tuesday' -> create 'fill prescription' task\n\n"
            "When you see a calendar event, check if it implies a task and "
            "suggest it to the user. Do NOT auto-create without asking."
        ),
        "relevance": "on_conflict",
        "disclosure_phase": "tool_name_selection",
    },
]

_TASKS_ONTOLOGY: dict[str, Any] = {
    "domain": "family",
    "concept_aliases": [
        {"alias": "todo", "canonical_concept": "task", "weight": 1.0},
        {"alias": "homework", "canonical_concept": "task", "weight": 0.9},
        {"alias": "errand", "canonical_concept": "task", "weight": 0.8},
        {"alias": "remind me to", "canonical_concept": "task", "weight": 0.7},
    ],
    "concept_resource_edges": [
        {"concept": "task", "resource_family": "task", "weight": 1.0},
    ],
    "resource_connector_edges": [
        {
            "resource_family": "task",
            "connector_id": "family.tasks",
            "weight": 1.0,
            "role": "primary",
        },
        {
            "resource_family": "calendar_event",
            "connector_id": "family.tasks",
            "weight": 0.5,
            "role": "companion",
        },
        {
            "resource_family": "chore",
            "connector_id": "family.tasks",
            "weight": 0.5,
            "role": "companion",
        },
    ],
    "operation_aliases": [
        {"alias": "assign", "operation_family": "create", "effect": "write"},
        {"alias": "complete", "operation_family": "complete", "effect": "write"},
        {"alias": "finish", "operation_family": "complete", "effect": "write"},
        {"alias": "add", "operation_family": "create", "effect": "write"},
    ],
}


# ---------------------------------------------------------------------------
# TASKS_DEFINITION
# ---------------------------------------------------------------------------

TASKS_DEFINITION = ToolDefinition(
    adapter_id="tasks",
    version="1.0.0",
    category="coordination",
    summary=(
        "Family to-do list with assignment, deadlines, priorities, and "
        "cross-person delegation — one-shot tasks, not recurring chores."
    ),
    title="Family Tasks",
    icon="checklist",
    description=(
        "FamilyOS native task tracker.  Each task has an optional assignee, "
        "a deadline, a priority, and a four-state lifecycle.  The LLM can "
        "create, assign, and complete tasks in response to calendar events, "
        "voice commands, or chat.  Every write fans out via SSE so all "
        "household devices stay in sync."
    ),
    entity_type="task_item",
    views=["list", "board", "calendar"],
    activity_profile="tasks.v1",
    domain_tags=["task_management", "delegation", "deadline"],
    filters=[
        FieldSpec(
            name="assigned_to",
            type="string",
            required=False,
            description="Filter by assignee ``member_id``.",
        ),
        FieldSpec(
            name="status",
            type="string",
            required=False,
            description="Filter by status: open | in_progress | done | cancelled.",
        ),
        FieldSpec(
            name="priority",
            type="string",
            required=False,
            description="Filter by priority: low | medium | high.",
        ),
    ],
    can_reference=["calendar_event", "reminder", "shopping_item"],
    feature_flags=["m15_tasks"],
    # ── Phase 1.1 enrichment (Epics 10.1-10.2) ──
    resource_kinds=["task"],
    actor_scope=["parent", "admin", "system"],
    snapshot_types=["daily_snapshot", "weekly_overview"],
    back_execution_profile=True,
    constitution=_TASKS_CONSTITUTION,
    policy_declarations=_TASKS_POLICY,
    guide_cards=_TASKS_GUIDE_CARDS,
    ontology=_TASKS_ONTOLOGY,
    tables_sql=_TASKS_DDL,
    actions=[
        # ------------------------------------------------------------------
        # 1. create_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="create_task",
            kind="write",
            summary="Create a new one-shot family task.",
            label="New task",
            primary=True,
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            idempotent=True,
            params=[
                FieldSpec(
                    name="title",
                    type="string",
                    required=True,
                    description="Short task description.",
                ),
                FieldSpec(
                    name="assigned_to",
                    type="string",
                    required=False,
                    description="``member_id`` of assignee; omit for unassigned.",
                ),
                FieldSpec(
                    name="due_at",
                    type="datetime",
                    required=False,
                    description="ISO 8601 deadline (not a start+end range).",
                ),
                FieldSpec(
                    name="list_id",
                    type="string",
                    required=False,
                    description="Optional ``TaskList.id`` to group the task.",
                ),
                FieldSpec(
                    name="priority",
                    type="string",
                    required=False,
                    description="low | medium | high (default medium).",
                ),
                FieldSpec(
                    name="linked_event_id",
                    type="string",
                    required=False,
                    description="Cross-tool back-link to a ``calendar_events.id``.",
                ),
                _VISIBILITY_FIELD,
                _VISIBLE_TO_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants a one-off to-do item with or without a deadline",
                    "user says 'X needs to do Y' — person-addressed work item",
                    "LLM wants to delegate an action item created from a calendar event",
                    "user wants to track something that needs to happen once (not recurring)",
                ],
                avoid_when=[
                    "task recurs weekly/daily → use chores.create_template",
                    "an alert must fire at a specific time → use reminders.create_reminder",
                    "user wants to block time with start+end → use calendar.create_event",
                    "user wants to track something to buy → use shopping.add_item",
                ],
                examples=[
                    "Who's picking up Riley today? → create_task(title='Pick up Riley', assigned_to=closest_parent, due_at=today@3pm)",
                    "Dad, submit the permission slip by Friday → create_task(title='Submit permission slip', assigned_to=dad, due_at=friday)",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.create_task.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 2. update_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="update_task",
            kind="write",
            summary="Patch fields of an existing task (title, due_at, priority, list_id, etc.).",
            label="Edit task",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                _TASK_ID_FIELD,
                FieldSpec(
                    name="expected_version",
                    type="integer",
                    required=False,
                    description="Optimistic-concurrency token; reject on mismatch.",
                ),
                FieldSpec(name="title", type="string", required=False),
                FieldSpec(name="due_at", type="datetime", required=False),
                FieldSpec(name="priority", type="string", required=False),
                FieldSpec(
                    name="status",
                    type="string",
                    required=False,
                    description="Lifecycle state: open | in_progress | done | cancelled.",
                ),
                FieldSpec(name="list_id", type="string", required=False),
                FieldSpec(name="linked_event_id", type="string", required=False),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants to change the title, deadline, or priority of an existing task"
                ],
                examples=[
                    "Move the permission slip deadline to Friday -> get_task(task_id) first, then update_task(task_id, due_at=friday)",
                    "Make pickup Riley high priority -> update_task(task_id, priority='high')",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.update_task.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 3. complete_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="complete_task",
            kind="write",
            summary="Mark a task done and stamp completed_at.",
            label="Mark done",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[_TASK_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
                FieldSpec(name="completed_at", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user says a task is done, finished, or completed",
                    "user marks their own or another member's task as complete",
                ],
                examples=[
                    "Riley finished the permission slip task -> complete_task(task_id)",
                    "Mark grocery pickup done -> get_task(task_id) first, then complete_task(task_id)",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.complete_task.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 4. reopen_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="reopen_task",
            kind="write",
            summary="Reopen a completed or cancelled task (reset to open).",
            label="Reopen task",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[_TASK_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user made a mistake marking a task done and wants to undo it",
                    "a previously cancelled task needs to be revived",
                ],
                avoid_when=["task is already open"],
                examples=[
                    "Undo marking pickup as done -> reopen_task(task_id)",
                    "Revive the cancelled weekend errands task -> reopen_task(task_id)",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.reopen_task.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 5. reassign_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="reassign_task",
            kind="write",
            summary="Change the assignee of a task (cross-member requires parent role).",
            label="Reassign",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[
                _TASK_ID_FIELD,
                FieldSpec(
                    name="new_assignee",
                    type="string",
                    required=True,
                    description="``member_id`` of the new assignee.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
                FieldSpec(name="assigned_to", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants to hand a task to a different family member",
                    "parent delegates a task originally created for themselves",
                ],
                avoid_when=["new_assignee is the same as the current assignee"],
                examples=[
                    "Give pickup duty to dad -> get_task(task_id) first, then reassign_task(task_id, new_assignee=dad_id)",
                    "Move Riley's homework check to mom -> reassign_task(task_id, new_assignee=mom_id)",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.reassign_task.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 6. delete_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="delete_task",
            kind="delete",
            summary="Soft-delete a task.",
            label="Delete task",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[_TASK_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to permanently remove a task"],
                examples=[
                    "Delete the duplicate pickup task -> get_task(task_id) to confirm, then delete_task(task_id)",
                    "Remove the old permission slip task -> list_tasks(...) to find id, then delete_task(task_id)",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.delete_task.delete.v1"]),
        ),
        # ------------------------------------------------------------------
        # 7. list_tasks
        # ------------------------------------------------------------------
        ActionSpec(
            name="list_tasks",
            kind="read",
            summary="Return tasks in the family space, ACL-filtered for the caller.",
            label="List tasks",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[
                FieldSpec(
                    name="assigned_to",
                    type="string",
                    required=False,
                    description="Filter to a specific assignee ``member_id``.",
                ),
                FieldSpec(
                    name="status",
                    type="string",
                    required=False,
                    description="Filter by status: open | in_progress | done | cancelled.",
                ),
                FieldSpec(
                    name="due_before",
                    type="datetime",
                    required=False,
                    description="Return only tasks whose ``due_at`` ≤ this value.",
                ),
                FieldSpec(
                    name="list_id",
                    type="string",
                    required=False,
                    description="Return only tasks belonging to this ``TaskList.id``.",
                ),
                FieldSpec(
                    name="priority",
                    type="string",
                    required=False,
                    description="Filter by priority: low | medium | high.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="tasks", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "planner needs to see open tasks before creating a duplicate",
                    "user asks what tasks are assigned to a specific person",
                    "user asks what tasks are due soon",
                ],
                examples=[
                    "What tasks does Riley have today? -> list_tasks(assigned_to=riley_id, due_before=end_of_day)",
                    "Check for duplicate before creating -> list_tasks(assigned_to=member_id, status='open')",
                    "Show high priority open tasks -> list_tasks(status='open', priority='high')",
                ],
            ),
        ),
        # ------------------------------------------------------------------
        # 8. get_task
        # ------------------------------------------------------------------
        ActionSpec(
            name="get_task",
            kind="read",
            summary="Fetch a single task by id (ACL-filtered).",
            label="Get task",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[_TASK_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task", type="object", required=True),
            ],
            llm=LLMHints(
                use_when=["user asks about the details of a specific task"],
                examples=[
                    "Read current state before mutating -> get_task(task_id)",
                    "Verify reassignment landed -> get_task(task_id) after write",
                ],
            ),
        ),
        # ------------------------------------------------------------------
        # 9. create_list
        # ------------------------------------------------------------------
        ActionSpec(
            name="create_list",
            kind="write",
            summary="Create a named task list (bucket for grouping tasks).",
            label="New list",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            idempotent=True,
            params=[
                FieldSpec(
                    name="name",
                    type="string",
                    required=True,
                    description="List name, e.g. 'Household', 'Weekend errands'.",
                ),
                FieldSpec(
                    name="color",
                    type="string",
                    required=False,
                    description="Optional hex color for UI chip.",
                ),
                _VISIBILITY_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="list_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["user wants to group tasks under a named category"],
                examples=[
                    "Create a Weekend errands list -> list_lists() first, then create_list(name='Weekend errands')",
                    "Make a School list for assignments -> create_list(name='School')",
                ],
            ),
            sse=SSESpec(emits=["family.tasks.create_list.write.v1"]),
        ),
        # ------------------------------------------------------------------
        # 10. list_lists
        # ------------------------------------------------------------------
        ActionSpec(
            name="list_lists",
            kind="read",
            summary="Return all task lists in the family space (ACL-filtered).",
            label="List task lists",
            min_band="GREEN",
            allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
            params=[],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="lists", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=["planner needs a list_id before creating a task in a named list"],
                examples=[
                    "Find the Household list id -> list_lists()",
                    "Check for duplicate list before creating -> list_lists()",
                ],
            ),
        ),
    ],
)
