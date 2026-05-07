"""M13.E2 — HIL durability integration tests.

Verifies the contract of :class:`k1.hil.sqlite_writer.SQLiteHILEventWriter`:

  * Append + read round-trip for the four lifecycle events.
  * ``resolver_id`` (M13.E2.I3) is persisted on Resolved events.
  * ``pending_request_ids()`` returns Requested-without-terminal IDs,
    enabling replay after a kernel crash.
  * Survives a process-level "restart" (close + re-open same file).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.hil.sqlite_writer import SQLiteHILEventWriter
from k1.hil.types import (
    HILBlockedEvent,
    HILRequestedEvent,
    HILResolvedEvent,
    HILTimedOutEvent,
)


def test_append_and_read_roundtrip_in_memory() -> None:
    writer = SQLiteHILEventWriter(":memory:")
    req = HILRequestedEvent(
        hil_request_id="hil-1",
        kind="approval",
        caller_key="back.alice",
        trace_id="t-1",
        timestamp_ms=1_700_000_000_000,
    )
    res = HILResolvedEvent(
        hil_request_id="hil-1",
        kind="approval",
        decision_summary="approved",
        timestamp_ms=1_700_000_005_000,
        duration_ms=5000,
        resolver_id="user.guardian.bob",
    )
    writer.append(req)
    writer.append(res)

    rows = writer.read_all()
    assert [r["event_type"] for r in rows] == [
        "HILRequestedEvent",
        "HILResolvedEvent",
    ]
    assert rows[1]["resolver_id"] == "user.guardian.bob"
    assert rows[1]["payload"]["resolver_id"] == "user.guardian.bob"


def test_append_rejects_unknown_event_type() -> None:
    writer = SQLiteHILEventWriter(":memory:")
    with pytest.raises(TypeError):
        writer.append(object())


def test_pending_request_ids_filters_terminal_events() -> None:
    writer = SQLiteHILEventWriter(":memory:")
    # hil-A: opened + resolved (not pending).
    writer.append(HILRequestedEvent("hil-A", "clarification", "back", "t", 1))
    writer.append(HILResolvedEvent("hil-A", "clarification", "ok", 2, 1, "user.alice"))
    # hil-B: opened only (pending).
    writer.append(HILRequestedEvent("hil-B", "approval", "back", "t", 3))
    # hil-C: opened + timed out (not pending).
    writer.append(HILRequestedEvent("hil-C", "approval", "back", "t", 4))
    writer.append(HILTimedOutEvent("hil-C", "approval", "back", 5, 60_000))
    # hil-D: opened + blocked (not pending).
    writer.append(HILRequestedEvent("hil-D", "selection", "back", "t", 6))
    writer.append(HILBlockedEvent("hil-D", "selection", "back", "ratelimit", 7))

    pending = writer.pending_request_ids()
    assert pending == ["hil-B"]


def test_durability_across_simulated_restart(tmp_path: Path) -> None:
    db = tmp_path / "hil.db"
    # Session 1: open a request and crash (no terminal event written).
    w1 = SQLiteHILEventWriter(db)
    w1.append(
        HILRequestedEvent(
            hil_request_id="hil-survivor",
            kind="approval",
            caller_key="back.alice",
            trace_id="t-survivor",
            timestamp_ms=1_700_000_000_000,
        )
    )
    w1.close()

    # Session 2: re-open the same file. The request must replay.
    w2 = SQLiteHILEventWriter(db)
    pending = w2.pending_request_ids()
    assert pending == ["hil-survivor"]
    rows = w2.read_all("hil-survivor")
    assert len(rows) == 1
    assert rows[0]["event_type"] == "HILRequestedEvent"

    # Resolve it in session 2; terminal event clears the pending list.
    w2.append(
        HILResolvedEvent(
            hil_request_id="hil-survivor",
            kind="approval",
            decision_summary="approved",
            timestamp_ms=1_700_000_010_000,
            duration_ms=10_000,
            resolver_id="user.guardian.bob",
        )
    )
    assert w2.pending_request_ids() == []
    w2.close()


def test_resolver_id_defaults_empty_for_legacy_events() -> None:
    """Backwards-compat: HILResolvedEvent without resolver_id still works."""
    writer = SQLiteHILEventWriter(":memory:")
    res = HILResolvedEvent(
        hil_request_id="hil-legacy",
        kind="approval",
        decision_summary="approved",
        timestamp_ms=1,
        duration_ms=1,
    )
    writer.append(res)
    rows = writer.read_all("hil-legacy")
    assert rows[0]["resolver_id"] == ""
    assert rows[0]["payload"]["resolver_id"] == ""
