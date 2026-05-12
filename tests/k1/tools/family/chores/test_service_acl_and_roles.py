"""ACL and role-gate tests for ChoresToolService."""

from __future__ import annotations

from tests.k1.tools.family.chores.conftest import make_ctx

# ---------------------------------------------------------------------------
# Template gate — parent+ only
# ---------------------------------------------------------------------------


async def test_create_template_blocked_for_child(svc):
    service, _, _ = svc
    child_ctx = make_ctx(user_id="c1", role="child", band="AMBER")
    out = await service.dispatch(
        "create_template",
        {"title": "Vacuum", "frequency": "weekly"},
        child_ctx,
    )
    assert out["success"] is False


async def test_create_template_blocked_for_guardian(svc):
    """Guardian is below parent — cannot manage templates."""
    service, _, _ = svc
    ctx = make_ctx(user_id="g1", role="guardian", band="AMBER")
    out = await service.dispatch(
        "create_template",
        {"title": "Vacuum", "frequency": "weekly"},
        ctx,
    )
    assert out["success"] is False


async def test_delete_template_blocked_for_elder(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    tmpl_res = await service.dispatch(
        "create_template", {"title": "Dishes", "frequency": "daily"}, parent_ctx
    )
    elder_ctx = make_ctx(user_id="e1", role="elder", band="AMBER")
    out = await service.dispatch(
        "delete_template", {"template_id": tmpl_res["template_id"]}, elder_ctx
    )
    assert out["success"] is False


async def test_reopen_blocked_for_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    occ_id = await _create_assigned_occ(service, parent_ctx, "riley")
    riley_ctx = make_ctx(user_id="riley", role="child", band="AMBER")
    await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)

    reopen = await service.dispatch("reopen_chore", {"occurrence_id": occ_id}, riley_ctx)
    assert reopen["success"] is False


# ---------------------------------------------------------------------------
# Occurrence gate — assignee or parent+
# ---------------------------------------------------------------------------


async def test_complete_by_assignee_allowed(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    occ_id = await _create_assigned_occ(service, parent_ctx, "riley")

    riley_ctx = make_ctx(user_id="riley", role="child", band="AMBER")
    out = await service.dispatch("complete_chore", {"occurrence_id": occ_id}, riley_ctx)
    assert out["success"] is True


async def test_complete_by_unrelated_child_blocked(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    occ_id = await _create_assigned_occ(service, parent_ctx, "riley")

    other_child = make_ctx(user_id="alex", role="child", band="AMBER")
    out = await service.dispatch("complete_chore", {"occurrence_id": occ_id}, other_child)
    assert out["success"] is False


async def test_skip_by_parent_allowed(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    occ_id = await _create_assigned_occ(service, parent_ctx, "riley")

    out = await service.dispatch(
        "skip_chore", {"occurrence_id": occ_id, "skip_reason": "excused"}, parent_ctx
    )
    assert out["success"] is True


# ---------------------------------------------------------------------------
# Assign gate — guardian+
# ---------------------------------------------------------------------------


async def test_assign_chore_blocked_for_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    tmpl_res = await service.dispatch(
        "create_template", {"title": "Mop floor", "frequency": "weekly"}, parent_ctx
    )
    child_ctx = make_ctx(user_id="c1", role="child", band="AMBER")
    out = await service.dispatch(
        "assign_chore",
        {"template_id": tmpl_res["template_id"], "assigned_to": "c1"},
        child_ctx,
    )
    assert out["success"] is False


async def test_assign_chore_allowed_for_guardian(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    tmpl_res = await service.dispatch(
        "create_template", {"title": "Mop floor", "frequency": "weekly"}, parent_ctx
    )
    guardian_ctx = make_ctx(user_id="g1", role="guardian", band="AMBER")
    out = await service.dispatch(
        "assign_chore",
        {"template_id": tmpl_res["template_id"], "assigned_to": "riley"},
        guardian_ctx,
    )
    assert out["success"] is True


# ---------------------------------------------------------------------------
# Band gate
# ---------------------------------------------------------------------------


async def test_band_crisis_blocks_create(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="CRISIS")
    out = await service.dispatch("create_template", {"title": "X", "frequency": "weekly"}, ctx)
    assert out["success"] is False
    assert out["error_code"] == "band_denied"


# ---------------------------------------------------------------------------
# Points override gate
# ---------------------------------------------------------------------------


async def test_points_override_ignored_for_child(svc):
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    occ_id = await _create_assigned_occ(service, parent_ctx, "riley", base_points=5)

    riley_ctx = make_ctx(user_id="riley", role="child", band="AMBER")
    out = await service.dispatch(
        "complete_chore",
        {"occurrence_id": occ_id, "points_override": 100},
        riley_ctx,
    )
    # Override ignored — base_points used
    assert out["points_awarded"] == 5


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _create_assigned_occ(service, ctx, assignee: str, *, base_points: int = 5) -> str:
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
