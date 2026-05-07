"""Tests for SessionRoutingStateReader (P1.1).

Validates that the routing reader correctly dispatches reads to the
appropriate per-session SessionStateManager based on session_id.
"""

from __future__ import annotations

import pytest

from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot
from k1.kernel.adapters.session_routing_reader import SessionRoutingStateReader

# ---------------------------------------------------------------------------
# Helpers — lightweight SSM stub
# ---------------------------------------------------------------------------


class _FakeSection:
    """Mimics a SessionState section object with to_dict()."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


class _FakeSSM:
    """Minimal SessionStateManager stub for routing tests."""

    def __init__(self, sections: dict[str, dict]) -> None:
        self._sections = {k: _FakeSection(v) for k, v in sections.items()}

    def get_section(self, name: str) -> _FakeSection:
        if name not in self._sections:
            from k1.sessionstate.errors import SectionNotFoundError

            raise SectionNotFoundError(name)
        return self._sections[name]

    def get_all_section_sizes(self) -> dict[str, int]:
        return {k: 100 for k in self._sections}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSessionRoutingStateReader:
    """Core routing behaviour."""

    def _make_reader(self, sessions: dict[str, _FakeSSM]) -> SessionRoutingStateReader:
        return SessionRoutingStateReader(
            session_lookup=lambda sid: sessions.get(sid),
        )

    def test_satisfies_protocol(self) -> None:
        reader = SessionRoutingStateReader(session_lookup=lambda _: None)
        assert isinstance(reader, ISessionStateReader)

    def test_read_section_returns_data_for_known_session(self) -> None:
        ssm = _FakeSSM({"control": {"safety_band": "GREEN"}})
        reader = self._make_reader({"sess-1": ssm})

        result = reader.read_section("sess-1", "control")
        assert result == {"safety_band": "GREEN"}

    def test_read_section_returns_none_for_unknown_session(self) -> None:
        reader = self._make_reader({})
        assert reader.read_section("no-such", "control") is None

    def test_read_section_returns_none_for_missing_section(self) -> None:
        ssm = _FakeSSM({"control": {"safety_band": "GREEN"}})
        reader = self._make_reader({"sess-1": ssm})

        assert reader.read_section("sess-1", "beliefs_active") is None

    def test_two_sessions_are_isolated(self) -> None:
        ssm_a = _FakeSSM({"control": {"safety_band": "GREEN"}})
        ssm_b = _FakeSSM({"control": {"safety_band": "RED"}})
        reader = self._make_reader({"a": ssm_a, "b": ssm_b})

        assert reader.read_section("a", "control") == {"safety_band": "GREEN"}
        assert reader.read_section("b", "control") == {"safety_band": "RED"}

    def test_read_sections_returns_multiple(self) -> None:
        ssm = _FakeSSM(
            {
                "control": {"safety_band": "GREEN"},
                "beliefs_active": {"facts": ["sky is blue"]},
            }
        )
        reader = self._make_reader({"s1": ssm})

        result = reader.read_sections("s1", ["control", "beliefs_active"])
        assert "control" in result
        assert "beliefs_active" in result
        assert result["control"]["safety_band"] == "GREEN"

    def test_read_sections_omits_missing(self) -> None:
        ssm = _FakeSSM({"control": {"safety_band": "GREEN"}})
        reader = self._make_reader({"s1": ssm})

        result = reader.read_sections("s1", ["control", "no_such_section"])
        assert "control" in result
        assert "no_such_section" not in result

    def test_get_snapshot_returns_all_sections(self) -> None:
        ssm = _FakeSSM(
            {
                "control": {"safety_band": "GREEN"},
                "beliefs_active": {"facts": []},
            }
        )
        reader = self._make_reader({"s1": ssm})

        snap = reader.get_snapshot("s1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "s1"
        assert "control" in snap.sections
        assert "beliefs_active" in snap.sections
        assert snap.timestamp_ms > 0

    def test_get_snapshot_returns_empty_for_unknown_session(self) -> None:
        reader = self._make_reader({})
        snap = reader.get_snapshot("unknown")
        assert snap.session_id == "unknown"
        assert snap.sections == {}

    def test_get_snapshot_two_sessions_isolated(self) -> None:
        ssm_a = _FakeSSM({"control": {"safety_band": "GREEN"}})
        ssm_b = _FakeSSM({"control": {"safety_band": "RED"}, "meta": {"age": 5}})
        reader = self._make_reader({"a": ssm_a, "b": ssm_b})

        snap_a = reader.get_snapshot("a")
        snap_b = reader.get_snapshot("b")
        assert snap_a.sections["control"]["safety_band"] == "GREEN"
        assert snap_b.sections["control"]["safety_band"] == "RED"
        assert "meta" not in snap_a.sections
        assert "meta" in snap_b.sections

    def test_session_lookup_exception_returns_none(self) -> None:
        """If the lookup raises, reader degrades gracefully."""

        def bad_lookup(sid: str):
            raise RuntimeError("boom")

        reader = SessionRoutingStateReader(session_lookup=bad_lookup)
        assert reader.read_section("s1", "control") is None
        assert reader.read_sections("s1", ["control"]) == {}
        snap = reader.get_snapshot("s1")
        assert snap.sections == {}
