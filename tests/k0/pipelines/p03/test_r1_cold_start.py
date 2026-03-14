"""
Tests for Cold Start Strategy — Issue 4.1.6.

Covers:
    - 3-level fallback: per-space → global → static priors
    - Progressive blending formula: α = sample_count / 500
    - Weight normalization after blending
    - Blending behavior at various sample counts

Spec Reference:
    - M4_EXECUTION.md Issue 4.1.6
    - Dossier Appendix C.2.1.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pytest

from k0.modules.consolidation.algorithms.importance_scorer import ImportanceScorer, LearnedWeights

# =============================================================================
# Mock Weight Store for Testing
# =============================================================================


@dataclass
class MockLearnedWeights:
    """Mock learned weights for testing."""

    weights: Dict[str, float]
    sample_count: int
    updated_at: int = 0


class MockWeightStore:
    """Mock weight store for testing cold start."""

    def __init__(self) -> None:
        self.space_weights: Dict[str, MockLearnedWeights] = {}
        self.global_weights: Optional[MockLearnedWeights] = None

    async def get_weights(
        self,
        space_id: str,
        param_prefix: str,
    ) -> Optional[LearnedWeights]:
        """Get weights for space or global."""
        if space_id == "__global__" and self.global_weights:
            return LearnedWeights(
                weights=self.global_weights.weights,
                sample_count=self.global_weights.sample_count,
                updated_at=self.global_weights.updated_at,
            )

        if space_id in self.space_weights:
            sw = self.space_weights[space_id]
            return LearnedWeights(
                weights=sw.weights,
                sample_count=sw.sample_count,
                updated_at=sw.updated_at,
            )

        return None

    def set_space_weights(
        self,
        space_id: str,
        weights: Dict[str, float],
        sample_count: int,
    ) -> None:
        """Set weights for a space."""
        self.space_weights[space_id] = MockLearnedWeights(
            weights=weights, sample_count=sample_count
        )

    def set_global_weights(
        self,
        weights: Dict[str, float],
        sample_count: int,
    ) -> None:
        """Set global fallback weights."""
        self.global_weights = MockLearnedWeights(weights=weights, sample_count=sample_count)


# =============================================================================
# Cold Start Fallback Tests
# =============================================================================


class TestColdStartFallback:
    """Test 3-level fallback hierarchy."""

    @pytest.mark.asyncio
    async def test_fallback_to_static_no_store(self) -> None:
        """Returns static priors when no store is configured."""
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)

        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "static"
        assert sample_count == 0
        # CONFIG_B static priors
        assert abs(weights.sentiment_weight - 0.10) < 0.01
        assert abs(weights.affect_weight - 0.12) < 0.01
        assert abs(weights.arousal_weight - 0.08) < 0.01
        assert abs(weights.surprise_weight - 0.15) < 0.01
        assert abs(weights.novelty_weight - 0.15) < 0.01
        assert abs(weights.social_weight - 0.15) < 0.01
        assert abs(weights.identity_weight - 0.10) < 0.01
        assert abs(weights.recency_weight - 0.15) < 0.01

    @pytest.mark.asyncio
    async def test_fallback_to_static_no_weights(self) -> None:
        """Returns static priors when store has no weights."""
        store = MockWeightStore()
        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)

        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "static"
        assert sample_count == 0

    @pytest.mark.asyncio
    async def test_fallback_to_global_when_space_empty(self) -> None:
        """Falls back to global weights when space has no weights."""
        store = MockWeightStore()
        store.set_global_weights(
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.15,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.15,
            },
            sample_count=600,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "global"
        assert sample_count == 600

    @pytest.mark.asyncio
    async def test_use_space_weights_when_available(self) -> None:
        """Uses per-space weights when available with 500+ samples."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.15,
                "identity": 0.10,
                "recency": 0.10,
            },
            sample_count=500,
        )
        store.set_global_weights(
            weights={
                "sentiment": 0.10,
                "affect": 0.10,
                "arousal": 0.10,
                "surprise": 0.15,
                "novelty": 0.20,
                "social": 0.15,
                "identity": 0.10,
                "recency": 0.10,
            },
            sample_count=1000,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "per-space"
        assert sample_count == 500


# =============================================================================
# Progressive Blending Tests
# =============================================================================


class TestProgressiveBlending:
    """Test progressive blending formula: α = sample_count / 500."""

    @pytest.mark.asyncio
    async def test_zero_samples_pure_static(self) -> None:
        """0 samples → pure static priors (α=0)."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.40,
                "affect": 0.10,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=0,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, _ = await scorer.get_weights_with_cold_start()

        # Below 100 samples, uses static (doesn't even blend)
        assert source == "static"

    @pytest.mark.asyncio
    async def test_50_samples_pure_static(self) -> None:
        """50 samples → pure static priors (below min_blend_samples)."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.40,
                "affect": 0.10,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=50,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, _ = await scorer.get_weights_with_cold_start()

        # Below 100 samples falls through to static
        assert source == "static"

    @pytest.mark.asyncio
    async def test_100_samples_begins_blending(self) -> None:
        """100 samples → begins blending (α=0.2)."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            # Extreme learned weights to see blending effect
            weights={
                "sentiment": 0.50,
                "affect": 0.10,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.05,
                "social": 0.05,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=100,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "per-space-blend"
        assert sample_count == 100

        # With α=0.2: blended = 0.2*learned + 0.8*static
        # sentiment: 0.2*0.50 + 0.8*0.10 = 0.18
        # Both dicts sum to 1.0, so blended sums to 1.0 (no normalization shift)
        # Should be between static (0.10) and learned (0.50)
        assert 0.10 < weights.sentiment_weight < 0.50

    @pytest.mark.asyncio
    async def test_250_samples_half_blend(self) -> None:
        """250 samples → half blending (α=0.5)."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.30,
                "affect": 0.15,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.15,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=250,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "per-space-blend"
        assert sample_count == 250

        # α=0.5: halfway between learned and static
        # sentiment: 0.5*0.30 + 0.5*0.10 = 0.20
        assert 0.10 < weights.sentiment_weight < 0.30

    @pytest.mark.asyncio
    async def test_499_samples_nearly_full(self) -> None:
        """499 samples → nearly full learned (α≈0.998)."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.25,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.15,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=499,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "per-space-blend"
        assert sample_count == 499

        # α≈1: almost purely learned
        assert 0.20 < weights.sentiment_weight < 0.30

    @pytest.mark.asyncio
    async def test_500_samples_pure_learned(self) -> None:
        """500+ samples → pure learned weights (α=1)."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.25,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.15,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=500,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "per-space"
        assert sample_count == 500

        # Pure learned weights (may be normalized)
        assert abs(weights.sentiment_weight - 0.25) < 0.05


# =============================================================================
# Weight Normalization Tests
# =============================================================================


class TestBlendedWeightNormalization:
    """Test that blended weights are properly normalized."""

    @pytest.mark.asyncio
    async def test_blended_weights_sum_to_one(self) -> None:
        """Blended weights should sum to 1.0."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.15,
                "novelty": 0.10,
                "social": 0.15,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=300,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, _, _ = await scorer.get_weights_with_cold_start()

        total = (
            weights.sentiment_weight
            + weights.affect_weight
            + weights.arousal_weight
            + weights.surprise_weight
            + weights.novelty_weight
            + weights.social_weight
            + weights.identity_weight
            + weights.recency_weight
        )
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_pure_learned_weights_sum_to_one(self) -> None:
        """Pure learned weights should sum to 1.0."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.15,
                "novelty": 0.10,
                "social": 0.15,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=600,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, _, _ = await scorer.get_weights_with_cold_start()

        total = (
            weights.sentiment_weight
            + weights.affect_weight
            + weights.arousal_weight
            + weights.surprise_weight
            + weights.novelty_weight
            + weights.social_weight
            + weights.identity_weight
            + weights.recency_weight
        )
        assert abs(total - 1.0) < 0.01


# =============================================================================
# Global Blending Tests
# =============================================================================


class TestGlobalBlending:
    """Test blending with global fallback weights."""

    @pytest.mark.asyncio
    async def test_global_blend_when_space_insufficient(self) -> None:
        """Uses global blend when space has insufficient samples."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.40,
                "affect": 0.10,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=50,  # Too few for blending
        )
        store.set_global_weights(
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.15,
                "social": 0.10,
                "identity": 0.10,
                "recency": 0.10,
            },
            sample_count=300,  # Enough for blending
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "global-blend"
        assert sample_count == 300

    @pytest.mark.asyncio
    async def test_global_full_when_1000_samples(self) -> None:
        """Uses full global weights at 1000+ samples."""
        store = MockWeightStore()
        store.set_global_weights(
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.15,
                "novelty": 0.10,
                "social": 0.10,
                "identity": 0.10,
                "recency": 0.10,
            },
            sample_count=1000,
        )

        scorer = ImportanceScorer(space_id="sp_new", weight_store=store)
        weights, source, sample_count = await scorer.get_weights_with_cold_start()

        assert source == "global"
        assert sample_count == 1000


# =============================================================================
# Blend Helper Tests
# =============================================================================


class TestBlendWeightsHelper:
    """Test the internal _blend_weights helper."""

    def test_blend_with_alpha_zero(self) -> None:
        """α=0 → pure static."""
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)

        learned = {
            "sentiment": 0.40,
            "affect": 0.10,
            "arousal": 0.05,
            "surprise": 0.10,
            "novelty": 0.10,
            "social": 0.10,
            "identity": 0.05,
            "recency": 0.10,
        }
        static = {
            "sentiment": 0.10,
            "affect": 0.12,
            "arousal": 0.08,
            "surprise": 0.15,
            "novelty": 0.15,
            "social": 0.15,
            "identity": 0.10,
            "recency": 0.15,
        }

        blended = scorer._blend_weights(learned, static, alpha=0.0)

        # Pure static
        assert abs(blended["sentiment"] - 0.10) < 0.01
        assert abs(blended["affect"] - 0.12) < 0.01

    def test_blend_with_alpha_one(self) -> None:
        """α=1 → pure learned."""
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)

        learned = {
            "sentiment": 0.40,
            "affect": 0.10,
            "arousal": 0.05,
            "surprise": 0.10,
            "novelty": 0.10,
            "social": 0.10,
            "identity": 0.05,
            "recency": 0.10,
        }
        static = {
            "sentiment": 0.10,
            "affect": 0.12,
            "arousal": 0.08,
            "surprise": 0.15,
            "novelty": 0.15,
            "social": 0.15,
            "identity": 0.10,
            "recency": 0.15,
        }

        blended = scorer._blend_weights(learned, static, alpha=1.0)

        # Pure learned
        assert abs(blended["sentiment"] - 0.40) < 0.01
        assert abs(blended["affect"] - 0.10) < 0.01

    def test_blend_with_alpha_half(self) -> None:
        """α=0.5 → halfway blend."""
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)

        learned = {
            "sentiment": 0.30,
            "affect": 0.10,
            "arousal": 0.08,
            "surprise": 0.15,
            "novelty": 0.12,
            "social": 0.10,
            "identity": 0.05,
            "recency": 0.10,
        }
        static = {
            "sentiment": 0.10,
            "affect": 0.30,
            "arousal": 0.08,
            "surprise": 0.15,
            "novelty": 0.12,
            "social": 0.10,
            "identity": 0.05,
            "recency": 0.10,
        }

        blended = scorer._blend_weights(learned, static, alpha=0.5)

        # Halfway: (0.30+0.10)/2 = 0.20, (0.10+0.30)/2 = 0.20
        assert abs(blended["sentiment"] - 0.20) < 0.01
        assert abs(blended["affect"] - 0.20) < 0.01

    def test_blend_normalizes_to_one(self) -> None:
        """Blended weights are normalized to sum to 1."""
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)

        learned = {
            "sentiment": 0.20,
            "affect": 0.15,
            "arousal": 0.10,
            "surprise": 0.15,
            "novelty": 0.10,
            "social": 0.15,
            "identity": 0.05,
            "recency": 0.10,
        }
        static = {
            "sentiment": 0.10,
            "affect": 0.12,
            "arousal": 0.08,
            "surprise": 0.15,
            "novelty": 0.15,
            "social": 0.15,
            "identity": 0.10,
            "recency": 0.15,
        }

        blended = scorer._blend_weights(learned, static, alpha=0.7)

        total = sum(blended.values())
        assert abs(total - 1.0) < 0.01


# =============================================================================
# Cache Invalidation Tests
# =============================================================================


class TestCacheWithColdStart:
    """Test cache behavior with cold start weights."""

    @pytest.mark.asyncio
    async def test_cold_start_caches_weights(self) -> None:
        """get_weights_with_cold_start caches the result."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.15,
                "social": 0.10,
                "identity": 0.10,
                "recency": 0.10,
            },
            sample_count=600,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)

        # First call
        weights1, _, _ = await scorer.get_weights_with_cold_start()

        # Modify store
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.40,
                "affect": 0.10,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=700,
        )

        # Second call should return cached
        weights2, _, _ = await scorer.get_weights_with_cold_start()

        # Same cached weights
        assert weights1.sentiment_weight == weights2.sentiment_weight

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self) -> None:
        """invalidate_weight_cache clears cached weights."""
        store = MockWeightStore()
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.20,
                "affect": 0.15,
                "arousal": 0.10,
                "surprise": 0.10,
                "novelty": 0.15,
                "social": 0.10,
                "identity": 0.10,
                "recency": 0.10,
            },
            sample_count=600,
        )

        scorer = ImportanceScorer(space_id="sp_test", weight_store=store)

        # First call
        await scorer.get_weights_with_cold_start()

        # Modify store
        store.set_space_weights(
            space_id="sp_test",
            weights={
                "sentiment": 0.40,
                "affect": 0.10,
                "arousal": 0.05,
                "surprise": 0.10,
                "novelty": 0.10,
                "social": 0.10,
                "identity": 0.05,
                "recency": 0.10,
            },
            sample_count=700,
        )

        # Invalidate cache
        scorer.invalidate_weight_cache()

        # Second call should get new weights
        weights2, _, _ = await scorer.get_weights_with_cold_start()

        assert abs(weights2.sentiment_weight - 0.40) < 0.05
