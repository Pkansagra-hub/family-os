"""
Unit tests for ImportanceScorer algorithm.

Tests the core importance scoring algorithm independently of the pipeline.

Spec Reference:
    - Dossier §2.4: Scientific Formulas - Importance Score
    - M4_EXECUTION.md Issue 4.1.1

Test Coverage:
    - ImportanceWeights configuration
    - ImportanceBreakdown component breakdown
    - compute_emotional_intensity() with various inputs
    - compute_social_factor() with participant counts
    - compute_novelty_factor() scaling
    - compute_importance_score() full formula
    - Event type multipliers (photo, milestone, routine)
    - score_batch() batch processing
    - select_batch() top-N selection
    - get_priority_tier() threshold mapping
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
    """Mock event for testing (simulates P03EventState)."""

    event_id: str = "evt_test_001"
    sentiment_score: float = 0.0
    affect_valence: float = 0.0
    # Issue 1 Fix: Use salience_score instead of novelty_score
    # novelty_score doesn't exist - salience_score is the proxy
    salience_score: float = 0.0
    participant_count: int = 1
    content_type: str = "message"
    intent_label: str = ""  # UltraBERT intent type (GAP-001 M8)

    # Fields set by scorer
    importance_score: float = 0.0
    recency_factor: float = 0.0
    affect_factor: float = 0.0
    social_factor: float = 0.0
    novelty_factor: float = 0.0
    importance_computed: bool = False

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float,
    ) -> None:
        """Mock set_importance method."""
        self.importance_score = score
        self.recency_factor = recency
        self.affect_factor = affect
        self.social_factor = social
        self.novelty_factor = novelty
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
        """Verify default weight values from Dossier C.2.1."""
        weights = ImportanceWeights()
        assert weights.sentiment_weight == 0.25
        assert weights.affect_weight == 0.30
        assert weights.novelty_weight == 0.25
        assert weights.social_weight == 0.20

    def test_custom_weights(self):
        """Custom weights can be provided."""
        weights = ImportanceWeights(
            sentiment_weight=0.4,
            affect_weight=0.3,
            novelty_weight=0.2,
            social_weight=0.1,
        )
        assert weights.sentiment_weight == 0.4
        assert abs(weights.total() - 1.0) < 0.001

    def test_as_dict(self):
        """Weights can be serialized to dict."""
        weights = ImportanceWeights()
        d = weights.as_dict()
        assert d["sentiment"] == 0.25
        assert d["affect"] == 0.30
        assert d["novelty"] == 0.25
        assert d["social"] == 0.20

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
            novelty_component=0.15,
            social_component=0.10,
            multiplier=1.2,
            final_score=0.60,
            weights_source="static",
        )
        d = breakdown.to_dict()
        assert d["emotional_component"] == 0.25
        assert d["novelty_component"] == 0.15
        assert d["social_component"] == 0.10
        assert d["multiplier"] == 1.2
        assert d["final_score"] == 0.60
        assert d["weights_source"] == "static"


# =============================================================================
# compute_emotional_intensity Tests
# =============================================================================


class TestComputeEmotionalIntensity:
    """Tests for emotional intensity computation."""

    def test_zero_inputs_zero_output(self, default_scorer, default_weights):
        """Zero sentiment and affect yields zero emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.0,
            affect_valence=0.0,
            weights=default_weights,
        )
        assert result == 0.0

    def test_high_sentiment_positive(self, default_scorer, default_weights):
        """High positive sentiment contributes to emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.9,
            affect_valence=0.0,
            weights=default_weights,
        )
        # 0.9 * 0.25 = 0.225
        assert abs(result - 0.225) < 0.001

    def test_high_sentiment_negative(self, default_scorer, default_weights):
        """High negative sentiment contributes equally (absolute value)."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=-0.9,
            affect_valence=0.0,
            weights=default_weights,
        )
        # |-0.9| * 0.25 = 0.225
        assert abs(result - 0.225) < 0.001

    def test_high_affect_valence(self, default_scorer, default_weights):
        """High affect valence contributes to emotional intensity."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.0,
            affect_valence=0.8,
            weights=default_weights,
        )
        # 0.8 * 0.30 = 0.24
        assert abs(result - 0.24) < 0.001

    def test_combined_sentiment_and_affect(self, default_scorer, default_weights):
        """Both sentiment and affect combine additively."""
        result = default_scorer.compute_emotional_intensity(
            sentiment_score=0.8,
            affect_valence=0.6,
            weights=default_weights,
        )
        # (0.8 * 0.25) + (0.6 * 0.30) = 0.20 + 0.18 = 0.38
        assert abs(result - 0.38) < 0.001


# =============================================================================
# compute_social_factor Tests
# =============================================================================


class TestComputeSocialFactor:
    """Tests for social factor computation."""

    def test_solo_event_zero_social(self, default_scorer, default_weights):
        """Solo event (1 participant) has zero social factor."""
        result = default_scorer.compute_social_factor(
            participant_count=1,
            weights=default_weights,
        )
        assert result == 0.0

    def test_pair_moderate_social(self, default_scorer, default_weights):
        """Two participants yields moderate social factor (~0.30 × weight)."""
        result = default_scorer.compute_social_factor(
            participant_count=2,
            weights=default_weights,
        )
        # log2(2) / 3.32 ≈ 0.301 × 0.20 ≈ 0.060
        assert 0.05 < result < 0.07

    def test_group_higher_social(self, default_scorer, default_weights):
        """Five participants yields higher social factor (~0.70 × weight)."""
        result = default_scorer.compute_social_factor(
            participant_count=5,
            weights=default_weights,
        )
        # log2(5) / 3.32 ≈ 0.70 × 0.20 ≈ 0.14
        assert 0.12 < result < 0.16

    def test_large_group_capped(self, default_scorer, default_weights):
        """Large groups are capped at 1.0 × weight."""
        result = default_scorer.compute_social_factor(
            participant_count=100,
            weights=default_weights,
        )
        # Capped at 1.0 × 0.20 = 0.20
        assert result == 0.20


# =============================================================================
# compute_novelty_factor Tests
# =============================================================================


class TestComputeNoveltyFactor:
    """Tests for novelty factor computation."""

    def test_zero_novelty(self, default_scorer, default_weights):
        """Zero novelty score yields zero novelty factor."""
        result = default_scorer.compute_novelty_factor(
            novelty_score=0.0,
            weights=default_weights,
        )
        assert result == 0.0

    def test_full_novelty(self, default_scorer, default_weights):
        """Full novelty (1.0) yields full novelty weight."""
        result = default_scorer.compute_novelty_factor(
            novelty_score=1.0,
            weights=default_weights,
        )
        assert result == 0.25  # novelty_weight

    def test_partial_novelty(self, default_scorer, default_weights):
        """Partial novelty scales linearly."""
        result = default_scorer.compute_novelty_factor(
            novelty_score=0.5,
            weights=default_weights,
        )
        assert result == 0.125  # 0.5 * 0.25

    def test_novelty_clamped_above_one(self, default_scorer, default_weights):
        """Novelty > 1.0 is clamped."""
        result = default_scorer.compute_novelty_factor(
            novelty_score=1.5,
            weights=default_weights,
        )
        assert result == 0.25  # Clamped to 1.0 × weight

    def test_novelty_clamped_below_zero(self, default_scorer, default_weights):
        """Negative novelty is clamped to 0."""
        result = default_scorer.compute_novelty_factor(
            novelty_score=-0.5,
            weights=default_weights,
        )
        assert result == 0.0


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
    """Tests for full importance score computation."""

    def test_neutral_event_low_score(self, default_scorer, default_weights):
        """Neutral event with no special factors has low score."""
        event = MockEvent(
            sentiment_score=0.0,
            affect_valence=0.0,
            salience_score=0.0,
            participant_count=1,
            content_type="message",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)
        assert score == 0.0
        assert breakdown.final_score == 0.0

    def test_emotional_event_higher_score(self, default_scorer, default_weights):
        """Emotional event has higher importance."""
        event = MockEvent(
            sentiment_score=0.9,
            affect_valence=0.8,
            salience_score=0.0,
            participant_count=1,
            content_type="message",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)
        # emotional = 0.9*0.25 + 0.8*0.30 = 0.465
        assert score > 0.4
        assert breakdown.emotional_component > 0.4

    def test_milestone_boost(self, default_scorer, default_weights):
        """Milestone events get 2x multiplier boost."""
        event = MockEvent(
            sentiment_score=0.5,
            affect_valence=0.5,
            salience_score=0.5,
            participant_count=1,
            content_type="milestone",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)
        assert breakdown.multiplier == 2.0
        # Base would be ~0.40, with 2x = ~0.80
        assert score > 0.7

    def test_routine_reduction(self, default_scorer, default_weights):
        """Routine events get 0.5x multiplier reduction."""
        event = MockEvent(
            sentiment_score=0.5,
            affect_valence=0.5,
            salience_score=0.5,
            participant_count=1,
            content_type="routine",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)
        assert breakdown.multiplier == 0.5
        # Base would be ~0.40, with 0.5x = ~0.20
        assert score < 0.25

    def test_score_normalized_to_one(self, default_scorer, default_weights):
        """Score is clamped to [0, 1] even with high inputs."""
        event = MockEvent(
            sentiment_score=1.0,
            affect_valence=1.0,
            salience_score=1.0,
            participant_count=100,
            content_type="milestone",  # 2x multiplier
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)
        assert score <= 1.0
        assert breakdown.final_score <= 1.0

    def test_breakdown_components_sum(self, default_scorer, default_weights):
        """Breakdown components should be traceable."""
        event = MockEvent(
            sentiment_score=0.6,
            affect_valence=0.4,
            salience_score=0.3,
            participant_count=3,
            content_type="message",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)
        # Verify breakdown contains all components
        assert breakdown.emotional_component > 0
        assert breakdown.novelty_component > 0
        assert breakdown.social_component > 0
        assert breakdown.multiplier == 1.0


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
        results = await default_scorer.score_batch([event])
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
        results = await default_scorer.score_batch(events)
        assert len(results) == 3
        # Higher sentiment should have higher score
        assert results[0]["importance_score"] > results[2]["importance_score"]

    @pytest.mark.asyncio
    async def test_event_state_updated(self, default_scorer):
        """Event state is updated in-place."""
        event = MockEvent(
            event_id="evt_001",
            sentiment_score=0.7,
            salience_score=0.5,
        )
        await default_scorer.score_batch([event])
        assert event.importance_computed is True
        assert event.importance_score > 0


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
    """Tests for priority tier mapping."""

    def test_critical_tier(self, default_scorer):
        """Score >= 0.80 is CRITICAL."""
        assert default_scorer.get_priority_tier(0.80) == "CRITICAL"
        assert default_scorer.get_priority_tier(0.95) == "CRITICAL"
        assert default_scorer.get_priority_tier(1.0) == "CRITICAL"

    def test_high_tier(self, default_scorer):
        """Score 0.50-0.79 is HIGH."""
        assert default_scorer.get_priority_tier(0.50) == "HIGH"
        assert default_scorer.get_priority_tier(0.65) == "HIGH"
        assert default_scorer.get_priority_tier(0.79) == "HIGH"

    def test_medium_tier(self, default_scorer):
        """Score 0.30-0.49 is MEDIUM."""
        assert default_scorer.get_priority_tier(0.30) == "MEDIUM"
        assert default_scorer.get_priority_tier(0.40) == "MEDIUM"
        assert default_scorer.get_priority_tier(0.49) == "MEDIUM"

    def test_low_tier(self, default_scorer):
        """Score < 0.30 is LOW."""
        assert default_scorer.get_priority_tier(0.0) == "LOW"
        assert default_scorer.get_priority_tier(0.15) == "LOW"
        assert default_scorer.get_priority_tier(0.29) == "LOW"


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
        # Should use static defaults, not learned
        assert weights.sentiment_weight == 0.25  # Default, not 0.30
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
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="query_memory",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        # Compute expected base score without intent boost
        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        # query_memory should boost by 1.2x
        expected = min(1.0, base_score * 1.2)
        assert abs(score - expected) < 0.001
        assert breakdown.multiplier == 1.0 * 1.2  # event_type * intent_boost

    def test_share_news_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """share_news intent gets 1.2x boost."""
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="share_news",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        expected = min(1.0, base_score * 1.2)
        assert abs(score - expected) < 0.001

    def test_set_reminder_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """set_reminder intent gets 1.15x boost."""
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="set_reminder",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        expected = min(1.0, base_score * 1.15)
        assert abs(score - expected) < 0.001

    def test_make_plan_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """make_plan intent gets 1.15x boost."""
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="make_plan",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        expected = min(1.0, base_score * 1.15)
        assert abs(score - expected) < 0.001

    def test_casual_chat_deboost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """casual_chat intent gets 0.9x (slight de-boost)."""
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="casual_chat",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        expected = base_score * 0.9
        assert abs(score - expected) < 0.001

    def test_express_feeling_no_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """express_feeling intent has no boost (1.0x) - handled by emotional component."""
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="express_feeling",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        # express_feeling is 1.0x, so no change
        assert abs(score - base_score) < 0.001

    def test_unknown_intent_no_boost(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """Unknown intents get no boost (1.0x default)."""
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            intent_label="unknown_intent",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        event_no_intent = MockEvent(sentiment_score=0.5, salience_score=0.5, intent_label="")
        base_score, _ = default_scorer.compute_importance_score(event_no_intent, default_weights)

        assert abs(score - base_score) < 0.001

    def test_intent_boost_stacks_with_event_type(
        self, default_scorer: ImportanceScorer, default_weights: ImportanceWeights
    ):
        """Intent boost stacks multiplicatively with event type boost."""
        # milestone (2.0x) + query_memory (1.2x) = 2.4x total multiplier
        event = MockEvent(
            sentiment_score=0.5,
            salience_score=0.5,
            content_type="milestone",
            intent_label="query_memory",
        )
        score, breakdown = default_scorer.compute_importance_score(event, default_weights)

        # Combined multiplier should be 2.0 * 1.2 = 2.4
        assert abs(breakdown.multiplier - 2.4) < 0.001

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
