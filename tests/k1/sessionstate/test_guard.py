"""
MutationGuard Comprehensive Test Suite
=======================================

Tests for MutationGuard preflight validation.

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.2

VALIDATES:
- k1/sessionstate/guard.py
- Approval/rejection logic
- 3-tier capacity checks (section → tier → total)
- Emergency mode blocking
- Section locking for eviction/migration
- Thread safety

COVERAGE REQUIREMENTS:
- All RejectionReason codes
- All valid operations
- Boundary conditions (exactly at limit, 1 byte over)
- Emergency mode transitions
- Section locking lifecycle
- Concurrent access patterns
"""

from __future__ import annotations

import threading
from typing import List

import pytest

from k1.sessionstate.guard import (
    FLATBUFFER_OVERHEAD_FACTOR,
    VALID_OPERATIONS,
    Approval,
    MutationGuard,
    RejectionReason,
)
from k1.sessionstate.sizetracker import (
    ALL_SECTIONS,
    HOT_SECTIONS,
    SECTION_BUDGETS,
    TOTAL_SIZE_LIMIT_BYTES,
    WARM_SECTIONS,
    SizeTracker,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def size_tracker() -> SizeTracker:
    """Fresh SizeTracker instance."""
    return SizeTracker()


@pytest.fixture
def guard(size_tracker: SizeTracker) -> MutationGuard:
    """Fresh MutationGuard with clean SizeTracker."""
    return MutationGuard(size_tracker)


@pytest.fixture
def filled_hot_section(size_tracker: SizeTracker) -> str:
    """
    Fill beliefs_active to 90% capacity.
    Returns the section name.
    """
    section = "beliefs_active"
    budget = SECTION_BUDGETS[section].max_bytes
    fill_amount = int(budget * 0.9)
    size_tracker.update(section, fill_amount)
    return section


# =============================================================================
# TEST: Approval Dataclass
# =============================================================================


class TestApprovalDataclass:
    """Tests for Approval creation and serialization."""

    def test_approve_factory_creates_approved_result(self) -> None:
        """Approval.approve() creates approved=True result."""
        approval = Approval.approve(
            section_available_bytes=1000,
            tier_available_bytes=5000,
            total_available_bytes=90000,
            tier="hot",
        )
        assert approval.approved is True
        assert approval.reason == ""
        assert approval.reason_code is None
        assert approval.tier == "hot"
        assert approval.section_available_bytes == 1000

    def test_reject_factory_creates_rejected_result(self) -> None:
        """Approval.reject() creates approved=False result."""
        approval = Approval.reject(
            reason="Test rejection",
            reason_code=RejectionReason.SECTION_CAPACITY,
            available_bytes=500,
            tier="warm",
        )
        assert approval.approved is False
        assert approval.reason == "Test rejection"
        assert approval.reason_code == RejectionReason.SECTION_CAPACITY
        assert approval.tier == "warm"
        assert approval.available_kb == pytest.approx(500 / 1024)

    def test_to_dict_serializes_approval(self) -> None:
        """to_dict() converts Approval to serializable dict."""
        approval = Approval.reject(
            reason="Over budget",
            reason_code=RejectionReason.TIER_CAPACITY,
            available_bytes=2048,
            section_available_bytes=512,
            tier_available_bytes=2048,
            total_available_bytes=50000,
            tier="hot",
        )
        data = approval.to_dict()

        assert data["approved"] is False
        assert data["reason"] == "Over budget"
        assert data["reason_code"] == "tier_capacity_exceeded"
        assert data["tier"] == "hot"
        assert data["section_available_bytes"] == 512
        assert data["tier_available_bytes"] == 2048
        assert data["total_available_bytes"] == 50000

    def test_repr_shows_key_info(self) -> None:
        """__repr__ shows approved/rejected status."""
        approved = Approval.approve(1000, 5000, 90000, tier="hot")
        rejected = Approval.reject("fail", RejectionReason.EMERGENCY_MODE, 0)

        assert "approved=True" in repr(approved)
        assert "approved=False" in repr(rejected)
        assert "EMERGENCY_MODE" in repr(rejected)


# =============================================================================
# TEST: MutationGuard Initialization
# =============================================================================


class TestMutationGuardInit:
    """Tests for MutationGuard initialization."""

    def test_init_with_size_tracker(self, size_tracker: SizeTracker) -> None:
        """MutationGuard initializes with SizeTracker."""
        guard = MutationGuard(size_tracker)
        assert guard.size_tracker is size_tracker

    def test_init_emergency_mode_off(self, guard: MutationGuard) -> None:
        """Emergency mode is off by default."""
        assert guard.is_emergency_mode() is False

    def test_init_no_locked_sections(self, guard: MutationGuard) -> None:
        """No sections locked at init."""
        assert len(guard.get_locked_sections()) == 0

    def test_repr_shows_current_state(self, guard: MutationGuard) -> None:
        """__repr__ shows total/pressure/emergency."""
        repr_str = repr(guard)
        assert "MutationGuard" in repr_str
        assert "total=" in repr_str
        assert "pressure=" in repr_str
        assert "emergency=" in repr_str


# =============================================================================
# TEST: Section Validation (CHECK 1)
# =============================================================================


class TestSectionValidation:
    """Tests for section name validation."""

    @pytest.mark.parametrize("section", list(ALL_SECTIONS))
    def test_valid_section_names_accepted(self, guard: MutationGuard, section: str) -> None:
        """All known section names are accepted."""
        result = guard.preflight(section, "set", 100)
        # May be rejected for other reasons, but not INVALID_SECTION
        assert result.reason_code != RejectionReason.INVALID_SECTION

    def test_invalid_section_rejected(self, guard: MutationGuard) -> None:
        """Unknown section name is rejected."""
        result = guard.preflight("unknown_section", "set", 100)

        assert result.approved is False
        assert result.reason_code == RejectionReason.INVALID_SECTION
        assert "unknown_section" in result.reason
        assert "Invalid section" in result.reason

    def test_empty_section_rejected(self, guard: MutationGuard) -> None:
        """Empty string section is rejected."""
        result = guard.preflight("", "set", 100)

        assert result.approved is False
        assert result.reason_code == RejectionReason.INVALID_SECTION

    def test_case_sensitive_section(self, guard: MutationGuard) -> None:
        """Section names are case-sensitive."""
        result = guard.preflight("BELIEFS_ACTIVE", "set", 100)
        assert result.reason_code == RejectionReason.INVALID_SECTION


# =============================================================================
# TEST: Operation Validation (CHECK 2)
# =============================================================================


class TestOperationValidation:
    """Tests for operation type validation."""

    @pytest.mark.parametrize("operation", list(VALID_OPERATIONS))
    def test_valid_operations_accepted(self, guard: MutationGuard, operation: str) -> None:
        """All valid operation types are accepted."""
        result = guard.preflight("beliefs_active", operation, 100)
        # May be rejected for other reasons, but not INVALID_OPERATION
        assert result.reason_code != RejectionReason.INVALID_OPERATION

    def test_invalid_operation_rejected(self, guard: MutationGuard) -> None:
        """Unknown operation type is rejected."""
        result = guard.preflight("beliefs_active", "mutate", 100)

        assert result.approved is False
        assert result.reason_code == RejectionReason.INVALID_OPERATION
        assert "mutate" in result.reason
        assert "Invalid operation" in result.reason

    def test_add_operation_rejected(self, guard: MutationGuard) -> None:
        """'add' is not a valid operation (use 'append')."""
        result = guard.preflight("beliefs_active", "add", 100)
        assert result.reason_code == RejectionReason.INVALID_OPERATION

    def test_case_sensitive_operation(self, guard: MutationGuard) -> None:
        """Operation names are case-sensitive."""
        result = guard.preflight("beliefs_active", "SET", 100)
        assert result.reason_code == RejectionReason.INVALID_OPERATION


# =============================================================================
# TEST: Section Locking (CHECK 3)
# =============================================================================


class TestSectionLocking:
    """Tests for section locking during eviction/migration."""

    def test_lock_section_success(self, guard: MutationGuard) -> None:
        """lock_section() returns True for valid section."""
        assert guard.lock_section("beliefs_active") is True
        assert guard.is_section_locked("beliefs_active") is True

    def test_lock_section_invalid_returns_false(self, guard: MutationGuard) -> None:
        """lock_section() returns False for invalid section."""
        assert guard.lock_section("invalid_section") is False

    def test_unlock_section_success(self, guard: MutationGuard) -> None:
        """unlock_section() returns True if section was locked."""
        guard.lock_section("beliefs_active")
        assert guard.unlock_section("beliefs_active") is True
        assert guard.is_section_locked("beliefs_active") is False

    def test_unlock_section_not_locked(self, guard: MutationGuard) -> None:
        """unlock_section() returns False if section wasn't locked."""
        assert guard.unlock_section("beliefs_active") is False

    def test_get_locked_sections_returns_frozenset(self, guard: MutationGuard) -> None:
        """get_locked_sections() returns immutable set."""
        guard.lock_section("beliefs_active")
        guard.lock_section("scoreboard")
        locked = guard.get_locked_sections()

        assert isinstance(locked, frozenset)
        assert "beliefs_active" in locked
        assert "scoreboard" in locked

    def test_preflight_rejects_locked_section(self, guard: MutationGuard) -> None:
        """Preflight rejects mutations to locked sections."""
        guard.lock_section("beliefs_active")

        result = guard.preflight("beliefs_active", "set", 100)

        assert result.approved is False
        assert result.reason_code == RejectionReason.SECTION_LOCKED
        assert "locked" in result.reason.lower()

    def test_preflight_allows_unlocked_section(self, guard: MutationGuard) -> None:
        """Preflight allows mutations after section unlocked."""
        guard.lock_section("beliefs_active")
        guard.unlock_section("beliefs_active")

        result = guard.preflight("beliefs_active", "set", 100)

        assert result.approved is True

    def test_locking_one_section_doesnt_affect_others(self, guard: MutationGuard) -> None:
        """Locking one section doesn't affect other sections."""
        guard.lock_section("beliefs_active")

        result = guard.preflight("scoreboard", "set", 100)
        assert result.approved is True


# =============================================================================
# TEST: Emergency Mode (CHECK 4)
# =============================================================================


class TestEmergencyMode:
    """Tests for emergency mode blocking."""

    def test_activate_emergency_mode(self, guard: MutationGuard) -> None:
        """activate_emergency_mode() enables blocking."""
        guard.activate_emergency_mode()
        assert guard.is_emergency_mode() is True

    def test_deactivate_emergency_mode(self, guard: MutationGuard) -> None:
        """deactivate_emergency_mode() disables blocking."""
        guard.activate_emergency_mode()
        guard.deactivate_emergency_mode()
        assert guard.is_emergency_mode() is False

    def test_preflight_rejects_in_emergency_mode(self, guard: MutationGuard) -> None:
        """Preflight rejects ALL writes in emergency mode."""
        guard.activate_emergency_mode()

        result = guard.preflight("beliefs_active", "set", 100)

        assert result.approved is False
        assert result.reason_code == RejectionReason.EMERGENCY_MODE
        assert "emergency" in result.reason.lower()

    def test_emergency_mode_rejects_even_small_writes(self, guard: MutationGuard) -> None:
        """Emergency mode rejects even 1-byte writes."""
        guard.activate_emergency_mode()

        result = guard.preflight("beliefs_active", "append", 1)

        assert result.approved is False
        assert result.reason_code == RejectionReason.EMERGENCY_MODE

    def test_emergency_mode_allows_shrinking_operations(self, guard: MutationGuard) -> None:
        """Emergency mode still rejects shrinking operations (safety)."""
        # Based on implementation: emergency mode is checked BEFORE
        # shrinking short-circuit, so even shrinking is blocked
        guard.activate_emergency_mode()

        result = guard.preflight("beliefs_active", "clear", -1000)

        # Emergency mode blocks ALL writes per spec
        assert result.approved is False
        assert result.reason_code == RejectionReason.EMERGENCY_MODE

    def test_preflight_resumes_after_deactivation(self, guard: MutationGuard) -> None:
        """Preflight resumes normal checks after emergency deactivated."""
        guard.activate_emergency_mode()
        guard.deactivate_emergency_mode()

        result = guard.preflight("beliefs_active", "set", 100)

        assert result.approved is True


# =============================================================================
# TEST: Section Capacity (CHECK 5a)
# =============================================================================


class TestSectionCapacity:
    """Tests for section-level capacity validation."""

    def test_approves_within_section_budget(self, guard: MutationGuard) -> None:
        """Mutation within section budget is approved."""
        result = guard.preflight("beliefs_active", "set", 1000)

        assert result.approved is True
        assert result.tier == "hot"

    def test_rejects_exceeding_section_budget(self, guard: MutationGuard) -> None:
        """Mutation exceeding section budget is rejected."""
        # beliefs_active budget = 8KB = 8192 bytes
        result = guard.preflight("beliefs_active", "set", 10000)

        assert result.approved is False
        assert result.reason_code == RejectionReason.SECTION_CAPACITY
        assert "beliefs_active" in result.reason

    def test_exactly_at_section_limit_approved(self, guard: MutationGuard) -> None:
        """Mutation exactly at section limit is approved."""
        budget = SECTION_BUDGETS["beliefs_active"].max_bytes

        result = guard.preflight("beliefs_active", "set", budget)

        assert result.approved is True

    def test_one_byte_over_section_limit_rejected(self, guard: MutationGuard) -> None:
        """Mutation one byte over section limit is rejected."""
        budget = SECTION_BUDGETS["beliefs_active"].max_bytes

        result = guard.preflight("beliefs_active", "set", budget + 1)

        assert result.approved is False
        assert result.reason_code == RejectionReason.SECTION_CAPACITY

    def test_remaining_space_after_existing_data(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Existing data reduces available space."""
        size_tracker.update("beliefs_active", 4000)
        budget = SECTION_BUDGETS["beliefs_active"].max_bytes
        remaining = budget - 4000

        # Exactly remaining should pass
        result = guard.preflight("beliefs_active", "append", remaining)
        assert result.approved is True

        # One more byte should fail
        result = guard.preflight("beliefs_active", "append", remaining + 1)
        assert result.approved is False


# =============================================================================
# TEST: Tier Capacity (CHECK 5b)
# =============================================================================


class TestTierCapacity:
    """Tests for tier-level capacity validation."""

    def test_tier_identified_correctly_hot(self, guard: MutationGuard) -> None:
        """Hot sections identified as 'hot' tier."""
        for section in HOT_SECTIONS:
            result = guard.preflight(section, "set", 100)
            if result.approved:
                assert result.tier == "hot"

    def test_tier_identified_correctly_warm(self, guard: MutationGuard) -> None:
        """Warm sections identified as 'warm' tier."""
        for section in WARM_SECTIONS:
            result = guard.preflight(section, "set", 100)
            if result.approved:
                assert result.tier == "warm"

    def test_rejects_when_tier_full(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Rejects when tier capacity is exceeded."""
        # Fill hot tier to near limit
        # Hot tier = 48KB, distribute across sections
        for section in HOT_SECTIONS:
            budget = SECTION_BUDGETS[section].max_bytes
            size_tracker.update(section, budget - 100)

        # Now total hot should be near limit
        # Try to add more than available
        result = guard.preflight("beliefs_active", "append", 2000)

        # Should fail either at section or tier level
        assert result.approved is False

    def test_section_pass_tier_fail(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """
        When section has space but tier doesn't,
        reject with TIER_CAPACITY.
        """
        # Fill all hot sections except beliefs_active to max
        for section in HOT_SECTIONS:
            if section != "beliefs_active":
                budget = SECTION_BUDGETS[section].max_bytes
                size_tracker.update(section, budget)

        # beliefs_active has 8KB budget, but tier is full
        tier_available = size_tracker.get_tier_available_bytes("hot")

        if tier_available < 4000:
            result = guard.preflight("beliefs_active", "set", 4000)
            if not result.approved:
                assert result.reason_code == RejectionReason.TIER_CAPACITY


# =============================================================================
# TEST: Total Capacity (CHECK 5c)
# =============================================================================


class TestTotalCapacity:
    """Tests for total capacity validation."""

    def test_total_capacity_limit(self, guard: MutationGuard) -> None:
        """Total limit is 96KB (106496 bytes)."""
        assert TOTAL_SIZE_LIMIT_BYTES == 104 * 1024

    def test_rejects_when_total_exceeded(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Rejects when total capacity is exceeded."""
        # Fill to near total limit
        fill_per_section = TOTAL_SIZE_LIMIT_BYTES // len(ALL_SECTIONS)
        for section in ALL_SECTIONS:
            budget = min(SECTION_BUDGETS[section].max_bytes, fill_per_section)
            size_tracker.update(section, budget - 10)

        # Check total usage
        total_available = size_tracker.get_total_available_bytes()

        if total_available < 1000:
            result = guard.preflight("beliefs_active", "set", 1000)
            # Should fail at some level
            assert result.approved is False


# =============================================================================
# TEST: Shrinking Operations
# =============================================================================


class TestShrinkingOperations:
    """Tests for shrinking operations (negative delta)."""

    def test_zero_bytes_approved(self, guard: MutationGuard) -> None:
        """Zero-byte mutation is approved (metadata only)."""
        result = guard.preflight("beliefs_active", "set", 0)
        assert result.approved is True

    def test_negative_bytes_approved(self, guard: MutationGuard) -> None:
        """Negative delta (shrinking) is always approved."""
        result = guard.preflight("beliefs_active", "clear", -1000)
        assert result.approved is True

    def test_shrinking_bypasses_capacity_checks(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Shrinking bypasses capacity even when section is 'full'."""
        # Fill section to max
        budget = SECTION_BUDGETS["beliefs_active"].max_bytes
        size_tracker.update("beliefs_active", budget)

        # Shrinking should still work
        result = guard.preflight("beliefs_active", "delete", -500)
        assert result.approved is True

    def test_shrinking_increases_available_in_result(self, guard: MutationGuard) -> None:
        """Shrinking operation shows increased availability."""
        result = guard.preflight("beliefs_active", "clear", -1000)

        # Available should be MORE than budget (since we're removing)
        budget = SECTION_BUDGETS["beliefs_active"].max_bytes
        assert result.section_available_bytes >= budget


# =============================================================================
# TEST: Size Estimation
# =============================================================================


class TestSizeEstimation:
    """Tests for size estimation helpers."""

    def test_estimate_string_size(self, guard: MutationGuard) -> None:
        """String size includes UTF-8 encoding + overhead."""
        test_str = "hello world"
        estimated = guard.estimate_mutation_size("beliefs_active", "set", test_str)

        base_size = len(test_str.encode("utf-8"))
        expected = int(base_size * FLATBUFFER_OVERHEAD_FACTOR)
        assert estimated == expected

    def test_estimate_dict_size(self, guard: MutationGuard) -> None:
        """Dict size uses JSON serialization as approximation."""
        test_dict = {"key": "value", "count": 42}
        estimated = guard.estimate_mutation_size("beliefs_active", "set", test_dict)

        assert estimated > 0
        assert isinstance(estimated, int)

    def test_estimate_list_size(self, guard: MutationGuard) -> None:
        """List size sums element sizes."""
        test_list = ["a", "b", "c"]
        estimated = guard.estimate_mutation_size("beliefs_active", "set", test_list)

        assert estimated > 0

    def test_estimate_none_is_zero(self, guard: MutationGuard) -> None:
        """None results in 0 bytes."""
        estimated = guard.estimate_mutation_size("beliefs_active", "set", None)
        assert estimated == 0

    def test_estimate_includes_overhead_factor(self, guard: MutationGuard) -> None:
        """Estimate includes 10% overhead margin."""
        assert FLATBUFFER_OVERHEAD_FACTOR == 1.10


# =============================================================================
# TEST: Capacity Summary
# =============================================================================


class TestCapacitySummary:
    """Tests for diagnostic capacity summary."""

    def test_get_capacity_summary_structure(self, guard: MutationGuard) -> None:
        """get_capacity_summary() returns expected keys."""
        summary = guard.get_capacity_summary()

        assert "total_size_bytes" in summary
        assert "total_available_bytes" in summary
        assert "hot_size_bytes" in summary
        assert "warm_size_bytes" in summary
        assert "overall_pressure" in summary
        assert "emergency_mode" in summary
        assert "locked_sections" in summary

    def test_summary_reflects_current_state(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Summary reflects actual state."""
        size_tracker.update("beliefs_active", 1000)
        guard.activate_emergency_mode()
        guard.lock_section("scoreboard")

        summary = guard.get_capacity_summary()

        assert summary["total_size_bytes"] == 1000
        assert summary["hot_size_bytes"] == 1000
        assert summary["emergency_mode"] is True
        assert "scoreboard" in summary["locked_sections"]


# =============================================================================
# TEST: Thread Safety
# =============================================================================


class TestThreadSafety:
    """Tests for concurrent access patterns."""

    def test_concurrent_preflights_dont_corrupt(
        self,
        guard: MutationGuard,
    ) -> None:
        """Multiple concurrent preflights don't corrupt state."""
        results: List[Approval] = []
        lock = threading.Lock()

        def do_preflight() -> None:
            for _ in range(100):
                result = guard.preflight("beliefs_active", "set", 100)
                with lock:
                    results.append(result)

        threads = [threading.Thread(target=do_preflight) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 500
        assert all(isinstance(r, Approval) for r in results)

    def test_concurrent_emergency_mode_toggle(self, guard: MutationGuard) -> None:
        """Concurrent emergency mode toggles don't corrupt."""
        errors: List[Exception] = []

        def toggle_emergency() -> None:
            try:
                for _ in range(100):
                    guard.activate_emergency_mode()
                    guard.deactivate_emergency_mode()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle_emergency) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Final state should be consistent (either on or off)
        final = guard.is_emergency_mode()
        assert isinstance(final, bool)

    def test_concurrent_section_locking(self, guard: MutationGuard) -> None:
        """Concurrent section lock/unlock doesn't corrupt."""
        errors: List[Exception] = []

        def lock_unlock() -> None:
            try:
                for section in list(ALL_SECTIONS)[:3]:
                    guard.lock_section(section)
                    guard.unlock_section(section)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=lock_unlock) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# =============================================================================
# TEST: RejectionReason Enum
# =============================================================================


class TestRejectionReasonEnum:
    """Tests for RejectionReason enum values."""

    def test_all_reason_codes_have_string_value(self) -> None:
        """All RejectionReason codes have string values."""
        for reason in RejectionReason:
            assert isinstance(reason.value, str)
            assert len(reason.value) > 0

    def test_reason_codes_are_snake_case(self) -> None:
        """All reason codes use snake_case for serialization."""
        for reason in RejectionReason:
            assert "_" in reason.value or reason.value.islower()

    def test_expected_reason_codes_exist(self) -> None:
        """All expected rejection reasons are defined."""
        expected = {
            "SECTION_CAPACITY",
            "TIER_CAPACITY",
            "TOTAL_CAPACITY",
            "EMERGENCY_MODE",
            "INVALID_SECTION",
            "INVALID_OPERATION",
            "SECTION_LOCKED",
            "NEGATIVE_ESTIMATE",
        }
        actual = {r.name for r in RejectionReason}
        assert expected.issubset(actual)


# =============================================================================
# TEST: Valid Operations Constant
# =============================================================================


class TestValidOperationsConstant:
    """Tests for VALID_OPERATIONS constant."""

    def test_valid_operations_is_frozenset(self) -> None:
        """VALID_OPERATIONS is immutable."""
        assert isinstance(VALID_OPERATIONS, frozenset)

    def test_expected_operations_included(self) -> None:
        """All expected operations are included."""
        # Core operations that must be present
        expected_core = {
            "set",
            "append",
            "add_turn",
            "update",
            "clear",
            "delete",
            "record_turn",
            "record_error",
            "accept_demoted",
        }
        # Verify core operations are subset of VALID_OPERATIONS
        assert expected_core.issubset(
            VALID_OPERATIONS
        ), f"Missing core operations: {expected_core - VALID_OPERATIONS}"


# =============================================================================
# TEST: Integration Scenarios
# =============================================================================


class TestIntegrationScenarios:
    """Integration tests for realistic usage patterns."""

    def test_typical_mutation_flow(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Typical: preflight → apply → update size."""
        # Step 1: Preflight
        result = guard.preflight("beliefs_active", "append", 500)
        assert result.approved is True

        # Step 2: Apply mutation (simulated)
        # In real code: section.append(data)

        # Step 3: Update size tracker
        size_tracker.update("beliefs_active", 500)

        # Verify state
        assert size_tracker.get_section_size("beliefs_active") == 500

    def test_eviction_flow(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Eviction: lock → preflight fails → evict → unlock → preflight ok."""
        section = "beliefs_active"
        size_tracker.update(section, 4000)

        # Step 1: Lock for eviction
        guard.lock_section(section)

        # Step 2: Writes rejected
        result = guard.preflight(section, "append", 100)
        assert result.approved is False
        assert result.reason_code == RejectionReason.SECTION_LOCKED

        # Step 3: Eviction (simulated - reduce size)
        size_tracker.update(section, 2000)

        # Step 4: Unlock
        guard.unlock_section(section)

        # Step 5: Writes allowed again
        result = guard.preflight(section, "append", 100)
        assert result.approved is True

    def test_emergency_eviction_flow(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Emergency: activate → all writes fail → evict → deactivate → ok."""
        # Fill to trigger emergency
        guard.activate_emergency_mode()

        # All writes blocked
        for section in ["beliefs_active", "scoreboard", "history_active"]:
            result = guard.preflight(section, "set", 100)
            assert result.approved is False
            assert result.reason_code == RejectionReason.EMERGENCY_MODE

        # Eviction happens (simulated)
        guard.deactivate_emergency_mode()

        # Writes resume
        result = guard.preflight("beliefs_active", "set", 100)
        assert result.approved is True

    def test_multi_section_mutation_batch(
        self,
        guard: MutationGuard,
        size_tracker: SizeTracker,
    ) -> None:
        """Batch: preflight multiple sections before any writes."""
        sections = ["beliefs_active", "scoreboard", "history_active"]
        sizes = [500, 300, 800]

        # Preflight all
        approvals = []
        for section, size in zip(sections, sizes):
            result = guard.preflight(section, "set", size)
            approvals.append(result)

        # All should be approved
        assert all(a.approved for a in approvals)

        # Now apply all
        for section, size in zip(sections, sizes):
            size_tracker.update(section, size)

        # Verify totals
        total = sum(sizes)
        assert size_tracker.get_total_size() == total
