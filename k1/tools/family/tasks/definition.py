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
            min_band="AMBER",
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
                    "task recurs weekly/daily → use chores.create_chore",
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
            min_band="AMBER",
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
            min_band="AMBER",
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
            min_band="AMBER",
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
            min_band="AMBER",
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
            min_band="AMBER",
            allowed_roles=["parent", "child", "guardian", "elder", "system"],
            params=[_TASK_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="task_id", type="string", required=True),
            ],
            llm=LLMHints(use_when=["user wants to permanently remove a task"]),
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
            llm=LLMHints(use_when=["user asks about the details of a specific task"]),
        ),
        # ------------------------------------------------------------------
        # 9. create_list
        # ------------------------------------------------------------------
        ActionSpec(
            name="create_list",
            kind="write",
            summary="Create a named task list (bucket for grouping tasks).",
            label="New list",
            min_band="AMBER",
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
            ),
        ),
    ],
)
