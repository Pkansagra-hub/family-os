"""Tests for SessionReadAdapter (E-0.5.6).

Covers I-0.5.6.1 + I-0.5.6.2:
  - SessionReadAdapter implements MW's ISessionReadPort
  - snapshot() reads multiple sections, omits missing
  - read_section() reads single section, returns None for unknown
  - Phantom sections (affective_baseline, ifl) return None gracefully
  - All 11 real SS sections that MW requests are readable
  - to_dict() conversion from section objects
  - MW-02: latency <1ms for lock-free reads
  - Protocol conformance via runtime_checkable

References:
  - E-0.5.6: SessionState->MemoryWriter Missing Adapter
  - k1/memory_writer/ports/session_read_port.py (ISessionReadPort)
  - k1/memory_writer/adapters/session_read_adapter.py (SessionReadAdapter)
  - k1/memory_writer/config.py (MW section lists)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from k1.memory_writer.adapters.session_read_adapter import SessionReadAdapter
from k1.memory_writer.ports.session_read_port import ISessionReadPort

# ---------------------------------------------------------------------------
# MW's configured sections (section-agnostic since E-MW-0.3)
# For backward-compat tests, use the known 13 sections MW previously read.
# ---------------------------------------------------------------------------
MW_ALL_SECTIONS: List[str] = [
    "beliefs_active",
    "beliefs_history",
    "history_active",
    "history_recent",
    "affective_now",
    "affective_baseline",
    "narrative_active",
    "scoreboard",
    "control",
    "persona",
    "task_state",
    "ifl",
    "meta",
]

# Sections that exist in SessionState (11 of MW's 13)
REAL_SS_SECTIONS: List[str] = [
    "beliefs_active",
    "beliefs_history",
    "history_active",
    "history_recent",
    "affective_now",
    "narrative_active",
    "scoreboard",
    "control",
    "persona",
    "task_state",
    "meta",
]

# Phantom sections: MW config references these but SS does not have them
PHANTOM_SECTIONS: List[str] = [
    "affective_baseline",
    "ifl",
]


# ---------------------------------------------------------------------------
# Fake SessionStateManager
# ---------------------------------------------------------------------------


class FakeSectionNotFoundError(KeyError):
    """Mirrors k1.sessionstate.manager.SectionNotFoundError."""

    def __init__(self, section: str) -> None:
        self.section = section
        super().__init__(f"Section '{section}' not found")


class FakeSection:
    """Minimal section stub with to_dict()."""

    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._name = name
        self._data = data if data is not None else {"section": name, "populated": True}

    def to_dict(self) -> Dict[str, Any]:
        return self._data.copy()


class FakeSessionStateManager:
    """Minimal SSM stub for adapter tests.

    Holds a dict of section_name -> FakeSection.
    Raises FakeSectionNotFoundError for unknown names, matching
    the real SSM's behavior.
    """

    def __init__(
        self,
        sections: Optional[Dict[str, FakeSection]] = None,
    ) -> None:
        self._sections = sections or {}

    def get_section(self, name: str) -> Any:
        if name not in self._sections:
            raise FakeSectionNotFoundError(name)
        return self._sections[name]

    @classmethod
    def with_real_sections(cls) -> "FakeSessionStateManager":
        """Create a manager with all 11 real SS sections that MW uses."""
        sections = {}
        for name in REAL_SS_SECTIONS:
            sections[name] = FakeSection(name)
        return cls(sections=sections)

    @classmethod
    def with_custom_data(cls, section_data: Dict[str, Dict[str, Any]]) -> "FakeSessionStateManager":
        """Create a manager with custom section data."""
        sections = {name: FakeSection(name, data) for name, data in section_data.items()}
        return cls(sections=sections)


# ===========================================================================
# Protocol conformance
# ===========================================================================


class TestSessionReadAdapterProtocol:
    """SessionReadAdapter satisfies MW's ISessionReadPort."""

    def test_isinstance_check(self) -> None:
        """Adapter passes runtime_checkable Protocol check."""
        adapter = SessionReadAdapter(FakeSessionStateManager())
        assert isinstance(adapter, ISessionReadPort)

    def test_has_snapshot_method(self) -> None:
        adapter = SessionReadAdapter(FakeSessionStateManager())
        assert callable(getattr(adapter, "snapshot", None))

    def test_has_read_section_method(self) -> None:
        adapter = SessionReadAdapter(FakeSessionStateManager())
        assert callable(getattr(adapter, "read_section", None))

    def test_no_write_methods(self) -> None:
        """MW-01: adapter exposes NO write methods."""
        adapter = SessionReadAdapter(FakeSessionStateManager())
        write_indicators = [
            "write",
            "set",
            "put",
            "update",
            "delete",
            "remove",
            "mutate",
            "clear",
            "reset",
        ]
        public_methods = [
            m for m in dir(adapter) if not m.startswith("_") and callable(getattr(adapter, m))
        ]
        for method_name in public_methods:
            for indicator in write_indicators:
                assert (
                    indicator not in method_name.lower()
                ), f"MW-01 violation: write-like method '{method_name}' found"


