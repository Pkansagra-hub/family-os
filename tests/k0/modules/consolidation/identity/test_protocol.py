"""Protocol conformance tests for IdentityStrategy (M9.2 -- D9).

Validates V1, V7, V10 exit gates.
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.identity import IdentityStrategy
from k0.modules.consolidation.identity.episodic import EpisodicIdentity
from k0.modules.consolidation.types import (
    IdentityResult,
    K1SignalBundle,
    ReconciliationCandidate,
    TruthRecord,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def episodic_identity() -> EpisodicIdentity:
    return EpisodicIdentity()


def _make_candidate(**overrides) -> ReconciliationCandidate:
    defaults = dict(
        candidate_id="cand-001",
        layer="st_epi",
        source_phase="R2",
        embedding=[0.1] * 768,
        metadata={
            "topics": {"travel", "food"},
            "participants": {"alice", "bob"},
            "focal": "alice",
            "social_context": "family",
            "place_id": "place-1",
            "locations": {"place-1"},
            "source_type": "chat",
            "source_types": {"chat"},
        },
        k1_signals=K1SignalBundle(),
        source_event_ids=("ev-1",),
        cycle_id="cycle-1",
        tenant_id="t1",
        space_id="s1",
    )
    defaults.update(overrides)
    return ReconciliationCandidate(**defaults)


def _make_truth(**overrides) -> TruthRecord:
    defaults = dict(
        record_id="truth-001",
        layer="st_epi",
        embedding=[0.2] * 768,
        confidence=0.8,
        version=1,
        observation_count=5,
        last_observed_ms=1_700_000_000_000,
        metadata={
            "topics": {"travel", "cooking"},
            "participants": {"alice", "carol"},
            "focal": "alice",
            "social_context": "family",
            "locations": {"place-1", "place-2"},
            "source_types": {"chat", "sms"},
        },
    )
    defaults.update(overrides)
    return TruthRecord(**defaults)


# ---------------------------------------------------------------------------
# V1: IdentityStrategy protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """EpisodicIdentity must satisfy the IdentityStrategy protocol."""

    def test_isinstance_check(self, episodic_identity: EpisodicIdentity):
        """V1: isinstance(EpisodicIdentity(...), IdentityStrategy) is True."""
        assert isinstance(episodic_identity, IdentityStrategy)

    def test_has_layer_name(self, episodic_identity: EpisodicIdentity):
        assert episodic_identity.layer_name == "st_epi"

    def test_has_score_identity(self, episodic_identity: EpisodicIdentity):
        assert callable(getattr(episodic_identity, "score_identity", None))

    def test_has_match_key(self, episodic_identity: EpisodicIdentity):
        assert callable(getattr(episodic_identity, "match_key", None))

    def test_score_identity_returns_identity_result(self, episodic_identity: EpisodicIdentity):
        result = episodic_identity.score_identity(_make_candidate(), _make_truth(), cosine_sim=0.75)
        assert isinstance(result, IdentityResult)

    def test_score_identity_result_has_probabilities(self, episodic_identity: EpisodicIdentity):
        result = episodic_identity.score_identity(_make_candidate(), _make_truth(), cosine_sim=0.5)
        assert hasattr(result, "p_create")
        assert hasattr(result, "p_extend")
        assert hasattr(result, "p_reinforce")
        assert hasattr(result, "score")
        assert hasattr(result, "recommended_action")


# ---------------------------------------------------------------------------
# V7: match_key returns None for episodes
# ---------------------------------------------------------------------------


class TestMatchKey:
    """Episodes have no key-based identity."""

    def test_match_key_returns_none(self, episodic_identity: EpisodicIdentity):
        """V7: match_key() always returns None for episodes."""
        result = episodic_identity.match_key(_make_candidate(), _make_truth())
        assert result is None

    def test_match_key_none_with_different_inputs(self, episodic_identity: EpisodicIdentity):
        cand = _make_candidate(candidate_id="x")
        truth = _make_truth(record_id="y")
        assert episodic_identity.match_key(cand, truth) is None


# ---------------------------------------------------------------------------
# V10: ReconciliationCandidate is frozen
# ---------------------------------------------------------------------------


class TestFrozenDataclasses:
    """Reconciliation types must be immutable."""

    def test_candidate_is_frozen(self):
        """V10: ReconciliationCandidate is frozen."""
        cand = _make_candidate()
        with pytest.raises(AttributeError):
            cand.candidate_id = "changed"  # type: ignore[misc]

    def test_truth_record_is_frozen(self):
        truth = _make_truth()
        with pytest.raises(AttributeError):
            truth.record_id = "changed"  # type: ignore[misc]

    def test_identity_result_is_frozen(self):
        result = IdentityResult(
            score=0.5,
            p_create=0.3,
            p_extend=0.4,
            p_reinforce=0.3,
            recommended_action="EXTEND",
        )
        with pytest.raises(AttributeError):
            result.score = 0.9  # type: ignore[misc]

    def test_k1_signal_bundle_is_frozen(self):
        sig = K1SignalBundle()
        with pytest.raises(AttributeError):
            sig.correction_signal = True  # type: ignore[misc]
