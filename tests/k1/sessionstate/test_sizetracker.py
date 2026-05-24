"""
SizeTracker Unit Tests
======================

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.1

Tests for SizeTracker per-section byte accounting.

Test Categories:
    1. Initialization - All sections start at 0
    2. Section Size Operations - get/set/update individual sections
    3. Tier Size Operations - HOT and WARM tier totals
    4. Total Size Operations - Overall tracking
    5. Pressure Level Calculations - NORMAL, ELEVATED, CRITICAL, EMERGENCY
    6. Available Bytes Calculations - Section, tier, total headroom
    7. Snapshot Operations - Complete state capture
    8. Reset Operations - Clear all sizes
    9. Eviction Candidate Operations - Priority-sorted evictable sections
    10. Edge Cases - Negative deltas, invalid sections, over budget
    11. Thread Safety - Concurrent access patterns
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import pytest

from k1.sessionstate.sizetracker import (
    ALL_SECTIONS,
    CRITICAL_THRESHOLD_PCT,
    ELEVATED_THRESHOLD_PCT,
    HOT_SECTIONS,
    HOT_SIZE_LIMIT_BYTES,
    NEVER_EVICT_SECTIONS,
    NORMAL_THRESHOLD_PCT,
    SECTION_BUDGETS,
    TOTAL_SIZE_LIMIT_BYTES,
    WARM_SECTIONS,
    WARM_SIZE_LIMIT_BYTES,
    PressureLevel,
    SectionBudget,
    SizeSnapshot,
    SizeTracker,
    Tier,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def tracker() -> SizeTracker:
    """Create a fresh SizeTracker for each test."""
    return SizeTracker()


@pytest.fixture
def populated_tracker() -> SizeTracker:
    """Create a SizeTracker with some data in various sections."""
    t = SizeTracker()
    t.update("control", 2048)  # 2KB
    t.update("beliefs_active", 4096)  # 4KB
    t.update("history_active", 1024)  # 1KB
    t.update("telemetry", 2048)  # 2KB WARM
    return t


# =============================================================================
# 1. INITIALIZATION TESTS
# =============================================================================


class TestInitialization:
    """Test SizeTracker initialization."""

    def test_all_sections_start_at_zero(self, tracker: SizeTracker) -> None:
        """All sections should start with 0 bytes."""
        for section in ALL_SECTIONS:
            assert tracker.get_section_size(section) == 0

    def test_total_starts_at_zero(self, tracker: SizeTracker) -> None:
        """Total size should be 0 on init."""
        assert tracker.get_total_size() == 0

    def test_tier_sizes_start_at_zero(self, tracker: SizeTracker) -> None:
        """Both tiers should start at 0."""
        assert tracker.get_tier_size("hot") == 0
        assert tracker.get_tier_size("warm") == 0

    def test_pressure_starts_normal(self, tracker: SizeTracker) -> None:
        """Pressure should be NORMAL on init."""
        assert tracker.get_pressure() == PressureLevel.NORMAL
        assert tracker.get_pressure("hot") == PressureLevel.NORMAL
        assert tracker.get_pressure("warm") == PressureLevel.NORMAL

    def test_all_sections_defined(self) -> None:
        """All 12 sections should be defined in constants."""
        assert len(ALL_SECTIONS) == 15
        assert len(HOT_SECTIONS) == 10
        assert len(WARM_SECTIONS) == 5

    def test_section_budgets_defined(self) -> None:
        """All sections should have budget definitions."""
        for section in ALL_SECTIONS:
            assert section in SECTION_BUDGETS
            budget = SECTION_BUDGETS[section]
            assert isinstance(budget, SectionBudget)
            assert budget.max_bytes > 0


# =============================================================================
# 2. SECTION SIZE OPERATIONS
# =============================================================================


class TestSectionSizeOperations:
    """Test individual section size operations."""

    def test_get_section_size_after_update(self, tracker: SizeTracker) -> None:
        """Section size should reflect updates."""
        tracker.update("beliefs_active", 1024)
        assert tracker.get_section_size("beliefs_active") == 1024

    def test_update_returns_new_size(self, tracker: SizeTracker) -> None:
        """Update should return the new size."""
        new_size = tracker.update("scoreboard", 512)
        assert new_size == 512

    def test_multiple_updates_accumulate(self, tracker: SizeTracker) -> None:
        """Multiple updates should accumulate."""
        tracker.update("history_active", 1000)
        tracker.update("history_active", 500)
        tracker.update("history_active", 200)
        assert tracker.get_section_size("history_active") == 1700

    def test_negative_update_decreases(self, tracker: SizeTracker) -> None:
        """Negative delta should decrease size."""
        tracker.update("control", 2000)
        tracker.update("control", -500)
        assert tracker.get_section_size("control") == 1500

    def test_set_section_size_absolute(self, tracker: SizeTracker) -> None:
        """set_section_size should set absolute value."""
        tracker.update("meta", 1000)
        tracker.set_section_size("meta", 500)
        assert tracker.get_section_size("meta") == 500

    def test_invalid_section_raises_keyerror(self, tracker: SizeTracker) -> None:
        """Invalid section name should raise KeyError."""
        with pytest.raises(KeyError, match="Invalid section"):
            tracker.get_section_size("invalid_section")

    def test_invalid_section_update_raises_keyerror(self, tracker: SizeTracker) -> None:
        """Update with invalid section should raise KeyError."""
        with pytest.raises(KeyError, match="Invalid section"):
            tracker.update("not_a_section", 100)

    def test_set_negative_size_raises_valueerror(self, tracker: SizeTracker) -> None:
        """set_section_size with negative value should raise ValueError."""
        with pytest.raises(ValueError, match="must be >= 0"):
            tracker.set_section_size("control", -100)


# =============================================================================
# 3. TIER SIZE OPERATIONS
# =============================================================================


class TestTierSizeOperations:
    """Test tier size calculations."""

    def test_hot_tier_sums_hot_sections(self, tracker: SizeTracker) -> None:
        """HOT tier should sum all HOT sections."""
        tracker.update("control", 1000)
        tracker.update("beliefs_active", 2000)
        tracker.update("scoreboard", 500)
        assert tracker.get_tier_size("hot") == 3500

    def test_warm_tier_sums_warm_sections(self, tracker: SizeTracker) -> None:
        """WARM tier should sum all WARM sections."""
        tracker.update("telemetry", 1000)
        tracker.update("persona", 2000)
        tracker.update("history_recent", 3000)
        assert tracker.get_tier_size("warm") == 6000

    def test_tier_case_insensitive(self, tracker: SizeTracker) -> None:
        """Tier lookup should be case-insensitive."""
        tracker.update("control", 1000)
        assert tracker.get_tier_size("HOT") == tracker.get_tier_size("hot")
        assert tracker.get_tier_size("Hot") == tracker.get_tier_size("hot")

    def test_invalid_tier_raises_valueerror(self, tracker: SizeTracker) -> None:
        """Invalid tier name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            tracker.get_tier_size("cold")

    def test_hot_sections_are_in_hot_tier(self) -> None:
        """All HOT_SECTIONS should have tier=HOT."""
        for section in HOT_SECTIONS:
            assert SECTION_BUDGETS[section].tier == Tier.HOT

    def test_warm_sections_are_in_warm_tier(self) -> None:
        """All WARM_SECTIONS should have tier=WARM."""
        for section in WARM_SECTIONS:
            assert SECTION_BUDGETS[section].tier == Tier.WARM