# ===========================================================================
# read_section() tests
# ===========================================================================


class TestReadSection:
    """read_section() retrieves a single section as a dict."""

    @pytest.mark.asyncio
    async def test_read_existing_section(self) -> None:
        """Returns dict for a section that exists."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("beliefs_active")
        assert isinstance(result, dict)
        assert result["section"] == "beliefs_active"

    @pytest.mark.asyncio
    async def test_read_unknown_section_returns_none(self) -> None:
        """Returns None for a section name that SS doesn't recognize."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("totally_invalid")
        assert result is None

    @pytest.mark.asyncio
    async def test_phantom_affective_baseline_returns_none(self) -> None:
        """affective_baseline is in MW config but not in SS -> None."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("affective_baseline")
        assert result is None

    @pytest.mark.asyncio
    async def test_phantom_ifl_returns_none(self) -> None:
        """ifl is in MW config but not in SS -> None."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("ifl")
        assert result is None

    @pytest.mark.asyncio
    async def test_read_all_real_sections(self) -> None:
        """All 11 real SS sections that MW uses are individually readable."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        for name in REAL_SS_SECTIONS:
            result = await adapter.read_section(name)
            assert result is not None, f"Section '{name}' should be readable"
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_read_section_custom_data(self) -> None:
        """Section data comes from to_dict(), not raw object."""
        manager = FakeSessionStateManager.with_custom_data(
            {
                "persona": {
                    "name": "Mom",
                    "tone": "warm",
                    "preferences": {"language": "en"},
                },
            }
        )
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("persona")
        assert result == {
            "name": "Mom",
            "tone": "warm",
            "preferences": {"language": "en"},
        }

    @pytest.mark.asyncio
    async def test_read_section_returns_dict_copy(self) -> None:
        """Returned dict is a copy, not a reference to internal state."""
        data = {"key": "value", "nested": {"a": 1}}
        manager = FakeSessionStateManager.with_custom_data({"control": data})
        adapter = SessionReadAdapter(manager)
        result1 = await adapter.read_section("control")
        result2 = await adapter.read_section("control")
        assert result1 == result2
        assert result1 is not result2  # different objects

    @pytest.mark.asyncio
    async def test_section_obj_without_to_dict_returns_none(self) -> None:
        """If section object lacks to_dict(), returns None gracefully."""

        class BareSection:
            pass

        manager = FakeSessionStateManager(
            sections={"meta": BareSection()}  # type: ignore[dict-item]
        )
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("meta")
        assert result is None

    @pytest.mark.asyncio
    async def test_section_obj_as_raw_dict(self) -> None:
        """If get_section returns a plain dict, adapter returns it."""

        class DictManager:
            def get_section(self, name: str) -> Dict[str, Any]:
                return {"raw": True, "section": name}

        adapter = SessionReadAdapter(DictManager())
        result = await adapter.read_section("control")
        assert result == {"raw": True, "section": "control"}


# ===========================================================================
# snapshot() tests
# ===========================================================================


class TestSnapshot:
    """snapshot() retrieves multiple sections in a single call."""

    @pytest.mark.asyncio
    async def test_snapshot_all_real_sections(self) -> None:
        """Snapshot of all 11 real sections returns all of them."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.snapshot(REAL_SS_SECTIONS)
        assert len(result) == len(REAL_SS_SECTIONS)
        for name in REAL_SS_SECTIONS:
            assert name in result
            assert isinstance(result[name], dict)

    @pytest.mark.asyncio
    async def test_snapshot_omits_phantom_sections(self) -> None:
        """Phantom sections are silently omitted from snapshot result."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        # Request all 13 MW sections (includes 2 phantoms)
        result = await adapter.snapshot(MW_ALL_SECTIONS)
        # Only 11 real sections should be present
        assert len(result) == len(REAL_SS_SECTIONS)
        for phantom in PHANTOM_SECTIONS:
            assert phantom not in result

    @pytest.mark.asyncio
    async def test_snapshot_empty_list(self) -> None:
        """Empty section list returns empty dict."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.snapshot([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_snapshot_single_section(self) -> None:
        """Single section in list returns single-entry dict."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.snapshot(["scoreboard"])
        assert len(result) == 1
        assert "scoreboard" in result

    @pytest.mark.asyncio
    async def test_snapshot_mixed_real_and_unknown(self) -> None:
        """Mix of real, phantom, and unknown sections: only real ones returned."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.snapshot(
            [
                "beliefs_active",  # real
                "affective_baseline",  # phantom
                "nonexistent_section",  # totally unknown
                "control",  # real
            ]
        )
        assert len(result) == 2
        assert "beliefs_active" in result
        assert "control" in result

    @pytest.mark.asyncio
    async def test_snapshot_preserves_section_data(self) -> None:
        """Snapshot returns correct data for each section."""
        manager = FakeSessionStateManager.with_custom_data(
            {
                "beliefs_active": {"topic": "family", "confidence": 0.9},
                "affective_now": {"valence": 0.7, "arousal": 0.3},
            }
        )
        adapter = SessionReadAdapter(manager)
        result = await adapter.snapshot(["beliefs_active", "affective_now"])
        assert result["beliefs_active"]["topic"] == "family"
        assert result["affective_now"]["valence"] == 0.7

    @pytest.mark.asyncio
    async def test_snapshot_duplicate_sections(self) -> None:
        """Duplicate section names in request still produce one entry."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        result = await adapter.snapshot(["meta", "meta", "meta"])
        assert len(result) == 1
        assert "meta" in result


# ===========================================================================
# MW-02: Latency (<1ms lock-free reads)
# ===========================================================================


class TestLatency:
    """MW-02: reads must complete in <1ms P99."""

    @pytest.mark.asyncio
    async def test_read_section_latency(self) -> None:
        """Single section read completes in <1ms."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        start = time.perf_counter_ns()
        await adapter.read_section("control")
        elapsed_ns = time.perf_counter_ns() - start
        elapsed_ms = elapsed_ns / 1_000_000
        assert elapsed_ms < 1.0, f"read_section took {elapsed_ms:.3f}ms (>1ms MW-02)"

    @pytest.mark.asyncio
    async def test_snapshot_13_sections_latency(self) -> None:
        """Full 13-section snapshot (MW's primary path) completes in <1ms."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        start = time.perf_counter_ns()
        await adapter.snapshot(MW_ALL_SECTIONS)
        elapsed_ns = time.perf_counter_ns() - start
        elapsed_ms = elapsed_ns / 1_000_000
        assert elapsed_ms < 1.0, f"snapshot(13) took {elapsed_ms:.3f}ms (>1ms MW-02)"

    @pytest.mark.asyncio
    async def test_repeated_reads_stable_latency(self) -> None:
        """100 consecutive reads stay under 1ms each (warm path)."""
        manager = FakeSessionStateManager.with_real_sections()
        adapter = SessionReadAdapter(manager)
        # Warm up
        await adapter.read_section("control")
        max_ms = 0.0
        for _ in range(100):
            start = time.perf_counter_ns()
            await adapter.read_section("control")
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
            max_ms = max(max_ms, elapsed_ms)
        assert max_ms < 1.0, f"Max read latency {max_ms:.3f}ms (>1ms MW-02)"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases and error boundaries."""

    @pytest.mark.asyncio
    async def test_empty_section_data(self) -> None:
        """Section with empty dict data returns empty dict (not None)."""
        manager = FakeSessionStateManager.with_custom_data(
            {
                "meta": {},
            }
        )
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("meta")
        assert result == {}
        assert result is not None

    @pytest.mark.asyncio
    async def test_section_with_nested_structure(self) -> None:
        """Complex nested data preserved through to_dict()."""
        complex_data = {
            "intents": [
                {"type": "recall", "confidence": 0.95},
                {"type": "inform", "confidence": 0.3},
            ],
            "domains": {"family": True, "health": False},
            "safety_band": "GREEN",
            "turn_number": 42,
        }
        manager = FakeSessionStateManager.with_custom_data(
            {
                "control": complex_data,
            }
        )
        adapter = SessionReadAdapter(manager)
        result = await adapter.read_section("control")
        assert result["intents"][0]["type"] == "recall"
        assert result["domains"]["family"] is True
        assert result["safety_band"] == "GREEN"
        assert result["turn_number"] == 42

    @pytest.mark.asyncio
    async def test_adapter_is_read_only(self) -> None:
        """Adapter exposes only read methods (MW-01)."""
        adapter = SessionReadAdapter(FakeSessionStateManager())
        public = [m for m in dir(adapter) if not m.startswith("_")]
        assert set(public) == {
            "snapshot",
            "read_section",
            "list_sections",
            "snapshot_all",
            "read_archived_history",
        }

    def test_adapter_uses_slots(self) -> None:
        """Adapter uses __slots__ for memory efficiency."""
        assert hasattr(SessionReadAdapter, "__slots__")
        adapter = SessionReadAdapter(FakeSessionStateManager())
        with pytest.raises(AttributeError):
            adapter.extra_attr = "should fail"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_manager_returning_none_section(self) -> None:
        """If get_section returns None (shouldn't happen but defensive), returns None."""

        class NoneManager:
            def get_section(self, name: str) -> None:
                return None

        adapter = SessionReadAdapter(NoneManager())
        result = await adapter.read_section("anything")
        assert result is None


