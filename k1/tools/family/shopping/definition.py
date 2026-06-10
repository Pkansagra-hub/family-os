"""k1.tools.family.shopping.definition -- declarative spec for Shopping."""

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
    _SHOPPING_DDL: str = _f.read()

_ALL_ROLES = ["guest", "child", "elder", "guardian", "parent", "system"]
_REQUEST_ROLES = ["child", "elder", "guardian", "parent", "system"]
_APPROVER_ROLES = ["guardian", "parent", "system"]

_CATEGORY_DESCRIPTION = (
    "Shopping category: groceries | clothes | household | school | pharmacy | "
    "gifts | pets | other."
)
_CATEGORY_FIELD = FieldSpec(
    name="category",
    type="string",
    required=False,
    description=_CATEGORY_DESCRIPTION,
)
_VISIBILITY_FIELD = FieldSpec(
    name="visibility",
    type="string",
    required=False,
    description="Row-level band: family | adults | named | private.",
)
_VISIBLE_TO_FIELD = FieldSpec(
    name="visible_to",
    type="array",
    required=False,
    description="Allow-list of member_ids when visibility='named'.",
)
_LIST_ID_FIELD = FieldSpec(
    name="list_id",
    type="string",
    required=True,
    description="ShoppingList.id.",
)
_ITEM_ID_FIELD = FieldSpec(
    name="item_id",
    type="string",
    required=True,
    description="ShoppingItem.id.",
)


# ---------------------------------------------------------------------------
# Phase 1.1 -- Constitution / Policy / Guide cards / Ontology (Epic 13.1-13.2)
#
# Grounded to the REAL shopping model, which is NOT a simple shared list: it
# has a parent-approval workflow. Children request items via add_item (status
# pending_parent_approval); parents approve_item / reject_item; check_off_item
# marks an approved item bought. Lists are managed by approvers (guardian+).
# ---------------------------------------------------------------------------

_SHOPPING_CONSTITUTION: dict[str, Any] = {
    "connector_id": "family.shopping",
    "constitution_id": "family.shopping.v1",
    "schema_version": "1.0.0",
    "execution_phases": ["read", "mutate"],
    "prerequisite_reads": [
        {
            "operation": "list",
            "resource_kind": "shopping_item",
            "reason": (
                "Check for a duplicate item (same name, same active list) before "
                "adding. The user may have already added 'milk'."
            ),
            "required": True,
            "timeout_ms": 5000,
        },
    ],
    "conflict_analysis_rules": [
        {
            "check": "duplicate",
            "with_resource_kinds": ["shopping_item"],
            "description": ("New item name matches an existing active item on the list."),
            "resolution": (
                "Tell the user: '{item_name} is already on the list (added "
                "{when}, qty: {qty})'. Options: add anyway (separate entry), "
                "update the existing item, or skip. Do NOT silently duplicate."
            ),
        },
    ],
    "companion_resource_roles": [
        {
            "resource_kind": "calendar_event",
            "role": "suggestion_source",
            "description": (
                "Other connectors may SUGGEST shopping items (calendar "
                "'birthday party Saturday' -> 'order cake?'). Those suggestions "
                "flow FROM other connectors TO shopping -- shopping does not need "
                "to read calendar/tasks/chores to function."
            ),
        },
    ],
    "hil_gates": [
        {
            "trigger": "missing_required_field",
            "field": "name",
            "prompt": "What item should I add to the shopping list?",
        },
        {
            "trigger": "missing_required_field",
            "field": "list_id",
            "prompt": "Which shopping list should I add this to?",
        },
        {
            "trigger": "duplicate_detected",
            "prompt": "'{item_name}' is already on the list (qty: {existing_qty}). What should I do?",
            "options": [
                "Add anyway (separate entry)",
                "Update the existing item",
                "Skip",
            ],
        },
        {
            "trigger": "child_request_pending",
            "prompt": (
                "{child_name}'s request for '{item_name}' is pending parent "
                "approval. Approve it now?"
            ),
            "options": ["Approve", "Reject", "Leave pending"],
        },
    ],
    "mutation_sequencing": [
        {
            "order": 1,
            "phase": "read",
            "operation": "list",
            "description": "Read the active shopping list to check for duplicates.",
        },
        {
            "order": 2,
            "phase": "mutate",
            "operation": "add",
            "description": (
                "Add the item if no duplicate. Child-originated requests land as "
                "pending_parent_approval; surface that to the user."
            ),
        },
        {
            "order": 3,
            "phase": "read",
            "operation": "list",
            "description": "Verify the item was added (read_after_write).",
        },
    ],
    "verification_requirements": [
        {
            "method": "read_after_write",
            "description": (
                "Read back the list and confirm the new item appears with the "
                "correct name, quantity, and approval_status."
            ),
            "required_for_submit": True,
        },
        {
            "method": "output_schema",
            "description": "Validate the returned item matches the expected schema.",
        },
    ],
    "precondition_summary": (
        "Before adding an item, I MUST list the active shopping list to check "
        "for duplicates. Shopping has a parent-approval workflow: child requests "
        "land as pending_parent_approval and need approve_item before they count "
        "as on the list. I present duplicate conflicts rather than silently "
        "creating a second entry."
    ),
    "companion_resource_summary": (
        "Shopping is mostly self-contained, but it has a real approval workflow: "
        "add_item (child request -> pending) -> approve_item | reject_item -> "
        "check_off_item when bought. Other connectors (calendar, chores) may "
        "suggest shopping items to the user, but shopping does not coordinate "
        "back with them."
    ),
    "hil_trigger_summary": (
        "I need human input when: item name or target list is missing, a "
        "duplicate item is detected, or a child request is pending approval."
    ),
    "degradation_policy": (
        "If read_after_write verification fails, retry once then submit degraded."
    ),
}