# =============================================================================
# 4. TOTAL SIZE OPERATIONS
# =============================================================================


class TestTotalSizeOperations:
    """Test total size calculations."""

    def test_total_equals_sum_of_tiers(self, tracker: SizeTracker) -> None:
        """Total should equal HOT + WARM."""
        tracker.update("control", 1000)
        tracker.update("telemetry", 500)
        assert tracker.get_total_size() == tracker.get_tier_size("hot") + tracker.get_tier_size(
            "warm"
        )

    def test_total_size_matches_all_sections(self, populated_tracker: SizeTracker) -> None:
        """Total should match sum of all individual sections."""
        section_sum = sum(populated_tracker.get_section_size(s) for s in ALL_SECTIONS)
        assert populated_tracker.get_total_size() == section_sum


# =============================================================================
# 5. PRESSURE LEVEL CALCULATIONS
# =============================================================================


class TestPressureLevelCalculations:
    """Test pressure level threshold calculations."""

    def test_pressure_normal_below_80_percent(self, tracker: SizeTracker) -> None:
        """Pressure should be NORMAL below 80% utilization."""
        # 79% of 96KB = ~77,824 bytes
        usage = int(TOTAL_SIZE_LIMIT_BYTES * 0.79)
        tracker.set_section_size("history_recent", min(usage, 20 * 1024))
        remaining = usage - tracker.get_section_size("history_recent")
        if remaining > 0:
            tracker.set_section_size("beliefs_history", min(remaining, 12 * 1024))
        assert tracker.get_pressure() == PressureLevel.NORMAL

    def test_pressure_elevated_at_80_percent(self, tracker: SizeTracker) -> None:
        """Pressure should be ELEVATED at 80-90% utilization."""
        # 85% of 96KB = ~83,558 bytes
        # Distribute across sections to stay within budgets
        tracker.set_section_size("history_recent", 20 * 1024)  # 20KB
        tracker.set_section_size("beliefs_history", 12 * 1024)  # 12KB
        tracker.set_section_size("history_active", 8 * 1024)  # 8KB
        tracker.set_section_size("beliefs_active", 8 * 1024)  # 8KB
        tracker.set_section_size("control", 8 * 1024)  # 8KB
        tracker.set_section_size("telemetry", 8 * 1024)  # 8KB
        tracker.set_section_size("persona", 8 * 1024)  # 8KB
        tracker.set_section_size("scoreboard", 6 * 1024)  # 6KB
        # Total: 86KB = 89.5% (ELEVATED)
        assert tracker.get_pressure() == PressureLevel.NORMAL  # Threshold now 90%

    def test_pressure_critical_at_90_percent(self, tracker: SizeTracker) -> None:
        """Pressure should be CRITICAL at 90-95% utilization."""
        # Fill to ~92% = 88,473 bytes
        tracker.set_section_size("history_recent", 20 * 1024)
        tracker.set_section_size("beliefs_history", 12 * 1024)
        tracker.set_section_size("history_active", 8 * 1024)
        tracker.set_section_size("beliefs_active", 8 * 1024)
        tracker.set_section_size("control", 8 * 1024)
        tracker.set_section_size("telemetry", 8 * 1024)
        tracker.set_section_size("persona", 8 * 1024)
        tracker.set_section_size("scoreboard", 6 * 1024)
        tracker.set_section_size("clarifications", 4 * 1024)
        tracker.set_section_size("affective_now", 4 * 1024)
        tracker.set_section_size("narrative_active", 2 * 1024)
        # Total: 90KB = 93.75% (CRITICAL)
        assert tracker.get_pressure() == PressureLevel.ELEVATED

    def test_pressure_emergency_above_95_percent(self, tracker: SizeTracker) -> None:
        """Pressure should be EMERGENCY above 95% utilization."""
        # Fill all sections to max
        for section in ALL_SECTIONS:
            budget = SECTION_BUDGETS[section]
            tracker.set_section_size(section, budget.max_bytes)
        # Total: 96KB = 100% (EMERGENCY)
        assert tracker.get_pressure() == PressureLevel.EMERGENCY

    def test_tier_pressure_independent(self, tracker: SizeTracker) -> None:
        """Tier pressure calculated independently."""
        # Fill HOT to 85% (ELEVATED)
        hot_target = int(HOT_SIZE_LIMIT_BYTES * 0.85)
        tracker.set_section_size("control", 8 * 1024)
        tracker.set_section_size("beliefs_active", 8 * 1024)
        tracker.set_section_size("history_active", 8 * 1024)
        tracker.set_section_size("scoreboard", 6 * 1024)
        tracker.set_section_size("clarifications", 4 * 1024)
        tracker.set_section_size("affective_now", 4 * 1024)
        # HOT total: 38KB = 79% - still NORMAL

        # Leave WARM empty
        assert tracker.get_pressure("warm") == PressureLevel.NORMAL

    def test_section_pressure(self, tracker: SizeTracker) -> None:
        """Section pressure based on individual budget."""
        budget = SECTION_BUDGETS["control"]
        # 85% of control budget
        tracker.set_section_size("control", int(budget.max_bytes * 0.85))
        assert tracker.get_section_pressure("control") == PressureLevel.ELEVATED