# =============================================================================
# B1+B2: read_archived_history (cold-archive enriched read for MW)
# =============================================================================


class TestReadArchivedHistory:
    """Tests for the enriched cold-archive read path (B1+B2)."""

    @pytest.mark.asyncio
    async def test_no_cold_archive_returns_empty(self) -> None:
        """When ``cold_archive`` is None the method returns []."""
        adapter = SessionReadAdapter(FakeSessionStateManager())
        assert await adapter.read_archived_history("sess-1") == []

    @pytest.mark.asyncio
    async def test_archive_failure_returns_empty(self) -> None:
        """If the archive raises, the method swallows and returns []."""

        class BoomArchive:
            def restore_all(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("disk")

        adapter = SessionReadAdapter(
            FakeSessionStateManager(), cold_archive=BoomArchive()
        )
        assert await adapter.read_archived_history("sess-1") == []

    @pytest.mark.asyncio
    async def test_returns_dedup_oldest_first(self) -> None:
        """End-to-end: archived FlatBuffer turns are restored, deduped, sorted."""
        from k1.sessionstate.sections.history_active import HistoryActiveSection

        # Build two archive blobs that overlap on turn-2.
        # Use explicit timestamps to ensure ordering survives the per-blob
        # turn_number counters (each section starts counting from 1).
        sec_a = HistoryActiveSection(session_id="sess-x")
        sec_a.add_turn("U1", "A1", turn_id="t-1", timestamp_ms=1_000)
        sec_a.add_turn("U2", "A2", turn_id="t-2", timestamp_ms=2_000)

        sec_b = HistoryActiveSection(session_id="sess-x")
        sec_b.add_turn("U2dup", "A2dup", turn_id="t-2", timestamp_ms=2_000)  # dup
        sec_b.add_turn("U3", "A3", turn_id="t-3", timestamp_ms=3_000)

        from dataclasses import dataclass

        @dataclass
        class _Result:
            success: bool
            data: bytes

        class StubArchive:
            def restore_all(
                self, section: str, session_id: str, limit: int = 100
            ) -> List[Any]:
                assert section == "history_active"
                assert session_id == "sess-x"
                return [
                    _Result(success=True, data=sec_b.to_flatbuffer()),
                    _Result(success=True, data=sec_a.to_flatbuffer()),
                ]

        adapter = SessionReadAdapter(
            FakeSessionStateManager(), cold_archive=StubArchive()
        )
        result = await adapter.read_archived_history("sess-x", limit=50)
        # Three unique turns (t-1, t-2, t-3) ordered oldest-first.
        ids = [t["turn_id"] for t in result]
        assert ids == ["t-1", "t-2", "t-3"]
        # Each has both user_message AND assistant_response (A1+A2 fix).
        for t in result:
            assert "user_message" in t
            assert "assistant_response" in t

    @pytest.mark.asyncio
    async def test_failed_results_skipped(self) -> None:
        """Failed RestoreResult entries are skipped, successful ones return."""
        from dataclasses import dataclass

        from k1.sessionstate.sections.history_active import HistoryActiveSection

        sec = HistoryActiveSection(session_id="sess-y")
        sec.add_turn("U", "A", turn_id="t-1")

        @dataclass
        class _Result:
            success: bool
            data: Optional[bytes]

        class MixedArchive:
            def restore_all(self, section: str, session_id: str, limit: int = 100):
                return [
                    _Result(success=False, data=None),
                    _Result(success=True, data=sec.to_flatbuffer()),
                    _Result(success=True, data=None),
                ]

        adapter = SessionReadAdapter(
            FakeSessionStateManager(), cold_archive=MixedArchive()
        )
        result = await adapter.read_archived_history("sess-y")
        assert len(result) == 1
        assert result[0]["turn_id"] == "t-1"
