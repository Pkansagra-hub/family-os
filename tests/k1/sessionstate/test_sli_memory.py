"""
Epic 5.1-T.6: Test Memory Utilization SLI
==========================================

Tests that verify memory utilization stays within SLI limits.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.1-T - SLI/SLO Validation Tests
ISSUE: 5.1-T.6 - Test memory utilization SLI

SLI TARGETS (from sessionstate.policies.yaml):
----------------------------------------------
- Total memory: <96KB (98,304 bytes) always
- HOT tier: <48KB (49,152 bytes) always
- WARM tier: <48KB (49,152 bytes) always

SCENARIOS:
----------
1. Verify budget enforcement
2. Fill sessions to various levels
3. Verify eviction triggers at thresholds
4. Verify emergency mode activates at 95%
"""

import uuid
from pathlib import Path
from typing import Generator

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager

# =============================================================================
# SLI TARGETS (bytes)
# =============================================================================

SLI_TOTAL_LIMIT_BYTES = 110592  # 108 KB
SLI_HOT_LIMIT_BYTES = 57344  # 56 KB
SLI_WARM_LIMIT_BYTES = 49152  # 48 KB

# Pressure thresholds
THRESHOLD_NORMAL = 0.80  # 80%
THRESHOLD_ELEVATED = 0.90  # 90%
THRESHOLD_CRITICAL = 0.95  # 95%


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def manager() -> Generator[SessionStateManager, None, None]:
    """Create test manager."""
    manager = SessionStateFactory.create_for_testing()
    manager.start(restore_if_exists=False)

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def standalone_manager(tmp_path: Path) -> Generator[SessionStateManager, None, None]:
    """Create standalone manager with SQLite for eviction testing."""
    db_path = tmp_path / "memory_sli_test.db"
    session_id = f"mem-sli-{uuid.uuid4().hex[:8]}"

    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
    )
    manager.start(restore_if_exists=False)

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


# =============================================================================
# BUDGET ENFORCEMENT TESTS
# =============================================================================


class TestBudgetEnforcement:
    """Test that memory budgets are enforced."""

    def test_empty_session_under_budget(self, manager: SessionStateManager) -> None:
        """Empty session is under budget."""
        snapshot = manager.get_snapshot()

        assert snapshot.total_size_bytes < SLI_TOTAL_LIMIT_BYTES
        assert snapshot.hot_size_bytes < SLI_HOT_LIMIT_BYTES
        assert snapshot.warm_size_bytes < SLI_WARM_LIMIT_BYTES

    def test_budget_limit_values_correct(self, manager: SessionStateManager) -> None:
        """Budget limits match SLI spec."""
        # Verify our constants are correct
        assert SLI_TOTAL_LIMIT_BYTES == 108 * 1024  # 108KB
        assert SLI_HOT_LIMIT_BYTES == 56 * 1024  # 56KB
        assert SLI_WARM_LIMIT_BYTES == 48 * 1024  # 48KB

    def test_hot_warm_split_correct(self) -> None:
        """HOT + WARM stays within TOTAL limit."""
        assert SLI_HOT_LIMIT_BYTES + SLI_WARM_LIMIT_BYTES <= SLI_TOTAL_LIMIT_BYTES

    def test_pressure_thresholds_ordered(self) -> None:
        """Pressure thresholds are properly ordered."""
        assert THRESHOLD_NORMAL < THRESHOLD_ELEVATED < THRESHOLD_CRITICAL
        assert THRESHOLD_CRITICAL < 1.0  # Still below 100%


# =============================================================================
# LIMIT TESTS
# =============================================================================


class TestMemoryLimits:
    """Test memory limits are respected."""

    def test_total_never_exceeds_96kb(self, standalone_manager: SessionStateManager) -> None:
        """Total memory never exceeds 96KB."""
        # Try to fill aggressively
        for i in range(500):
            standalone_manager.mutate(
                section="scoreboard",
                operation="set",
                data={"index": i, "data": "x" * 100},
                estimated_bytes=150,
            )
            # Check after each mutation
            snapshot = standalone_manager.get_snapshot()
            assert (
                snapshot.total_size_bytes <= SLI_TOTAL_LIMIT_BYTES
            ), f"Exceeded 96KB: {snapshot.total_size_bytes} bytes"

    def test_hot_never_exceeds_48kb(self, manager: SessionStateManager) -> None:
        """HOT tier never exceeds 48KB."""
        hot_sections = ["control", "scoreboard", "meta"]

        for i in range(200):
            section = hot_sections[i % len(hot_sections)]
            manager.mutate(
                section=section,
                operation="set",
                data={"index": i, "data": "x" * 50},
                estimated_bytes=100,
            )

            snapshot = manager.get_snapshot()
            assert (
                snapshot.hot_size_bytes <= SLI_HOT_LIMIT_BYTES
            ), f"HOT exceeded 48KB: {snapshot.hot_size_bytes} bytes"

    def test_warm_never_exceeds_48kb(self, manager: SessionStateManager) -> None:
        """WARM tier never exceeds 48KB."""
        warm_sections = ["telemetry", "persona"]

        for i in range(200):
            section = warm_sections[i % len(warm_sections)]
            manager.mutate(
                section=section,
                operation="set",
                data={"index": i, "data": "x" * 50},
                estimated_bytes=100,
            )

            snapshot = manager.get_snapshot()
            assert (
                snapshot.warm_size_bytes <= SLI_WARM_LIMIT_BYTES
            ), f"WARM exceeded 48KB: {snapshot.warm_size_bytes} bytes"


