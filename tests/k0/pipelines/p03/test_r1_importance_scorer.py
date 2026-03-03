"""Unit tests for ImportanceScorer algorithm (CONFIG_B, POC validated).

Tests the core importance scoring algorithm independently of the pipeline.

Spec Reference:
    - Dossier 2.4: Scientific Formulas - Importance Score
    - M4_EXECUTION.md Issue 4.1.1
    - P03 R1 Discovery: P03_R1_IMPORTANCE_SCORING_DISCOVERY.md

Test Coverage:
    - ImportanceWeights 8-field CONFIG_B defaults
    - ImportanceBreakdown 17-field component tracking
    - compute_emotional_intensity() (sentiment + affect + arousal)
    - compute_social_factor() (participants + intimacy)
    - compute_novelty_factor() (categorical + salience fallback)
    - compute_surprise_factor()
    - compute_identity_factor() (relevance + domains fallback)
    - compute_recency_factor() (exponential decay lambda=0.005)
    - derive_source_reliability() (floor=0.3)
    - compute_importance_score() full CONFIG_B formula (6+7)
    - Multiplicative modulator stacking
    - Event type multipliers
    - Intent boost multipliers
    - 6-tier priority classification
    - score_batch() batch processing
    - select_batch() top-N selection
    - Learned weights vs static defaults
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceBreakdown,
    ImportanceScorer,
    ImportanceWeights,
    LearnedWeights,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing (simulates P03EventState with CONFIG_B fields)."""

    event_id: str = "evt_test_001"
    # Emotional signals
    sentiment_score: float = 0.0
    affect_valence: float = 0.0
    affect_arousal: float = 0.0
    # Cognitive signals
    surprise_level: float = 0.0
    novelty: str = ""  # Categorical: ROUTINE/EXPECTED/NOVEL/SURPRISING
    salience_score: float = 0.0  # Fallback for novelty when categorical empty
    # Social signals
    num_participants: int = 1
    social_intimacy: str = ""  # HIGH/MEDIUM/LOW
    # Identity signals
    identity_relevance: float = 0.0
    identity_domains_json: str = "[]"
    # Temporal
    timestamp: int = 0  # ms since epoch
    # Modulators
    content_type: str = "message"
    activity_type_ultrabert: str = ""
    intent_label: str = ""  # UltraBERT intent type (GAP-001 M8)
    intent_ultrabert: str = ""
    elaboration_depth: str = ""  # MENTION/DISCUSSED/ELABORATED/DEEPLY_PROCESSED
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = ""  # EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION
    temporal_orientation: str = ""  # PAST/ONGOING/FUTURE_COMMITMENT
    source_reliability: float = 1.0
    source_type: str = ""
    memory_tier: str = "routine"  # routine/notable/significant/landmark

    # Fields set by scorer
    importance_score: float = 0.0
    recency_factor: float = 0.0
    affect_factor: float = 0.0
    social_factor: float = 0.0
    novelty_factor: float = 0.0
    surprise_factor: float = 0.0
    identity_factor: float = 0.0
    importance_computed: bool = False

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float,
        surprise: float = 0.0,
        identity: float = 0.0,
    ) -> None:
        """Mock set_importance method (CONFIG_B signature)."""
        self.importance_score = score
        self.recency_factor = recency
        self.affect_factor = affect
        self.social_factor = social
        self.novelty_factor = novelty
        self.surprise_factor = surprise
        self.identity_factor = identity
        self.importance_computed = True


class MockWeightStore:
    """Mock weight store for testing learned weights."""

    def __init__(self, weights: Optional[LearnedWeights] = None):
        self._weights = weights

    async def get_weights(self, space_id: str, param_prefix: str) -> Optional[LearnedWeights]:
        return self._weights


@pytest.fixture
def default_scorer() -> ImportanceScorer:
    """Create scorer with static defaults (no weight store)."""
    return ImportanceScorer(space_id="sp_test")


@pytest.fixture
def default_weights() -> ImportanceWeights:
    """Default weights configuration."""
    return ImportanceWeights()


# =============================================================================
# ImportanceWeights Tests
# =============================================================================


class TestImportanceWeights:
    """Tests for ImportanceWeights configuration."""

    def test_default_weights_sum_to_one(self):
        """Default weights should sum to 1.0 for normalization."""
        weights = ImportanceWeights()
        assert abs(weights.total() - 1.0) < 0.001

    def test_default_values(self):
        """Verify default weight values from CONFIG_B (POC validated)."""
        weights = ImportanceWeights()
        assert weights.sentiment_weight == 0.10
        assert weights.affect_weight == 0.12
        assert weights.arousal_weight == 0.08
        assert weights.surprise_weight == 0.15
        assert weights.novelty_weight == 0.15
        assert weights.social_weight == 0.15
        assert weights.identity_weight == 0.10
        assert weights.recency_weight == 0.15

    def test_custom_weights(self):
        """Custom weights can be provided."""
        weights = ImportanceWeights(
            sentiment_weight=0.15,
            affect_weight=0.15,
            arousal_weight=0.10,
            surprise_weight=0.10,
            novelty_weight=0.15,
            social_weight=0.10,
            identity_weight=0.10,
            recency_weight=0.15,
        )
        assert weights.sentiment_weight == 0.15
        assert abs(weights.total() - 1.0) < 0.001

    def test_as_dict(self):
        """Weights can be serialized to dict."""
        weights = ImportanceWeights()
        d = weights.as_dict()
        assert d["sentiment"] == 0.10
        assert d["affect"] == 0.12
        assert d["arousal"] == 0.08
        assert d["surprise"] == 0.15
        assert d["novelty"] == 0.15
        assert d["social"] == 0.15
        assert d["identity"] == 0.10
        assert d["recency"] == 0.15
        assert len(d) == 8

    def test_weights_are_frozen(self):
        """Weights dataclass is immutable (frozen)."""
        weights = ImportanceWeights()
        with pytest.raises(Exception):  # FrozenInstanceError
            weights.sentiment_weight = 0.5  # type: ignore


