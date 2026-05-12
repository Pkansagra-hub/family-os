"""ACL and role-gate tests for ``TasksToolService``."""

from __future__ import annotations

import pytest

from tests.k1.tools.family.tasks.conftest import make_ctx


async def test_private_task_hidden_from_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_task",
        {"title": "Parents only", "visibility": "private"},
        parent_ctx,
    )
    task_id = create_res["task_id"]

    child_ctx = make_ctx(user_id="child1", role="child", band="GREEN")
    out = await service.dispatch("get_task", {"task_id": task_id}, child_ctx)
    assert out["success"] is False


async def test_adults_task_hidden_from_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_task",
        {"title": "Adults errand", "visibility": "adults"},
        parent_ctx,
    )
    task_id = create_res["task_id"]

    child_ctx = make_ctx(user_id="child1", role="child", band="GREEN")
    out = await service.dispatch("get_task", {"task_id": task_id}, child_ctx)
    assert out["success"] is False


async def test_band_gate_crisis_blocks_write(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="CRISIS")
    out = await service.dispatch("create_task", {"title": "Blocked"}, ctx)
    assert out["success"] is False
    assert out["error_code"] == "band_denied"


async def test_reassign_cross_member_requires_parent(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Assign me"}, parent_ctx)
    task_id = create_res["task_id"]

    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")
    out = await service.dispatch(
        "reassign_task",
        {"task_id": task_id, "new_assignee": "child2"},
        child_ctx,
    )
    assert out["success"] is False


async def test_reopen_own_task_allowed_for_child(svc):
    service, _, _ = svc
    # Child creates and completes their own task; parent reopens on behalf
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")

    # Parent creates a task with child as actor by using child's ctx
    create_res = await service.dispatch("create_task", {"title": "My own chore"}, child_ctx)
    task_id = create_res["task_id"]
    await service.dispatch("complete_task", {"task_id": task_id}, child_ctx)

    # Child reopens own task (actor == ctx.user_id)
    reopen_res = await service.dispatch("reopen_task", {"task_id": task_id}, child_ctx)
    assert reopen_res["success"] is True


async def test_reopen_others_task_blocked_for_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")

    create_res = await service.dispatch("create_task", {"title": "Parent task"}, parent_ctx)
    task_id = create_res["task_id"]
    await service.dispatch("complete_task", {"task_id": task_id}, parent_ctx)

    out = await service.dispatch("reopen_task", {"task_id": task_id}, child_ctx)
    assert out["success"] is False


async def test_create_list_visible_to_family(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    await service.dispatch("create_list", {"name": "Shared list"}, parent_ctx)

    child_ctx = make_ctx(user_id="child1", role="child", band="GREEN")
    ll = await service.dispatch("list_lists", {}, child_ctx)
    assert ll["count"] == 1
    assert ll["lists"][0]["name"] == "Shared list"