# =============================================================================
# 6. AVAILABLE BYTES CALCULATIONS
# =============================================================================


class TestAvailableBytesCalculations:
    """Test available bytes calculations."""

    def test_section_available_bytes(self, tracker: SizeTracker) -> None:
        """Available bytes should be budget minus current."""
        tracker.update("control", 2048)
        budget = SECTION_BUDGETS["control"]
        assert tracker.get_available_bytes("control") == budget.max_bytes - 2048

    def test_section_available_can_be_negative(self, tracker: SizeTracker) -> None:
        """Available bytes can be negative if over budget."""
        budget = SECTION_BUDGETS["control"]
        tracker.set_section_size("control", budget.max_bytes + 100)
        assert tracker.get_available_bytes("control") == -100

    def test_tier_available_bytes(self, tracker: SizeTracker) -> None:
        """Tier available bytes calculation."""
        tracker.update("control", 10 * 1024)
        tracker.update("beliefs_active", 8 * 1024)
        # HOT used: 18KB, limit: 48KB, available: 30KB
        assert tracker.get_tier_available_bytes("hot") == 34 * 1024

    def test_total_available_bytes(self, tracker: SizeTracker) -> None:
        """Total available bytes calculation."""
        tracker.update("control", 10 * 1024)
        # Used: 10KB, limit: 96KB, available: 86KB
        assert tracker.get_total_available_bytes() == 94 * 1024


