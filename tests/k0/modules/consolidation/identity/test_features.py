"""Feature extraction unit tests (M9.2 -- D10).

Validates V2, V11 exit gates: each of the 11 features computed correctly.
"""

from __future__ import annotations

import numpy as np
import pytest

from k0.modules.consolidation.identity.features import (
    FEATURE_NAMES,
    NUM_FEATURES,
    extract_features,
    jaccard,
)
from k0.modules.consolidation.types import K1SignalBundle, ReconciliationCandidate, TruthRecord

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


# ---------------------------------------------------------------------------
# jaccard()
# ---------------------------------------------------------------------------


class TestJaccard:
    def test_identical_sets(self):
        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert jaccard({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        assert jaccard({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)

    def test_empty_both(self):
        assert jaccard(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard({"a"}, set()) == 0.0

    def test_single_element_match(self):
        assert jaccard({"x"}, {"x"}) == 1.0


# ---------------------------------------------------------------------------
# Feature vector shape and ordering
# ---------------------------------------------------------------------------


class TestFeatureVector:
    def test_returns_ndarray_shape_11(self):
        vec = extract_features(_cand(), _truth(), 0.5)
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (NUM_FEATURES,)
        assert vec.dtype == np.float64

    def test_feature_count_matches_names(self):
        assert NUM_FEATURES == 11
        assert len(FEATURE_NAMES) == 11


# ---------------------------------------------------------------------------
# Individual feature tests (indexed by FEATURE_NAMES order)
# ---------------------------------------------------------------------------


class TestCosineSimFeature:
    """Index 0: cosine_sim -- passthrough."""

    def test_passthrough(self):
        vec = extract_features(_cand(), _truth(), 0.87)
        assert vec[0] == pytest.approx(0.87)

    def test_zero(self):
        vec = extract_features(_cand(), _truth(), 0.0)
        assert vec[0] == pytest.approx(0.0)


class TestTopicOverlap:
    """Index 1: jaccard of topics."""

    def test_overlap(self):
        c = _cand(metadata={"topics": {"travel", "food"}})
        t = _truth(metadata={"topics": {"travel", "cooking"}})
        vec = extract_features(c, t, 0.5)
        # jaccard({travel,food}, {travel,cooking}) = 1/3
        assert vec[1] == pytest.approx(1.0 / 3.0)

    def test_no_topics(self):
        vec = extract_features(_cand(), _truth(), 0.5)
        assert vec[1] == pytest.approx(0.0)


class TestParticipantOverlap:
    """Index 2: jaccard of participants."""

    def test_overlap(self):
        c = _cand(metadata={"participants": {"alice", "bob"}})
        t = _truth(metadata={"participants": {"alice", "carol"}})
        vec = extract_features(c, t, 0.5)
        # jaccard = 1/3
        assert vec[2] == pytest.approx(1.0 / 3.0)

    def test_identical(self):
        c = _cand(metadata={"participants": {"alice"}})
        t = _truth(metadata={"participants": {"alice"}})
        vec = extract_features(c, t, 0.5)
        assert vec[2] == pytest.approx(1.0)


class TestFocusMatch:
    """Index 3: binary match on focal person."""

    def test_match(self):
        c = _cand(metadata={"focal": "alice"})
        t = _truth(metadata={"focal": "alice"})
        vec = extract_features(c, t, 0.5)
        assert vec[3] == pytest.approx(1.0)

    def test_mismatch(self):
        c = _cand(metadata={"focal": "alice"})
        t = _truth(metadata={"focal": "bob"})
        vec = extract_features(c, t, 0.5)
        assert vec[3] == pytest.approx(0.0)

    def test_empty_focal(self):
        c = _cand(metadata={"focal": ""})
        t = _truth(metadata={"focal": "alice"})
        vec = extract_features(c, t, 0.5)
        assert vec[3] == pytest.approx(0.0)


class TestSocialContextMatch:
    """Index 4: binary match on social context."""

    def test_match(self):
        c = _cand(metadata={"social_context": "family"})
        t = _truth(metadata={"social_context": "family"})
        vec = extract_features(c, t, 0.5)
        assert vec[4] == pytest.approx(1.0)

    def test_mismatch(self):
        c = _cand(metadata={"social_context": "work"})
        t = _truth(metadata={"social_context": "family"})
        vec = extract_features(c, t, 0.5)
        assert vec[4] == pytest.approx(0.0)


class TestLocationMatch:
    """Index 5: candidate.place_id in existing.locations."""

    def test_match(self):
        c = _cand(metadata={"place_id": "p1"})
        t = _truth(metadata={"locations": {"p1", "p2"}})
        vec = extract_features(c, t, 0.5)
        assert vec[5] == pytest.approx(1.0)

    def test_no_match(self):
        c = _cand(metadata={"place_id": "p3"})
        t = _truth(metadata={"locations": {"p1", "p2"}})
        vec = extract_features(c, t, 0.5)
        assert vec[5] == pytest.approx(0.0)

    def test_empty_place_id(self):
        c = _cand(metadata={"place_id": ""})
        t = _truth(metadata={"locations": {"p1"}})
        vec = extract_features(c, t, 0.5)
        assert vec[5] == pytest.approx(0.0)


class TestSourceTypeMatch:
    """Index 6: candidate.source_type in existing.source_types."""

    def test_match(self):
        c = _cand(metadata={"source_type": "chat"})
        t = _truth(metadata={"source_types": {"chat", "sms"}})
        vec = extract_features(c, t, 0.5)
        assert vec[6] == pytest.approx(1.0)

    def test_no_match(self):
        c = _cand(metadata={"source_type": "email"})
        t = _truth(metadata={"source_types": {"chat"}})
        vec = extract_features(c, t, 0.5)
        assert vec[6] == pytest.approx(0.0)


class TestInteractionFeatures:
    """Index 7: sim_x_focus_match, Index 8: sim_x_participant_overlap."""

    def test_sim_x_focus_match(self):
        c = _cand(metadata={"focal": "alice"})
        t = _truth(metadata={"focal": "alice"})
        vec = extract_features(c, t, 0.8)
        assert vec[7] == pytest.approx(0.8 * 1.0)  # cosine * focus

    def test_sim_x_focus_mismatch(self):
        c = _cand(metadata={"focal": "alice"})
        t = _truth(metadata={"focal": "bob"})
        vec = extract_features(c, t, 0.8)
        assert vec[7] == pytest.approx(0.0)  # cosine * 0

    def test_sim_x_participant_overlap(self):
        c = _cand(metadata={"participants": {"alice", "bob"}})
        t = _truth(metadata={"participants": {"alice", "carol"}})
        vec = extract_features(c, t, 0.9)
        # participant_overlap = 1/3
        assert vec[8] == pytest.approx(0.9 * (1.0 / 3.0))


class TestK1SignalFeatures:
    """Index 9: correction_signal_any, Index 10: contradiction_signal_any."""

    def test_no_signals(self):
        vec = extract_features(_cand(), _truth(), 0.5)
        assert vec[9] == pytest.approx(0.0)
        assert vec[10] == pytest.approx(0.0)

    def test_correction_signal(self):
        vec = extract_features(_cand(correction_signal=True), _truth(), 0.5)
        assert vec[9] == pytest.approx(1.0)
        assert vec[10] == pytest.approx(0.0)

    def test_contradiction_signal(self):
        vec = extract_features(_cand(contradiction_signal=True), _truth(), 0.5)
        assert vec[9] == pytest.approx(0.0)
        assert vec[10] == pytest.approx(1.0)

    def test_both_signals(self):
        vec = extract_features(
            _cand(correction_signal=True, contradiction_signal=True),
            _truth(),
            0.5,
        )
        assert vec[9] == pytest.approx(1.0)
        assert vec[10] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# V11: IdentityResult.features contains all 11 feature names
# ---------------------------------------------------------------------------


class TestFeatureNameContract:
    def test_all_11_names_present(self):
        """V11: features dict keys == FEATURE_NAMES."""
        from k0.modules.consolidation.identity.episodic import EpisodicIdentity

        scorer = EpisodicIdentity()
        result = scorer.score_identity(_cand(), _truth(), 0.5)
        assert set(result.features.keys()) == set(FEATURE_NAMES)
        assert len(result.features) == 11