_SHOPPING_POLICY: dict[str, Any] = {
    "operation_role_gates": {
        # List management is approver-only (guardian+).
        "create_list": ["guardian", "parent"],
        "delete_list": ["guardian", "parent"],
        # Anyone can REQUEST an item; child requests stay pending until a
        # parent/guardian approves (enforced at the service layer).
        "add_item": ["parent", "child", "guardian", "elder"],
        # Item lifecycle management is approver-only.
        "update_item": ["guardian", "parent"],
        "approve_item": ["guardian", "parent"],
        "reject_item": ["guardian", "parent"],
        "check_off_item": ["guardian", "parent"],
        "delete_item": ["guardian", "parent"],
    },
    "operation_safety_bands": {
        "create_list": "AMBER",
        "delete_list": "AMBER",
        "add_item": "AMBER",
        "update_item": "AMBER",
        "approve_item": "AMBER",
        "reject_item": "AMBER",
        "check_off_item": "AMBER",
        "delete_item": "AMBER",
    },
}

_SHOPPING_GUIDE_CARDS: list[dict[str, Any]] = [
    {
        "guide_id": "family.shopping.guide.01",
        "title": "How to Manage the Family Shopping List",
        "content": (
            "The family shopping list is shared, but child requests need parent "
            "approval before they count.\n\n"
            "Best practices:\n"
            "1. Always LIST the active list before adding -- avoid duplicates.\n"
            "2. Be specific: '2% milk - half gallon' not just 'milk'.\n"
            "3. Include quantity: 'bananas (6)', 'paper towels (2-pack)'.\n"
            "4. Child adds land as pending_parent_approval -- tell the child it "
            "needs a parent to approve.\n"
            "5. Use check_off_item when an approved item is bought.\n\n"
            "The shopping list is NOT a todo list. For 'remember to go "
            "shopping', use family.tasks. For 'buy milk every Tuesday', use "
            "family.chores (recurring) or family.reminders (notification)."
        ),
        "relevance": "always",
        "disclosure_phase": "connector_summary",
    },
    {
        "guide_id": "family.shopping.guide.02",
        "title": "The Approval Workflow",
        "content": (
            "Child-originated requests are NOT immediately on the list:\n"
            "1. add_item by a child -> approval_status = pending_parent_approval.\n"
            "2. A parent/guardian calls approve_item (now counts) or reject_item "
            "(declined, kept for audit).\n"
            "3. When the approved item is bought, call check_off_item.\n\n"
            "When a parent asks 'what are the kids asking for?', use "
            "list_items(approval_status='pending_parent_approval'). Never "
            "silently approve -- approval is an explicit parent action."
        ),
        "relevance": "on_conflict",
        "disclosure_phase": "tool_name_selection",
    },
]