# =============================================================================
# ImportanceBreakdown Tests
# =============================================================================


class TestImportanceBreakdown:
    """Tests for ImportanceBreakdown component tracking."""

    def test_breakdown_to_dict(self):
        """Breakdown can be serialized for audit logging."""
        breakdown = ImportanceBreakdown(
            emotional_component=0.25,
            surprise_component=0.10,
            novelty_component=0.15,
            social_component=0.10,
            identity_component=0.05,
            recency_component=0.12,
            base_score=0.77,
            elab_boost=1.05,
            goal_boost=1.15,
            arc_boost=1.0,
            temporal_boost=1.0,
            type_multiplier=1.2,
            intent_boost=1.0,
            tier_multiplier=1.0,
            reliability=0.95,
            final_score=0.60,
            weights_source="static",
        )
        d = breakdown.to_dict()
        assert d["emotional_component"] == 0.25
        assert d["surprise_component"] == 0.10
        assert d["novelty_component"] == 0.15
        assert d["social_component"] == 0.10
        assert d["identity_component"] == 0.05
        assert d["recency_component"] == 0.12
        assert d["base_score"] == 0.77
        assert d["elab_boost"] == 1.05
        assert d["goal_boost"] == 1.15
        assert d["type_multiplier"] == 1.2
        assert d["intent_boost"] == 1.0
        assert d["tier_multiplier"] == 1.0
        assert d["reliability"] == 0.95
        assert d["final_score"] == 0.60
        assert d["weights_source"] == "static"
        assert len(d) == 17


# =============================================================================
# compute_emotional_intensity Tests
# =============================================================================


class TestComputeEmotionalIntensity:
    """Tests for emotional intensity computation (sentiment + affect + arousal)."""

    def test_zero_inputs_zero_output(self, default_scorer, default_weights):
        """Zero sentiment, affect, and arousal yields zero emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.0,
            affect_valence=0.0,
            affect_arousal=0.0,
            weights=default_weights,
        )
        assert result == 0.0

    def test_high_sentiment_positive(self, default_scorer, default_weights):
        """High positive sentiment contributes to emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.9,
            affect_valence=0.0,
            affect_arousal=0.0,
            weights=default_weights,
        )
        # 0.9 * 0.10 = 0.09
        assert abs(result - 0.09) < 0.001

    def test_high_sentiment_negative(self, default_scorer, default_weights):
        """High negative sentiment contributes equally (absolute value)."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=-0.9,
            affect_valence=0.0,
            affect_arousal=0.0,
            weights=default_weights,
        )
        # |-0.9| * 0.10 = 0.09
        assert abs(result - 0.09) < 0.001

    def test_high_affect_valence(self, default_scorer, default_weights):
        """High affect valence contributes to emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.0,
            affect_valence=0.8,
            affect_arousal=0.0,
            weights=default_weights,
        )
        # 0.8 * 0.12 = 0.096
        assert abs(result - 0.096) < 0.001

    def test_arousal_contribution(self, default_scorer, default_weights):
        """Arousal contributes independently to emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.0,
            affect_valence=0.0,
            affect_arousal=1.0,
            weights=default_weights,
        )
        # 1.0 * 0.08 = 0.08
        assert abs(result - 0.08) < 0.001

    def test_combined_sentiment_affect_arousal(self, default_scorer, default_weights):
        """All three emotional signals combine additively."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.8,
            affect_valence=0.6,
            affect_arousal=0.5,
            weights=default_weights,
        )
        # (0.8 * 0.10) + (0.6 * 0.12) + (0.5 * 0.08) = 0.08 + 0.072 + 0.04 = 0.192
        assert abs(result - 0.192) < 0.001

    def test_arousal_clamped(self, default_scorer, default_weights):
        """Arousal > 1.0 is clamped to 1.0."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.0,
            affect_valence=0.0,
            affect_arousal=2.0,
            weights=default_weights,
        )
        # Clamped to 1.0 * 0.08 = 0.08
        assert abs(result - 0.08) < 0.001

    def test_max_emotional(self, default_scorer, default_weights):
        """Maximum emotional = sent_w + affect_w + arousal_w = 0.30."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=1.0,
            affect_valence=1.0,
            affect_arousal=1.0,
            weights=default_weights,
        )
        # 0.10 + 0.12 + 0.08 = 0.30
        assert abs(result - 0.30) < 0.001


