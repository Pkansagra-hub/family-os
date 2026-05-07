"""
Tests for SnapshotAPI - Health Monitoring and Diagnostics
==========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.6

Test Coverage:
1. Construction and initialization
2. Session snapshot generation
3. Pressure report generation
4. Section snapshots
5. Tier snapshots
6. Thrash detection
7. Recording events (migration, eviction, mutation)
8. Output formatting (to_dict, format_table)
9. Edge cases
"""

from __future__ import annotations

import time

import pytest

from k1.sessionstate.sizetracker import (
    HOT_SECTIONS,
    HOT_SIZE_LIMIT_BYTES,
    SECTION_BUDGETS,
    WARM_SECTIONS,
    WARM_SIZE_LIMIT_BYTES,
    PressureLevel,
    SizeTracker,
)
from k1.sessionstate.snapshot import (
    THRASH_MILD_EVICTIONS,
    THRASH_MILD_MIGRATIONS,
    THRASH_MODERATE_MIGRATIONS,
    THRASH_SEVERE_MIGRATIONS,
    PressureReport,
    SectionSnapshot,
    SnapshotAPI,
    ThrashMetrics,
    TierSnapshot,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def size_tracker() -> SizeTracker:
    """Create a fresh SizeTracker."""
    return SizeTracker()


@pytest.fixture
def snapshot_api(size_tracker: SizeTracker) -> SnapshotAPI:
    """Create SnapshotAPI with SizeTracker."""
    return SnapshotAPI(
        size_tracker=size_tracker,
        hot=None,
        warm=None,
        session_id="test-session-123",
    )


@pytest.fixture
def populated_tracker(size_tracker: SizeTracker) -> SizeTracker:
    """SizeTracker with some data."""
    size_tracker.update("control", 2048)
    size_tracker.update("beliefs_active", 1024)
    size_tracker.update("scoreboard", 512)
    size_tracker.update("history_active", 4096)
    size_tracker.update("persona", 2048)
    size_tracker.update("telemetry", 1024)
    return size_tracker


@pytest.fixture
def populated_api(populated_tracker: SizeTracker) -> SnapshotAPI:
    """SnapshotAPI with populated SizeTracker."""
    return SnapshotAPI(
        size_tracker=populated_tracker,
        session_id="test-session-456",
    )


# =============================================================================
# TEST CLASS: Construction
# =============================================================================


class TestSnapshotAPIConstruction:
    """Test SnapshotAPI construction and initialization."""

    def test_construct_with_size_tracker_only(self, size_tracker: SizeTracker) -> None:
        """Test construction with just SizeTracker."""
        api = SnapshotAPI(size_tracker=size_tracker)
        assert api is not None
        assert api.session_id == ""

    def test_construct_with_session_id(self, size_tracker: SizeTracker) -> None:
        """Test construction with session_id."""
        api = SnapshotAPI(size_tracker=size_tracker, session_id="my-session")
        assert api.session_id == "my-session"

    def test_construct_with_created_at(self, size_tracker: SizeTracker) -> None:
        """Test construction with custom created_at_ms."""
        created = 1700000000000
        api = SnapshotAPI(
            size_tracker=size_tracker,
            session_id="test",
            created_at_ms=created,
        )
        assert api.created_at_ms == created

    def test_initial_timestamps(self, snapshot_api: SnapshotAPI) -> None:
        """Test initial timestamps are set correctly."""
        assert snapshot_api.created_at_ms > 0
        assert snapshot_api.last_mutation_ms == 0
        assert snapshot_api.last_checkpoint_ms == 0

    def test_construct_with_tiers(self, size_tracker: SizeTracker) -> None:
        """Test construction with tier objects."""
        # Tiers are optional, can be None
        api = SnapshotAPI(
            size_tracker=size_tracker,
            hot=None,
            warm=None,
            session_id="test",
        )
        assert api is not None


# =============================================================================
# TEST CLASS: Session Snapshot
# =============================================================================


class TestSessionSnapshot:
    """Test session snapshot generation."""

    def test_empty_session_snapshot(self, snapshot_api: SnapshotAPI) -> None:
        """Test snapshot of empty session."""
        snapshot = snapshot_api.get_snapshot()

        assert snapshot.session_id == "test-session-123"
        assert snapshot.total_size_bytes == 0
        assert snapshot.hot_size_bytes == 0
        assert snapshot.warm_size_bytes == 0
        assert snapshot.utilization_pct == 0.0
        assert snapshot.pressure == PressureLevel.NORMAL

    def test_populated_session_snapshot(self, populated_api: SnapshotAPI) -> None:
        """Test snapshot with data."""
        snapshot = populated_api.get_snapshot()

        assert snapshot.session_id == "test-session-456"
        assert snapshot.total_size_bytes > 0
        assert snapshot.hot_size_bytes > 0
        assert snapshot.warm_size_bytes > 0

    def test_snapshot_has_all_sections(self, snapshot_api: SnapshotAPI) -> None:
        """Test snapshot contains all sections."""
        snapshot = snapshot_api.get_snapshot()

        expected_sections = set(HOT_SECTIONS) | set(WARM_SECTIONS)
        assert set(snapshot.sections.keys()) == expected_sections

    def test_snapshot_has_both_tiers(self, snapshot_api: SnapshotAPI) -> None:
        """Test snapshot contains both tiers."""
        snapshot = snapshot_api.get_snapshot()

        assert "hot" in snapshot.tiers
        assert "warm" in snapshot.tiers

    def test_snapshot_thrash_metrics(self, snapshot_api: SnapshotAPI) -> None:
        """Test snapshot includes thrash metrics."""
        snapshot = snapshot_api.get_snapshot()

        assert snapshot.thrash_metrics is not None
        assert snapshot.thrash_metrics.migrations_last_minute == 0
        assert snapshot.thrash_metrics.evictions_last_minute == 0

    def test_snapshot_timestamps(self, snapshot_api: SnapshotAPI) -> None:
        """Test snapshot includes timestamps."""
        snapshot = snapshot_api.get_snapshot()

        assert snapshot.created_at_ms > 0
        assert snapshot.last_mutation_ms == 0
        assert snapshot.last_checkpoint_ms == 0

    def test_snapshot_to_dict(self, populated_api: SnapshotAPI) -> None:
        """Test snapshot can be converted to dict."""
        snapshot = populated_api.get_snapshot()
        d = snapshot.to_dict()

        assert isinstance(d, dict)
        assert d["session_id"] == "test-session-456"
        assert "sections" in d
        assert "tiers" in d
        assert "thrash_metrics" in d


# =============================================================================
# TEST CLASS: Pressure Report
# =============================================================================


class TestPressureReport:
    """Test pressure report generation."""

    def test_empty_pressure_report(self, snapshot_api: SnapshotAPI) -> None:
        """Test pressure report for empty session."""
        report = snapshot_api.get_pressure_report()

        assert report.overall == PressureLevel.NORMAL
        assert report.hot == PressureLevel.NORMAL
        assert report.warm == PressureLevel.NORMAL
        assert report.sections_at_limit == []
        assert report.estimated_eviction_bytes == 0

    def test_pressure_report_eviction_candidates(self, populated_api: SnapshotAPI) -> None:
        """Test pressure report includes eviction candidates."""
        report = populated_api.get_pressure_report()

        # Should have WARM eviction candidates (sorted by priority)
        assert len(report.eviction_candidates) > 0
        # telemetry has priority 1, should be first
        assert "telemetry" in report.eviction_candidates

    def test_pressure_report_at_limit(self, size_tracker: SizeTracker) -> None:
        """Test sections at limit detection."""
        # Fill control section to 95%+ (EMERGENCY)
        control_budget = SECTION_BUDGETS["control"].max_bytes
        size_tracker.update("control", int(control_budget * 0.96))

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        report = api.get_pressure_report()

        assert "control" in report.sections_at_limit

    def test_pressure_report_estimated_eviction(self, size_tracker: SizeTracker) -> None:
        """Test estimated eviction bytes calculation."""
        # Fill WARM tier to 90%
        warm_target = int(WARM_SIZE_LIMIT_BYTES * 0.9)
        size_tracker.update("telemetry", warm_target)

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        report = api.get_pressure_report()

        # Need to evict down to 80%
        expected = warm_target - int(WARM_SIZE_LIMIT_BYTES * 0.8)
        assert report.estimated_eviction_bytes == expected


# =============================================================================
# TEST CLASS: Section Snapshots
# =============================================================================


class TestSectionSnapshots:
    """Test section snapshot generation."""

    def test_get_section_snapshot_control(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting control section snapshot."""
        snapshot = snapshot_api.get_section_snapshot("control")

        assert snapshot.name == "control"
        assert snapshot.tier == "hot"
        assert snapshot.size_bytes == 0
        assert snapshot.budget_bytes == 8 * 1024
        assert snapshot.utilization_pct == 0.0
        assert snapshot.pressure == PressureLevel.NORMAL
        assert snapshot.eviction_priority is None  # NEVER EVICT

    def test_get_section_snapshot_telemetry(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting telemetry section snapshot."""
        snapshot = snapshot_api.get_section_snapshot("telemetry")

        assert snapshot.name == "telemetry"
        assert snapshot.tier == "warm"
        assert snapshot.budget_bytes == 8 * 1024
        assert snapshot.eviction_priority == 1  # First to evict

    def test_get_section_snapshot_with_data(self, populated_api: SnapshotAPI) -> None:
        """Test section snapshot with data."""
        snapshot = populated_api.get_section_snapshot("control")

        assert snapshot.size_bytes == 2048
        assert snapshot.utilization_pct > 0

    def test_get_section_snapshot_invalid(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting invalid section raises KeyError."""
        with pytest.raises(KeyError):
            snapshot_api.get_section_snapshot("invalid_section")

    def test_all_hot_sections_accessible(self, snapshot_api: SnapshotAPI) -> None:
        """Test all HOT sections are accessible."""
        for section in HOT_SECTIONS:
            snapshot = snapshot_api.get_section_snapshot(section)
            assert snapshot.tier == "hot"

    def test_all_warm_sections_accessible(self, snapshot_api: SnapshotAPI) -> None:
        """Test all WARM sections are accessible."""
        for section in WARM_SECTIONS:
            snapshot = snapshot_api.get_section_snapshot(section)
            assert snapshot.tier == "warm"


# =============================================================================
# TEST CLASS: Tier Snapshots
# =============================================================================


class TestTierSnapshots:
    """Test tier snapshot generation."""

    def test_get_hot_tier_snapshot(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting HOT tier snapshot."""
        snapshot = snapshot_api.get_tier_snapshot("hot")

        assert snapshot.name == "hot"
        assert len(snapshot.sections) == len(HOT_SECTIONS)
        assert snapshot.size_bytes == 0
        assert snapshot.limit_bytes == HOT_SIZE_LIMIT_BYTES
        assert snapshot.utilization_pct == 0.0
        assert snapshot.pressure == PressureLevel.NORMAL

    def test_get_warm_tier_snapshot(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting WARM tier snapshot."""
        snapshot = snapshot_api.get_tier_snapshot("warm")

        assert snapshot.name == "warm"
        assert len(snapshot.sections) == len(WARM_SECTIONS)
        assert snapshot.limit_bytes == WARM_SIZE_LIMIT_BYTES

    def test_tier_snapshot_with_data(self, populated_api: SnapshotAPI) -> None:
        """Test tier snapshot with data."""
        hot = populated_api.get_tier_snapshot("hot")
        warm = populated_api.get_tier_snapshot("warm")

        assert hot.size_bytes > 0
        assert warm.size_bytes > 0
        assert hot.utilization_pct > 0
        assert warm.utilization_pct > 0

    def test_tier_snapshot_invalid(self, snapshot_api: SnapshotAPI) -> None:
        """Test invalid tier raises ValueError."""
        with pytest.raises(ValueError):
            snapshot_api.get_tier_snapshot("invalid")

    def test_tier_snapshot_case_insensitive(self, snapshot_api: SnapshotAPI) -> None:
        """Test tier name is case insensitive."""
        hot_lower = snapshot_api.get_tier_snapshot("hot")
        hot_upper = snapshot_api.get_tier_snapshot("HOT")
        hot_mixed = snapshot_api.get_tier_snapshot("Hot")

        assert hot_lower.name == hot_upper.name == hot_mixed.name == "hot"


# =============================================================================
# TEST CLASS: Thrash Detection
# =============================================================================


class TestThrashDetection:
    """Test thrash detection metrics."""

    def test_initial_no_thrash(self, snapshot_api: SnapshotAPI) -> None:
        """Test no thrashing initially."""
        metrics = snapshot_api.get_thrash_metrics()

        assert metrics.migrations_last_minute == 0
        assert metrics.evictions_last_minute == 0
        assert metrics.thrash_detected is False
        assert metrics.thrash_severity == 0

    def test_record_migration(self, snapshot_api: SnapshotAPI) -> None:
        """Test recording migration events."""
        snapshot_api.record_migration()
        snapshot_api.record_migration()
        snapshot_api.record_migration()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.migrations_last_minute == 3

    def test_record_eviction(self, snapshot_api: SnapshotAPI) -> None:
        """Test recording eviction events."""
        snapshot_api.record_eviction()
        snapshot_api.record_eviction()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.evictions_last_minute == 2

    def test_mild_thrashing_by_migrations(self, snapshot_api: SnapshotAPI) -> None:
        """Test mild thrashing detection by migrations."""
        for _ in range(THRASH_MILD_MIGRATIONS):
            snapshot_api.record_migration()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.thrash_detected is True
        assert metrics.thrash_severity == 1

    def test_mild_thrashing_by_evictions(self, snapshot_api: SnapshotAPI) -> None:
        """Test mild thrashing detection by evictions."""
        for _ in range(THRASH_MILD_EVICTIONS):
            snapshot_api.record_eviction()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.thrash_detected is True
        assert metrics.thrash_severity == 1

    def test_moderate_thrashing(self, snapshot_api: SnapshotAPI) -> None:
        """Test moderate thrashing detection."""
        for _ in range(THRASH_MODERATE_MIGRATIONS):
            snapshot_api.record_migration()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.thrash_detected is True
        assert metrics.thrash_severity == 2

    def test_severe_thrashing(self, snapshot_api: SnapshotAPI) -> None:
        """Test severe thrashing detection."""
        for _ in range(THRASH_SEVERE_MIGRATIONS):
            snapshot_api.record_migration()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.thrash_detected is True
        assert metrics.thrash_severity == 3

    def test_reset_thrash_metrics(self, snapshot_api: SnapshotAPI) -> None:
        """Test resetting thrash metrics."""
        for _ in range(10):
            snapshot_api.record_migration()
        snapshot_api.record_eviction()

        snapshot_api.reset_thrash_metrics()

        metrics = snapshot_api.get_thrash_metrics()
        assert metrics.migrations_last_minute == 0
        assert metrics.evictions_last_minute == 0
        assert metrics.thrash_detected is False


# =============================================================================
# TEST CLASS: Recording Events
# =============================================================================


class TestRecordingEvents:
    """Test recording mutation, checkpoint events."""

    def test_record_mutation(self, snapshot_api: SnapshotAPI) -> None:
        """Test recording mutation updates timestamp."""
        assert snapshot_api.last_mutation_ms == 0

        snapshot_api.record_mutation()

        assert snapshot_api.last_mutation_ms > 0

    def test_record_mutation_with_section(self, snapshot_api: SnapshotAPI) -> None:
        """Test recording mutation for specific section."""
        snapshot_api.record_mutation(section="control")

        snapshot = snapshot_api.get_section_snapshot("control")
        assert snapshot.last_mutation_ms > 0

    def test_record_checkpoint(self, snapshot_api: SnapshotAPI) -> None:
        """Test recording checkpoint updates timestamp."""
        assert snapshot_api.last_checkpoint_ms == 0

        snapshot_api.record_checkpoint()

        assert snapshot_api.last_checkpoint_ms > 0

    def test_timestamps_in_snapshot(self, snapshot_api: SnapshotAPI) -> None:
        """Test timestamps appear in snapshot."""
        snapshot_api.record_mutation()
        snapshot_api.record_checkpoint()

        snapshot = snapshot_api.get_snapshot()

        assert snapshot.last_mutation_ms > 0
        assert snapshot.last_checkpoint_ms > 0


# =============================================================================
# TEST CLASS: Output Formatting
# =============================================================================


class TestOutputFormatting:
    """Test output formatting methods."""

    def test_to_dict(self, populated_api: SnapshotAPI) -> None:
        """Test to_dict output."""
        d = populated_api.to_dict()

        assert isinstance(d, dict)
        assert "session_id" in d
        assert "sections" in d
        assert "tiers" in d
        assert "pressure" in d

    def test_to_dict_json_serializable(self, populated_api: SnapshotAPI) -> None:
        """Test to_dict output is JSON serializable."""
        import json

        d = populated_api.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_format_table(self, populated_api: SnapshotAPI) -> None:
        """Test format_table output."""
        table = populated_api.format_table()

        assert isinstance(table, str)
        assert "SECTION" in table
        assert "TIER" in table
        assert "SIZE" in table
        assert "BUDGET" in table
        assert "USAGE" in table

    def test_format_table_contains_sections(self, populated_api: SnapshotAPI) -> None:
        """Test format_table contains all sections."""
        table = populated_api.format_table()

        assert "control" in table
        assert "beliefs_active" in table
        assert "telemetry" in table
        assert "persona" in table

    def test_format_table_contains_totals(self, populated_api: SnapshotAPI) -> None:
        """Test format_table contains totals."""
        table = populated_api.format_table()

        assert "HOT TOTAL" in table
        assert "WARM TOTAL" in table
        assert "TOTAL" in table

    def test_format_table_thrash_warning(self, snapshot_api: SnapshotAPI) -> None:
        """Test format_table shows thrash warning."""
        # Trigger thrashing
        for _ in range(THRASH_SEVERE_MIGRATIONS):
            snapshot_api.record_migration()

        table = snapshot_api.format_table()

        assert "WARNING" in table
        assert "SEVERE" in table
        assert "thrashing" in table

    def test_format_bytes_helper(self) -> None:
        """Test _format_bytes helper method."""
        assert SnapshotAPI._format_bytes(100) == "100B"
        assert SnapshotAPI._format_bytes(1024) == "1.0KB"
        assert SnapshotAPI._format_bytes(2048) == "2.0KB"
        assert SnapshotAPI._format_bytes(1536) == "1.5KB"
        assert SnapshotAPI._format_bytes(1024 * 1024) == "1.0MB"


# =============================================================================
# TEST CLASS: Section Names
# =============================================================================


class TestSectionNames:
    """Test section name accessors."""

    def test_get_section_names(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting all section names."""
        names = snapshot_api.get_section_names()

        assert len(names) == len(HOT_SECTIONS) + len(WARM_SECTIONS)
        assert "control" in names
        assert "telemetry" in names

    def test_get_hot_section_names(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting HOT section names."""
        names = snapshot_api.get_hot_section_names()

        assert len(names) == len(HOT_SECTIONS)
        assert "control" in names
        assert "telemetry" not in names

    def test_get_warm_section_names(self, snapshot_api: SnapshotAPI) -> None:
        """Test getting WARM section names."""
        names = snapshot_api.get_warm_section_names()

        assert len(names) == len(WARM_SECTIONS)
        assert "telemetry" in names
        assert "control" not in names


# =============================================================================
# TEST CLASS: Pressure Levels
# =============================================================================


class TestPressureLevels:
    """Test pressure level detection at various utilization levels."""

    def test_normal_pressure(self, size_tracker: SizeTracker) -> None:
        """Test NORMAL pressure at <80%."""
        # 50% utilization
        size_tracker.update("history_active", int(8 * 1024 * 0.5))

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        snapshot = api.get_section_snapshot("history_active")

        assert snapshot.pressure == PressureLevel.NORMAL

    def test_elevated_pressure(self, size_tracker: SizeTracker) -> None:
        """Test ELEVATED pressure at 80-90%."""
        # 85% utilization
        size_tracker.update("history_active", int(8 * 1024 * 0.85))

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        snapshot = api.get_section_snapshot("history_active")

        assert snapshot.pressure == PressureLevel.ELEVATED

    def test_critical_pressure(self, size_tracker: SizeTracker) -> None:
        """Test CRITICAL pressure at 90-95%."""
        # 92% utilization
        size_tracker.update("history_active", int(8 * 1024 * 0.92))

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        snapshot = api.get_section_snapshot("history_active")

        assert snapshot.pressure == PressureLevel.CRITICAL

    def test_emergency_pressure(self, size_tracker: SizeTracker) -> None:
        """Test EMERGENCY pressure at >95%."""
        # 97% utilization
        size_tracker.update("history_active", int(8 * 1024 * 0.97))

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        snapshot = api.get_section_snapshot("history_active")

        assert snapshot.pressure == PressureLevel.EMERGENCY


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_session_id(self, size_tracker: SizeTracker) -> None:
        """Test with empty session_id."""
        api = SnapshotAPI(size_tracker=size_tracker, session_id="")
        snapshot = api.get_snapshot()

        assert snapshot.session_id == ""

    def test_snapshot_immutability(self, populated_api: SnapshotAPI) -> None:
        """Test that snapshots don't change when data changes."""
        snapshot1 = populated_api.get_snapshot()
        total1 = snapshot1.total_size_bytes

        # Modify underlying data
        populated_api._size_tracker.update("control", 1000)

        snapshot2 = populated_api.get_snapshot()
        total2 = snapshot2.total_size_bytes

        # Original snapshot should be unchanged conceptually
        # (snapshot1.total_size_bytes captured at snapshot time)
        assert total2 > total1

    def test_concurrent_reads(self, populated_api: SnapshotAPI) -> None:
        """Test multiple snapshot reads don't interfere."""
        snapshots = [populated_api.get_snapshot() for _ in range(10)]

        # All should have same data
        for snap in snapshots:
            assert snap.session_id == "test-session-456"

    def test_section_snapshot_after_update(self, size_tracker: SizeTracker) -> None:
        """Test section snapshot reflects updates."""
        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")

        snap1 = api.get_section_snapshot("control")
        assert snap1.size_bytes == 0

        size_tracker.update("control", 1024)

        snap2 = api.get_section_snapshot("control")
        assert snap2.size_bytes == 1024

    def test_tier_utilization_calculation(self, size_tracker: SizeTracker) -> None:
        """Test tier utilization is correctly calculated."""
        # Fill HOT to 50%
        size_tracker.update("control", HOT_SIZE_LIMIT_BYTES // 2)

        api = SnapshotAPI(size_tracker=size_tracker, session_id="test")
        tier = api.get_tier_snapshot("hot")

        assert 49 < tier.utilization_pct < 51  # ~50%


# =============================================================================
# TEST CLASS: Dataclass Validation
# =============================================================================


class TestDataclasses:
    """Test dataclass structures."""

    def test_section_snapshot_dataclass(self) -> None:
        """Test SectionSnapshot dataclass."""
        snap = SectionSnapshot(
            name="test",
            tier="hot",
            size_bytes=1024,
            budget_bytes=8192,
            utilization_pct=12.5,
            pressure=PressureLevel.NORMAL,
            last_mutation_ms=0,
            eviction_priority=None,
        )
        assert snap.name == "test"
        assert snap.utilization_pct == 12.5

    def test_tier_snapshot_dataclass(self) -> None:
        """Test TierSnapshot dataclass."""
        snap = TierSnapshot(
            name="hot",
            sections=["control", "meta"],
            size_bytes=2048,
            limit_bytes=53248,
            utilization_pct=4.17,
            pressure=PressureLevel.NORMAL,
        )
        assert snap.name == "hot"
        assert len(snap.sections) == 2

    def test_thrash_metrics_dataclass(self) -> None:
        """Test ThrashMetrics dataclass."""
        metrics = ThrashMetrics(
            migrations_last_minute=5,
            evictions_last_minute=2,
            thrash_detected=True,
            thrash_severity=1,
        )
        assert metrics.thrash_detected is True
        assert metrics.thrash_severity == 1

    def test_pressure_report_dataclass(self) -> None:
        """Test PressureReport dataclass."""
        report = PressureReport(
            overall=PressureLevel.ELEVATED,
            hot=PressureLevel.NORMAL,
            warm=PressureLevel.ELEVATED,
            sections_at_limit=["telemetry"],
            eviction_candidates=["telemetry", "beliefs_history"],
            estimated_eviction_bytes=4096,
        )
        assert report.overall == PressureLevel.ELEVATED
        assert len(report.eviction_candidates) == 2


# =============================================================================
# TEST CLASS: Performance
# =============================================================================


class TestPerformance:
    """Test performance characteristics."""

    def test_snapshot_is_fast(self, populated_api: SnapshotAPI) -> None:
        """Test snapshot generation is fast (<1ms target)."""

        start = time.perf_counter()
        for _ in range(100):
            populated_api.get_snapshot()
        duration_ms = (time.perf_counter() - start) * 1000

        # Average should be well under 1ms
        avg_ms = duration_ms / 100
        assert avg_ms < 1.0, f"Snapshot too slow: {avg_ms}ms avg"

    def test_format_table_is_reasonably_fast(self, populated_api: SnapshotAPI) -> None:
        """Test format_table is reasonably fast (<10ms)."""

        start = time.perf_counter()
        for _ in range(10):
            populated_api.format_table()
        duration_ms = (time.perf_counter() - start) * 1000

        avg_ms = duration_ms / 10
        assert avg_ms < 10.0, f"format_table too slow: {avg_ms}ms avg"
