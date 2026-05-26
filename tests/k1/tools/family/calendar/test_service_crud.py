"""CRUD + happy-path tests for ``CalendarToolService``."""

from __future__ import annotations

from tests.k1.tools.family.calendar.conftest import make_ctx


def _evt_params(**over):
    p = {
        "title": "Soccer game",
        "start": "2026-05-15T10:00:00+00:00",
        "end": "2026-05-15T11:30:00+00:00",
    }
    p.update(over)
    return p


async def test_create_event_persists_and_emits(svc) -> None:
    service, pub, _ = svc
    out = await service.dispatch("create_event", _evt_params(), make_ctx())
    assert out["success"] is True
    assert out["version"] == 1
    assert out["event_id"]
    # SSE fan-out emitted exactly once
    assert any(t.startswith("family.calendar.create_event") for t, _ in pub.published)


async def test_get_event_returns_full_row(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch("create_event", _evt_params(), make_ctx())
    out = await service.dispatch("get_event", {"event_id": created["event_id"]}, make_ctx())
    assert out["success"] is True
    assert out["event"]["title"] == "Soccer game"
    assert out["event"]["version"] == 1


async def test_create_event_persists_generic_metadata(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch(
        "create_event",
        _evt_params(
            metadata={
                "_semantic": {
                    "authority": {
                        "guidance_scope": "general",
                        "requires_external_authority": True,
                    },
                    "future_weave": {"prep_notes": ["bring paperwork"]},
                }
            }
        ),
        make_ctx(),
    )

    out = await service.dispatch("get_event", {"event_id": created["event_id"]}, make_ctx())

    assert out["event"]["metadata"]["_semantic"]["authority"]["guidance_scope"] == "general"
    assert out["event"]["metadata"]["_semantic"]["future_weave"]["prep_notes"] == [
        "bring paperwork"
    ]


async def test_update_event_bumps_version(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch("create_event", _evt_params(), make_ctx())
    eid = created["event_id"]
    out = await service.dispatch(
        "update_event",
        {"event_id": eid, "expected_version": 1, "title": "Soccer (rescheduled)"},
        make_ctx(),
    )
    assert out["success"] is True
    assert out["version"] == 2
    got = await service.dispatch("get_event", {"event_id": eid}, make_ctx())
    assert got["event"]["title"] == "Soccer (rescheduled)"


async def test_update_event_rejects_stale_expected_version(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch("create_event", _evt_params(), make_ctx())
    out = await service.dispatch(
        "update_event",
        {"event_id": created["event_id"], "expected_version": 99, "title": "x"},
        make_ctx(),
    )
    assert out["success"] is False
    assert out["error_code"] == "dispatch_failed"
    assert "stale" in out["error_message"]


async def test_delete_event_soft_deletes(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch("create_event", _evt_params(), make_ctx())
    eid = created["event_id"]
    out = await service.dispatch("delete_event", {"event_id": eid}, make_ctx())
    assert out["success"] is True
    # Soft-deleted rows are filtered out of read paths.
    lst = await service.dispatch("list_events", {}, make_ctx())
    assert all(r["id"] != eid for r in lst["events"])


async def test_list_events_window_filter(svc) -> None:
    service, _, _ = svc
    await service.dispatch(
        "create_event",
        _evt_params(title="A", start="2026-05-15T10:00:00+00:00", end="2026-05-15T11:00:00+00:00"),
        make_ctx(),
    )
    await service.dispatch(
        "create_event",
        _evt_params(title="B", start="2026-06-15T10:00:00+00:00", end="2026-06-15T11:00:00+00:00"),
        make_ctx(),
    )
    out = await service.dispatch(
        "list_events",
        {"start": "2026-06-01T00:00:00+00:00", "end": "2026-06-30T00:00:00+00:00"},
        make_ctx(),
    )
    titles = {r["title"] for r in out["events"]}
    assert titles == {"B"}


async def test_list_events_window_filter_accepts_date_aliases_and_overlaps(svc) -> None:
    service, _, _ = svc
    await service.dispatch(
        "create_event",
        _evt_params(
            title="Spans Window",
            start="2026-05-31T22:00:00+00:00",
            end="2026-06-01T02:00:00+00:00",
        ),
        make_ctx(),
    )
    await service.dispatch(
        "create_event",
        _evt_params(
            title="Outside",
            start="2026-07-15T10:00:00+00:00",
            end="2026-07-15T11:00:00+00:00",
        ),
        make_ctx(),
    )

    out = await service.dispatch(
        "list_events",
        {"start_date": "2026-06-01", "end_date": "2026-06-30"},
        make_ctx(),
    )

    titles = {r["title"] for r in out["events"]}
    assert titles == {"Spans Window"}


async def test_list_events_member_filter(svc) -> None:
    service, _, _ = svc
    await service.dispatch(
        "create_event",
        _evt_params(title="A", attendees=["alice"]),
        make_ctx(),
    )
    await service.dispatch(
        "create_event",
        _evt_params(title="B", attendees=["bob"]),
        make_ctx(),
    )
    out = await service.dispatch("list_events", {"member_filter": ["alice"]}, make_ctx())
    assert {r["title"] for r in out["events"]} == {"A"}


async def test_create_event_idempotent_replay(svc) -> None:
    service, _, _ = svc
    ctx = make_ctx(idem_key="key-1")
    first = await service.dispatch("create_event", _evt_params(), ctx)
    second = await service.dispatch("create_event", _evt_params(), ctx)
    assert second.get("idempotent_replay") is True
    assert second["event_id"] == first["event_id"]


async def test_respond_to_invite_records_rsvp(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch(
        "create_event",
        _evt_params(attendees=["u1"]),
        make_ctx(user_id="u_creator"),
    )
    out = await service.dispatch(
        "respond_to_invite",
        {"event_id": created["event_id"], "response": "yes"},
        make_ctx(user_id="u1"),
    )
    assert out["success"] is True
    assert out["response"] == "yes"


async def test_respond_to_invite_blocks_non_attendee(svc) -> None:
    service, _, _ = svc
    created = await service.dispatch(
        "create_event",
        _evt_params(attendees=["alice"]),
        make_ctx(user_id="u_creator", role="parent"),
    )
    # child role, not in attendees -> rejected
    out = await service.dispatch(
        "respond_to_invite",
        {"event_id": created["event_id"], "response": "yes"},
        make_ctx(user_id="someone_else", role="child"),
    )
    assert out["success"] is False
    assert out["error_code"] == "dispatch_failed"