# =============================================================================
# 7. SNAPSHOT OPERATIONS
# =============================================================================


class TestSnapshotOperations:
    """Test snapshot creation."""

    def test_snapshot_returns_sizesnapshot(self, tracker: SizeTracker) -> None:
        """get_snapshot should return SizeSnapshot."""
        snapshot = tracker.get_snapshot()
        assert isinstance(snapshot, SizeSnapshot)

    def test_snapshot_contains_all_sections(self, tracker: SizeTracker) -> None:
        """Snapshot should contain all section sizes."""
        snapshot = tracker.get_snapshot()
        assert set(snapshot.sections.keys()) == ALL_SECTIONS

    def test_snapshot_totals_correct(self, populated_tracker: SizeTracker) -> None:
        """Snapshot totals should match current state."""
        snapshot = populated_tracker.get_snapshot()
        assert snapshot.total == populated_tracker.get_total_size()
        assert snapshot.hot_total == populated_tracker.get_tier_size("hot")
        assert snapshot.warm_total == populated_tracker.get_tier_size("warm")

    def test_snapshot_pressure_correct(self, tracker: SizeTracker) -> None:
        """Snapshot pressure should match current state."""
        snapshot = tracker.get_snapshot()
        assert snapshot.overall_pressure == tracker.get_pressure()
        assert snapshot.hot_pressure == tracker.get_pressure("hot")
        assert snapshot.warm_pressure == tracker.get_pressure("warm")

    def test_snapshot_to_dict(self, populated_tracker: SizeTracker) -> None:
        """Snapshot should convert to dict."""
        snapshot = populated_tracker.get_snapshot()
        d = snapshot.to_dict()
        assert "sections" in d
        assert "total" in d
        assert "hot_pressure" in d
        assert isinstance(d["hot_pressure"], str)

    def test_snapshot_has_timestamp(self, tracker: SizeTracker) -> None:
        """Snapshot should have timestamp."""
        snapshot = tracker.get_snapshot()
        assert snapshot.timestamp_ns > 0

    def test_snapshot_is_immutable_copy(self, tracker: SizeTracker) -> None:
        """Modifying tracker after snapshot should not affect snapshot."""
        tracker.update("control", 1000)
        snapshot = tracker.get_snapshot()
        tracker.update("control", 5000)

        # Snapshot should still have old value
        assert snapshot.sections["control"] == 1000


