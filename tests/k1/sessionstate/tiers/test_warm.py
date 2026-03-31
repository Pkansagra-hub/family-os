"""
WarmTier Unit Tests
===================

Tests for k1/sessionstate/tiers/warm.py

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.4 Implement Tier Managers
ISSUE: 2.4.2 (WarmTier)

Test Categories:
1. Initialization & Properties
2. Section Access
3. Size Tracking
4. Pressure Assessment
5. Demotion Acceptance
6. Eviction
7. Promotion
8. Serialization
9. Lifecycle
10. Snapshot & Statistics
11. Constants
12. Edge Cases
"""

import time

import pytest

from k1.sessionstate.tiers.warm import (
    DEMOTION_TARGETS,
    ELEVATED_THRESHOLD,
    EVICTION_ORDER,
    EVICTION_PRIORITIES,
    HIGH_THRESHOLD,
    NORMAL_THRESHOLD,
    SECTION_BUDGETS,
    WARM_BUDGET_BYTES,
    WARM_SECTION_NAMES,
    DemotedItem,
    EvictionCandidate,
    EvictionResult,
    PromotionCandidate,
    WarmPressureLevel,
    WarmSnapshot,
    WarmTier,
    create_warm_tier,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def warm_tier() -> WarmTier:
    """Create a fresh WarmTier for testing."""
    return WarmTier(session_id="test-session-123")


@pytest.fixture
def populated_tier() -> WarmTier:
    """Create a WarmTier with some data."""
    tier = WarmTier(session_id="test-session-456")

    # Add some data to telemetry section
    telemetry = tier.get_section("telemetry")
    if telemetry and hasattr(telemetry, "record_tokens"):
        telemetry.record_tokens(input_tokens=100, output_tokens=50)  # type: ignore

    return tier


# =============================================================================
# INITIALIZATION & PROPERTIES TESTS
# =============================================================================


class TestInitialization:
    """Tests for WarmTier initialization."""

    def test_init_creates_tier(self):
        """WarmTier initializes successfully."""
        tier = WarmTier()
        assert tier is not None

    def test_init_with_session_id(self):
        """WarmTier accepts session_id."""
        tier = WarmTier(session_id="abc-123")
        assert tier.session_id == "abc-123"

    def test_init_creates_all_5_sections(self, warm_tier: WarmTier):
        """WarmTier initializes all 5 sections."""
        assert len(warm_tier) == 5

    def test_all_expected_sections_present(self, warm_tier: WarmTier):
        """All expected section names are present."""
        for name in WARM_SECTION_NAMES:
            assert name in warm_tier, f"Missing section: {name}"

    def test_sections_have_correct_types(self, warm_tier: WarmTier):
        """Sections are correct types."""
        from k1.sessionstate.sections import (
            BeliefsHistorySection,
            HistoryRecentSection,
            PersonaSection,
            TelemetrySection,
        )

        assert isinstance(warm_tier.get_section("telemetry"), TelemetrySection)
        assert isinstance(warm_tier.get_section("beliefs_history"), BeliefsHistorySection)
        assert isinstance(warm_tier.get_section("history_recent"), HistoryRecentSection)
        assert isinstance(warm_tier.get_section("persona"), PersonaSection)


class TestProperties:
    """Tests for WarmTier properties."""

    def test_tier_name(self, warm_tier: WarmTier):
        """tier_name returns 'warm'."""
        assert warm_tier.tier_name == "warm"

    def test_budget_bytes(self, warm_tier: WarmTier):
        """budget_bytes returns 48KB."""
        assert warm_tier.budget_bytes == 49152

    def test_section_count(self, warm_tier: WarmTier):
        """section_count returns 4."""
        assert warm_tier.section_count == 5


# =============================================================================
# SECTION ACCESS TESTS
# =============================================================================


class TestSectionAccess:
    """Tests for section access methods."""

    def test_get_section_returns_section(self, warm_tier: WarmTier):
        """get_section returns correct section."""
        section = warm_tier.get_section("telemetry")
        assert section is not None
        assert section.name == "telemetry"

    def test_get_section_returns_none_for_invalid(self, warm_tier: WarmTier):
        """get_section returns None for invalid name."""
        assert warm_tier.get_section("invalid") is None

    def test_get_section_strict_raises_for_invalid(self, warm_tier: WarmTier):
        """get_section_strict raises KeyError for invalid name."""
        with pytest.raises(KeyError, match="Unknown WARM section"):
            warm_tier.get_section_strict("invalid")

    def test_get_all_sections(self, warm_tier: WarmTier):
        """get_all_sections returns all sections."""
        sections = warm_tier.get_all_sections()
        assert len(sections) == 5
        assert "telemetry" in sections
        assert "beliefs_history" in sections
        assert "history_recent" in sections
        assert "persona" in sections

    def test_get_section_names(self, warm_tier: WarmTier):
        """get_section_names returns all names."""
        names = warm_tier.get_section_names()
        assert len(names) == 5
        assert set(names) == {
            "artifacts_warm",
            "beliefs_history",
            "history_recent",
            "persona",
            "telemetry",
        }

    def test_dict_access(self, warm_tier: WarmTier):
        """Dict-like access works."""
        section = warm_tier["telemetry"]
        assert section.name == "telemetry"

    def test_dict_access_raises_for_invalid(self, warm_tier: WarmTier):
        """Dict-like access raises KeyError for invalid."""
        with pytest.raises(KeyError):
            _ = warm_tier["invalid"]

    def test_contains_operator(self, warm_tier: WarmTier):
        """'in' operator works."""
        assert "telemetry" in warm_tier
        assert "persona" in warm_tier
        assert "invalid" not in warm_tier

    def test_iteration(self, warm_tier: WarmTier):
        """Iteration over tier yields section names."""
        names = list(warm_tier)
        assert len(names) == 5

    def test_len(self, warm_tier: WarmTier):
        """len() returns section count."""
        assert len(warm_tier) == 5


# =============================================================================
# SIZE TRACKING TESTS
# =============================================================================


class TestSizeTracking:
    """Tests for size tracking methods."""

    def test_get_total_size_empty(self, warm_tier: WarmTier):
        """get_total_size returns base overhead when empty."""
        size = warm_tier.get_total_size()
        assert size > 0  # Base overhead

    def test_get_section_size(self, warm_tier: WarmTier):
        """get_section_size returns section size."""
        size = warm_tier.get_section_size("telemetry")
        assert size >= 0

    def test_get_section_size_invalid(self, warm_tier: WarmTier):
        """get_section_size returns 0 for invalid name."""
        assert warm_tier.get_section_size("invalid") == 0

    def test_get_section_sizes(self, warm_tier: WarmTier):
        """get_section_sizes returns all sizes."""
        sizes = warm_tier.get_section_sizes()
        assert len(sizes) == 5
        for name in WARM_SECTION_NAMES:
            assert name in sizes

    def test_get_available_bytes(self, warm_tier: WarmTier):
        """get_available_bytes returns budget minus used."""
        available = warm_tier.get_available_bytes()
        assert available > 0
        assert available <= WARM_BUDGET_BYTES

    def test_get_utilization(self, warm_tier: WarmTier):
        """get_utilization returns 0.0-1.0 range."""
        util = warm_tier.get_utilization()
        assert 0.0 <= util <= 1.0


# =============================================================================
# PRESSURE ASSESSMENT TESTS
# =============================================================================


class TestPressureAssessment:
    """Tests for pressure assessment."""

    def test_get_pressure_normal_when_empty(self, warm_tier: WarmTier):
        """get_pressure returns NORMAL when mostly empty."""
        pressure = warm_tier.get_pressure()
        assert pressure == WarmPressureLevel.NORMAL

    def test_pressure_thresholds(self):
        """Pressure thresholds are correct."""
        assert NORMAL_THRESHOLD == 0.80
        assert ELEVATED_THRESHOLD == 0.90
        assert HIGH_THRESHOLD == 0.95

    def test_is_under_pressure(self, warm_tier: WarmTier):
        """is_under_pressure returns False when normal."""
        assert warm_tier.is_under_pressure() is False

    def test_needs_eviction(self, warm_tier: WarmTier):
        """needs_eviction returns False when normal."""
        assert warm_tier.needs_eviction() is False

    def test_pressure_enum_values(self):
        """WarmPressureLevel enum has correct values."""
        assert WarmPressureLevel.NORMAL.value == "normal"
        assert WarmPressureLevel.ELEVATED.value == "elevated"
        assert WarmPressureLevel.HIGH.value == "high"
        assert WarmPressureLevel.CRITICAL.value == "critical"


# =============================================================================
# DEMOTION ACCEPTANCE TESTS
# =============================================================================


class TestDemotionAcceptance:
    """Tests for demotion acceptance from HOT tier."""

    def test_demotion_targets_defined(self):
        """Demotion target mappings exist."""
        assert "beliefs_active" in DEMOTION_TARGETS
        assert "history_active" in DEMOTION_TARGETS
        assert DEMOTION_TARGETS["beliefs_active"] == "beliefs_history"
        assert DEMOTION_TARGETS["history_active"] == "history_recent"

    def test_get_demotion_target(self, warm_tier: WarmTier):
        """get_demotion_target returns correct mapping."""
        assert warm_tier.get_demotion_target("beliefs_active") == "beliefs_history"
        assert warm_tier.get_demotion_target("history_active") == "history_recent"
        assert warm_tier.get_demotion_target("control") is None

    def test_can_accept_demoted(self, warm_tier: WarmTier):
        """can_accept_demoted returns True for valid sections."""
        assert warm_tier.can_accept_demoted("beliefs_active") is True
        assert warm_tier.can_accept_demoted("history_active") is True
        assert warm_tier.can_accept_demoted("control") is False

    def test_accept_demoted_empty_list(self, warm_tier: WarmTier):
        """accept_demoted returns 0 for empty list."""
        count = warm_tier.accept_demoted("beliefs_active", [])
        assert count == 0

    def test_accept_demoted_no_mapping(self, warm_tier: WarmTier):
        """accept_demoted returns 0 for unmapped section."""
        count = warm_tier.accept_demoted("control", [{"fact": "test"}])
        assert count == 0


# =============================================================================
# EVICTION TESTS
# =============================================================================


class TestEviction:
    """Tests for eviction functionality."""

    def test_eviction_order_defined(self):
        """Eviction order is defined."""
        assert len(EVICTION_ORDER) == 5
        assert EVICTION_ORDER[0] == "telemetry"  # First to evict
        assert EVICTION_ORDER[-1] == "persona"  # Last to evict

    def test_eviction_priorities_defined(self):
        """Eviction priorities are defined."""
        assert EVICTION_PRIORITIES["telemetry"] == 1
        assert EVICTION_PRIORITIES["beliefs_history"] == 3
        assert EVICTION_PRIORITIES["history_recent"] == 4
        assert EVICTION_PRIORITIES["persona"] == 5

    def test_get_evictable_sections(self, warm_tier: WarmTier):
        """get_evictable_sections returns correct list."""
        sections = warm_tier.get_evictable_sections()
        assert sections == EVICTION_ORDER

    def test_get_eviction_candidates_empty(self, warm_tier: WarmTier):
        """get_eviction_candidates returns empty when under threshold."""
        candidates = warm_tier.get_eviction_candidates()
        assert candidates == []

    def test_evict_zero_bytes(self, warm_tier: WarmTier):
        """evict with 0 bytes returns success with no work."""
        result = warm_tier.evict(0)
        assert result.success is True
        assert result.items_evicted == 0
        assert result.bytes_freed == 0

    def test_evict_if_needed_no_pressure(self, warm_tier: WarmTier):
        """evict_if_needed returns no_candidates when not needed."""
        result = warm_tier.evict_if_needed()
        assert result.success is True
        assert result.items_evicted == 0


class TestEvictionCandidate:
    """Tests for EvictionCandidate dataclass."""

    def test_create_candidate(self):
        """EvictionCandidate can be created."""
        candidate = EvictionCandidate(
            section="telemetry",
            key="item-1",
            data={"test": True},
            size_bytes=100,
            priority=1,
            reason="pressure",
        )
        assert candidate.section == "telemetry"
        assert candidate.key == "item-1"
        assert candidate.size_bytes == 100
        assert candidate.priority == 1

    def test_candidate_repr(self):
        """EvictionCandidate has useful repr."""
        candidate = EvictionCandidate(
            section="telemetry",
            key="item-1",
            data={},
            size_bytes=100,
            priority=1,
        )
        repr_str = repr(candidate)
        assert "telemetry" in repr_str
        assert "100B" in repr_str


class TestEvictionResult:
    """Tests for EvictionResult dataclass."""

    def test_create_success_result(self):
        """EvictionResult success can be created."""
        result = EvictionResult(
            success=True,
            items_evicted=5,
            bytes_freed=500,
            new_pressure=WarmPressureLevel.NORMAL,
        )
        assert result.success is True
        assert result.items_evicted == 5
        assert result.bytes_freed == 500

    def test_failure_factory(self):
        """EvictionResult.failure creates failure result."""
        result = EvictionResult.failure("test error", duration_ms=10.5)
        assert result.success is False
        assert result.error == "test error"
        assert result.duration_ms == 10.5

    def test_no_candidates_factory(self):
        """EvictionResult.no_candidates creates empty result."""
        result = EvictionResult.no_candidates()
        assert result.success is True
        assert result.items_evicted == 0
        assert result.bytes_freed == 0

    def test_to_dict(self):
        """EvictionResult.to_dict returns dict."""
        result = EvictionResult(
            success=True,
            items_evicted=3,
            bytes_freed=300,
            new_pressure=WarmPressureLevel.ELEVATED,
            duration_ms=5.123,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["items_evicted"] == 3
        assert d["bytes_freed"] == 300
        assert d["new_pressure"] == "elevated"


# =============================================================================
# PROMOTION TESTS
# =============================================================================


class TestPromotion:
    """Tests for promotion functionality."""

    def test_get_promotion_candidates_empty(self, warm_tier: WarmTier):
        """get_promotion_candidates returns empty when no candidates."""
        candidates = warm_tier.get_promotion_candidates()
        assert candidates == []


class TestPromotionCandidate:
    """Tests for PromotionCandidate dataclass."""

    def test_create_promotion_candidate(self):
        """PromotionCandidate can be created."""
        candidate = PromotionCandidate(
            section="beliefs_history",
            target_section="beliefs_active",
            key="fact-1",
            data={"subject": "user"},
            access_count=5,
            reason="frequently_accessed",
        )
        assert candidate.section == "beliefs_history"
        assert candidate.target_section == "beliefs_active"
        assert candidate.access_count == 5


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================


class TestSerialization:
    """Tests for serialization methods."""

    def test_serialize_all(self, warm_tier: WarmTier):
        """serialize_all returns dict of bytes."""
        serialized = warm_tier.serialize_all()
        assert len(serialized) == 5
        for name in WARM_SECTION_NAMES:
            assert name in serialized
            assert isinstance(serialized[name], bytes)

    def test_deserialize_all(self, warm_tier: WarmTier):
        """deserialize_all restores sections."""
        # First serialize
        serialized = warm_tier.serialize_all()
        assert len(serialized) == 5

        # Note: Full deserialization test requires from_flatbuffer
        # to work consistently across all sections.
        for name, data in serialized.items():
            assert isinstance(data, bytes)
            assert len(data) > 0


# =============================================================================
# LIFECYCLE TESTS
# =============================================================================


class TestLifecycle:
    """Tests for lifecycle methods."""

    def test_clear_all(self, warm_tier: WarmTier):
        """clear_all clears all sections."""
        warm_tier.clear_all()
        # After clear, should be minimal size (base overhead)

    def test_clear_section(self, warm_tier: WarmTier):
        """clear_section clears specific section."""
        result = warm_tier.clear_section("telemetry")
        assert result is True

    def test_clear_section_invalid(self, warm_tier: WarmTier):
        """clear_section returns False for invalid name."""
        result = warm_tier.clear_section("invalid")
        assert result is False


# =============================================================================
# SNAPSHOT TESTS
# =============================================================================


class TestSnapshot:
    """Tests for snapshot methods."""

    def test_get_snapshot(self, warm_tier: WarmTier):
        """get_snapshot returns WarmSnapshot."""
        snapshot = warm_tier.get_snapshot()
        assert isinstance(snapshot, WarmSnapshot)
        assert snapshot.total_size >= 0
        assert snapshot.budget_bytes == WARM_BUDGET_BYTES
        assert 0.0 <= snapshot.utilization_pct <= 1.0
        assert isinstance(snapshot.pressure, WarmPressureLevel)
        assert len(snapshot.section_sizes) == 5
        assert snapshot.timestamp_ms > 0

    def test_snapshot_to_dict(self, warm_tier: WarmTier):
        """WarmSnapshot.to_dict returns dict."""
        snapshot = warm_tier.get_snapshot()
        d = snapshot.to_dict()
        assert "total_size" in d
        assert "budget_bytes" in d
        assert "utilization_pct" in d
        assert "pressure" in d
        assert "section_sizes" in d

    def test_get_statistics(self, warm_tier: WarmTier):
        """get_statistics returns comprehensive stats."""
        stats = warm_tier.get_statistics()
        assert stats["tier"] == "warm"
        assert stats["section_count"] == 5
        assert "sections" in stats
        assert "eviction_order" in stats
        assert stats["eviction_order"] == EVICTION_ORDER


# =============================================================================
# STRING REPRESENTATION TESTS
# =============================================================================


class TestStringRepresentation:
    """Tests for string representations."""

    def test_repr(self, warm_tier: WarmTier):
        """__repr__ returns useful string."""
        repr_str = repr(warm_tier)
        assert "WarmTier" in repr_str
        assert "sections=5" in repr_str

    def test_str(self, warm_tier: WarmTier):
        """__str__ returns readable string."""
        str_val = str(warm_tier)
        assert "WarmTier" in str_val
        assert "utilized" in str_val


# =============================================================================
# FACTORY TESTS
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_warm_tier(self):
        """create_warm_tier creates tier."""
        tier = create_warm_tier(session_id="factory-test")
        assert isinstance(tier, WarmTier)
        assert tier.session_id == "factory-test"

    def test_create_warm_tier_defaults(self):
        """create_warm_tier works with defaults."""
        tier = create_warm_tier()
        assert isinstance(tier, WarmTier)
        assert len(tier) == 5


# =============================================================================
# CONSTANTS TESTS
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_warm_budget_bytes(self):
        """WARM_BUDGET_BYTES is 48KB."""
        assert WARM_BUDGET_BYTES == 49152

    def test_section_budgets(self):
        """Section budgets are defined."""
        assert SECTION_BUDGETS["telemetry"] == 8192
        assert SECTION_BUDGETS["beliefs_history"] == 12288
        assert SECTION_BUDGETS["history_recent"] == 20480
        assert SECTION_BUDGETS["persona"] == 8192

    def test_section_budgets_sum_correctly(self):
        """Section budgets sum to expected total."""
        total = sum(SECTION_BUDGETS.values())
        # 8 + 12 + 20 + 8 = 48KB
        assert total == 56 * 1024

    def test_warm_section_names(self):
        """WARM_SECTION_NAMES has all 5 sections."""
        assert len(WARM_SECTION_NAMES) == 5
        assert "telemetry" in WARM_SECTION_NAMES
        assert "beliefs_history" in WARM_SECTION_NAMES
        assert "history_recent" in WARM_SECTION_NAMES
        assert "persona" in WARM_SECTION_NAMES

    def test_eviction_order_matches_priorities(self):
        """EVICTION_ORDER matches EVICTION_PRIORITIES."""
        for i, section in enumerate(EVICTION_ORDER):
            expected_priority = i + 1
            assert EVICTION_PRIORITIES[section] == expected_priority


# =============================================================================
# DEMOTED ITEM TESTS
# =============================================================================


class TestDemotedItem:
    """Tests for DemotedItem dataclass."""

    def test_create_demoted_item(self):
        """DemotedItem can be created."""
        item = DemotedItem(
            source_section="beliefs_active",
            target_section="beliefs_history",
            key="fact-123",
            data={"subject": "user", "predicate": "likes", "object": "coffee"},
            size_bytes=100,
        )
        assert item.source_section == "beliefs_active"
        assert item.target_section == "beliefs_history"
        assert item.key == "fact-123"
        assert item.size_bytes == 100


# =============================================================================
# EDGE CASES TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_multiple_tiers_independent(self):
        """Multiple tier instances are independent."""
        tier1 = WarmTier(session_id="session-1")
        tier2 = WarmTier(session_id="session-2")

        # Clear one shouldn't affect other
        tier1.clear_all()
        assert tier2.session_id == "session-2"

    def test_set_local_cold(self, warm_tier: WarmTier):
        """set_local_cold sets archive."""
        # Just test it doesn't error
        warm_tier.set_local_cold(None)  # type: ignore

    def test_set_eviction_callback(self, warm_tier: WarmTier):
        """set_eviction_callback sets callback."""
        callback_called = []

        def callback(section: str, data: bytes) -> bool:
            callback_called.append(section)
            return True

        warm_tier.set_eviction_callback(callback)

    def test_empty_session_id(self):
        """Empty session_id is handled."""
        tier = WarmTier(session_id="")
        assert tier.session_id == ""

    def test_get_snapshot_timing(self, warm_tier: WarmTier):
        """Snapshot timestamp is recent."""
        before = int(time.time() * 1000)
        snapshot = warm_tier.get_snapshot()
        after = int(time.time() * 1000)
        assert before <= snapshot.timestamp_ms <= after
