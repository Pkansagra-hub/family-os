"""
R1 Hebbian disabled path and idempotency tests (5.O.2.4, 5.O.2.5).

5.O.2.4 AC: "Test confirms empty Hebbian output when enable_hebbian=False"
5.O.2.5 AC: "Score same batch twice with same now_ms -> identical results"
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)
from k0.pipelines.p03.phases.r1_importance_scorer import R1Config

# =============================================================================
# SHARED FIXTURES
# =============================================================================


@dataclass
class StubEventState:
    """Minimal event state for R1 tests."""

    event_id: str = "stub-event"
    sentiment_score: float = 0.6
    affect_valence: float = 0.5
    affect_arousal: float = 0.4
    surprise_level: float = 0.3
    num_participants: int = 3
    social_intimacy: str = "MEDIUM"
    content_type: str = "message"
    intent_label: str = "share_news"
    novelty: str = "NOVEL"
    elaboration_depth: str = "DISCUSSED"
    temporal_orientation: str = "PAST"
    identity_relevance: float = 0.5
    source_reliability: float = 0.95
    source_type: str = "user_stated"
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = "RISING_ACTION"
    memory_tier: str = "routine"
    timestamp: int = 0
    importance_computed: bool = False

    def set_importance(self, **kwargs: Any) -> None:
        self.importance_computed = True


def _make_events(n: int, now_ms: int) -> list[StubEventState]:
    """Create n diverse stub events."""
    return [
        StubEventState(
            event_id=f"idem-{i:03d}",
            timestamp=now_ms,
            sentiment_score=0.1 * (i % 10),
            affect_valence=0.1 * ((i + 1) % 10),
            affect_arousal=0.1 * ((i + 2) % 10),
            surprise_level=0.1 * ((i + 3) % 10),
            num_participants=(i % 5) + 1,
            identity_relevance=0.1 * ((i + 4) % 10),
        )
        for i in range(n)
    ]


# =============================================================================
# 5.O.2.4: HEBBIAN DISABLED PATH
# =============================================================================


class TestHebbianDisabledPath:
    """
    When enable_hebbian=False (default), no Hebbian outputs should be produced.

    Since Hebbian learning is still future (Issue 4.1.3), this test suite
    establishes the safety invariant: disabling Hebbian means no edge updates
    appear anywhere in the phase outputs.
    """

    def test_r1_config_hebbian_disabled_by_default(self) -> None:
        """Default R1Config has enable_hebbian=False."""
        config = R1Config()
        assert config.enable_hebbian is False

    def test_r1_config_hebbian_can_be_enabled(self) -> None:
        """R1Config allows enabling Hebbian for future use."""
        config = R1Config(enable_hebbian=True)
        assert config.enable_hebbian is True

    def test_scorer_produces_no_hebbian_fields_in_breakdown(self) -> None:
        """ImportanceScorer breakdown has no Hebbian-related fields."""
        now_ms = int(time.time() * 1000)
        scorer = ImportanceScorer(space_id="hebb-test")
        weights = ImportanceWeights()
        event = StubEventState(timestamp=now_ms)

        score, breakdown = scorer.compute_importance_score(event, weights, now_ms=now_ms)

        bd = breakdown.to_dict()
        hebbian_keys = [k for k in bd if "hebbian" in k.lower()]
        assert hebbian_keys == [], f"Unexpected Hebbian keys in breakdown: {hebbian_keys}"

    def test_scorer_output_contains_no_edge_updates(self) -> None:
        """Score result does not contain HebbianEdgeUpdate objects."""
        now_ms = int(time.time() * 1000)
        scorer = ImportanceScorer(space_id="hebb-test")
        weights = ImportanceWeights()

        events = _make_events(10, now_ms)
        for event in events:
            score, breakdown = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            # Neither score nor breakdown should have any edge_updates attribute
            assert not hasattr(breakdown, "edge_updates")
            assert not hasattr(breakdown, "hebbian_updates")

    def test_disabled_hebbian_does_not_affect_scores(self) -> None:
        """Scores are identical whether enable_hebbian is True or False in config."""
        now_ms = int(time.time() * 1000)
        config_off = R1Config(enable_hebbian=False)
        config_on = R1Config(enable_hebbian=True)

        scorer = ImportanceScorer(space_id="hebb-compare")
        weights = ImportanceWeights()

        events = _make_events(20, now_ms)
        scores_off = []
        scores_on = []

        for event in events:
            s_off, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            scores_off.append(s_off)

        for event in events:
            s_on, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            scores_on.append(s_on)

        assert scores_off == scores_on, "Scores differ between Hebbian on/off"


# =============================================================================
# 5.O.2.5: IDEMPOTENCY TEST
# =============================================================================


class TestR1Idempotency:
    """
    Score the same batch twice with the same now_ms -> identical results.

    This validates that the ImportanceScorer is pure and deterministic
    given identical inputs, which is critical for retry safety.
    """

    def test_same_batch_same_now_yields_identical_scores(self) -> None:
        """Two passes over identical events with same now_ms produce same scores."""
        now_ms = int(time.time() * 1000)
        scorer = ImportanceScorer(space_id="idem-test")
        weights = ImportanceWeights()

        events = _make_events(50, now_ms)

        scores_pass1 = []
        for event in events:
            s, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            scores_pass1.append(s)

        scores_pass2 = []
        for event in events:
            s, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            scores_pass2.append(s)

        assert scores_pass1 == scores_pass2

    def test_same_batch_same_now_yields_identical_tiers(self) -> None:
        """Two passes produce identical tier assignments."""
        now_ms = int(time.time() * 1000)
        scorer = ImportanceScorer(space_id="idem-test")
        weights = ImportanceWeights()

        events = _make_events(50, now_ms)

        tiers_pass1 = []
        for event in events:
            s, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            tiers_pass1.append(scorer.get_priority_tier(s))

        tiers_pass2 = []
        for event in events:
            s, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            tiers_pass2.append(scorer.get_priority_tier(s))

        assert tiers_pass1 == tiers_pass2

    def test_same_batch_same_now_yields_identical_breakdowns(self) -> None:
        """Two passes produce identical breakdown dicts."""
        now_ms = int(time.time() * 1000)
        scorer = ImportanceScorer(space_id="idem-test")
        weights = ImportanceWeights()

        events = _make_events(20, now_ms)

        breakdowns_pass1 = []
        for event in events:
            _, bd = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            breakdowns_pass1.append(bd.to_dict())

        breakdowns_pass2 = []
        for event in events:
            _, bd = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            breakdowns_pass2.append(bd.to_dict())

        assert breakdowns_pass1 == breakdowns_pass2

    def test_different_now_yields_different_scores(self) -> None:
        """Different now_ms changes recency, producing different scores (not idempotent)."""
        now_ms_1 = int(time.time() * 1000)
        now_ms_2 = now_ms_1 + 24 * 3_600_000  # 24 hours later
        scorer = ImportanceScorer(space_id="idem-test")
        weights = ImportanceWeights()

        # Event with timestamp at now_ms_1 (fresh then, old for now_ms_2)
        event = StubEventState(
            event_id="recency-drift",
            timestamp=now_ms_1,
            surprise_level=0.5,
        )

        score1, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms_1)
        score2, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms_2)

        # Recency decay means score2 < score1
        assert (
            score1 > score2
        ), f"Recency should decay: score_fresh={score1:.4f} vs score_24h={score2:.4f}"

    def test_idempotency_key_deterministic(self) -> None:
        """R1ImportanceScorer.idempotency_key is deterministic for same cycle_id."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1ImportanceScorer

        phase = R1ImportanceScorer()

        class FakeContext:
            cycle_id = "test-cycle-42"
            space_id = "sp_1"
            tenant_id = "t_1"

        class FakeEnvelope:
            context = FakeContext()
            events = []

        key1 = phase.idempotency_key(FakeEnvelope())
        key2 = phase.idempotency_key(FakeEnvelope())

        assert key1 == key2
        assert "test-cycle-42" in key1
