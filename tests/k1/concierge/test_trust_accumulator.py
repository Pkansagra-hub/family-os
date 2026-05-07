"""
tests.k1.concierge.test_trust_accumulator
E-0.5.26 I-0.5.26.1: TrustAccumulator (OPP-4) tests.

Validates:
    1. Initial state and defaults.
    2. Trust score clamping (min=0.0, max=1.0).
    3. record_outcome() for all 6 event types.
    4. should_auto_approve() threshold: ≥0.85 trust AND risk=="low".
    5. Boundary tests: 0.84/0.85/0.86 trust × low/medium/high risk.
    6. get_dynamic_max_rounds() trust-based adjustment.
    7. snapshot() / restore() round-trip.
    8. Trust accumulation over sequences.
    9. Unknown event handling (no-op).
"""

from __future__ import annotations

import pytest

from k1.concierge.protocols.trust_accumulator import (
    TRUST_EVENT_APPROVE,
    TRUST_EVENT_AUTO_SUCCESS,
    TRUST_EVENT_CANCEL,
    TRUST_EVENT_MODIFY,
    TRUST_EVENT_REJECT,
    TRUST_EVENT_TIMEOUT,
    TrustAccumulator,
    TrustConfig,
    TrustSnapshot,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def ta() -> TrustAccumulator:
    return TrustAccumulator()


@pytest.fixture
def ta_high() -> TrustAccumulator:
    """Accumulator starting at high trust (above auto-approve threshold)."""
    return TrustAccumulator(TrustConfig(initial_trust=0.90))


@pytest.fixture
def ta_low() -> TrustAccumulator:
    """Accumulator starting at very low trust."""
    return TrustAccumulator(TrustConfig(initial_trust=0.05))


# =========================================================================
# 1. Initial state + defaults
# =========================================================================


class TestInitialState:
    def test_default_trust(self, ta: TrustAccumulator) -> None:
        assert ta.trust_score == 0.5

    def test_zero_interactions(self, ta: TrustAccumulator) -> None:
        assert ta.total_interactions == 0

    def test_custom_initial_trust(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.7))
        assert ta.trust_score == 0.7

    def test_default_config_values(self) -> None:
        cfg = TrustConfig()
        assert cfg.initial_trust == 0.5
        assert cfg.reward_approve == 0.05
        assert cfg.penalty_reject == -0.10
        assert cfg.penalty_cancel == -0.07
        assert cfg.penalty_modify == -0.03
        assert cfg.reward_auto_success == 0.08
        assert cfg.auto_approve_threshold == 0.85
        assert cfg.min_trust == 0.0
        assert cfg.max_trust == 1.0
        assert cfg.decay_per_turn == 0.0


# =========================================================================
# 2. record_outcome() for each event type
# =========================================================================


class TestRecordOutcome:
    def test_approve_increases_trust(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome(TRUST_EVENT_APPROVE)
        assert new == pytest.approx(0.55)
        assert ta.trust_score == pytest.approx(0.55)

    def test_reject_decreases_trust(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome(TRUST_EVENT_REJECT)
        assert new == pytest.approx(0.40)

    def test_cancel_decreases_trust(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome(TRUST_EVENT_CANCEL)
        assert new == pytest.approx(0.43)

    def test_modify_slight_decrease(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome(TRUST_EVENT_MODIFY)
        assert new == pytest.approx(0.47)

    def test_auto_success_increases_trust(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome(TRUST_EVENT_AUTO_SUCCESS)
        assert new == pytest.approx(0.58)

    def test_timeout_no_change(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome(TRUST_EVENT_TIMEOUT)
        assert new == pytest.approx(0.50)

    def test_unknown_event_no_change(self, ta: TrustAccumulator) -> None:
        new = ta.record_outcome("unknown_event")
        assert new == pytest.approx(0.50)

    def test_interaction_count_increments(self, ta: TrustAccumulator) -> None:
        ta.record_outcome(TRUST_EVENT_APPROVE)
        ta.record_outcome(TRUST_EVENT_REJECT)
        assert ta.total_interactions == 2


# =========================================================================
# 3. Trust clamping
# =========================================================================


class TestTrustClamping:
    def test_clamped_to_max(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.98))
        ta.record_outcome(TRUST_EVENT_APPROVE)  # +0.05 → 1.03 → clamped 1.0
        assert ta.trust_score == 1.0

    def test_clamped_to_min(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.02))
        ta.record_outcome(TRUST_EVENT_REJECT)  # -0.10 → -0.08 → clamped 0.0
        assert ta.trust_score == 0.0

    def test_repeated_approvals_stay_at_max(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.95))
        for _ in range(10):
            ta.record_outcome(TRUST_EVENT_APPROVE)
        assert ta.trust_score == 1.0

    def test_repeated_rejections_stay_at_min(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.10))
        for _ in range(10):
            ta.record_outcome(TRUST_EVENT_REJECT)
        assert ta.trust_score == 0.0


# =========================================================================
# 4. should_auto_approve() — threshold boundary tests
# =========================================================================


class TestShouldAutoApprove:
    def test_below_threshold_low_risk(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.84))
        assert ta.should_auto_approve("low") is False

    def test_at_threshold_low_risk(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.85))
        assert ta.should_auto_approve("low") is True

    def test_above_threshold_low_risk(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.86))
        assert ta.should_auto_approve("low") is True

    def test_above_threshold_medium_risk(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.90))
        assert ta.should_auto_approve("medium") is False

    def test_above_threshold_high_risk(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.95))
        assert ta.should_auto_approve("high") is False

    def test_default_risk_is_low(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.90))
        assert ta.should_auto_approve() is True

    def test_max_trust_low_risk(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=1.0))
        assert ta.should_auto_approve("low") is True

    def test_zero_trust_low_risk(self, ta_low: TrustAccumulator) -> None:
        assert ta_low.should_auto_approve("low") is False

    def test_custom_threshold(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.6, auto_approve_threshold=0.5))
        assert ta.should_auto_approve("low") is True


