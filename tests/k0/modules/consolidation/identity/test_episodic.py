"""EpisodicIdentity end-to-end scoring tests (M9.2 -- D11).

Validates V3, V4, V6, V8 exit gates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k0.modules.consolidation.identity.episodic import EpisodicIdentity
from k0.modules.consolidation.identity.features import FEATURE_NAMES, NUM_FEATURES
from k0.modules.consolidation.types import (
    IdentityResult,
    K1SignalBundle,
    ReconciliationCandidate,
    TruthRecord,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cand(metadata: dict | None = None, **k1) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id="c1",
        layer="st_epi",
        source_phase="R2",
        metadata=metadata or {},
        k1_signals=K1SignalBundle(**k1),
    )


def _truth(metadata: dict | None = None) -> TruthRecord:
    return TruthRecord(
        record_id="t1",
        layer="st_epi",
        metadata=metadata or {},
    )


@pytest.fixture()
def scorer() -> EpisodicIdentity:
    return EpisodicIdentity()


# ---------------------------------------------------------------------------
# V3: Frozen weights loaded correctly
# ---------------------------------------------------------------------------


class TestWeightsLoading:
    def test_coef_shape(self, scorer: EpisodicIdentity):
        """V3: coef_.shape == (3, 11)."""
        assert scorer._coef.shape == (3, NUM_FEATURES)

    def test_intercept_shape(self, scorer: EpisodicIdentity):
        """V3: intercept_.shape == (3,)."""
        assert scorer._intercept.shape == (3,)

    def test_classes_count(self, scorer: EpisodicIdentity):
        assert scorer._classes == ["CREATE", "EXTEND", "REINFORCE"]

    def test_threshold(self, scorer: EpisodicIdentity):
        assert scorer._threshold == pytest.approx(0.35)

    def test_weights_file_exists(self):
        p = (
            Path(__file__).parents[5]
            / "k0"
            / "modules"
            / "consolidation"
            / "identity"
            / "weights"
            / "episodic_v1.json"
        )
        assert p.exists()

    def test_bad_weights_raises(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text(
            '{"classes":["A","B"],"coefficients":[[1,2],[3,4]],"intercepts":[0,0],"feature_names":["x","y"]}'
        )
        with pytest.raises(ValueError, match="Weight matrix shape"):
            EpisodicIdentity(weights_path=bad)


# ---------------------------------------------------------------------------
# V4: Softmax output sums to 1.0
# ---------------------------------------------------------------------------


class TestSoftmaxNormalization:
    def test_probabilities_sum_to_one(self, scorer: EpisodicIdentity):
        """V4: abs(sum(proba) - 1.0) < 1e-6."""
        result = scorer.score_identity(_cand(), _truth(), 0.5)
        total = result.p_create + result.p_extend + result.p_reinforce
        assert total == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.parametrize("cosine_sim", [0.0, 0.1, 0.5, 0.9, 1.0])
    def test_sum_across_cosine_range(self, scorer: EpisodicIdentity, cosine_sim: float):
        result = scorer.score_identity(_cand(), _truth(), cosine_sim)
        total = result.p_create + result.p_extend + result.p_reinforce
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_probabilities_non_negative(self, scorer: EpisodicIdentity):
        result = scorer.score_identity(_cand(), _truth(), 0.5)
        assert result.p_create >= 0.0
        assert result.p_extend >= 0.0
        assert result.p_reinforce >= 0.0

    def test_score_equals_p_extend_plus_p_reinforce(self, scorer: EpisodicIdentity):
        result = scorer.score_identity(_cand(), _truth(), 0.5)
        assert result.score == pytest.approx(result.p_extend + result.p_reinforce, abs=1e-9)


# ---------------------------------------------------------------------------
# V6: K1 signals NOT checked by strategy (strategy still scores normally)
# ---------------------------------------------------------------------------


class TestK1SignalPassthrough:
    """Strategy computes features from K1 signals but does NOT bypass scoring."""

    def test_correction_signal_still_scores(self, scorer: EpisodicIdentity):
        """V6: score_identity returns a result even with correction_signal=True."""
        result = scorer.score_identity(_cand(correction_signal=True), _truth(), 0.5)
        assert isinstance(result, IdentityResult)
        assert 0.0 <= result.score <= 1.0

    def test_contradiction_signal_still_scores(self, scorer: EpisodicIdentity):
        result = scorer.score_identity(_cand(contradiction_signal=True), _truth(), 0.5)
        assert isinstance(result, IdentityResult)
        assert 0.0 <= result.score <= 1.0


# ---------------------------------------------------------------------------
# V8: No sklearn import in production code
# ---------------------------------------------------------------------------


class TestNoSklearn:
    def test_no_sklearn_in_identity_modules(self):
        """V8: no sklearn import in production identity code."""
        identity_dir = Path(__file__).parents[5] / "k0" / "modules" / "consolidation" / "identity"
        for py in identity_dir.rglob("*.py"):
            content = py.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert (
                    "import sklearn" not in stripped and "from sklearn" not in stripped
                ), f"sklearn import found in {py.name}: {stripped}"


# ---------------------------------------------------------------------------
# Scoring behaviour
# ---------------------------------------------------------------------------


class TestScoringBehaviour:
    def test_high_similarity_high_score(self, scorer: EpisodicIdentity):
        """High topic + participant + cosine overlap should yield high p_assign."""
        c = _cand(
            metadata={
                "topics": {"travel", "food"},
                "participants": {"alice", "bob"},
                "focal": "alice",
                "social_context": "family",
                "place_id": "p1",
                "source_type": "chat",
            }
        )
        t = _truth(
            metadata={
                "topics": {"travel", "food"},
                "participants": {"alice", "bob"},
                "focal": "alice",
                "social_context": "family",
                "locations": {"p1"},
                "source_types": {"chat"},
            }
        )
        result = scorer.score_identity(c, t, cosine_sim=0.95)
        assert result.score > 0.5  # Should lean EXTEND/REINFORCE

    def test_low_similarity_low_score(self, scorer: EpisodicIdentity):
        """Completely disjoint metadata should yield lower p_assign than high-match case."""
        c = _cand(
            metadata={
                "topics": {"sports"},
                "participants": {"dave"},
                "focal": "dave",
                "social_context": "work",
                "place_id": "p99",
                "source_type": "email",
            }
        )
        t = _truth(
            metadata={
                "topics": {"cooking"},
                "participants": {"eve"},
                "focal": "eve",
                "social_context": "family",
                "locations": {"p1"},
                "source_types": {"chat"},
            }
        )
        low_result = scorer.score_identity(c, t, cosine_sim=0.1)
        # Compare against a high-match pair to verify monotonicity
        c_hi = _cand(
            metadata={
                "topics": {"cooking"},
                "participants": {"eve"},
                "focal": "eve",
                "social_context": "family",
                "place_id": "p1",
                "source_type": "chat",
            }
        )
        hi_result = scorer.score_identity(c_hi, t, cosine_sim=0.95)
        assert low_result.score < hi_result.score

    def test_recommended_action_is_valid(self, scorer: EpisodicIdentity):
        result = scorer.score_identity(_cand(), _truth(), 0.5)
        assert result.recommended_action in {"CREATE", "EXTEND", "REINFORCE"}

    def test_result_features_dict(self, scorer: EpisodicIdentity):
        result = scorer.score_identity(_cand(), _truth(), 0.5)
        assert set(result.features.keys()) == set(FEATURE_NAMES)
        assert all(isinstance(v, float) for v in result.features.values())
