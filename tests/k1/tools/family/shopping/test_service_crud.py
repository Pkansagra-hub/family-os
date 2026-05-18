"""CRUD + approval tests for ShoppingToolService."""

from __future__ import annotations

from tests.k1.tools.family.shopping.conftest import make_ctx


async def _create_grocery_list(service):
    return await service.dispatch(
        "create_list",
        {"name": "Groceries", "category": "groceries"},
        make_ctx(user_id="parent1", role="parent"),
    )


async def test_create_list_and_add_parent_item(svc):
    service, pub, _ = svc
    create = await _create_grocery_list(service)
    assert create["success"] is True

    add = await service.dispatch(
        "add_item",
        {"list_id": create["list_id"], "name": "milk", "category": "groceries"},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert add["success"] is True
    assert add["approval_status"] == "approved"
    assert any(t.startswith("family.shopping.add_item") for t, _ in pub.published)


async def test_child_add_item_requires_parent_approval(svc):
    service, _, _ = svc
    create = await _create_grocery_list(service)

    add = await service.dispatch(
        "add_item",
        {"list_id": create["list_id"], "name": "new shoes", "category": "clothes"},
        make_ctx(user_id="child1", role="child"),
    )
    assert add["success"] is True
    assert add["approval_status"] == "pending_parent_approval"

    pending = await service.dispatch(
        "list_items",
        {"approval_status": "pending_parent_approval"},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert pending["count"] == 1
    assert pending["items"][0]["requested_by"] == "child1"


async def test_child_cannot_approve_or_check_off_pending_item(svc):
    service, _, _ = svc
    create = await _create_grocery_list(service)
    add = await service.dispatch(
        "add_item",
        {"list_id": create["list_id"], "name": "candy", "category": "groceries"},
        make_ctx(user_id="child1", role="child"),
    )
    item_id = add["item_id"]

    approve = await service.dispatch(
        "approve_item",
        {"item_id": item_id},
        make_ctx(user_id="child1", role="child"),
    )
    assert approve["success"] is False

    check = await service.dispatch(
        "check_off_item",
        {"item_id": item_id},
        make_ctx(user_id="child1", role="child"),
    )
    assert check["success"] is False


async def test_parent_approves_then_checks_off_child_item(svc):
    service, _, _ = svc
    create = await _create_grocery_list(service)
    add = await service.dispatch(
        "add_item",
        {"list_id": create["list_id"], "name": "school notebook", "category": "school"},
        make_ctx(user_id="child1", role="child"),
    )
    item_id = add["item_id"]

    pending_check = await service.dispatch(
        "check_off_item",
        {"item_id": item_id},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert pending_check["success"] is False

    approved = await service.dispatch(
        "approve_item",
        {"item_id": item_id},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert approved["approval_status"] == "approved"

    checked = await service.dispatch(
        "check_off_item",
        {"item_id": item_id},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert checked["success"] is True

    got = await service.dispatch("get_item", {"item_id": item_id}, make_ctx())
    assert got["item"]["status"] == "checked"


async def test_parent_rejects_child_item(svc):
    service, _, _ = svc
    create = await _create_grocery_list(service)
    add = await service.dispatch(
        "add_item",
        {"list_id": create["list_id"], "name": "expensive toy", "category": "gifts"},
        make_ctx(user_id="child1", role="child"),
    )

    rejected = await service.dispatch(
        "reject_item",
        {"item_id": add["item_id"], "rejection_reason": "not this week"},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert rejected["approval_status"] == "rejected"

    got = await service.dispatch("get_item", {"item_id": add["item_id"]}, make_ctx())
    assert got["item"]["rejection_reason"] == "not this week"


async def test_category_and_approval_filters(svc):
    service, _, _ = svc
    create = await _create_grocery_list(service)
    list_id = create["list_id"]
    await service.dispatch(
        "add_item",
        {"list_id": list_id, "name": "milk", "category": "groceries"},
        make_ctx(user_id="parent1", role="parent"),
    )
    await service.dispatch(
        "add_item",
        {"list_id": list_id, "name": "jacket", "category": "clothes"},
        make_ctx(user_id="child1", role="child"),
    )

    groceries = await service.dispatch("list_items", {"category": "groceries"}, make_ctx())
    assert groceries["count"] == 1
    assert groceries["items"][0]["name"] == "milk"

    pending = await service.dispatch(
        "list_items", {"approval_status": "pending_parent_approval"}, make_ctx()
    )
    assert pending["count"] == 1
    assert pending["items"][0]["name"] == "jacket"


async def test_delete_item_hides_row(svc):
    service, _, _ = svc
    create = await _create_grocery_list(service)
    add = await service.dispatch(
        "add_item",
        {"list_id": create["list_id"], "name": "old item"},
        make_ctx(user_id="parent1", role="parent"),
    )
    item_id = add["item_id"]

    deleted = await service.dispatch(
        "delete_item",
        {"item_id": item_id},
        make_ctx(user_id="parent1", role="parent"),
    )
    assert deleted["success"] is True

    got = await service.dispatch("get_item", {"item_id": item_id}, make_ctx())
    assert got["success"] is False