# =========================================================================
# 5. get_dynamic_max_rounds()
# =========================================================================


class TestDynamicMaxRounds:
    def test_default_trust_returns_base(self, ta: TrustAccumulator) -> None:
        assert ta.get_dynamic_max_rounds(2) == 2

    def test_high_trust_reduces_rounds(self, ta_high: TrustAccumulator) -> None:
        assert ta_high.get_dynamic_max_rounds(3) == 2

    def test_very_high_trust_floor_is_one(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.95))
        assert ta.get_dynamic_max_rounds(1) == 1  # max(1, 1-1) = 1

    def test_low_trust_increases_rounds(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.15))
        assert ta.get_dynamic_max_rounds(2) == 3

    def test_mid_trust_returns_base(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.5))
        assert ta.get_dynamic_max_rounds(4) == 4

    def test_trust_exactly_0_9(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.9))
        assert ta.get_dynamic_max_rounds(2) == 1

    def test_trust_exactly_0_2(self) -> None:
        ta = TrustAccumulator(TrustConfig(initial_trust=0.2))
        assert ta.get_dynamic_max_rounds(2) == 3


# =========================================================================
# 6. snapshot() / restore() round-trip
# =========================================================================


class TestSnapshotRestore:
    def test_snapshot_fields(self, ta: TrustAccumulator) -> None:
        ta.record_outcome(TRUST_EVENT_APPROVE)
        ta.record_outcome(TRUST_EVENT_REJECT)
        snap = ta.snapshot()
        assert isinstance(snap, TrustSnapshot)
        assert snap.trust_score == pytest.approx(0.45)
        assert snap.total_interactions == 2
        assert snap.approvals == 1
        assert snap.rejections == 1
        assert snap.auto_approvals == 0
        assert snap.last_event == TRUST_EVENT_REJECT

    def test_restore_recovers_state(self) -> None:
        ta1 = TrustAccumulator()
        ta1.record_outcome(TRUST_EVENT_APPROVE)
        ta1.record_outcome(TRUST_EVENT_APPROVE)
        ta1.record_outcome(TRUST_EVENT_AUTO_SUCCESS)
        snap = ta1.snapshot()

        ta2 = TrustAccumulator()
        ta2.restore(snap)
        assert ta2.trust_score == ta1.trust_score
        assert ta2.total_interactions == ta1.total_interactions

    def test_snapshot_auto_approvals_counted(self) -> None:
        ta = TrustAccumulator()
        ta.record_outcome(TRUST_EVENT_AUTO_SUCCESS)
        ta.record_outcome(TRUST_EVENT_AUTO_SUCCESS)
        snap = ta.snapshot()
        assert snap.auto_approvals == 2

    def test_snapshot_last_event_ns_populated(self, ta: TrustAccumulator) -> None:
        ta.record_outcome(TRUST_EVENT_APPROVE)
        snap = ta.snapshot()
        assert snap.last_event_ns > 0


# =========================================================================
# 7. Accumulation sequences
# =========================================================================


class TestAccumulationSequences:
    def test_gradual_trust_buildup(self) -> None:
        """7 approvals from 0.5: 0.5 + 7*0.05 = 0.85 → auto-approve."""
        ta = TrustAccumulator()
        for _ in range(7):
            ta.record_outcome(TRUST_EVENT_APPROVE)
        assert ta.trust_score == pytest.approx(0.85)
        assert ta.should_auto_approve("low") is True

    def test_trust_erosion(self) -> None:
        """High trust eroded by rejections."""
        ta = TrustAccumulator(TrustConfig(initial_trust=0.90))
        ta.record_outcome(TRUST_EVENT_REJECT)  # 0.80
        assert ta.should_auto_approve("low") is False
        assert ta.trust_score == pytest.approx(0.80)

    def test_mixed_sequence(self) -> None:
        """approve, reject, approve, modify → net: +0.05 -0.10 +0.05 -0.03 = -0.03"""
        ta = TrustAccumulator()
        ta.record_outcome(TRUST_EVENT_APPROVE)
        ta.record_outcome(TRUST_EVENT_REJECT)
        ta.record_outcome(TRUST_EVENT_APPROVE)
        ta.record_outcome(TRUST_EVENT_MODIFY)
        assert ta.trust_score == pytest.approx(0.47)
        assert ta.total_interactions == 4

    def test_timeout_preserves_trust(self, ta_high: TrustAccumulator) -> None:
        original = ta_high.trust_score
        ta_high.record_outcome(TRUST_EVENT_TIMEOUT)
        assert ta_high.trust_score == original
