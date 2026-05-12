"""ACL and role-gate tests for ``RemindersToolService``."""

from __future__ import annotations

from tests.k1.tools.family.reminders.conftest import make_ctx

_TIME_TRIGGER = {"kind": "time", "fire_at": "2026-06-01T09:00:00Z"}


async def test_create_cross_member_blocked_for_child(svc):
    """Child cannot set a reminder for a different family member."""
    service, _, _ = svc
    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")
    out = await service.dispatch(
        "create_reminder",
        {"title": "For dad", "recipient": "dad1", "trigger": _TIME_TRIGGER},
        child_ctx,
    )
    assert out["success"] is False


async def test_create_self_reminder_allowed_for_child(svc):
    """Child CAN set a reminder for themselves."""
    service, _, _ = svc
    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")
    out = await service.dispatch(
        "create_reminder",
        {"title": "My reminder", "recipient": "child1", "trigger": _TIME_TRIGGER},
        child_ctx,
    )
    assert out["success"] is True


async def test_private_reminder_hidden_from_child(svc):
    """A private reminder from parent should not be visible to a child."""
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {
            "title": "Private note",
            "recipient": "u1",
            "trigger": _TIME_TRIGGER,
            "visibility": "private",
        },
        parent_ctx,
    )
    reminder_id = create_res["reminder_id"]

    child_ctx = make_ctx(user_id="child1", role="child", band="GREEN")
    out = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, child_ctx)
    assert out["success"] is False


async def test_snooze_by_recipient_allowed(svc):
    """The recipient (not creator) can snooze their own reminder."""
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Remind dad", "recipient": "dad1", "trigger": _TIME_TRIGGER},
        parent_ctx,
    )
    reminder_id = create_res["reminder_id"]
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)

    # dad1 is the recipient — should be allowed to snooze
    dad_ctx = make_ctx(user_id="dad1", role="elder", band="AMBER")
    out = await service.dispatch(
        "snooze_reminder",
        {"reminder_id": reminder_id, "snooze_until": "2026-06-01T09:10:00Z"},
        dad_ctx,
    )
    assert out["success"] is True


async def test_snooze_by_unrelated_child_blocked(svc):
    """An unrelated child cannot snooze another person's reminder."""
    service, _, _ = svc
    parent_ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Dad reminder", "recipient": "dad1", "trigger": _TIME_TRIGGER},
        parent_ctx,
    )
    reminder_id = create_res["reminder_id"]
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)

    child_ctx = make_ctx(user_id="child1", role="child", band="AMBER")
    out = await service.dispatch(
        "snooze_reminder",
        {"reminder_id": reminder_id, "snooze_until": "2026-06-01T09:10:00Z"},
        child_ctx,
    )
    assert out["success"] is False


async def test_fire_reminder_blocked_for_non_system(svc):
    """LLM or a human caller cannot fire a reminder — system role only."""
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "LLM fire attempt", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]

    out = await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, ctx)
    assert out["success"] is False


async def test_band_gate_crisis_blocks_create(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="CRISIS")
    out = await service.dispatch(
        "create_reminder",
        {"title": "Crisis block", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    assert out["success"] is False
    assert out["error_code"] == "band_denied"


async def test_guardian_can_create_for_other_member(svc):
    """Guardian role satisfies the cross-member guard."""
    service, _, _ = svc
    guardian_ctx = make_ctx(user_id="g1", role="guardian", band="AMBER")
    out = await service.dispatch(
        "create_reminder",
        {"title": "Remind child", "recipient": "child1", "trigger": _TIME_TRIGGER},
        guardian_ctx,
    )
    assert out["success"] is True
