"""Confidence model tests for ConfidenceModel (M9.4).

Covers V14 (monotonicity), V15 (bounds), plus per-action formulas
and boundary values.
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.reconciliation.confidence import ConfidenceModel  # noqa: E402
from k0.pipelines.p03.event_state import ReconciliationAction

# ===================================================================
# V14: Monotonicity
# ===================================================================


class TestMonotonicity:
    """V14: Confidence monotonically increases with similarity for same action."""

    def test_reinforce_monotonic(self):
        """Higher similarity -> higher confidence for REINFORCE."""
        sims = [0.85, 0.88, 0.92, 0.96, 1.0]
        confidences = [
            ConfidenceModel.compute(ReconciliationAction.REINFORCE, s, 1, 1, True) for s in sims
        ]
        for i in range(len(confidences) - 1):
            assert confidences[i] <= confidences[i + 1], (
                f"REINFORCE: conf at sim={sims[i]} ({confidences[i]:.4f}) > "
                f"conf at sim={sims[i+1]} ({confidences[i+1]:.4f})"
            )

    def test_extend_monotonic(self):
        """Higher similarity -> higher confidence for EXTEND."""
        sims = [0.60, 0.65, 0.70, 0.75, 0.80]
        confidences = [
            ConfidenceModel.compute(ReconciliationAction.EXTEND, s, 1, 1, True) for s in sims
        ]
        for i in range(len(confidences) - 1):
            assert confidences[i] <= confidences[i + 1]

    def test_evolve_monotonic(self):
        """Higher similarity -> higher confidence for EVOLVE."""
        sims = [0.40, 0.44, 0.48, 0.52, 0.56]
        confidences = [
            ConfidenceModel.compute(ReconciliationAction.EVOLVE, s, 1, 1, True) for s in sims
        ]
        for i in range(len(confidences) - 1):
            assert confidences[i] <= confidences[i + 1]


# ===================================================================
# V15: Bounds [0.0, 1.0]
# ===================================================================


class TestBounds:
    """V15: Confidence always in [0.0, 1.0]."""

    @pytest.mark.parametrize("action", list(ReconciliationAction))
    def test_confidence_in_bounds(self, action):
        """All actions produce confidence in [0.0, 1.0]."""
        for sim in [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]:
            for cc in [0, 1, 3, 5, 10]:
                for im in [True, False]:
                    conf = ConfidenceModel.compute(action, sim, cc, cc, im)
                    assert 0.0 <= conf <= 1.0, (
                        f"Out of bounds: action={action.value}, sim={sim}, "
                        f"cc={cc}, im={im} -> {conf}"
                    )

    def test_extreme_similarity_values(self):
        """Extreme input values still produce bounded output."""
        for sim in [-1.0, -0.5, 0.0, 1.0, 1.5, 100.0]:
            conf = ConfidenceModel.compute(ReconciliationAction.REINFORCE, sim, 1, 1, True)
            assert 0.0 <= conf <= 1.0

    def test_zero_candidates(self):
        """Zero compatible candidates -> valid confidence."""
        conf = ConfidenceModel.compute(ReconciliationAction.CREATE, 0.0, 0, 0, False)
        assert 0.0 <= conf <= 1.0


# ===================================================================
# Per-action confidence ranges
# ===================================================================


class TestPerActionFormulas:
    """Per-action confidence range verification (M9.4.8 table)."""

    def test_reinforce_range(self):
        """REINFORCE: base=0.50 + evidence(0-0.40) + boosts."""
        # Minimum: sim=0.85, no boosts
        low = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.85, 0, 0, False)
        assert 0.50 <= low <= 0.55

        # Maximum: sim=1.0, identity=True, 5+ compatible
        high = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 1.0, 5, 5, True)
        assert 0.90 <= high <= 1.0

    def test_extend_range(self):
        """EXTEND: base=0.45 + evidence(0-0.35) + boosts."""
        low = ConfidenceModel.compute(ReconciliationAction.EXTEND, 0.60, 0, 0, False)
        assert 0.45 <= low <= 0.50

        high = ConfidenceModel.compute(ReconciliationAction.EXTEND, 0.85, 5, 5, True)
        assert 0.80 <= high <= 0.95

    def test_evolve_range(self):
        """EVOLVE: base=0.40 + evidence(0-0.25) + boosts."""
        low = ConfidenceModel.compute(ReconciliationAction.EVOLVE, 0.40, 0, 0, False)
        assert 0.40 <= low <= 0.45

        high = ConfidenceModel.compute(ReconciliationAction.EVOLVE, 0.60, 5, 5, True)
        assert 0.65 <= high <= 0.80

    def test_create_range(self):
        """CREATE: base=0.35 + evidence=0.15 (flat) + boosts."""
        low = ConfidenceModel.compute(ReconciliationAction.CREATE, 0.0, 0, 0, False)
        assert 0.50 <= low <= 0.55  # 0.35 + 0.15

        high = ConfidenceModel.compute(ReconciliationAction.CREATE, 0.0, 5, 10, True)
        assert 0.55 <= high <= 0.65

    def test_contradict_fixed(self):
        """CONTRADICT: fixed 0.90 (Tier 1 only)."""
        conf = ConfidenceModel.compute(ReconciliationAction.CONTRADICT, 0.0, 0, 0, False)
        assert conf == 0.90

    def test_skip_fixed(self):
        """SKIP: fixed 1.00."""
        conf = ConfidenceModel.compute(ReconciliationAction.SKIP, 0.0, 0, 0, False)
        assert conf == 1.00

    def test_prune_fixed(self):
        """PRUNE: fixed 1.00."""
        conf = ConfidenceModel.compute(ReconciliationAction.PRUNE, 0.0, 0, 0, False)
        assert conf == 1.00


# ===================================================================
# Identity and count boosts
# ===================================================================


class TestBoosts:
    """Identity and count boost mechanics."""

    def test_identity_boost(self):
        """Identity match adds 0.05."""
        without = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 1, 1, False)
        with_match = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 1, 1, True)
        assert abs((with_match - without) - 0.05) < 1e-6

    def test_count_boost_3(self):
        """3+ compatible adds 0.02."""
        base = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 2, 2, False)
        boosted = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 3, 3, False)
        assert abs((boosted - base) - 0.02) < 1e-6

    def test_count_boost_5(self):
        """5+ compatible adds 0.05."""
        base = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 2, 2, False)
        boosted = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 5, 5, False)
        assert abs((boosted - base) - 0.05) < 1e-6

    def test_count_boost_1_or_2_is_zero(self):
        """1 or 2 compatible -> no count boost."""
        c1 = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 1, 1, False)
        c2 = ConfidenceModel.compute(ReconciliationAction.REINFORCE, 0.90, 2, 2, False)
        assert abs(c1 - c2) < 1e-6
