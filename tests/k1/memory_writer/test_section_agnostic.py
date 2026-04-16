"""Tests for section-agnostic reading (E-MW-0.3).

Covers I-MW-0.3.1 through I-MW-0.3.5:
  - ISessionReadPort has list_sections() and snapshot_all() methods
  - SessionReadAdapter.list_sections() returns ALL_SECTIONS from sizetracker
  - SessionReadAdapter.snapshot_all() reads everything minus exclude set
  - MWConfig.skip_sections replaces old hot/warm lists
  - New SS sections are automatically included (no config change needed)
  - Backward compat: existing snapshot() / read_section() unchanged

References:
  - E-MW-0.3: Section-Agnostic Reading
  - k1/memory_writer/ports/session_read_port.py (ISessionReadPort)
  - k1/memory_writer/adapters/session_read_adapter.py (SessionReadAdapter)
  - k1/memory_writer/config.py (MWConfig, skip_sections)
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet
from unittest.mock import patch

import pytest

from k1.memory_writer.adapters.session_read_adapter import SessionReadAdapter
from k1.memory_writer.config import _DEFAULT_SKIP_SECTIONS, _PHANTOM_SECTIONS, MWConfig
from k1.memory_writer.ports.session_read_port import ISessionReadPort

# ---------------------------------------------------------------------------
# The 15 real ALL_SECTIONS from sizetracker (authoritative)
# ---------------------------------------------------------------------------
ALL_15_SECTIONS: FrozenSet[str] = frozenset(
    {
        "control",
        "beliefs_active",
        "scoreboard",
        "history_active",
        "clarifications",
        "affective_now",
        "narrative_active",
        "meta",
        "task_state",
        "task_artifacts",
        "beliefs_history",
        "history_recent",
        "persona",
        "telemetry",
        "artifacts_warm",
    }
)


# ---------------------------------------------------------------------------
# Fake SessionStateManager (minimal stub for adapter tests)
# ---------------------------------------------------------------------------


class FakeSectionNotFoundError(KeyError):
    """Mirrors k1.sessionstate.manager.SectionNotFoundError."""

    def __init__(self, section: str) -> None:
        self.section = section
        super().__init__(f"Section '{section}' not found")


class FakeSection:
    """Minimal section stub with to_dict()."""

    def __init__(self, name: str) -> None:
        self._name = name

    def to_dict(self) -> Dict[str, Any]:
        return {"section": self._name, "populated": True}


class FakeSSM:
    """Fake SessionStateManager with configurable section set."""

    def __init__(self, sections: FrozenSet[str]) -> None:
        self._sections = sections

    def get_section(self, name: str) -> FakeSection:
        if name not in self._sections:
            raise FakeSectionNotFoundError(name)
        return FakeSection(name)


# ---------------------------------------------------------------------------
# §1 — ISessionReadPort Protocol surface
# ---------------------------------------------------------------------------


class TestProtocolSurface:
    """Verify ISessionReadPort declares list_sections and snapshot_all."""

    def test_list_sections_in_protocol(self):
        assert hasattr(ISessionReadPort, "list_sections")

    def test_snapshot_all_in_protocol(self):
        assert hasattr(ISessionReadPort, "snapshot_all")

    def test_list_sections_is_async(self):
        import inspect

        method = getattr(ISessionReadPort, "list_sections")
        assert inspect.iscoroutinefunction(method)

    def test_snapshot_all_is_async(self):
        import inspect

        method = getattr(ISessionReadPort, "snapshot_all")
        assert inspect.iscoroutinefunction(method)

    def test_adapter_satisfies_protocol(self):
        """SessionReadAdapter is runtime_checkable against ISessionReadPort."""
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        assert isinstance(adapter, ISessionReadPort)


# ---------------------------------------------------------------------------
# §2 — list_sections()
# ---------------------------------------------------------------------------


class TestListSections:
    """Test SessionReadAdapter.list_sections()."""

    @pytest.mark.asyncio
    async def test_returns_frozenset(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        with patch(
            "k1.memory_writer.adapters.session_read_adapter.ALL_SECTIONS",
            ALL_15_SECTIONS,
            create=True,
        ):
            # Patch the import inside the method
            with patch(
                "k1.sessionstate.sizetracker.ALL_SECTIONS",
                ALL_15_SECTIONS,
            ):
                result = await adapter.list_sections()
        assert isinstance(result, frozenset)

    @pytest.mark.asyncio
    async def test_returns_all_15_sections(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.list_sections()
        assert result == ALL_15_SECTIONS
        assert len(result) == 15

    @pytest.mark.asyncio
    async def test_includes_telemetry_and_artifacts_warm(self):
        """list_sections() returns ALL sections, including skipped ones."""
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.list_sections()
        assert "telemetry" in result
        assert "artifacts_warm" in result


# ---------------------------------------------------------------------------
# §3 — snapshot_all()
# ---------------------------------------------------------------------------


class TestSnapshotAll:
    """Test SessionReadAdapter.snapshot_all()."""

    @pytest.mark.asyncio
    async def test_returns_all_except_excluded(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        exclude = frozenset({"telemetry", "artifacts_warm"})
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.snapshot_all(exclude=exclude)
        assert "telemetry" not in result
        assert "artifacts_warm" not in result
        assert len(result) == 13

    @pytest.mark.asyncio
    async def test_no_exclude_returns_all(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.snapshot_all()
        assert len(result) == 15

    @pytest.mark.asyncio
    async def test_exclude_empty_frozenset(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.snapshot_all(exclude=frozenset())
        assert len(result) == 15

    @pytest.mark.asyncio
    async def test_result_keys_match_non_excluded(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        exclude = frozenset({"telemetry", "artifacts_warm"})
        expected = ALL_15_SECTIONS - exclude
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.snapshot_all(exclude=exclude)
        assert set(result.keys()) == expected

    @pytest.mark.asyncio
    async def test_each_section_has_data(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.snapshot_all(exclude=frozenset({"telemetry"}))
        for name, data in result.items():
            assert isinstance(data, dict)
            assert data["section"] == name

    @pytest.mark.asyncio
    async def test_missing_section_omitted(self):
        """If SSM doesn't have a section, snapshot_all omits it."""
        partial = ALL_15_SECTIONS - {"clarifications"}
        adapter = SessionReadAdapter(manager=FakeSSM(partial))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            ALL_15_SECTIONS,
        ):
            result = await adapter.snapshot_all()
        assert "clarifications" not in result
        assert len(result) == 14


