"""CRUD + lifecycle tests for ``TasksToolService``."""

from __future__ import annotations

import pytest

from tests.k1.tools.family.tasks.conftest import make_ctx


async def test_create_task_and_emit(svc):
    service, pub, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    res = await service.dispatch("create_task", {"title": "Buy milk"}, ctx)
    assert res["success"] is True
    task_id = res["task_id"]
    assert task_id
    assert res["version"] == 1
    assert any(t.startswith("family.tasks.create_task") for t, _ in pub.published)


async def test_get_task(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Walk dog"}, ctx)
    task_id = create_res["task_id"]

    get_res = await service.dispatch("get_task", {"task_id": task_id}, make_ctx())
    assert get_res["success"] is True
    assert get_res["task"]["title"] == "Walk dog"


async def test_update_task_bumps_version(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Original"}, ctx)
    task_id = create_res["task_id"]

    upd = await service.dispatch(
        "update_task",
        {"task_id": task_id, "title": "Updated", "expected_version": 1},
        ctx,
    )
    assert upd["version"] == 2
    get_res = await service.dispatch("get_task", {"task_id": task_id}, make_ctx())
    assert get_res["task"]["title"] == "Updated"


async def test_update_task_stale_version_raises(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Stale test"}, ctx)
    task_id = create_res["task_id"]

    out = await service.dispatch(
        "update_task",
        {"task_id": task_id, "title": "Bad", "expected_version": 99},
        ctx,
    )
    assert out["success"] is False


async def test_complete_task_stamps_completed_at(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Submit form"}, ctx)
    task_id = create_res["task_id"]

    comp = await service.dispatch("complete_task", {"task_id": task_id}, ctx)
    assert comp["success"] is True
    assert comp["completed_at"]

    get_res = await service.dispatch("get_task", {"task_id": task_id}, make_ctx())
    assert get_res["task"]["status"] == "done"
    assert get_res["task"]["completed_at"]


async def test_complete_task_idempotent(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Done twice"}, ctx)
    task_id = create_res["task_id"]

    comp1 = await service.dispatch("complete_task", {"task_id": task_id}, ctx)
    comp2 = await service.dispatch("complete_task", {"task_id": task_id}, ctx)
    assert comp1["completed_at"] == comp2["completed_at"]


async def test_reopen_task_clears_completed_at(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Reopen me"}, ctx)
    task_id = create_res["task_id"]
    await service.dispatch("complete_task", {"task_id": task_id}, ctx)

    reopen = await service.dispatch("reopen_task", {"task_id": task_id}, ctx)
    assert reopen["success"] is True

    get_res = await service.dispatch("get_task", {"task_id": task_id}, make_ctx())
    assert get_res["task"]["status"] == "open"
    assert get_res["task"]["completed_at"] is None


async def test_reassign_task_self_allowed_for_child(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="child1", role="child", band="AMBER")
    create_res = await service.dispatch(
        "create_task",
        {"title": "Own task"},
        make_ctx(user_id="u1", role="parent", band="AMBER"),
    )
    task_id = create_res["task_id"]

    # child reassigns the task to themselves -- allowed
    res = await service.dispatch(
        "reassign_task",
        {"task_id": task_id, "new_assignee": "child1"},
        ctx,
    )
    assert res["assigned_to"] == "child1"


async def test_reassign_task_cross_member_blocked_for_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Delegate me"}, parent_ctx)
    task_id = create_res["task_id"]

    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")
    out = await service.dispatch(
        "reassign_task",
        {"task_id": task_id, "new_assignee": "child2"},
        child_ctx,
    )
    assert out["success"] is False


async def test_delete_task_soft_delete(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Delete me"}, ctx)
    task_id = create_res["task_id"]

    del_res = await service.dispatch("delete_task", {"task_id": task_id}, ctx)
    assert del_res["success"] is True

    # Row still exists but is soft-deleted — filter_rows excludes it
    out = await service.dispatch("get_task", {"task_id": task_id}, make_ctx())
    assert out["success"] is False


async def test_list_tasks_assigned_to_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    await service.dispatch("create_task", {"title": "T1", "assigned_to": "alice"}, ctx)
    await service.dispatch("create_task", {"title": "T2", "assigned_to": "bob"}, ctx)

    res = await service.dispatch("list_tasks", {"assigned_to": "alice"}, make_ctx())
    assert res["count"] == 1
    assert res["tasks"][0]["assigned_to"] == "alice"


async def test_list_tasks_status_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch("create_task", {"title": "Finish me"}, ctx)
    await service.dispatch("complete_task", {"task_id": create_res["task_id"]}, ctx)
    await service.dispatch("create_task", {"title": "Still open"}, ctx)

    res = await service.dispatch("list_tasks", {"status": "done"}, make_ctx())
    assert res["count"] == 1

    res_open = await service.dispatch("list_tasks", {"status": "open"}, make_ctx())
    assert res_open["count"] == 1


async def test_create_list_and_list_lists(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_list", {"name": "Weekend errands", "color": "#FF5733"}, ctx
    )
    assert create_res["success"] is True
    list_id = create_res["list_id"]

    ll = await service.dispatch("list_lists", {}, make_ctx())
    assert ll["count"] == 1
    assert ll["lists"][0]["name"] == "Weekend errands"
    assert ll["lists"][0]["id"] == list_id