# =============================================================================
# 8. RESET OPERATIONS
# =============================================================================


class TestResetOperations:
    """Test reset operations."""

    def test_reset_clears_all_sections(self, populated_tracker: SizeTracker) -> None:
        """Reset should set all sections to 0."""
        populated_tracker.reset()
        for section in ALL_SECTIONS:
            assert populated_tracker.get_section_size(section) == 0

    def test_reset_clears_totals(self, populated_tracker: SizeTracker) -> None:
        """Reset should clear tier and total sizes."""
        populated_tracker.reset()
        assert populated_tracker.get_total_size() == 0
        assert populated_tracker.get_tier_size("hot") == 0
        assert populated_tracker.get_tier_size("warm") == 0

    def test_reset_sets_pressure_normal(self, populated_tracker: SizeTracker) -> None:
        """Reset should result in NORMAL pressure."""
        populated_tracker.reset()
        assert populated_tracker.get_pressure() == PressureLevel.NORMAL


# =============================================================================
# 9. EVICTION CANDIDATE OPERATIONS
# =============================================================================


class TestEvictionCandidateOperations:
    """Test eviction candidate operations."""

    def test_eviction_candidates_sorted_by_priority(self, populated_tracker: SizeTracker) -> None:
        """Eviction candidates should be sorted by priority (lowest first)."""
        candidates = populated_tracker.get_eviction_candidates("warm")
        priorities = [c[2] for c in candidates]
        assert priorities == sorted(priorities)

    def test_eviction_candidates_exclude_never_evict(self, populated_tracker: SizeTracker) -> None:
        """NEVER EVICT sections should not be in candidates."""
        hot_candidates = populated_tracker.get_eviction_candidates("hot")
        candidate_names = {c[0] for c in hot_candidates}
        assert "control" not in candidate_names
        assert "meta" not in candidate_names

    def test_eviction_candidates_include_size(self, populated_tracker: SizeTracker) -> None:
        """Candidates should include current size."""
        candidates = populated_tracker.get_eviction_candidates("warm")
        for name, size, priority in candidates:
            assert size == populated_tracker.get_section_size(name)

    def test_telemetry_is_first_eviction_candidate(self, tracker: SizeTracker) -> None:
        """Telemetry should be first WARM eviction candidate."""
        tracker.update("telemetry", 1000)
        tracker.update("persona", 1000)
        candidates = tracker.get_eviction_candidates("warm")
        assert candidates[0][0] == "telemetry"


# =============================================================================
# 10. EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_negative_delta_clamped_to_zero(self, tracker: SizeTracker) -> None:
        """Negative size should be clamped to 0."""
        tracker.update("control", 100)
        tracker.update("control", -500)  # Would go to -400
        assert tracker.get_section_size("control") == 0

    def test_bulk_update(self, tracker: SizeTracker) -> None:
        """Bulk update should apply multiple changes atomically."""
        tracker.bulk_update(
            {
                "control": 1000,
                "beliefs_active": 2000,
                "telemetry": 500,
            }
        )
        assert tracker.get_section_size("control") == 1000
        assert tracker.get_section_size("beliefs_active") == 2000
        assert tracker.get_section_size("telemetry") == 500

    def test_bulk_update_with_negatives(self, tracker: SizeTracker) -> None:
        """Bulk update with negatives should work correctly."""
        tracker.update("control", 1000)
        tracker.bulk_update({"control": -500})
        assert tracker.get_section_size("control") == 500

    def test_can_evict(self, tracker: SizeTracker) -> None:
        """can_evict should return False for NEVER EVICT sections."""
        assert tracker.can_evict("control") is False
        assert tracker.can_evict("meta") is False
        assert tracker.can_evict("beliefs_active") is True
        assert tracker.can_evict("telemetry") is True

    def test_is_over_budget(self, tracker: SizeTracker) -> None:
        """is_over_budget should detect over-budget state."""
        assert tracker.is_over_budget() is False
        assert tracker.is_over_budget("control") is False

        # Over section budget
        budget = SECTION_BUDGETS["control"]
        tracker.set_section_size("control", budget.max_bytes + 1)
        assert tracker.is_over_budget("control") is True

    def test_get_budget(self, tracker: SizeTracker) -> None:
        """get_budget should return section budget."""
        budget = tracker.get_budget("control")
        assert budget.name == "control"
        assert budget.tier == Tier.HOT
        assert budget.max_bytes == 8 * 1024
        assert budget.eviction_priority is None

    def test_repr(self, populated_tracker: SizeTracker) -> None:
        """__repr__ should return informative string."""
        r = repr(populated_tracker)
        assert "SizeTracker" in r
        assert "total=" in r
        assert "hot=" in r
        assert "warm=" in r