_SHOPPING_ONTOLOGY: dict[str, Any] = {
    "domain": "family",
    "concept_aliases": [
        {"alias": "groceries", "canonical_concept": "shopping_item", "weight": 0.9},
        {"alias": "buy", "canonical_concept": "shopping_item", "weight": 0.8},
        {"alias": "shopping list", "canonical_concept": "shopping_item", "weight": 1.0},
        {"alias": "purchase", "canonical_concept": "shopping_item", "weight": 0.8},
        {"alias": "supplies", "canonical_concept": "shopping_item", "weight": 0.6},
    ],
    "concept_resource_edges": [
        {"concept": "shopping_item", "resource_family": "shopping_item", "weight": 1.0},
    ],
    "resource_connector_edges": [
        {
            "resource_family": "shopping_item",
            "connector_id": "family.shopping",
            "weight": 1.0,
            "role": "primary",
        },
    ],
    "operation_aliases": [
        {"alias": "add", "operation_family": "add", "effect": "write"},
        {"alias": "need", "operation_family": "add", "effect": "write"},
        {"alias": "buy", "operation_family": "check", "effect": "write"},
        {"alias": "got it", "operation_family": "check", "effect": "write"},
        {"alias": "approve", "operation_family": "approve", "effect": "write"},
    ],
}


