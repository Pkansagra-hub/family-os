"""k1.tools.family.chores.definition -- declarative spec for the Chores adapter.

Exposes :data:`CHORES_DEFINITION`, the single source of truth consumed by:

* :func:`k1.fabric.manifest_translator.register_definition` -- registers
  each :class:`ActionSpec` as a Fabric ``CapabilityContract``.
* :func:`k1.tools.family.manifest.ui_manifest` -- role-filtered UI manifest.
* :func:`k1.tools.family.manifest.llm_tool_specs` -- LLM tool specs with
  ``use_when`` / ``avoid_when`` / ``examples`` hints.
* :class:`ChoresToolService` -- consumes ``DEFINITION.tables_sql`` at
  construction time to create the SQLite projection tables.

9 actions
---------
Templates (3):
    1. ``create_template``  write  GREEN  idempotent  (parent+ only)
    2. ``update_template``  write  GREEN              (parent+ only)
    3. ``delete_template``  delete GREEN              (parent+ only)

Occurrences (6):
    4. ``assign_chore``     write  GREEN              (parent+ or guardian+)
    5. ``complete_chore``   write  GREEN              (assignee | parent+)
    6. ``skip_chore``       write  GREEN              (assignee | parent+)
    7. ``reopen_chore``     write  GREEN              (parent+ only)
  8. ``list_chores``      read   GREEN              (all roles incl. guest)
  9. ``chore_summary``    read   GREEN              (all roles incl. guest)
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
    _CHORES_DDL: str = _f.read()

# ---------------------------------------------------------------------------
# Shared field helpers
# ---------------------------------------------------------------------------

_VISIBILITY_FIELD = FieldSpec(
    name="visibility",
    type="string",
    required=False,
    description="Row-level band: ``family`` | ``adults`` | ``named`` | ``private``.",
)
_TEMPLATE_ID_FIELD = FieldSpec(
    name="template_id",
    type="string",
    required=True,
    description="``ChoreTemplate.id``.",
)
_OCCURRENCE_ID_FIELD = FieldSpec(
    name="occurrence_id",
    type="string",
    required=True,
    description="``ChoreOccurrence.id``.",
)

_ALL_ROLES = ["guest", "child", "elder", "guardian", "parent", "system"]
_WRITE_ROLES = ["child", "elder", "guardian", "parent", "system"]
_PARENT_PLUS = ["parent", "system"]
_GUARDIAN_PLUS = ["guardian", "parent", "system"]

# ---------------------------------------------------------------------------
# Phase 1.1 -- Constitution / Policy / Guide cards / Ontology (Epic 12.1-12.2)
#
# Grounded to the REAL chore model:
#   Templates (parent-only): create_template, update_template, delete_template
#   Occurrences: assign_chore (guardian+), complete_chore / skip_chore
#                (child+), reopen_chore (parent-only)
#   Reads: list_chores, chore_summary (all roles)
# Gamification is base_points auto-tallied on completion -- there is NO
# verify_chore and NO redeem_reward action.  Chores are RECURRING (templates
# carry a frequency), distinct from one-shot tasks.
# ---------------------------------------------------------------------------

_CHORES_CONSTITUTION: dict[str, Any] = {
    "connector_id": "family.chores",
    "constitution_id": "family.chores.v1",
    "schema_version": "1.0.0",
    "execution_phases": ["read", "mutate"],
    "prerequisite_reads": [
        {
            "operation": "list",
            "resource_kind": "chore",
            "reason": (
                "Check for an existing template (same title + assignee + "
                "frequency) before creating a duplicate."
            ),
            "required": True,
            "timeout_ms": 5000,
        },
        {
            "operation": "list",
            "resource_kind": "event",
            "reason": (
                "Check the assignee's calendar for the chore's recurring time "
                "window. A 'Saturdays 10am' chore may conflict with a specific "
                "Saturday event."
            ),
            "required": False,
            "timeout_ms": 3000,
        },
    ],
    "conflict_analysis_rules": [
        {
            "check": "duplicate",
            "with_resource_kinds": ["chore"],
            "description": (
                "New template must not duplicate an existing template for the "
                "same assignee with the same title and frequency."
            ),
            "resolution": (
                "Tell the user: '{assignee} already has chore {existing_title} "
                "with the same schedule.' Create anyway or update the existing "
                "template?"
            ),
        },
        {
            "check": "time_overlap",
            "with_resource_kinds": ["event"],
            "description": (
                "A chore's recurring slot conflicts with a specific calendar "
                "event. Calendar events take precedence (specific one-time "
                "commitments); chores are recurring and flexible."
            ),
            "resolution": (
                "Warn: '{assignee} has {event_title} during the chore's regular "
                "time on {dates}. The child can work around the event -- do not "
                "block.' Offer: keep chore as-is, adjust time for those dates, "
                "or cancel."
            ),
        },
        {
            "check": "workload_balance",
            "with_resource_kinds": ["chore"],
            "description": (
                "One household member has significantly more active chores than "
                "others. Fairness check -- advisory only, never blocking."
            ),
            "resolution": (
                "If one person has >=3 more chores/week than another, mention "
                "it: '{person} has {n} chores/week, {other} has {m}. Balance the "
                "workload?' The parent always decides -- do NOT block creation."
            ),
        },
    ],
    "companion_resource_roles": [
        {
            "resource_kind": "event",
            "role": "conflict_source",
            "description": (
                "Calendar events take precedence over recurring chore slots. "
                "Chores are flexible -- the child works around specific events."
            ),
        },
        {
            "resource_kind": "task",
            "role": "distinct_sibling",
            "description": (
                "CRITICAL DISTINCTION: Chores are RECURRING + GAMIFIED (a "
                "template with a frequency and base_points, e.g. 'vacuum every "
                "Saturday, earn 5 points'). Tasks are ONE-SHOT ('pick up Riley "
                "today'). If the user describes something recurring with points "
                "or allowance -- that is a CHORE (create_template), not a task. "
                "If the user says 'assign kitchen cleanup to Riley weekly', that "
                "is a chore. See the 'Chores vs Tasks' guide card."
            ),
        },
    ],
    "hil_gates": [
        {
            "trigger": "missing_required_field",
            "field": "title",
            "prompt": "What chore needs to be done?",
        },
        {
            "trigger": "missing_required_field",
            "field": "frequency",
            "prompt": "How often should this chore recur? (daily, weekly, every Saturday, etc.)",
        },
        {
            "trigger": "ambiguous_person",
            "prompt": "Which person did you mean? I found: {candidate_names}.",
        },
        {
            "trigger": "time_conflict_detected",
            "prompt": "This chore's time conflicts with: {conflict_summary}. What should I do?",
            "options": [
                "Keep chore as-is (child works around event)",
                "Adjust time for conflicting dates",
                "Cancel",
            ],
        },
    ],
    "mutation_sequencing": [
        {
            "order": 1,
            "phase": "read",
            "operation": "list",
            "description": (
                "Read current chores + calendar for the assignee's recurring " "time window."
            ),
        },
        {
            "order": 2,
            "phase": "mutate",
            "operation": "create",
            "description": (
                "Create the template if no duplicate. Warn about calendar "
                "conflicts (advisory). Check workload balance (advisory)."
            ),
        },
        {
            "order": 3,
            "phase": "read",
            "operation": "list",
            "description": "Verify template was created (read_after_write).",
        },
    ],
    "verification_requirements": [
        {
            "method": "read_after_write",
            "description": "Read back the created template and confirm all fields match.",
            "required_for_submit": True,
        },
        {
            "method": "output_schema",
            "description": "Validate the returned template matches the expected schema.",
        },
    ],
    "precondition_summary": (
        "Before creating a chore template, I MUST list existing chores to check "
        "for duplicates (same assignee + title + frequency). I SHOULD check the "
        "assignee's calendar for time-window conflicts. Calendar events take "
        "precedence over recurring chore slots. I SHOULD also check workload "
        "balance across household members (advisory only)."
    ),
    "companion_resource_summary": (
        "Calendar events take precedence over recurring chore slots. Chores are "
        "DISTINCT from tasks: chores are recurring templates with base_points "
        "gamification (auto-tallied on completion -- there is no separate verify "
        "or redeem step), tasks are one-shot action items. The chore flow is "
        "create_template -> assign_chore -> complete_chore | skip_chore. See the "
        "'Chores vs Tasks' and 'How Chore Points Work' guide cards."
    ),
    "hil_trigger_summary": (
        "I need human input when: chore title or frequency is missing, a person "
        "reference is ambiguous, or a calendar time conflict is detected."
    ),
    "degradation_policy": (
        "If read_after_write verification fails, retry once then submit degraded."
    ),
    # ── RES-017: Teaching surface fields (2026-06-17) ──────────────
    "how_to_sequence": [
        "1. Read current chores + calendar for the assignee's recurring time window.",
        "2. Create the template if no duplicate. Warn about calendar conflicts "
        "(advisory). Check workload balance across household members (advisory).",
        "3. Verify template was created (read_after_write).",
    ],
    "what_to_verify": [
        "After create/update: Read back the template and confirm all fields "
        "match the submitted values.",
        "Validate the returned template matches the expected output schema.",
    ],
    "when_to_ask_human": [
        {
            "trigger": "missing_required_field",
            "reason": "Chore title is required.",
            "prompt": "What chore needs to be done?",
        },
        {
            "trigger": "missing_required_field",
            "reason": "Chore frequency is required.",
            "prompt": "How often should this chore recur? (daily, weekly, every Saturday, etc.)",
        },
        {
            "trigger": "ambiguous_person",
            "reason": "Person reference could not be resolved to a single member.",
            "prompt": "Which person did you mean? I found: {candidate_names}.",
        },
        {
            "trigger": "time_conflict_detected",
            "reason": "This chore's recurring time conflicts with a calendar event.",
            "prompt": "This chore's time conflicts with: {conflict_summary}. What should I do?",
        },
    ],
    "companion_connectors": [
        {
            "connector_id": "family.calendar",
            "role": "conflict_source",
            "description": (
                "Calendar events take precedence over recurring chore slots. "
                "Chores are flexible — the child works around specific events."
            ),
        },
        {
            "connector_id": "family.tasks",
            "role": "distinct_sibling",
            "description": (
                "CRITICAL DISTINCTION: Chores are RECURRING + GAMIFIED (a "
                "template with a frequency and base_points, e.g. 'vacuum every "
                "Saturday, earn 5 points'). Tasks are ONE-SHOT ('pick up Riley "
                "today'). If the user describes something recurring with points "
                "or allowance — that is a CHORE, not a task."
            ),
        },
    ],
    "conflict_rules": [
        (
            "If duplicate with chores: New template must not duplicate an "
            "existing template for the same assignee with the same title and "
            "frequency. Resolution: Tell the user the chore already exists. "
            "Offer: create anyway or update existing template."
        ),
        (
            "If time_overlap with events: A chore's recurring slot conflicts "
            "with a specific calendar event. Calendar events take precedence. "
            "Resolution: Warn the user but do not block — the child can work "
            "around the event."
        ),
        (
            "If workload_balance with chores: One household member has "
            "significantly more active chores than others. Resolution: "
            "Mention the imbalance (advisory only). The parent always "
            "decides — do NOT block creation."
        ),
    ],
}

_CHORES_POLICY: dict[str, Any] = {
    "operation_role_gates": {
        # Template management is parent-only (defines the recurring chore).
        "create_template": ["parent"],
        "update_template": ["parent"],
        "delete_template": ["parent"],
        # Assigning an occurrence to a member is guardian+.
        "assign_chore": ["guardian", "parent"],
        # Completing / skipping an occurrence is open to the household (the
        # assignee marks their own chore done).
        "complete_chore": ["parent", "child", "guardian", "elder"],
        "skip_chore": ["parent", "child", "guardian", "elder"],
        # Reopening a completed/skipped occurrence is parent-only.
        "reopen_chore": ["parent"],
    },
    "operation_safety_bands": {
        "create_template": "GREEN",
        "update_template": "GREEN",
        "delete_template": "AMBER",
        "assign_chore": "GREEN",
        "complete_chore": "GREEN",
        "skip_chore": "GREEN",
        "reopen_chore": "GREEN",
    },
}

_CHORES_GUIDE_CARDS: list[dict[str, Any]] = [
    {
        "guide_id": "family.chores.guide.01",
        "title": "Chores vs Tasks -- Know the Difference",
        "content": (
            "CHORES are RECURRING + GAMIFIED (templates):\n"
            "  'Vacuum living room every Saturday -- earn 5 points'\n"
            "  'Unload dishwasher daily -- earn 3 points'\n"
            "Chores have: a recurrence frequency, base_points, and an "
            "occurrence lifecycle (assign -> complete | skip). Points are "
            "auto-tallied for the leaderboard on completion.\n\n"
            "TASKS are ONE-SHOT to-do items:\n"
            "  'Pick up Riley from school today'\n"
            "  'Buy birthday cake for Saturday's party'\n"
            "Tasks have NO recurrence and NO points.\n\n"
            "RED FLAGS that mean CHORE not task:\n"
            "- 'every [day/week/Saturday]' -> recurring = chore\n"
            "- 'earn points' or 'allowance' or 'leaderboard' -> chore\n"
            "- 'assign [child] to [recurring duty]' -> chore\n\n"
            "If ANY red flag is present, use family.chores create_template, not "
            "family.tasks."
        ),
        "relevance": "always",
        "disclosure_phase": "connector_summary",
    },
    {
        "guide_id": "family.chores.guide.02",
        "title": "How Chore Points Work",
        "content": (
            "The chore flow has three real stages:\n\n"
            "1. CREATE TEMPLATE (parent) -- Define the recurring chore with a "
            "title, frequency, optional assignee, and base_points. Example: "
            "create_template(title='Vacuum', frequency='weekly', "
            "assigned_to='riley', base_points=5).\n\n"
            "2. ASSIGN / GENERATE OCCURRENCE -- The scheduler (or assign_chore) "
            "creates a dated occurrence for a member.\n\n"
            "3. COMPLETE or SKIP (the assignee) -- complete_chore tallies the "
            "base_points to the member's leaderboard total automatically. "
            "skip_chore marks it skipped with no points. reopen_chore (parent) "
            "can undo a completion/skip.\n\n"
            "There is NO separate parent verification step and NO redeem/cash-out "
            "action -- points are display-only leaderboard tallies."
        ),
        "relevance": "always",
        "disclosure_phase": "connector_summary",
    },
    {
        "guide_id": "family.chores.guide.03",
        "title": "Fair Workload Distribution",
        "content": (
            "When assigning chores, check the balance across household members:\n"
            "- Count active chores per person.\n"
            "- If one person has >=3 more than another, mention it.\n"
            "- This is ADVISORY ONLY -- the parent always decides.\n"
            "- Do NOT block chore creation for workload balance.\n"
            "- Consider age-appropriateness: younger kids get fewer/simpler chores."
        ),
        "relevance": "on_conflict",
        "disclosure_phase": "tool_name_selection",
    },
]

_CHORES_ONTOLOGY: dict[str, Any] = {
    "domain": "family",
    "concept_aliases": [
        {"alias": "clean", "canonical_concept": "chore", "weight": 0.8},
        {"alias": "housework", "canonical_concept": "chore", "weight": 0.9},
        {"alias": "duty", "canonical_concept": "chore", "weight": 0.7},
        {"alias": "responsibility", "canonical_concept": "chore", "weight": 0.6},
        {"alias": "allowance", "canonical_concept": "chore", "weight": 0.7},
    ],
    "concept_resource_edges": [
        {"concept": "chore", "resource_family": "chore", "weight": 1.0},
    ],
    "resource_connector_edges": [
        {
            "resource_family": "chore",
            "connector_id": "family.chores",
            "weight": 1.0,
            "role": "primary",
        },
        {
            "resource_family": "event",
            "connector_id": "family.chores",
            "weight": 0.5,
            "role": "companion",
        },
    ],
    "operation_aliases": [
        {"alias": "assign", "operation_family": "assign", "effect": "write"},
        {"alias": "complete", "operation_family": "complete", "effect": "write"},
        {"alias": "finish", "operation_family": "complete", "effect": "write"},
        {"alias": "skip", "operation_family": "skip", "effect": "write"},
    ],
}

# ---------------------------------------------------------------------------
# CHORES_DEFINITION
# ---------------------------------------------------------------------------

CHORES_DEFINITION = ToolDefinition(
    adapter_id="chores",
    version="1.0.0",
    category="coordination",
    summary=(
        "Recurring family chore management with gamification points — "
        "create templates, generate occurrences, complete or skip them."
    ),
    title="Family Chores",
    icon="checklist_rtl",
    description=(
        "FamilyOS native chore tracker.  Parents define chore templates with "
        "a frequency and base points.  Occurrences are generated by the "
        "scheduler (or on-demand) and assigned to family members.  Members "
        "complete or skip occurrences; points are tallied for leaderboard "
        "display.  Distinct from Tasks (one-shot) and Reminders (time/location "
        "alerts)."
    ),
    entity_type="chore",
    views=["board", "list", "leaderboard"],
    activity_profile="chores.v1",
    domain_tags=["chores", "recurrence", "gamification", "reward_tracking"],
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
            description="Filter by status: pending | done | skipped.",
        ),
    ],
    can_reference=["task", "event", "reminder"],
    feature_flags=["m15_chores"],
    # ── Phase 1.1 enrichment (Epics 12.1-12.2) ──
    resource_kinds=["chore"],
    # ── Phase 2.6 taxonomy (Epic 23.5) ──
    domain_id="family",
    resource_families=["chore"],
    actor_scope=["parent", "admin", "system"],
    snapshot_types=["daily_snapshot", "weekly_overview"],
    constitution=_CHORES_CONSTITUTION,
    policy_declarations=_CHORES_POLICY,
    guide_cards=_CHORES_GUIDE_CARDS,
    ontology=_CHORES_ONTOLOGY,
    tables_sql=_CHORES_DDL,
    actions=[
        # ── Template management ──────────────────────────────────────────
        ActionSpec(
            name="create_template",
            kind="write",
            summary="Create a new recurring chore template.",
            min_band="GREEN",
            idempotent=True,
            allowed_roles=_PARENT_PLUS,
            params=[
                FieldSpec(
                    name="title",
                    type="string",
                    required=True,
                    description="Short name, e.g. 'Vacuum living room'.",
                ),
                FieldSpec(
                    name="description",
                    type="string",
                    required=False,
                    description="Extended instructions for the assignee.",
                ),
                FieldSpec(
                    name="assigned_to",
                    type="string",
                    required=False,
                    description="Default assignee member_id; ``null`` = pool.",
                ),
                FieldSpec(
                    name="frequency",
                    type="string",
                    required=False,
                    description=(
                        "daily | weekly | monthly | once, or a natural recurrence "
                        "phrase such as 'every 3 days'. Default: weekly."
                    ),
                ),
                FieldSpec(
                    name="base_points",
                    type="integer",
                    required=False,
                    description="Gamification points per completion. Default: 0.",
                ),
                FieldSpec(
                    name="due_at",
                    type="datetime",
                    required=False,
                    description="Optional ISO 8601 due timestamp for the first pending occurrence.",
                ),
                _VISIBILITY_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="template_id", type="string", required=True),
                FieldSpec(name="occurrence_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            sse=SSESpec(
                emits=["family.chores.create_template.write.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=[
                    "user wants to set up a recurring household chore",
                    "parent asks to add a new chore to the rota",
                    "chore needs to repeat daily, weekly, or monthly",
                ],
                avoid_when=[
                    "task is one-off — use tasks.create_task instead",
                    "user wants a time-based alert — use reminders.create_reminder",
                ],
                examples=[
                    "create_template(title='Take out trash', frequency='weekly', assigned_to='riley', base_points=5)",
                    "create_template(title='Unload dishwasher', frequency='daily', base_points=3)",
                ],
            ),
        ),
        ActionSpec(
            name="update_template",
            kind="write",
            summary="Edit a chore template (title, frequency, base_points, assigned_to).",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            params=[
                _TEMPLATE_ID_FIELD,
                FieldSpec(name="title", type="string", required=False),
                FieldSpec(name="description", type="string", required=False),
                FieldSpec(name="assigned_to", type="string", required=False),
                FieldSpec(
                    name="frequency",
                    type="string",
                    required=False,
                    description="daily | weekly | monthly | once, or a natural recurrence phrase.",
                ),
                FieldSpec(name="base_points", type="integer", required=False),
                FieldSpec(
                    name="is_active",
                    type="boolean",
                    required=False,
                    description="Set false to pause occurrence generation.",
                ),
                _VISIBILITY_FIELD,
            ],
            sse=SSESpec(
                emits=["family.chores.update_template.write.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=[
                    "parent wants to change chore frequency or point value",
                    "pause a chore temporarily with is_active=false",
                ],
                avoid_when=[
                    "user wants to mark an occurrence done — use complete_chore",
                ],
                examples=[
                    "update_template(template_id='t1', base_points=10)",
                    "update_template(template_id='t1', is_active=false)",
                ],
            ),
        ),
        ActionSpec(
            name="delete_template",
            kind="delete",
            summary="Soft-delete a chore template and all its pending occurrences.",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            params=[_TEMPLATE_ID_FIELD],
            sse=SSESpec(
                emits=["family.chores.delete_template.delete.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=["parent removes a chore from the family rota permanently"],
                avoid_when=["use update_template(is_active=false) to pause instead"],
                examples=["delete_template(template_id='t1')"],
            ),
        ),
        # ── Occurrence management ────────────────────────────────────────
        ActionSpec(
            name="assign_chore",
            kind="write",
            summary="Create or re-assign a chore occurrence to a family member.",
            min_band="GREEN",
            allowed_roles=_GUARDIAN_PLUS,
            params=[
                _TEMPLATE_ID_FIELD,
                FieldSpec(
                    name="assigned_to",
                    type="string",
                    required=True,
                    description="member_id of the assignee.",
                ),
                FieldSpec(
                    name="due_at",
                    type="datetime",
                    required=False,
                    description="ISO 8601 UTC due timestamp.",
                ),
                FieldSpec(
                    name="points_awarded",
                    type="integer",
                    required=False,
                    description="Override base_points for this occurrence.",
                ),
                _VISIBILITY_FIELD,
            ],
            sse=SSESpec(
                emits=["family.chores.assign_chore.write.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=[
                    "explicitly assign a chore occurrence to a specific member",
                    "swap chore assignment for this week",
                ],
                avoid_when=[
                    "create_template already sets a default assignee; only use this to override",
                ],
                examples=[
                    "assign_chore(template_id='t1', assigned_to='alex', due_at='2026-05-19T08:00:00Z')",
                ],
            ),
        ),
        ActionSpec(
            name="complete_chore",
            kind="write",
            summary="Mark a chore occurrence as done and award points.",
            min_band="GREEN",
            allowed_roles=_WRITE_ROLES,
            params=[
                _OCCURRENCE_ID_FIELD,
                FieldSpec(
                    name="completed_by",
                    type="string",
                    required=False,
                    description="member_id completing the chore; defaults to caller.",
                ),
                FieldSpec(
                    name="points_override",
                    type="integer",
                    required=False,
                    description="Parent may override points; child callers are ignored.",
                ),
            ],
            sse=SSESpec(
                emits=["family.chores.complete_chore.write.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=[
                    "member says they finished their chore",
                    "'I did the dishes', 'I vacuumed' — mark occurrence done",
                ],
                avoid_when=[
                    "chore is already done — operation is idempotent but noisy",
                ],
                examples=[
                    "complete_chore(occurrence_id='o1')",
                    "complete_chore(occurrence_id='o1', completed_by='riley')",
                ],
            ),
        ),
        ActionSpec(
            name="skip_chore",
            kind="write",
            summary="Mark a chore occurrence as skipped (no points awarded).",
            min_band="GREEN",
            allowed_roles=_WRITE_ROLES,
            params=[
                _OCCURRENCE_ID_FIELD,
                FieldSpec(
                    name="skip_reason",
                    type="string",
                    required=False,
                    description="Optional note explaining why it was skipped.",
                ),
            ],
            sse=SSESpec(
                emits=["family.chores.skip_chore.write.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=[
                    "member explicitly says they are skipping a chore",
                    "parent excuses a chore for this week",
                ],
                avoid_when=[
                    "use complete_chore if the chore was actually done",
                ],
                examples=[
                    "skip_chore(occurrence_id='o1', skip_reason='school trip')",
                ],
            ),
        ),
        ActionSpec(
            name="reopen_chore",
            kind="write",
            summary="Revert a done or skipped occurrence back to pending.",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            params=[
                _OCCURRENCE_ID_FIELD,
                FieldSpec(
                    name="reason",
                    type="string",
                    required=False,
                    description="Optional note for the audit log.",
                ),
            ],
            sse=SSESpec(
                emits=["family.chores.reopen_chore.write.v1"],
                redact_fields=[],
            ),
            llm=LLMHints(
                use_when=[
                    "parent wants to undo a completion (chore not actually done properly)",
                    "mistaken skip needs to be reopened",
                ],
                avoid_when=[
                    "chore is already pending — no-op",
                ],
                examples=[
                    "reopen_chore(occurrence_id='o1', reason='dishes were still dirty')",
                ],
            ),
        ),
        ActionSpec(
            name="list_chores",
            kind="read",
            summary="List chore occurrences for a space, optionally filtered by assignee, status, or due window.",
            min_band="GREEN",
            allowed_roles=_ALL_ROLES,
            params=[
                FieldSpec(
                    name="assigned_to",
                    type="string",
                    required=False,
                    description="Filter by assignee member_id.",
                ),
                FieldSpec(
                    name="status",
                    type="string",
                    required=False,
                    description="Filter by status: pending | done | skipped.",
                ),
                FieldSpec(
                    name="due_before",
                    type="datetime",
                    required=False,
                    description="Return only occurrences due before this ISO 8601 timestamp.",
                ),
                FieldSpec(
                    name="template_id",
                    type="string",
                    required=False,
                    description="Filter to occurrences of a specific template.",
                ),
            ],
            llm=LLMHints(
                use_when=[
                    "display family chore board or child's chore list",
                    "check what chores are due this week",
                    "answer 'what chores does Riley still have to do?'",
                ],
                avoid_when=[
                    "user wants one-shot tasks — use tasks.list_tasks",
                    "user wants reminders — use reminders.list_reminders",
                ],
                examples=[
                    "list_chores(assigned_to='riley', status='pending')",
                    "list_chores(due_before='2026-05-19T00:00:00Z')",
                ],
            ),
        ),
        ActionSpec(
            name="chore_summary",
            kind="read",
            summary="Return per-member points tally and completion stats for the space.",
            min_band="GREEN",
            allowed_roles=_ALL_ROLES,
            params=[
                FieldSpec(
                    name="since",
                    type="datetime",
                    required=False,
                    description="Summarise completions on or after this ISO timestamp.",
                ),
            ],
            llm=LLMHints(
                use_when=[
                    "display chore leaderboard or points totals",
                    "answer 'who has the most points this week?'",
                    "parent wants a weekly chore completion report",
                ],
                avoid_when=[
                    "user wants the raw list of occurrences — use list_chores",
                ],
                examples=[
                    "chore_summary()",
                    "chore_summary(since='2026-05-12T00:00:00Z')",
                ],
            ),
        ),
    ],
)