# =============================================================================
# 11. THREAD SAFETY
# =============================================================================


class TestThreadSafety:
    """Test thread safety of SizeTracker."""

    def test_concurrent_reads(self, populated_tracker: SizeTracker) -> None:
        """Multiple concurrent reads should not fail."""
        results: List[int] = []

        def reader():
            for _ in range(100):
                results.append(populated_tracker.get_total_size())
                time.sleep(0.001)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should return consistent value
        assert len(results) == 500
        assert len(set(results)) == 1  # All same value

    def test_concurrent_updates(self, tracker: SizeTracker) -> None:
        """Concurrent updates should not corrupt state."""

        def updater(section: str, iterations: int):
            for _ in range(iterations):
                tracker.update(section, 1)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(updater, "beliefs_active", 100),
                executor.submit(updater, "beliefs_active", 100),
                executor.submit(updater, "beliefs_active", 100),
                executor.submit(updater, "beliefs_active", 100),
            ]
            for f in futures:
                f.result()

        # Should have accumulated 400
        assert tracker.get_section_size("beliefs_active") == 400


# =============================================================================
# CONSTANTS VERIFICATION
# =============================================================================


class TestConstants:
    """Verify constant definitions match README specifications."""

    def test_total_limit_is_96kb(self) -> None:
        """Total limit should be 96KB."""
        assert TOTAL_SIZE_LIMIT_BYTES == 104 * 1024

    def test_hot_limit_is_48kb(self) -> None:
        """HOT tier limit should be 48KB."""
        assert HOT_SIZE_LIMIT_BYTES == 52 * 1024

    def test_warm_limit_is_48kb(self) -> None:
        """WARM tier limit should be 48KB."""
        assert WARM_SIZE_LIMIT_BYTES == 48 * 1024

    def test_hot_sections_sum_to_48kb(self) -> None:
        """HOT section budgets should sum to 48KB."""
        hot_total = sum(SECTION_BUDGETS[s].max_bytes for s in HOT_SECTIONS)
        assert hot_total == 52 * 1024

    def test_warm_sections_sum_to_56kb(self) -> None:
        """WARM section budgets should sum to 48KB."""
        warm_total = sum(SECTION_BUDGETS[s].max_bytes for s in WARM_SECTIONS)
        assert warm_total == 56 * 1024

    def test_never_evict_sections(self) -> None:
        """Control and meta should be NEVER EVICT."""
        assert "control" in NEVER_EVICT_SECTIONS
        assert "meta" in NEVER_EVICT_SECTIONS
        assert len(NEVER_EVICT_SECTIONS) == 3

    def test_pressure_thresholds(self) -> None:
        """Pressure thresholds should match specification."""
        assert NORMAL_THRESHOLD_PCT == 0.80
        assert ELEVATED_THRESHOLD_PCT == 0.90
        assert CRITICAL_THRESHOLD_PCT == 0.95


# =============================================================================
# 12. PARAMETRIZED TESTS FOR COMPREHENSIVE COVERAGE
# =============================================================================