# =============================================================================
# compute_social_factor Tests
# =============================================================================


class TestComputeSocialFactor:
    """Tests for social factor computation (participants + intimacy)."""

    def test_solo_event_zero_social(self, default_scorer, default_weights):
        """Solo event (1 participant) has zero social factor."""
        result = default_scorer.compute_social_factor(
            num_participants=1,
            social_intimacy="",
            weights=default_weights,
        )
        assert result == 0.0

    def test_pair_moderate_social(self, default_scorer, default_weights):
        """Two participants yields moderate social factor (~0.30 x weight)."""
        result = default_scorer.compute_social_factor(
            num_participants=2,
            social_intimacy="",
            weights=default_weights,
        )
        # log2(2) / 3.32 ~ 0.301 x 0.15 ~ 0.045
        assert 0.04 < result < 0.06

    def test_group_higher_social(self, default_scorer, default_weights):
        """Five participants yields higher social factor (~0.70 x weight)."""
        result = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="",
            weights=default_weights,
        )
        # log2(5) / 3.32 ~ 0.70 x 0.15 ~ 0.105
        assert 0.09 < result < 0.12

    def test_large_group_capped(self, default_scorer, default_weights):
        """Large groups are capped at 1.0 x weight."""
        result = default_scorer.compute_social_factor(
            num_participants=100,
            social_intimacy="",
            weights=default_weights,
        )
        # Capped at 1.0 x 0.15 = 0.15
        assert result == 0.15

    def test_high_intimacy_boost(self, default_scorer, default_weights):
        """HIGH intimacy multiplies social by 1.2."""
        base = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="",
            weights=default_weights,
        )
        boosted = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="HIGH",
            weights=default_weights,
        )
        assert abs(boosted - base * 1.2) < 0.001

    def test_low_intimacy_reduction(self, default_scorer, default_weights):
        """LOW intimacy multiplies social by 0.8."""
        base = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="",
            weights=default_weights,
        )
        reduced = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="LOW",
            weights=default_weights,
        )
        assert abs(reduced - base * 0.8) < 0.001

    def test_medium_intimacy_neutral(self, default_scorer, default_weights):
        """MEDIUM intimacy multiplies social by 1.0 (neutral)."""
        base = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="",
            weights=default_weights,
        )
        medium = default_scorer.compute_social_factor(
            num_participants=5,
            social_intimacy="MEDIUM",
            weights=default_weights,
        )
        assert abs(medium - base) < 0.001


# =============================================================================
# compute_novelty_factor Tests
# =============================================================================


