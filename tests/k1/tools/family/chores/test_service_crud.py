"""CRUD + lifecycle tests for ChoresToolService."""

from __future__ import annotations

from tests.k1.tools.family.chores.conftest import make_ctx

# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------


async def test_create_template_and_emit(svc):
    service, pub, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    res = await service.dispatch(
        "create_template",
        {"title": "Vacuum living room", "frequency": "weekly", "base_points": 5},
        ctx,
    )
    assert res["success"] is True
    assert res["template_id"]
    assert res["occurrence_id"]
    assert res["version"] == 1
    assert any(t.startswith("family.chores.create_template") for t, _ in pub.published)

    listed = await service.dispatch("list_chores", {}, ctx)
    assert listed["count"] == 1
    assert listed["chores"][0]["template_id"] == res["template_id"]
    assert listed["chores"][0]["id"] == res["occurrence_id"]
    assert listed["chores"][0]["title"] == "Vacuum living room"
    assert listed["chores"][0]["status"] == "pending"


async def test_create_template_accepts_natural_frequency(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    res = await service.dispatch(
        "create_template",
        {"title": "Water plants", "frequency": "every 3 days", "assigned_to": "riley"},
        ctx,
    )
    assert res["success"] is True
    template = service._select_template(res["template_id"], ctx.space_id)
    assert template is not None
    assert template.frequency == "custom"
    assert template.metadata["recurrence"] == {
        "raw": "every 3 days",
        "interval_count": 3,
        "interval_unit": "day",
    }

    listed = await service.dispatch("list_chores", {"assigned_to": "riley"}, ctx)
    assert listed["count"] == 1
    assert listed["chores"][0]["id"] == res["occurrence_id"]
    assert listed["chores"][0]["assigned_to"] == "riley"


async def test_update_template(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    create_res = await service.dispatch(
        "create_template",
        {"title": "Dishes", "frequency": "daily", "base_points": 3},
        ctx,
    )
    template_id = create_res["template_id"]

    upd = await service.dispatch(
        "update_template",
        {"template_id": template_id, "base_points": 10},
        ctx,
    )
    assert upd["version"] == 2


async def test_update_template_deactivate(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    create_res = await service.dispatch(
        "create_template",
        {"title": "Mow lawn", "frequency": "weekly"},
        ctx,
    )
    template_id = create_res["template_id"]
    upd = await service.dispatch(
        "update_template",
        {"template_id": template_id, "is_active": False},
        ctx,
    )
    assert upd["success"] is True


async def test_delete_template(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    create_res = await service.dispatch(
        "create_template",
        {"title": "Clean bathroom", "frequency": "weekly"},
        ctx,
    )
    template_id = create_res["template_id"]
    del_res = await service.dispatch("delete_template", {"template_id": template_id}, ctx)
    assert del_res["success"] is True


# ---------------------------------------------------------------------------
# Occurrence CRUD
# ---------------------------------------------------------------------------


async def test_assign_chore_creates_occurrence(svc):
    service, pub, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    tmpl_res = await service.dispatch(
        "create_template",
        {"title": "Vacuum", "frequency": "weekly", "base_points": 5},
        ctx,
    )
    template_id = tmpl_res["template_id"]

    assign_res = await service.dispatch(
        "assign_chore",
        {
            "template_id": template_id,
            "assigned_to": "riley",
            "due_at": "2026-05-19T08:00:00Z",
        },
        ctx,
    )
    assert assign_res["success"] is True
    assert assign_res["occurrence_id"]
    assert any(t.startswith("family.chores.assign_chore") for t, _ in pub.published)


async def test_complete_chore(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, ctx, "riley")

    riley_ctx = make_ctx(user_id="riley", role="child", band="GREEN")
    done = await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)
    assert done["success"] is True
    assert done["completed_at"]
    assert done["points_awarded"] == 5


async def test_complete_chore_idempotent(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, ctx, "riley")
    riley_ctx = make_ctx(user_id="riley", role="child", band="GREEN")

    d1 = await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)
    d2 = await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)
    assert d1["completed_at"] == d2["completed_at"]


async def test_skip_chore(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, ctx, "riley")

    riley_ctx = make_ctx(user_id="riley", role="child", band="GREEN")
    skip = await service.dispatch(
        "skip_chore",
        {"occurrence_id": occ_id, "skip_reason": "school trip"},
        riley_ctx,
    )
    assert skip["success"] is True


async def test_reopen_chore(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, parent_ctx, "riley")

    riley_ctx = make_ctx(user_id="riley", role="child", band="GREEN")
    await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)

    reopen = await service.dispatch(
        "reopen_chore",
        {"occurrence_id": occ_id, "reason": "not done properly"},
        parent_ctx,
    )
    assert reopen["success"] is True


async def test_list_chores_assigned_to_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    await _create_assigned_occurrence(service, ctx, "riley")
    await _create_assigned_occurrence(service, ctx, "alex")

    res = await service.dispatch("list_chores", {"assigned_to": "riley"}, make_ctx())
    assert res["count"] == 1
    assert res["chores"][0]["assigned_to"] == "riley"


async def test_list_chores_status_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, ctx, "riley")
    await _create_assigned_occurrence(service, ctx, "alex")

    riley_ctx = make_ctx(user_id="riley", role="child", band="GREEN")
    await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)

    done_list = await service.dispatch("list_chores", {"status": "done"}, make_ctx())
    assert done_list["count"] == 1

    pending_list = await service.dispatch("list_chores", {"status": "pending"}, make_ctx())
    assert pending_list["count"] == 1


async def test_chore_summary_points_tally(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, ctx, "riley", base_points=5)
    riley_ctx = make_ctx(user_id="riley", role="child", band="GREEN")
    await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)

    summary = await service.dispatch("chore_summary", {}, make_ctx())
    assert summary["success"] is True
    riley_entry = next((m for m in summary["summary"] if m["member_id"] == "riley"), None)
    assert riley_entry is not None
    assert riley_entry["total_points"] == 5
    assert riley_entry["done"] == 1


async def test_points_override_by_parent(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    occ_id = await _create_assigned_occurrence(service, ctx, "riley", base_points=5)

    done = await service.dispatch(
        "complete_chore",
        {"occurrence_id": occ_id, "points_override": 10},
        ctx,  # parent caller
    )
    assert done["points_awarded"] == 10


async def test_due_before_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="GREEN")
    tmpl_res = await service.dispatch(
        "create_template",
        {"title": "Vacuum", "frequency": "weekly", "base_points": 5},
        ctx,
    )
    template_id = tmpl_res["template_id"]
    # One occurrence due early, one late.
    await service.dispatch(
        "assign_chore",
        {"template_id": template_id, "assigned_to": "riley", "due_at": "2026-05-13T08:00:00Z"},
        ctx,
    )
    await service.dispatch(
        "assign_chore",
        {"template_id": template_id, "assigned_to": "riley", "due_at": "2026-06-01T08:00:00Z"},
        ctx,
    )
    res = await service.dispatch("list_chores", {"due_before": "2026-05-20T00:00:00Z"}, make_ctx())
    assert res["count"] == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_assigned_occurrence(service, ctx, assignee: str, *, base_points: int = 5) -> str:
    tmpl_res = await service.dispatch(
        "create_template",
        {"title": "Vacuum", "frequency": "weekly", "base_points": base_points},
        ctx,
    )
    assign_res = await service.dispatch(
        "assign_chore",
        {"template_id": tmpl_res["template_id"], "assigned_to": assignee},
        ctx,
    )
    return assign_res["occurrence_id"]
