"""k1.tools.family.shopping.definition -- declarative spec for Shopping."""

from __future__ import annotations

import os

from k1.tools.family.definition import (
    ActionSpec,
    FieldSpec,
    LLMHints,
    Role,
    SSESpec,
    ToolDefinition,
)

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "tables.sql"), encoding="utf-8") as _f:
    _SHOPPING_DDL: str = _f.read()

_ALL_ROLES: list[Role] = ["guest", "child", "elder", "guardian", "parent", "system"]
_REQUEST_ROLES: list[Role] = ["child", "elder", "guardian", "parent", "system"]
_APPROVER_ROLES: list[Role] = ["guardian", "parent", "system"]

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
    description="Allow-list of family member references when visibility='named'.",
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
            description="Filter by requesting family member reference, e.g. Riley or riley.",
        ),
    ],
    can_reference=["task_item", "calendar_event", "reminder"],
    feature_flags=["m15_shopping"],
    tables_sql=_SHOPPING_DDL,
    actions=[
        ActionSpec(
            name="create_list",
            kind="write",
            summary="Create a parent-managed shopping list bucket.",
            label="New list",
            primary=True,
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
            prompt_template="shopping_activity_v1",
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
                    description=(
                        "Family member reference requesting the item, e.g. Riley or riley; "
                        "child callers are forced to themselves."
                    ),
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
            allowed_roles=_APPROVER_ROLES,
            params=[
                _ITEM_ID_FIELD,
                FieldSpec(name="name", type="string", required=False),
                FieldSpec(name="quantity", type="string", required=False),
                FieldSpec(name="unit", type="string", required=False),
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
            min_band="GREEN",
            prompt_template="shopping_activity_v1",
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
            prompt_template="shopping_activity_v1",
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
            prompt_template="shopping_activity_v1",
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