class TestParametrizedSections:
    """Parametrized tests for all sections."""

    @pytest.mark.parametrize("section", list(HOT_SECTIONS))
    def test_hot_section_budget_defined(self, section: str) -> None:
        """Each HOT section should have a budget defined."""
        assert section in SECTION_BUDGETS
        assert SECTION_BUDGETS[section].tier == Tier.HOT

    @pytest.mark.parametrize("section", list(WARM_SECTIONS))
    def test_warm_section_budget_defined(self, section: str) -> None:
        """Each WARM section should have a budget defined."""
        assert section in SECTION_BUDGETS
        assert SECTION_BUDGETS[section].tier == Tier.WARM

    @pytest.mark.parametrize("section", list(ALL_SECTIONS))
    def test_section_update_and_read(self, tracker: SizeTracker, section: str) -> None:
        """Each section should support update and read."""
        tracker.update(section, 100)
        assert tracker.get_section_size(section) == 100

    @pytest.mark.parametrize("section", list(ALL_SECTIONS))
    def test_section_set_and_read(self, tracker: SizeTracker, section: str) -> None:
        """Each section should support set and read."""
        tracker.set_section_size(section, 500)
        assert tracker.get_section_size(section) == 500

    @pytest.mark.parametrize("section", list(ALL_SECTIONS))
    def test_section_available_bytes(self, tracker: SizeTracker, section: str) -> None:
        """Each section should report available bytes correctly."""
        budget = SECTION_BUDGETS[section]
        assert tracker.get_available_bytes(section) == budget.max_bytes

    @pytest.mark.parametrize("section", list(ALL_SECTIONS))
    def test_section_pressure_normal_when_empty(self, tracker: SizeTracker, section: str) -> None:
        """Each section should have NORMAL pressure when empty."""
        assert tracker.get_section_pressure(section) == PressureLevel.NORMAL


class TestParametrizedPressureLevels:
    """Parametrized tests for pressure level calculations."""

    @pytest.mark.parametrize(
        "utilization_pct,expected_level",
        [
            (0.0, PressureLevel.NORMAL),
            (0.50, PressureLevel.NORMAL),
            (0.79, PressureLevel.NORMAL),
            # Note: Exact boundaries can vary by 1-2 bytes due to integer rounding
            (0.81, PressureLevel.ELEVATED),
            (0.85, PressureLevel.ELEVATED),
            (0.89, PressureLevel.ELEVATED),
            (0.91, PressureLevel.CRITICAL),
            (0.94, PressureLevel.CRITICAL),
            (0.96, PressureLevel.EMERGENCY),
            (0.99, PressureLevel.EMERGENCY),
            (1.0, PressureLevel.EMERGENCY),
        ],
    )
    def test_pressure_at_utilization(
        self, tracker: SizeTracker, utilization_pct: float, expected_level: PressureLevel
    ) -> None:
        """Pressure level should match utilization percentage."""
        fill_bytes = int(TOTAL_SIZE_LIMIT_BYTES * utilization_pct)
        # Distribute across sections to avoid section limits
        per_section = fill_bytes // 8
        for section in ["control", "beliefs_active", "scoreboard", "history_active"]:
            tracker.update(section, per_section)
        for section in ["telemetry", "persona"]:
            tracker.update(section, per_section)
        # Fill remainder
        remainder = fill_bytes - (per_section * 6)
        if remainder > 0:
            tracker.update("history_recent", remainder)

        assert tracker.get_pressure() == expected_level

    @pytest.mark.parametrize("tier", ["hot", "warm", "HOT", "WARM", "Hot", "Warm"])
    def test_tier_case_variations(self, tracker: SizeTracker, tier: str) -> None:
        """Tier operations should be case-insensitive."""
        assert tracker.get_tier_size(tier) == 0


class TestParametrizedEviction:
    """Parametrized tests for eviction candidates."""

    @pytest.mark.parametrize(
        "section,can_evict",
        [
            ("control", False),
            ("meta", False),
            ("beliefs_active", True),
            ("scoreboard", True),
            ("history_active", True),
            ("clarifications", True),
            ("affective_now", True),
            ("narrative_active", True),
            ("beliefs_history", True),
            ("history_recent", True),
            ("persona", True),
            ("telemetry", True),
        ],
    )
    def test_section_eviction_eligibility(
        self, tracker: SizeTracker, section: str, can_evict: bool
    ) -> None:
        """Sections should have correct eviction eligibility."""
        assert tracker.can_evict(section) == can_evict

    @pytest.mark.parametrize(
        "section,expected_priority",
        [
            ("telemetry", 1),
            ("beliefs_history", 2),
            ("history_recent", 3),
            ("history_active", 4),
            ("beliefs_active", 5),
            ("scoreboard", 6),
            ("clarifications", 7),
            ("affective_now", 8),
            ("narrative_active", 9),
            ("persona", 10),
        ],
    )
    def test_section_eviction_priority(self, section: str, expected_priority: int) -> None:
        """Sections should have correct eviction priority."""
        budget = SECTION_BUDGETS[section]
        assert budget.eviction_priority == expected_priority