# ---------------------------------------------------------------------------
# §4 — New sections auto-included
# ---------------------------------------------------------------------------


class TestNewSectionAutoIncluded:
    """New SS sections appear automatically without config changes."""

    @pytest.mark.asyncio
    async def test_new_section_included(self):
        """A hypothetical new section is automatically picked up."""
        extended = ALL_15_SECTIONS | {"future_section"}
        adapter = SessionReadAdapter(manager=FakeSSM(extended))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            extended,
        ):
            result = await adapter.snapshot_all()
        assert "future_section" in result

    @pytest.mark.asyncio
    async def test_new_section_excluded_if_in_skip(self):
        """A new section can be excluded via skip_sections."""
        extended = ALL_15_SECTIONS | {"future_section"}
        adapter = SessionReadAdapter(manager=FakeSSM(extended))
        with patch(
            "k1.sessionstate.sizetracker.ALL_SECTIONS",
            extended,
        ):
            result = await adapter.snapshot_all(exclude=frozenset({"future_section"}))
        assert "future_section" not in result


# ---------------------------------------------------------------------------
# §5 — MWConfig skip_sections
# ---------------------------------------------------------------------------


class TestConfigSkipSections:
    """MWConfig.skip_sections replaces old hot/warm hardcoded lists."""

    def test_default_skip_sections(self):
        cfg = MWConfig()
        assert cfg.skip_sections == frozenset({"telemetry", "artifacts_warm"})

    def test_skip_sections_is_frozenset(self):
        cfg = MWConfig()
        assert isinstance(cfg.skip_sections, frozenset)

    def test_custom_skip_sections(self):
        cfg = MWConfig(skip_sections=frozenset({"meta", "control"}))
        assert cfg.skip_sections == frozenset({"meta", "control"})

    def test_empty_skip_sections(self):
        cfg = MWConfig(skip_sections=frozenset())
        assert cfg.skip_sections == frozenset()

    def test_default_skip_sections_constant(self):
        assert _DEFAULT_SKIP_SECTIONS == frozenset({"telemetry", "artifacts_warm"})

    def test_phantom_sections_constant(self):
        assert _PHANTOM_SECTIONS == frozenset({"affective_baseline", "ifl"})

    def test_no_session_sections_hot_field(self):
        """Old hot/warm fields are removed."""
        assert not hasattr(MWConfig, "session_sections_hot")

    def test_no_session_sections_warm_field(self):
        assert not hasattr(MWConfig, "session_sections_warm")

    def test_no_all_sections_property(self):
        assert not hasattr(MWConfig(), "all_sections")


# ---------------------------------------------------------------------------
# §6 — Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Existing snapshot() and read_section() still work."""

    @pytest.mark.asyncio
    async def test_snapshot_explicit_sections(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        result = await adapter.snapshot(["persona", "control"])
        assert set(result.keys()) == {"persona", "control"}

    @pytest.mark.asyncio
    async def test_read_section_returns_data(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        result = await adapter.read_section("persona")
        assert result is not None
        assert result["section"] == "persona"

    @pytest.mark.asyncio
    async def test_read_section_unknown_returns_none(self):
        adapter = SessionReadAdapter(manager=FakeSSM(ALL_15_SECTIONS))
        result = await adapter.read_section("nonexistent_section")
        assert result is None
