"""Tests for ``BaseToolService`` dispatch backbone (§E15.0.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.tools.family.base import WriteContext
from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import default_policy
from k1.tools.family.storage import K1FamilyStore
from tests.k1.tools.family._stubs import (
    DemoToolService,
    RecordingSsePublisher,
)


@pytest.fixture()
def svc(tmp_path: Path):
    store = K1FamilyStore(str(tmp_path / "k.db"))
    pub = RecordingSsePublisher()
    emitter = EventEmitter(pub)
    idem = IdempotencyStore(store.conn)
    service = DemoToolService(store.conn, emitter, default_policy(), idem)
    try:
        yield service, pub, store
    finally:
        store.close()


def _ctx(
    role: str = "parent", band: str = "GREEN", idem_key: str | None = None, space_id: str = "h1"
) -> WriteContext:
    return WriteContext(
        user_id="u1",
        space_id=space_id,
        trace_id="t1",
        role=role,  # type: ignore[arg-type]
        band=band,  # type: ignore[arg-type]
        idempotency_key=idem_key,
    )


async def test_tables_sql_runs_at_construction(svc) -> None:
    service, _, store = svc
    rows = store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in rows]
    assert "demo_schema_version" in names
    assert "demo_log" in names


async def test_dispatch_happy_path(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("echo", {"message": "hi"}, _ctx())
    assert out == {"echo": "hi", "success": True}


async def test_unknown_action_returns_envelope(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("nope", {}, _ctx())
    assert out["success"] is False
    assert out["error_code"] == "action_not_found"


async def test_role_denied(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("record_write", {"payload": "x"}, _ctx(role="guest"))
    assert out["success"] is False
    assert out["error_code"] == "role_denied"


async def test_min_role_below(svc) -> None:
    service, _, _ = svc
    # record_write min_role=parent; elder is below parent in ladder
    # but elder is not in allowed_roles, so role_denied fires first.
    out = await service.dispatch("record_write", {"payload": "x"}, _ctx(role="elder"))
    assert out["error_code"] == "role_denied"


async def test_band_denied(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("adults_only", {}, _ctx(band="CRISIS"))
    assert out["error_code"] == "band_denied"


async def test_handler_exception_translated(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("boom", {}, _ctx())
    assert out["success"] is False
    assert out["error_code"] == "dispatch_failed"
    assert "kaboom" in out["error_message"]


async def test_non_dict_return_translated(svc) -> None:
    service, _, _ = svc
    out = await service.dispatch("bad_return", {}, _ctx())
    assert out["error_code"] == "invalid_result"


async def test_idempotent_replay(svc) -> None:
    service, pub, _ = svc
    ctx = _ctx(idem_key="ikey-1")
    out1 = await service.dispatch("record_write", {"payload": "alpha"}, ctx)
    out2 = await service.dispatch("record_write", {"payload": "alpha"}, ctx)
    assert out1["id"] == out2["id"]
    assert out2.get("idempotent_replay") is True
    # Event was emitted only on the first (non-replay) call.
    write_topics = [t for t, _ in pub.published if "record_write" in t]
    assert len(write_topics) == 1


async def test_event_emitted_on_write(svc) -> None:
    service, pub, _ = svc
    out = await service.dispatch("record_write", {"payload": "p1"}, _ctx())
    assert out["success"] is True
    topics = [t for t, _ in pub.published]
    assert "family.demo.record_write.write.v1" in topics