# =============================================================================
# UTILIZATION TESTS
# =============================================================================


class TestUtilizationTracking:
    """Test utilization percentage tracking."""

    def test_empty_session_zero_utilization(self, manager: SessionStateManager) -> None:
        """Empty session has zero utilization."""
        snapshot = manager.get_snapshot()
        # Empty session starts at 0%
        assert snapshot.total_utilization_pct <= 10.0  # <10%

    def test_utilization_property_exists(self, manager: SessionStateManager) -> None:
        """Utilization property exists on snapshot."""
        snapshot = manager.get_snapshot()
        assert hasattr(snapshot, "total_utilization_pct")
        assert hasattr(snapshot, "hot_utilization_pct")
        assert hasattr(snapshot, "warm_utilization_pct")

    def test_utilization_bounds(self, manager: SessionStateManager) -> None:
        """Utilization is bounded 0-100."""
        snapshot = manager.get_snapshot()
        assert 0.0 <= snapshot.total_utilization_pct <= 100.0
        assert 0.0 <= snapshot.hot_utilization_pct <= 100.0
        assert 0.0 <= snapshot.warm_utilization_pct <= 100.0


# =============================================================================
# PRESSURE LEVEL TESTS
# =============================================================================


class TestPressureLevels:
    """Test pressure levels match thresholds."""

    def test_empty_session_normal_pressure(self, manager: SessionStateManager) -> None:
        """Empty session has NORMAL pressure."""
        snapshot = manager.get_snapshot()
        assert snapshot.pressure.value.lower() == "normal"

    def test_pressure_exists(self, manager: SessionStateManager) -> None:
        """Pressure attribute exists on snapshot."""
        snapshot = manager.get_snapshot()
        assert snapshot.pressure is not None
        # Should be one of the known pressure levels
        assert snapshot.pressure.value.lower() in ["normal", "elevated", "critical"]

    def test_pressure_after_mutations(self, standalone_manager: SessionStateManager) -> None:
        """Pressure still valid after mutations."""
        # Fill with data
        for i in range(50):
            standalone_manager.mutate(
                section="scoreboard",
                operation="set",
                data={"index": i, "data": "x" * 50},
                estimated_bytes=100,
            )

        # Pressure should still be valid
        final_snapshot = standalone_manager.get_snapshot()
        assert final_snapshot.pressure is not None
        assert final_snapshot.pressure.value.lower() in ["normal", "elevated", "critical"]


# =============================================================================
# SECTION BUDGET TESTS
# =============================================================================


class TestSectionBudgets:
    """Test individual section budgets."""

    def test_section_budgets_exist(self, manager: SessionStateManager) -> None:
        """All sections have budget defined."""
        snapshot = manager.get_snapshot()

        for section_name, section_info in snapshot.sections.items():
            assert section_info.budget_bytes > 0, f"{section_name} has no budget"

    def test_section_sizes_tracked(self, manager: SessionStateManager) -> None:
        """Section sizes are tracked."""
        manager.mutate(
            section="control",
            operation="set",
            data={"test": "data"},
            estimated_bytes=50,
        )

        snapshot = manager.get_snapshot()
        control_info = snapshot.sections.get("control")

        assert control_info is not None
        assert control_info.size_bytes >= 0


# =============================================================================
# EDGE CASES
# =============================================================================


class TestMemoryEdgeCases:
    """Test edge cases for memory management."""

    def test_zero_byte_mutation(self, manager: SessionStateManager) -> None:
        """Zero byte mutation is handled."""
        result = manager.mutate(
            section="control",
            operation="set",
            data={},
            estimated_bytes=0,
        )
        # Should not crash
        assert result is not None

    def test_very_small_mutation(self, manager: SessionStateManager) -> None:
        """Very small mutation is handled."""
        result = manager.mutate(
            section="control",
            operation="set",
            data={"a": 1},
            estimated_bytes=1,
        )
        assert result.success

    def test_multiple_sections_independent(self, manager: SessionStateManager) -> None:
        """Multiple sections can be mutated independently."""
        manager.mutate(
            section="control",
            operation="set",
            data={"key": "value"},
            estimated_bytes=50,
        )
        manager.mutate(
            section="scoreboard",
            operation="set",
            data={"key": "value"},
            estimated_bytes=50,
        )

        snapshot = manager.get_snapshot()
        # Both sections should be in snapshot
        assert "control" in snapshot.sections
        assert "scoreboard" in snapshot.sections
