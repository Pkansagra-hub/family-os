"""
C2-prep Issue 4.5 — SnapshotStateReadAdapter tests.

Validates adapter satisfies Planner's IStateReadPort, reads from bound snapshot.
"""

from __future__ import annotations

import asyncio

from k1.concierge.adapters.snapshot_state_read import SnapshotStateReadAdapter
from k1.fabric.ports.state_reader import SessionSnapshot
from k1.planner.ports.state_read_port import IStateReadPort


class TestSnapshotStateReadProtocol:
    def test_satisfies_istatereadport(self) -> None:
        assert isinstance(SnapshotStateReadAdapter(), IStateReadPort)


class TestSnapshotStateReadBehaviour:
    def test_read_sections_unbound_returns_empty(self) -> None:
        adapter = SnapshotStateReadAdapter()
        result = asyncio.run(
            adapter.read_sections(["beliefs_active", "control"])
        )
        assert isinstance(result, SessionSnapshot)
        assert result.sections == {}

    def test_bind_then_read_returns_filtered(self) -> None:
        snapshot = SessionSnapshot(
            session_id="sess-1",
            sections={
                "beliefs_active": {"belief": "sky_is_blue"},
                "control": {"safety_band": "GREEN"},
                "history_recent": {"turns": []},
            },
            timestamp_ms=1000,
        )
        adapter = SnapshotStateReadAdapter()
        adapter.bind(snapshot)
        result = asyncio.run(
            adapter.read_sections(["beliefs_active", "control"])
        )
        assert "beliefs_active" in result.sections
        assert "control" in result.sections
        assert "history_recent" not in result.sections

    def test_bind_then_read_all_sections(self) -> None:
        snapshot = SessionSnapshot(
            session_id="sess-1",
            sections={
                "beliefs_active": {"b": 1},
                "control": {"c": 2},
            },
            timestamp_ms=2000,
        )
        adapter = SnapshotStateReadAdapter()
        adapter.bind(snapshot)
        result = asyncio.run(
            adapter.read_sections(["beliefs_active", "control"])
        )
        assert len(result.sections) == 2

    def test_bind_preserves_session_id(self) -> None:
        snapshot = SessionSnapshot(session_id="sess-99", sections={"a": {"x": 1}})
        adapter = SnapshotStateReadAdapter()
        adapter.bind(snapshot)
        result = asyncio.run(adapter.read_sections(["a"]))
        assert result.session_id == "sess-99"

    def test_bind_preserves_timestamp(self) -> None:
        snapshot = SessionSnapshot(session_id="s", sections={"a": {"x": 1}}, timestamp_ms=42000)
        adapter = SnapshotStateReadAdapter()
        adapter.bind(snapshot)
        result = asyncio.run(adapter.read_sections(["a"]))
        assert result.timestamp_ms == 42000

    def test_bind_none_resets_to_empty(self) -> None:
        snapshot = SessionSnapshot(session_id="s", sections={"a": {"x": 1}})
        adapter = SnapshotStateReadAdapter()
        adapter.bind(snapshot)
        adapter.bind(None)
        result = asyncio.run(adapter.read_sections(["a"]))
        assert result.sections == {}

    def test_rebind_overwrites_previous(self) -> None:
        snap1 = SessionSnapshot(session_id="s1", sections={"a": {"v": 1}})
        snap2 = SessionSnapshot(session_id="s2", sections={"b": {"v": 2}})
        adapter = SnapshotStateReadAdapter()
        adapter.bind(snap1)
        adapter.bind(snap2)
        result = asyncio.run(adapter.read_sections(["a", "b"]))
        assert "a" not in result.sections
        assert "b" in result.sections
        assert result.session_id == "s2"