class TestComputeNoveltyFactor:
    """Tests for novelty factor computation (categorical + fallback)."""

    def test_routine_novelty(self, default_scorer, default_weights):
        """ROUTINE categorical maps to 0.10 x weight."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="ROUTINE",
            salience_fallback=0.0,
            weights=default_weights,
        )
        # 0.10 * 0.15 = 0.015
        assert abs(result - 0.015) < 0.001

    def test_expected_novelty(self, default_scorer, default_weights):
        """EXPECTED categorical maps to 0.30 x weight."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="EXPECTED",
            salience_fallback=0.0,
            weights=default_weights,
        )
        # 0.30 * 0.15 = 0.045
        assert abs(result - 0.045) < 0.001

    def test_novel_novelty(self, default_scorer, default_weights):
        """NOVEL categorical maps to 0.70 x weight."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="NOVEL",
            salience_fallback=0.0,
            weights=default_weights,
        )
        # 0.70 * 0.15 = 0.105
        assert abs(result - 0.105) < 0.001

    def test_surprising_novelty(self, default_scorer, default_weights):
        """SURPRISING categorical maps to 1.00 x weight."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="SURPRISING",
            salience_fallback=0.0,
            weights=default_weights,
        )
        # 1.00 * 0.15 = 0.15
        assert abs(result - 0.15) < 0.001

    def test_empty_falls_back_to_salience(self, default_scorer, default_weights):
        """Empty categorical falls back to salience_score."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="",
            salience_fallback=0.5,
            weights=default_weights,
        )
        # 0.5 * 0.15 = 0.075
        assert abs(result - 0.075) < 0.001

    def test_unknown_falls_back_to_salience(self, default_scorer, default_weights):
        """Unknown categorical falls back to salience_score."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="UNKNOWN",
            salience_fallback=0.8,
            weights=default_weights,
        )
        # 0.8 * 0.15 = 0.12
        assert abs(result - 0.12) < 0.001

    def test_case_insensitive(self, default_scorer, default_weights):
        """Categorical lookup is case-insensitive."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="novel",
            salience_fallback=0.0,
            weights=default_weights,
        )
        assert abs(result - 0.105) < 0.001

    def test_salience_clamped(self, default_scorer, default_weights):
        """Salience fallback is clamped to [0, 1]."""
        result = default_scorer.compute_novelty_factor(
            novelty_categorical="",
            salience_fallback=1.5,
            weights=default_weights,
        )
        assert abs(result - 0.15) < 0.001  # Clamped to 1.0


# =============================================================================
# compute_surprise_factor Tests
# =============================================================================


class TestComputeSurpriseFactor:
    """Tests for surprise factor computation."""

    def test_zero_surprise(self, default_scorer, default_weights):
        """Zero surprise yields zero factor."""
        result = default_scorer.compute_surprise_factor(surprise_level=0.0, weights=default_weights)
        assert result == 0.0

    def test_full_surprise(self, default_scorer, default_weights):
        """Full surprise (1.0) yields full weight."""
        result = default_scorer.compute_surprise_factor(surprise_level=1.0, weights=default_weights)
        # 1.0 * 0.15 = 0.15
        assert abs(result - 0.15) < 0.001

    def test_partial_surprise(self, default_scorer, default_weights):
        """Partial surprise scales linearly."""
        result = default_scorer.compute_surprise_factor(surprise_level=0.6, weights=default_weights)
        # 0.6 * 0.15 = 0.09
        assert abs(result - 0.09) < 0.001

    def test_surprise_clamped(self, default_scorer, default_weights):
        """Surprise > 1.0 is clamped."""
        result = default_scorer.compute_surprise_factor(surprise_level=2.0, weights=default_weights)
        assert abs(result - 0.15) < 0.001


# =============================================================================
# compute_identity_factor Tests
# =============================================================================


class TestComputeIdentityFactor:
    """Tests for identity factor computation."""

    def test_zero_identity(self, default_scorer, default_weights):
        """Zero identity relevance and no domains yields zero."""
        result = default_scorer.compute_identity_factor(
            identity_relevance=0.0,
            identity_domains_json="[]",
            weights=default_weights,
        )
        assert result == 0.0

    def test_high_relevance(self, default_scorer, default_weights):
        """High identity_relevance is used directly."""
        result = default_scorer.compute_identity_factor(
            identity_relevance=0.8,
            identity_domains_json="[]",
            weights=default_weights,
        )
        # 0.8 * 0.10 = 0.08
        assert abs(result - 0.08) < 0.001

    def test_domains_fallback(self, default_scorer, default_weights):
        """Falls back to identity_domains count / 9.0 when relevance=0."""
        import json

        domains = json.dumps(["parent", "spouse", "professional"])
        result = default_scorer.compute_identity_factor(
            identity_relevance=0.0,
            identity_domains_json=domains,
            weights=default_weights,
        )
        # 3/9 = 0.333 * 0.10 = 0.0333
        assert abs(result - 0.0333) < 0.002

    def test_many_domains_capped(self, default_scorer, default_weights):
        """Identity signal from domains is capped at 1.0."""
        import json

        domains = json.dumps(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])
        result = default_scorer.compute_identity_factor(
            identity_relevance=0.0,
            identity_domains_json=domains,
            weights=default_weights,
        )
        # 10/9 > 1.0, capped to 1.0 * 0.10 = 0.10
        assert abs(result - 0.10) < 0.001

    def test_invalid_json_yields_zero(self, default_scorer, default_weights):
        """Invalid JSON yields zero (no domains)."""
        result = default_scorer.compute_identity_factor(
            identity_relevance=0.0,
            identity_domains_json="not_json",
            weights=default_weights,
        )
        assert result == 0.0


# =============================================================================
# compute_recency_factor Tests
# =============================================================================


class TestComputeRecencyFactor:
    """Tests for recency factor computation (lambda=0.005)."""

    def test_zero_timestamp_yields_zero(self, default_scorer, default_weights):
        """Zero event timestamp yields zero recency."""
        result = default_scorer.compute_recency_factor(
            event_timestamp_ms=0, now_ms=1_000_000_000_000, weights=default_weights
        )
        assert result == 0.0

    def test_very_recent_event(self, default_scorer, default_weights):
        """Event 1 hour ago has high recency."""
        import math

        now = 1_000_000_000_000
        one_hour_ago = now - 3_600_000  # 1 hour
        result = default_scorer.compute_recency_factor(
            event_timestamp_ms=one_hour_ago, now_ms=now, weights=default_weights
        )
        # exp(-0.005 * 1) * 0.15 = 0.995 * 0.15 ~= 0.1493
        expected = math.exp(-0.005 * 1.0) * 0.15
        assert abs(result - expected) < 0.001

    def test_one_week_old_event(self, default_scorer, default_weights):
        """Event 1 week (168h) ago has significant decay."""
        import math

        now = 1_000_000_000_000
        one_week_ago = now - (168 * 3_600_000)
        result = default_scorer.compute_recency_factor(
            event_timestamp_ms=one_week_ago, now_ms=now, weights=default_weights
        )
        # exp(-0.005 * 168) * 0.15 = exp(-0.84) * 0.15 ~= 0.432 * 0.15 = 0.0648
        expected = math.exp(-0.005 * 168.0) * 0.15
        assert abs(result - expected) < 0.001

    def test_half_life_approximately_6_days(self, default_scorer, default_weights):
        """Half-life is approximately 139 hours (~6 days)."""
        import math

        now = 1_000_000_000_000
        half_life_hours = math.log(2) / 0.005  # ~138.6h
        half_life_ms = int(half_life_hours * 3_600_000)
        result = default_scorer.compute_recency_factor(
            event_timestamp_ms=now - half_life_ms, now_ms=now, weights=default_weights
        )
        # Should be approximately 0.5 * recency_weight = 0.075
        assert abs(result - 0.075) < 0.002


# =============================================================================
# derive_source_reliability Tests
# =============================================================================


class TestDeriveSourceReliability:
    """Tests for source reliability derivation (floor=0.3)."""

    def test_default_reliability(self, default_scorer):
        """Default (1.0) with no source_type returns 1.0."""
        result = default_scorer.derive_source_reliability(source_reliability=1.0, source_type="")
        assert result == 1.0

    def test_explicit_reliability(self, default_scorer):
        """Explicit reliability < 1.0 is used directly."""
        result = default_scorer.derive_source_reliability(source_reliability=0.8, source_type="")
        assert result == 0.8

    def test_source_type_fallback(self, default_scorer):
        """Falls back to SOURCE_TYPE_RELIABILITY when reliability=1.0."""
        result = default_scorer.derive_source_reliability(
            source_reliability=1.0, source_type="system_inferred"
        )
        assert result == 0.60

    def test_floor_applied(self, default_scorer):
        """Reliability is floored at 0.3."""
        result = default_scorer.derive_source_reliability(source_reliability=0.1, source_type="")
        assert result == 0.3

    def test_user_stated_high_reliability(self, default_scorer):
        """user_stated source type has 0.95 reliability."""
        result = default_scorer.derive_source_reliability(
            source_reliability=1.0, source_type="user_stated"
        )
        assert result == 0.95


# =============================================================================
# Modulator Tests
# =============================================================================


class TestModulators:
    """Tests for multiplicative modulators (elaboration, goal, arc, temporal, tier)."""

    def test_elaboration_map_values(self, default_scorer):
        """Elaboration map has correct values."""
        assert default_scorer.ELABORATION_MAP["MENTION"] == 1.00
        assert default_scorer.ELABORATION_MAP["DISCUSSED"] == 1.05
        assert default_scorer.ELABORATION_MAP["ELABORATED"] == 1.10
        assert default_scorer.ELABORATION_MAP["DEEPLY_PROCESSED"] == 1.15

    def test_arc_map_values(self, default_scorer):
        """Arc map has correct values."""
        assert default_scorer.ARC_MAP["EXPOSITION"] == 1.00
        assert default_scorer.ARC_MAP["RISING_ACTION"] == 1.05
        assert default_scorer.ARC_MAP["CLIMAX"] == 1.15
        assert default_scorer.ARC_MAP["RESOLUTION"] == 1.00

    def test_temporal_map_values(self, default_scorer):
        """Temporal map has correct values."""
        assert default_scorer.TEMPORAL_MAP["PAST"] == 1.00
        assert default_scorer.TEMPORAL_MAP["ONGOING"] == 1.05
        assert default_scorer.TEMPORAL_MAP["FUTURE_COMMITMENT"] == 1.10

    def test_memory_tier_map_values(self, default_scorer):
        """Memory tier map has correct values."""
        assert default_scorer.MEMORY_TIER_MAP["routine"] == 1.00
        assert default_scorer.MEMORY_TIER_MAP["notable"] == 1.10
        assert default_scorer.MEMORY_TIER_MAP["significant"] == 1.25
        assert default_scorer.MEMORY_TIER_MAP["landmark"] == 1.50

    def test_goal_boost_value(self, default_scorer):
        """Goal boost is 1.15."""
        assert default_scorer.GOAL_BOOST == 1.15

    def test_novelty_map_values(self, default_scorer):
        """Novelty map has correct values."""
        assert default_scorer.NOVELTY_MAP["ROUTINE"] == 0.10
        assert default_scorer.NOVELTY_MAP["EXPECTED"] == 0.30
        assert default_scorer.NOVELTY_MAP["NOVEL"] == 0.70
        assert default_scorer.NOVELTY_MAP["SURPRISING"] == 1.00

    def test_intimacy_scale_values(self, default_scorer):
        """Intimacy scale has correct values."""
        assert default_scorer.INTIMACY_SCALE["HIGH"] == 1.20
        assert default_scorer.INTIMACY_SCALE["MEDIUM"] == 1.00
        assert default_scorer.INTIMACY_SCALE["LOW"] == 0.80


# =============================================================================
# Event Type Multiplier Tests
# =============================================================================


class TestEventTypeMultipliers:
    """Tests for event type multipliers."""

    def test_message_default_multiplier(self, default_scorer):
        """Message type has 1.0 multiplier."""
        assert default_scorer.get_event_type_multiplier("message") == 1.0

    def test_photo_higher_multiplier(self, default_scorer):
        """Photo type has 1.2 multiplier (visual memories weighted higher)."""
        assert default_scorer.get_event_type_multiplier("photo") == 1.2

    def test_milestone_highest_multiplier(self, default_scorer):
        """Milestone type has 2.0 multiplier (birthdays, anniversaries)."""
        assert default_scorer.get_event_type_multiplier("milestone") == 2.0

    def test_routine_lower_multiplier(self, default_scorer):
        """Routine type has 0.5 multiplier (daily repeated events)."""
        assert default_scorer.get_event_type_multiplier("routine") == 0.5

    def test_unknown_type_default(self, default_scorer):
        """Unknown type defaults to 1.0 multiplier."""
        assert default_scorer.get_event_type_multiplier("unknown_type") == 1.0

    def test_case_insensitive(self, default_scorer):
        """Event types are case-insensitive."""
        assert default_scorer.get_event_type_multiplier("PHOTO") == 1.2
        assert default_scorer.get_event_type_multiplier("Milestone") == 2.0


# =============================================================================
# compute_importance_score Tests
# =============================================================================


class TestComputeImportanceScore:
    """Tests for full importance score computation (CONFIG_B formula)."""

    def test_neutral_event_low_score(self, default_scorer, default_weights):
        """Neutral event with no special factors has low score."""
        event = MockEvent(
            sentiment_score=0.0,
            affect_valence=0.0,
            affect_arousal=0.0,
            num_participants=1,
            content_type="message",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        assert score == 0.0
        assert breakdown.final_score == 0.0

    def test_emotional_event_higher_score(self, default_scorer, default_weights):
        """Emotional event has higher importance."""
        event = MockEvent(
            sentiment_score=0.9,
            affect_valence=0.8,
            affect_arousal=0.7,
            num_participants=1,
            content_type="message",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        # emotional = 0.9*0.10 + 0.8*0.12 + 0.7*0.08 = 0.09+0.096+0.056 = 0.242
        assert score > 0.20
        assert breakdown.emotional_component > 0.20

    def test_milestone_boost(self, default_scorer, default_weights):
        """Milestone events get 2x multiplier boost."""
        event = MockEvent(
            sentiment_score=0.5,
            affect_valence=0.5,
            salience_score=0.5,
            num_participants=1,
            content_type="milestone",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        assert breakdown.type_multiplier == 2.0
        assert score > 0.15

    def test_routine_reduction(self, default_scorer, default_weights):
        """Routine events get 0.5x multiplier reduction."""
        event = MockEvent(
            sentiment_score=0.5,
            affect_valence=0.5,
            salience_score=0.5,
            num_participants=1,
            content_type="routine",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        assert breakdown.type_multiplier == 0.5

    def test_score_normalized_to_one(self, default_scorer, default_weights):
        """Score is clamped to [0, 1] even with high inputs."""
        event = MockEvent(
            sentiment_score=1.0,
            affect_valence=1.0,
            affect_arousal=1.0,
            surprise_level=1.0,
            novelty="SURPRISING",
            num_participants=100,
            social_intimacy="HIGH",
            identity_relevance=1.0,
            timestamp=999_999_999_000,  # Recent
            content_type="milestone",  # 2x multiplier
            elaboration_depth="DEEPLY_PROCESSED",
            narrative_is_goal_event=True,
            narrative_arc_position="CLIMAX",
            temporal_orientation="FUTURE_COMMITMENT",
            memory_tier="landmark",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        assert score <= 1.0
        assert breakdown.final_score <= 1.0

    def test_breakdown_components_present(self, default_scorer, default_weights):
        """Breakdown contains all 6 additive components."""
        event = MockEvent(
            sentiment_score=0.6,
            affect_valence=0.4,
            affect_arousal=0.3,
            surprise_level=0.5,
            novelty="NOVEL",
            num_participants=3,
            social_intimacy="MEDIUM",
            identity_relevance=0.4,
            timestamp=999_990_000_000,
            content_type="message",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        assert breakdown.emotional_component > 0
        assert breakdown.surprise_component > 0
        assert breakdown.novelty_component > 0
        assert breakdown.social_component > 0
        assert breakdown.identity_component > 0
        assert breakdown.recency_component > 0
        assert breakdown.base_score > 0
        assert breakdown.type_multiplier == 1.0

    def test_modulator_stacking(self, default_scorer, default_weights):
        """All modulators multiply onto the base score."""
        event = MockEvent(
            sentiment_score=0.5,
            affect_valence=0.5,
            elaboration_depth="ELABORATED",  # 1.10x
            narrative_is_goal_event=True,  # 1.15x
            narrative_arc_position="CLIMAX",  # 1.15x
            temporal_orientation="FUTURE_COMMITMENT",  # 1.10x
            memory_tier="notable",  # 1.10x
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=1_000_000_000_000
        )
        assert breakdown.elab_boost == 1.10
        assert breakdown.goal_boost == 1.15
        assert breakdown.arc_boost == 1.15
        assert breakdown.temporal_boost == 1.10
        assert breakdown.tier_multiplier == 1.10


# =============================================================================
# score_batch Tests
# =============================================================================


class TestScoreBatch:
    """Tests for batch scoring."""

    @pytest.mark.asyncio
    async def test_empty_batch(self, default_scorer):
        """Empty batch returns empty results."""
        results = await default_scorer.score_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_single_event(self, default_scorer):
        """Single event is scored correctly."""
        event = MockEvent(
            event_id="evt_001",
            sentiment_score=0.5,
            salience_score=0.3,
        )
        results = await default_scorer.score_batch([event], now_ms=1_000_000_000_000)
        assert len(results) == 1
        assert results[0]["event_id"] == "evt_001"
        assert results[0]["importance_score"] > 0

    @pytest.mark.asyncio
    async def test_multiple_events(self, default_scorer):
        """Multiple events are all scored."""
        events = [
            MockEvent(event_id="evt_001", sentiment_score=0.9),
            MockEvent(event_id="evt_002", sentiment_score=0.5),
            MockEvent(event_id="evt_003", sentiment_score=0.1),
        ]
        results = await default_scorer.score_batch(events, now_ms=1_000_000_000_000)
        assert len(results) == 3
        # Higher sentiment should have higher score
        assert results[0]["importance_score"] > results[2]["importance_score"]

    @pytest.mark.asyncio
    async def test_event_state_updated(self, default_scorer):
        """Event state is updated in-place with all factors."""
        event = MockEvent(
            event_id="evt_001",
            sentiment_score=0.7,
            salience_score=0.5,
        )
        await default_scorer.score_batch([event], now_ms=1_000_000_000_000)
        assert event.importance_computed is True
        assert event.importance_score > 0

    @pytest.mark.asyncio
    async def test_batch_returns_priority_tier(self, default_scorer):
        """score_batch results include priority_tier."""
        event = MockEvent(
            sentiment_score=0.9,
            affect_valence=0.9,
            affect_arousal=0.9,
            surprise_level=0.9,
            novelty="SURPRISING",
            num_participants=10,
            social_intimacy="HIGH",
            identity_relevance=0.9,
            timestamp=999_999_999_000,
            content_type="milestone",
            memory_tier="landmark",
        )
        results = await default_scorer.score_batch([event], now_ms=1_000_000_000_000)
        assert "priority_tier" in results[0]
        assert results[0]["priority_tier"] in (
            "CRITICAL",
            "HIGH",
            "MEDIUM_HIGH",
            "MEDIUM",
            "LOW_MEDIUM",
            "LOW",
        )


# =============================================================================
# select_batch Tests
# =============================================================================


class TestSelectBatch:
    """Tests for top-N selection."""

    def test_select_top_n(self, default_scorer):
        """Selects top N events by importance."""
        events = [
            {"event_id": "evt_001", "importance_score": 0.3},
            {"event_id": "evt_002", "importance_score": 0.9},
            {"event_id": "evt_003", "importance_score": 0.5},
            {"event_id": "evt_004", "importance_score": 0.7},
        ]
        selected = default_scorer.select_batch(events, batch_size=2)
        assert len(selected) == 2
        assert selected[0]["event_id"] == "evt_002"  # Highest (0.9)
        assert selected[1]["event_id"] == "evt_004"  # Second (0.7)

    def test_select_all_if_batch_larger(self, default_scorer):
        """Returns all if batch_size > event count."""
        events = [
            {"event_id": "evt_001", "importance_score": 0.5},
        ]
        selected = default_scorer.select_batch(events, batch_size=10)
        assert len(selected) == 1

    def test_select_empty(self, default_scorer):
        """Empty list returns empty."""
        selected = default_scorer.select_batch([], batch_size=10)
        assert selected == []


# =============================================================================
# Priority Tier Tests
# =============================================================================


class TestGetPriorityTier:
    """Tests for 6-tier priority mapping (POC Phase 6 validated)."""

    def test_critical_tier(self, default_scorer):
        """Score >= 0.80 is CRITICAL."""
        assert default_scorer.get_priority_tier(0.80) == "CRITICAL"
        assert default_scorer.get_priority_tier(0.95) == "CRITICAL"
        assert default_scorer.get_priority_tier(1.0) == "CRITICAL"

    def test_high_tier(self, default_scorer):
        """Score 0.60-0.79 is HIGH."""
        assert default_scorer.get_priority_tier(0.60) == "HIGH"
        assert default_scorer.get_priority_tier(0.70) == "HIGH"
        assert default_scorer.get_priority_tier(0.79) == "HIGH"

    def test_medium_high_tier(self, default_scorer):
        """Score 0.45-0.59 is MEDIUM_HIGH."""
        assert default_scorer.get_priority_tier(0.45) == "MEDIUM_HIGH"
        assert default_scorer.get_priority_tier(0.50) == "MEDIUM_HIGH"
        assert default_scorer.get_priority_tier(0.59) == "MEDIUM_HIGH"

    def test_medium_tier(self, default_scorer):
        """Score 0.30-0.44 is MEDIUM."""
        assert default_scorer.get_priority_tier(0.30) == "MEDIUM"
        assert default_scorer.get_priority_tier(0.37) == "MEDIUM"
        assert default_scorer.get_priority_tier(0.44) == "MEDIUM"

    def test_low_medium_tier(self, default_scorer):
        """Score 0.15-0.29 is LOW_MEDIUM."""
        assert default_scorer.get_priority_tier(0.15) == "LOW_MEDIUM"
        assert default_scorer.get_priority_tier(0.20) == "LOW_MEDIUM"
        assert default_scorer.get_priority_tier(0.29) == "LOW_MEDIUM"

    def test_low_tier(self, default_scorer):
        """Score < 0.15 is LOW."""
        assert default_scorer.get_priority_tier(0.0) == "LOW"
        assert default_scorer.get_priority_tier(0.10) == "LOW"
        assert default_scorer.get_priority_tier(0.14) == "LOW"


# =============================================================================
# Learned Weights Tests
# =============================================================================


class TestLearnedWeights:
    """Tests for learned weights loading."""

    @pytest.mark.asyncio
    async def test_static_weights_when_no_store(self):
        """Uses static weights when no weight store provided."""
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)
        weights = await scorer.get_weights()
        assert weights == ImportanceWeights()
        assert scorer._weights_source == "static"

    @pytest.mark.asyncio
    async def test_static_weights_when_insufficient_samples(self):
        """Uses static weights when sample_count < 500."""
        learned = LearnedWeights(
            weights={"sentiment": 0.30, "affect": 0.30, "novelty": 0.20, "social": 0.20},
            sample_count=100,  # Below 500 threshold
            updated_at=1704067200000,
        )
        store = MockWeightStore(learned)
        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights = await scorer.get_weights()
        # Should use static defaults (CONFIG_B), not learned
        assert weights.sentiment_weight == 0.10  # CONFIG_B default
        assert scorer._weights_source == "static"

    @pytest.mark.asyncio
    async def test_learned_weights_when_sufficient_samples(self):
        """Uses learned weights when sample_count >= 500."""
        learned = LearnedWeights(
            weights={"sentiment": 0.30, "affect": 0.30, "novelty": 0.20, "social": 0.20},
            sample_count=600,  # Above 500 threshold
            updated_at=1704067200000,
        )
        store = MockWeightStore(learned)
        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights = await scorer.get_weights()
        assert weights.sentiment_weight == 0.30  # Learned value
        assert scorer._weights_source == "learned"

    @pytest.mark.asyncio
    async def test_weights_cached(self):
        """Weights are cached after first load."""
        store = MockWeightStore(None)
        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        await scorer.get_weights()
        await scorer.get_weights()  # Second call should use cache
        # If it worked, store was only queried once (cache)
        assert scorer._cached_weights is not None

    def test_invalidate_cache(self):
        """Cache can be invalidated."""
        scorer = ImportanceScorer(space_id="sp_test")
        scorer._cached_weights = ImportanceWeights()
        scorer._weights_source = "learned"
        scorer.invalidate_weight_cache()
        assert scorer._cached_weights is None
        assert scorer._weights_source == "static"


# =============================================================================
# Intent Boost Multiplier Tests (GAP-001 Milestone 8, Issue 8.2)
# =============================================================================


class TestIntentBoostMultipliers:
    """Tests for intent-based importance boost multipliers."""

    def test_query_memory_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """query_memory intent gets 1.2x boost."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="query_memory",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        # query_memory should boost by 1.2x
        expected = min(1.0, base_score * 1.2)
        assert abs(score - expected) < 0.001
        assert abs(breakdown.intent_boost - 1.2) < 0.001

    def test_share_news_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """share_news intent gets 1.2x boost."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="share_news",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        expected = min(1.0, base_score * 1.2)
        assert abs(score - expected) < 0.001

    def test_set_reminder_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """set_reminder intent gets 1.15x boost."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="set_reminder",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        expected = min(1.0, base_score * 1.15)
        assert abs(score - expected) < 0.001

    def test_make_plan_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """make_plan intent gets 1.15x boost."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="make_plan",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        expected = min(1.0, base_score * 1.15)
        assert abs(score - expected) < 0.001

    def test_casual_chat_deboost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """casual_chat intent gets 0.9x (slight de-boost)."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="casual_chat",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        expected = base_score * 0.9
        assert abs(score - expected) < 0.001

    def test_express_feeling_no_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """express_feeling intent has no boost (1.0x) - handled by emotional component."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="express_feeling",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        assert abs(score - base_score) < 0.001

    def test_unknown_intent_no_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """Unknown intents get no boost (1.0x default)."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="unknown_intent",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(
            event_no_intent, default_weights, now_ms=now_ms
        )

        assert abs(score - base_score) < 0.001

    def test_intent_boost_stacks_with_event_type(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """Intent boost stacks multiplicatively with event type boost."""
        now_ms = 1_000_000_000_000
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            content_type="milestone",
            intent_label="query_memory",
        )
        score, breakdown = default_scorer.compute_importance_score(
            event, default_weights, now_ms=now_ms
        )

        assert abs(breakdown.type_multiplier - 2.0) < 0.001
        assert abs(breakdown.intent_boost - 1.2) < 0.001

    def test_all_intent_multipliers_exist(self, default_scorer: ImportanceScorer):
        """All 8 UltraBERT intent types have defined multipliers."""
        expected_intents = [
            "query_memory",
            "share_news",
            "set_reminder",
            "make_plan",
            "seek_advice",
            "reflect",
            "express_feeling",
            "casual_chat",
        ]
        for intent in expected_intents:
            assert intent in default_scorer.INTENT_BOOST_MULTIPLIERS, f"Missing intent: {intent}"
