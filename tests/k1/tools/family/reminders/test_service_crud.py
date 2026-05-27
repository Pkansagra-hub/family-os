"""CRUD + lifecycle tests for ``RemindersToolService``."""

from __future__ import annotations

import pytest

from tests.k1.tools.family.reminders.conftest import make_ctx

_TIME_TRIGGER = {"kind": "time", "fire_at": "2026-06-01T09:00:00Z"}
_LOC_TRIGGER = {
    "kind": "location_leave",
    "location": {"lat": 37.77, "lon": -122.41, "radius_m": 200, "name": "work"},
}


async def test_create_reminder_and_emit(svc):
    service, pub, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    res = await service.dispatch(
        "create_reminder",
        {"title": "Pick up Riley", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    assert res["success"] is True
    reminder_id = res["reminder_id"]
    assert reminder_id
    assert res["version"] == 1
    assert any(t.startswith("family.reminders.create_reminder") for t, _ in pub.published)


async def test_get_reminder(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Dentist reminder", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    get_res = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, make_ctx())
    assert get_res["success"] is True
    assert get_res["reminder"]["title"] == "Dentist reminder"
    assert get_res["reminder"]["status"] == "scheduled"


async def test_update_reminder_while_scheduled(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Old title", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]

    upd = await service.dispatch(
        "update_reminder",
        {"reminder_id": reminder_id, "title": "New title"},
        ctx,
    )
    assert upd["version"] == 2
    get_res = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, make_ctx())
    assert get_res["reminder"]["title"] == "New title"


async def test_update_reminder_after_fired_blocked(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Fire me", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    # Fire it via system ctx
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)

    # Now update should fail
    upd = await service.dispatch(
        "update_reminder",
        {"reminder_id": reminder_id, "title": "Too late"},
        ctx,
    )
    assert upd["success"] is False


async def test_fire_reminder_stamps_fired_at(svc):
    service, pub, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Take meds", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]

    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    fire_res = await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)
    assert fire_res["success"] is True
    assert fire_res["fired_at"]
    assert fire_res["push_title"] == "Take meds"
    assert "u1" in fire_res["push_recipient_ids"]

    get_res = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, make_ctx())
    assert get_res["reminder"]["status"] == "fired"


async def test_fire_reminder_idempotent(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Double fire", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    fire1 = await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)
    fire2 = await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)
    assert fire1["fired_at"] == fire2["fired_at"]


async def test_snooze_reminder(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Snooze me", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)

    snooze_res = await service.dispatch(
        "snooze_reminder",
        {"reminder_id": reminder_id, "snooze_until": "2026-06-01T09:10:00Z"},
        ctx,
    )
    assert snooze_res["success"] is True
    assert snooze_res["snoozed_until"] == "2026-06-01T09:10:00Z"

    get_res = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, make_ctx())
    assert get_res["reminder"]["status"] == "snoozed"


async def test_dismiss_reminder(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Dismiss me", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)

    dismiss_res = await service.dispatch("dismiss_reminder", {"reminder_id": reminder_id}, ctx)
    assert dismiss_res["success"] is True

    get_res = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, make_ctx())
    assert get_res["reminder"]["status"] == "dismissed"


async def test_dismiss_idempotent(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Dismiss twice", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": reminder_id}, sys_ctx)
    d1 = await service.dispatch("dismiss_reminder", {"reminder_id": reminder_id}, ctx)
    d2 = await service.dispatch("dismiss_reminder", {"reminder_id": reminder_id}, ctx)
    assert d1["success"] is True
    assert d2["success"] is True


async def test_delete_reminder_soft_delete(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Delete me", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    reminder_id = create_res["reminder_id"]
    del_res = await service.dispatch("delete_reminder", {"reminder_id": reminder_id}, ctx)
    assert del_res["success"] is True

    out = await service.dispatch("get_reminder", {"reminder_id": reminder_id}, make_ctx())
    assert out["success"] is False


async def test_list_reminders_recipient_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    await service.dispatch(
        "create_reminder",
        {"title": "For alice", "recipient": "alice", "trigger": _TIME_TRIGGER},
        ctx,
    )
    await service.dispatch(
        "create_reminder",
        {"title": "For bob", "recipient": "bob", "trigger": _TIME_TRIGGER},
        ctx,
    )
    res = await service.dispatch("list_reminders", {"recipient": "alice"}, make_ctx())
    assert res["count"] == 1
    assert res["reminders"][0]["recipient"] == "alice"


async def test_create_reminder_normalizes_named_recipient(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="alex", role="guardian", band="GREEN")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Vitamins", "recipient": "Nana Liz", "trigger": _TIME_TRIGGER},
        ctx,
    )

    out = await service.dispatch("get_reminder", {"reminder_id": create_res["reminder_id"]}, ctx)
    assert out["reminder"]["recipient"] == "nana_liz"


async def test_list_reminders_recipient_filter_accepts_display_name(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="alex", role="parent", band="GREEN")
    await service.dispatch(
        "create_reminder",
        {"title": "Self reminder", "recipient": "alex", "trigger": _TIME_TRIGGER},
        ctx,
    )

    res = await service.dispatch("list_reminders", {"recipient": "Alex"}, ctx)
    assert res["count"] == 1
    assert res["reminders"][0]["recipient"] == "alex"


async def test_list_reminders_status_filter(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {"title": "Fire me", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )
    sys_ctx = make_ctx(user_id="system", role="system", band="AMBER")
    await service.dispatch("fire_reminder", {"reminder_id": create_res["reminder_id"]}, sys_ctx)
    await service.dispatch(
        "create_reminder",
        {"title": "Still scheduled", "recipient": "u1", "trigger": _TIME_TRIGGER},
        ctx,
    )

    fired = await service.dispatch("list_reminders", {"status": "fired"}, make_ctx())
    assert fired["count"] == 1

    scheduled = await service.dispatch("list_reminders", {"status": "scheduled"}, make_ctx())
    assert scheduled["count"] == 1


async def test_location_trigger_reminder_round_trip(svc):
    service, _, _ = svc
    ctx = make_ctx(user_id="u1", role="parent", band="AMBER")
    create_res = await service.dispatch(
        "create_reminder",
        {
            "title": "Grab milk when leaving work",
            "recipient": "u1",
            "trigger": _LOC_TRIGGER,
        },
        ctx,
    )
    assert create_res["success"] is True
    get_res = await service.dispatch(
        "get_reminder", {"reminder_id": create_res["reminder_id"]}, make_ctx()
    )
    trig = get_res["reminder"]["trigger"]
    assert trig["kind"] == "location_leave"
    assert trig["location"]["name"] == "work"
