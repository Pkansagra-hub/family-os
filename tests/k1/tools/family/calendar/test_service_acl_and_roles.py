"""ACL, role-gate, and policy tests for ``CalendarToolService``."""

from __future__ import annotations

from tests.k1.tools.family.calendar.conftest import make_ctx


def _evt_params(**over):
    p = {
        "title": "Doctor appointment",
        "start": "2026-05-15T10:00:00+00:00",
        "end": "2026-05-15T11:00:00+00:00",
    }
    p.update(over)
    return p


async def test_set_visibility_blocks_child(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch("create_event", _evt_params(), make_ctx(role="parent"))
    out = await service.dispatch(
        "set_visibility",
        {"event_id": created["event_id"], "visibility": "adults"},
        make_ctx(role="child"),
    )
    assert out["success"] is False
    # child is not in allowed_roles for set_visibility -> role_denied
    assert out["error_code"] == "role_denied"


async def test_set_visibility_promotes_band(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch("create_event", _evt_params(), make_ctx(role="parent"))
    out = await service.dispatch(
        "set_visibility",
        {"event_id": created["event_id"], "visibility": "adults"},
        make_ctx(role="parent"),
    )
    assert out["success"] is True
    assert out["visibility"] == "adults"


async def test_list_events_filters_private_for_other_user(svc) -> None:
    service, _, _ = svc
    # A parent creates a private event.
    await service.dispatch(
        "create_event",
        _evt_params(visibility="private"),
        make_ctx(user_id="alice", role="parent"),
    )
    # A child (no cross-user-read privilege) MUST NOT see it.
    out = await service.dispatch("list_events", {}, make_ctx(user_id="kid1", role="child"))
    assert out["count"] == 0


async def test_list_events_filters_adults_for_child(svc) -> None:
    service, _, _ = svc
    await service.dispatch(
        "create_event",
        _evt_params(visibility="adults"),
        make_ctx(role="parent"),
    )
    out = await service.dispatch("list_events", {}, make_ctx(user_id="kid1", role="child"))
    assert out["count"] == 0


async def test_band_gate_blocks_crisis_writes(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("create_event", _evt_params(), make_ctx(band="CRISIS"))
    assert out["success"] is False
    assert out["error_code"] == "band_denied"


async def test_connect_feed_parent_only(svc) -> None:
    service, _, _ = svc
    out_child = await service.dispatch(
        "connect_feed",
        {"feed_source": "google", "account": "x@example.com"},
        make_ctx(role="child"),
    )
    assert out_child["error_code"] == "role_denied"
    out_parent = await service.dispatch(
        "connect_feed",
        {"feed_source": "google", "account": "x@example.com"},
        make_ctx(role="parent"),
    )
    assert out_parent["success"] is True
    assert out_parent["feed_id"]


async def test_list_feeds_and_disconnect(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch(
        "connect_feed",
        {"feed_source": "outlook", "account": "y@example.com"},
        make_ctx(role="parent"),
    )
    listed = await service.dispatch("list_feeds", {}, make_ctx(role="parent"))
    assert listed["count"] >= 1
    out = await service.dispatch(
        "disconnect_feed",
        {"feed_id": created["feed_id"]},
        make_ctx(role="parent"),
    )
    assert out["success"] is True
    listed2 = await service.dispatch("list_feeds", {}, make_ctx(role="parent"))
    assert all(f["id"] != created["feed_id"] for f in listed2["feeds"])