SHOPPING_DEFINITION = ToolDefinition(
    adapter_id="shopping",
    version="1.0.0",
    category="coordination",
    summary=(
        "Family shopping lists with categorized items and parent approval for "
        "child-originated requests."
    ),
    title="Shopping",
    icon="shopping_cart",
    description=(
        "FamilyOS native shopping app. Parents manage shared lists such as "
        "Groceries, Clothes, School, Pharmacy, Gifts, Pets, Household, and Other. "
        "Children may request items, but child-originated requests remain pending "
        "until a parent or guardian explicitly approves them."
    ),
    entity_type="shopping_item",
    views=["list", "categories", "pending_approval"],
    activity_profile="shopping.v1",
    domain_tags=["shopping", "procurement", "groceries", "clothes", "approval"],
    filters=[
        _CATEGORY_FIELD,
        FieldSpec(
            name="status",
            type="string",
            required=False,
            description="Filter by status: needed | checked.",
        ),
        FieldSpec(
            name="approval_status",
            type="string",
            required=False,
            description="Filter by approval: approved | pending_parent_approval | rejected.",
        ),
        FieldSpec(
            name="requested_by",
            type="string",
            required=False,
            description="Filter by requesting member_id.",
        ),
    ],
    can_reference=["task_item", "calendar_event", "reminder"],
    feature_flags=["m15_shopping"],
    # ── Phase 1.1 enrichment (Epics 13.1-13.2) ──
    resource_kinds=["shopping_item"],
    actor_scope=["parent", "admin", "system"],
    snapshot_types=["daily_snapshot"],
    constitution=_SHOPPING_CONSTITUTION,
    policy_declarations=_SHOPPING_POLICY,
    guide_cards=_SHOPPING_GUIDE_CARDS,
    ontology=_SHOPPING_ONTOLOGY,
    tables_sql=_SHOPPING_DDL,
    actions=[
        ActionSpec(
            name="create_list",
            kind="write",
            summary="Create a parent-managed shopping list bucket.",
            label="New list",
            primary=True,
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            idempotent=True,
            params=[
                FieldSpec(name="name", type="string", required=True, description="List name."),
                _CATEGORY_FIELD,
                _VISIBILITY_FIELD,
                _VISIBLE_TO_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="list_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "parent wants to create a shared shopping list or category bucket",
                    "family needs a new grocery, clothes, school, pharmacy, gift, pet, household, or other list",
                ],
                avoid_when=[
                    "child asks to add an item -> use add_item so it can require approval",
                    "user wants a one-shot task -> use tasks.create_task",
                ],
                examples=[
                    "Create a Groceries list -> create_list(name='Groceries', category='groceries')",
                    "Make a Clothes list -> create_list(name='Clothes', category='clothes')",
                ],
            ),
            sse=SSESpec(emits=["family.shopping.create_list.write.v1"]),
        ),
        ActionSpec(
            name="delete_list",
            kind="delete",
            summary="Soft-delete a shopping list bucket.",
            label="Delete list",
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            params=[_LIST_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="list_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["parent wants to remove a shopping list bucket"],
                avoid_when=["user only wants to remove one item -> use delete_item"],
                examples=[
                    "Remove the old Clothes list -> list_lists() to find id, then delete_list(list_id)",
                ],
            ),
            sse=SSESpec(emits=["family.shopping.delete_list.delete.v1"]),
        ),
        ActionSpec(
            name="list_lists",
            kind="read",
            summary="Return shopping lists in the family space.",
            label="List shopping lists",
            min_band="GREEN",
            allowed_roles=_ALL_ROLES,
            params=[_CATEGORY_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="lists", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "planner needs a list_id before adding a shopping item",
                    "user asks what shopping lists exist",
                ],
                examples=[
                    "Find the Groceries list id -> list_lists(category='groceries')",
                    "Check for duplicate list before creating -> list_lists()",
                ],
            ),
        ),
        ActionSpec(
            name="add_item",
            kind="write",
            summary="Add an item to a shopping list; child requests require parent approval.",
            label="Add item",
            primary=True,
            min_band="AMBER",
            allowed_roles=_REQUEST_ROLES,
            idempotent=True,
            params=[
                _LIST_ID_FIELD,
                FieldSpec(name="name", type="string", required=True, description="Item name."),
                FieldSpec(
                    name="quantity",
                    type="string",
                    required=False,
                    description="Flexible quantity text, e.g. 2, one pack, or 3T.",
                ),
                FieldSpec(name="unit", type="string", required=False),
                _CATEGORY_FIELD,
                FieldSpec(
                    name="requested_by",
                    type="string",
                    required=False,
                    description="member_id requesting the item; child callers are forced to themselves.",
                ),
                FieldSpec(name="notes", type="string", required=False),
                FieldSpec(
                    name="priority",
                    type="string",
                    required=False,
                    description="low | medium | high.",
                ),
                _VISIBILITY_FIELD,
                _VISIBLE_TO_FIELD,
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
                FieldSpec(name="approval_status", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants to add groceries, clothes, school supplies, medicine, gifts, pet supplies, or household goods",
                    "child asks for something to be bought and parent approval is required",
                ],
                avoid_when=[
                    "user wants a task assignment -> use tasks.create_task",
                    "user wants a reminder alert -> use reminders.create_reminder",
                ],
                examples=[
                    "Add milk to groceries -> add_item(list_id, name='milk', category='groceries')",
                    "Child asks for new shoes -> add_item(list_id, name='new shoes', category='clothes') returns pending_parent_approval",
                ],
            ),
            sse=SSESpec(emits=["family.shopping.add_item.write.v1"]),
        ),
        ActionSpec(
            name="update_item",
            kind="write",
            summary="Patch an existing shopping item.",
            label="Edit item",
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            params=[
                _ITEM_ID_FIELD,
                FieldSpec(name="name", type="string", required=False),
                FieldSpec(name="quantity", type="string", required=False),
                FieldSpec(name="unit", type="string", required=False),
                FieldSpec(name="list_id", type="string", required=False),
                _CATEGORY_FIELD,
                FieldSpec(name="notes", type="string", required=False),
                FieldSpec(name="priority", type="string", required=False),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item_id", type="string", required=True),
                FieldSpec(name="version", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=["parent wants to correct item details before purchase"],
                avoid_when=["user wants to approve a pending child request -> use approve_item"],
                examples=[
                    "Change milk quantity to 2 gallons -> get_item(item_id), then update_item(item_id, quantity='2', unit='gallons')",
                ],
            ),
            sse=SSESpec(emits=["family.shopping.update_item.write.v1"]),
        ),
        ActionSpec(
            name="approve_item",
            kind="write",
            summary="Approve a pending child shopping request.",
            label="Approve item",
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            params=[
                _ITEM_ID_FIELD,
                FieldSpec(name="approval_note", type="string", required=False),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item_id", type="string", required=True),
                FieldSpec(name="approval_status", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["parent explicitly approves a child shopping request"],
                avoid_when=["no explicit approval was given"],
                examples=[
                    "Approve Riley's shoe request -> get_item(item_id), then approve_item(item_id)",
                ],
            ),
            sse=SSESpec(emits=["family.shopping.approve_item.write.v1"]),
        ),
        ActionSpec(
            name="reject_item",
            kind="write",
            summary="Reject a pending child shopping request.",
            label="Reject item",
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            params=[
                _ITEM_ID_FIELD,
                FieldSpec(name="rejection_reason", type="string", required=False),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item_id", type="string", required=True),
                FieldSpec(name="approval_status", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["parent explicitly rejects a child shopping request"],
                avoid_when=["parent wants to buy the item -> use approve_item"],
                examples=[
                    "Reject the candy request -> reject_item(item_id, rejection_reason='not today')"
                ],
            ),
            sse=SSESpec(emits=["family.shopping.reject_item.write.v1"]),
        ),
        ActionSpec(
            name="check_off_item",
            kind="write",
            summary="Mark an approved shopping item as bought or done.",
            label="Check off",
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            params=[
                _ITEM_ID_FIELD,
                FieldSpec(name="checked_by", type="string", required=False),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item_id", type="string", required=True),
                FieldSpec(name="checked_at", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["parent says an approved shopping item was bought or checked off"],
                avoid_when=["item is still pending parent approval"],
                examples=["Bought the milk -> get_item(item_id), then check_off_item(item_id)"],
            ),
            sse=SSESpec(emits=["family.shopping.check_off_item.write.v1"]),
        ),
        ActionSpec(
            name="delete_item",
            kind="delete",
            summary="Soft-delete a shopping item.",
            label="Delete item",
            min_band="AMBER",
            allowed_roles=_APPROVER_ROLES,
            params=[_ITEM_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item_id", type="string", required=True),
            ],
            llm=LLMHints(
                use_when=["parent wants to remove an item from the shopping list"],
                avoid_when=[
                    "parent wants to reject a child request but keep audit context -> use reject_item"
                ],
                examples=[
                    "Remove the duplicate milk item -> get_item(item_id), then delete_item(item_id)"
                ],
            ),
            sse=SSESpec(emits=["family.shopping.delete_item.delete.v1"]),
        ),
        ActionSpec(
            name="list_items",
            kind="read",
            summary="Return shopping items, optionally filtered by list, category, status, requestor, or approval.",
            label="List items",
            min_band="GREEN",
            allowed_roles=_ALL_ROLES,
            params=[
                FieldSpec(name="list_id", type="string", required=False),
                _CATEGORY_FIELD,
                FieldSpec(
                    name="status",
                    type="string",
                    required=False,
                    description="needed | checked.",
                ),
                FieldSpec(name="requested_by", type="string", required=False),
                FieldSpec(
                    name="approval_status",
                    type="string",
                    required=False,
                    description="approved | pending_parent_approval | rejected.",
                ),
            ],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="items", type="array", required=True),
                FieldSpec(name="count", type="integer", required=True),
            ],
            llm=LLMHints(
                use_when=[
                    "user asks what is on a shopping list",
                    "parent reviews pending child shopping requests",
                    "planner checks for duplicate shopping items before adding",
                ],
                examples=[
                    "Show pending child requests -> list_items(approval_status='pending_parent_approval')",
                    "What groceries are still needed? -> list_items(category='groceries', status='needed')",
                ],
            ),
        ),
        ActionSpec(
            name="get_item",
            kind="read",
            summary="Fetch one shopping item by id.",
            label="Get item",
            min_band="GREEN",
            allowed_roles=_ALL_ROLES,
            params=[_ITEM_ID_FIELD],
            result=[
                FieldSpec(name="success", type="boolean", required=True),
                FieldSpec(name="item", type="object", required=True),
            ],
            llm=LLMHints(
                use_when=["user asks about a specific shopping item or approval request"],
                examples=[
                    "Read current approval state before approving -> get_item(item_id)",
                    "Verify the item was checked off -> get_item(item_id) after write",
                ],
            ),
        ),
    ],
)
