"""
C2-prep Issue 4.1 — NullSessionStateReaderAdapter tests.

Validates null adapter satisfies ISessionStateReader and returns empty for all reads.
"""

from __future__ import annotations

from k1.concierge.adapters.null_state_reader import NullSessionStateReaderAdapter
from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot


class TestNullSessionStateReaderProtocol:
    def test_satisfies_isessionstatereader(self) -> None:
        assert isinstance(NullSessionStateReaderAdapter(), ISessionStateReader)


class TestNullSessionStateReaderBehaviour:
    def test_read_section_returns_none(self) -> None:
        adapter = NullSessionStateReaderAdapter()
        assert adapter.read_section("sess-1", "affective_now") is None

    def test_read_sections_returns_empty_dict(self) -> None:
        adapter = NullSessionStateReaderAdapter()
        result = adapter.read_sections("sess-1", ["affective_now", "cognitive"])
        assert result == {}

    def test_get_snapshot_returns_empty_snapshot(self) -> None:
        adapter = NullSessionStateReaderAdapter()
        snap = adapter.get_snapshot("sess-1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.sections == {}

    def test_get_snapshot_preserves_session_id(self) -> None:
        adapter = NullSessionStateReaderAdapter()
        snap = adapter.get_snapshot("sess-42")
        assert snap.session_id == "sess-42"