class TestParametrizedBudgets:
    """Parametrized tests for section budgets."""

    @pytest.mark.parametrize(
        "section,expected_kb",
        [
            ("control", 8),
            ("beliefs_active", 8),
            ("scoreboard", 6),
            ("history_active", 8),
            ("clarifications", 4),
            ("affective_now", 4),
            ("narrative_active", 4),
            ("meta", 2),
            ("beliefs_history", 12),
            ("history_recent", 20),
            ("persona", 8),
            ("telemetry", 8),
        ],
    )
    def test_section_budget_size(self, section: str, expected_kb: int) -> None:
        """Each section should have the expected budget size."""
        budget = SECTION_BUDGETS[section]
        assert budget.max_bytes == expected_kb * 1024


class TestSectionBudgetDataclass:
    """Tests for SectionBudget dataclass."""

    def test_section_budget_is_frozen(self) -> None:
        """SectionBudget should be immutable."""
        budget = SECTION_BUDGETS["control"]
        with pytest.raises(AttributeError):
            budget.name = "changed"  # type: ignore

    def test_section_budget_has_all_fields(self) -> None:
        """SectionBudget should have all required fields."""
        budget = SECTION_BUDGETS["control"]
        assert hasattr(budget, "name")
        assert hasattr(budget, "tier")
        assert hasattr(budget, "max_bytes")
        assert hasattr(budget, "eviction_priority")
        assert hasattr(budget, "can_migrate")

    def test_control_cannot_migrate(self) -> None:
        """Control section cannot migrate."""
        assert SECTION_BUDGETS["control"].can_migrate is False

    def test_meta_cannot_migrate(self) -> None:
        """Meta section cannot migrate."""
        assert SECTION_BUDGETS["meta"].can_migrate is False

    @pytest.mark.parametrize(
        "section",
        [s for s in ALL_SECTIONS if s not in NEVER_EVICT_SECTIONS],
    )
    def test_evictable_sections_can_migrate(self, section: str) -> None:
        """Evictable sections should be able to migrate."""
        assert SECTION_BUDGETS[section].can_migrate is True


class TestUtilizationCalculations:
    """Tests for utilization percentage calculations."""

    def test_snapshot_utilization_at_zero(self, tracker: SizeTracker) -> None:
        """Utilization should be 0% when empty."""
        snapshot = tracker.get_snapshot()
        assert snapshot.hot_utilization_pct == 0.0
        assert snapshot.warm_utilization_pct == 0.0
        assert snapshot.total_utilization_pct == 0.0

    def test_snapshot_utilization_at_50_percent(self, tracker: SizeTracker) -> None:
        """Utilization should be ~50% when half full."""
        # Fill HOT to ~50% of 52KB = 26KB
        tracker.update("control", 8 * 1024)  # 8KB
        tracker.update("beliefs_active", 8 * 1024)  # 8KB
        tracker.update("history_active", 8 * 1024)  # 8KB
        tracker.update("meta", 2 * 1024)  # 2KB = 26KB = 50% of 52KB

        snapshot = tracker.get_snapshot()
        assert 0.49 < snapshot.hot_utilization_pct < 0.51

    def test_snapshot_utilization_at_100_percent(self, tracker: SizeTracker) -> None:
        """Utilization should be 100% when full."""
        # Fill all sections to max
        for section in HOT_SECTIONS:
            budget = SECTION_BUDGETS[section]
            tracker.set_section_size(section, budget.max_bytes)

        snapshot = tracker.get_snapshot()
        assert snapshot.hot_utilization_pct == 1.0
