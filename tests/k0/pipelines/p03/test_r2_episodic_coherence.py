"""
Tests for EpisodicCoherenceScorer - Per-episode semantic coherence.

M4-RSCH-04: equal_weight coherence rho=0.4556 post-correction.
Replaces broken silhouette (mean=-0.0329) as primary quality signal.

Tests:
    1. Narrative coherence: single-thread=1.0, mixed<1.0, no-thread=None
    2. Social coherence: same-context=1.0, mixed<1.0
    3. Spatial coherence: same-location=1.0, mixed<1.0
    4. Temporal coherence: tight=high, spread=low
    5. Affective coherence: similar-affect=high, diverse=low
    6. Composite: equal-weight mean of populated dimensions
    7. Missing-signal fallback: 0.5 neutral for missing dimensions
    8. Batch aggregation: mean, min, max, std
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from k0.modules.consolidation.algorithms.episodic_coherence import (
    BatchCoherenceSummary,
    EpisodicCoherenceResult,
    EpisodicCoherenceScorer,
    compute_batch_coherence,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockContext:
    """Mock ObservationContext for coherence testing."""

    observed_at: int = 0
    narrative_thread_id: Optional[str] = None
    social_context: Optional[str] = None
    location_name: Optional[str] = None
    geohash_6: Optional[str] = None
    affect_valence: Optional[float] = None


# =============================================================================
# Narrative Coherence
# =============================================================================


class TestNarrativeCoherence:
    """Test narrative dimension of coherence."""

    def test_single_thread_is_perfectly_coherent(self) -> None:
        """All events sharing same thread_id -> narrative=1.0."""
        members = [
            MockContext(narrative_thread_id="thread-A"),
            MockContext(narrative_thread_id="thread-A"),
            MockContext(narrative_thread_id="thread-A"),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.narrative == 1.0

    def test_mixed_threads_less_than_one(self) -> None:
        """Multiple threads -> narrative < 1.0."""
        members = [
            MockContext(narrative_thread_id="thread-A"),
            MockContext(narrative_thread_id="thread-A"),
            MockContext(narrative_thread_id="thread-B"),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.narrative is not None
        assert result.dimensions.narrative == pytest.approx(2 / 3, abs=0.01)

    def test_no_threads_returns_none(self) -> None:
        """No narrative_thread_id on any event -> None (uncertain)."""
        members = [
            MockContext(),
            MockContext(),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.narrative is None


# =============================================================================
# Social Coherence
# =============================================================================


class TestSocialCoherence:
    """Test social dimension of coherence."""

    def test_same_social_context_is_coherent(self) -> None:
        """All events in same social context -> social=1.0."""
        members = [
            MockContext(social_context="family"),
            MockContext(social_context="family"),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.social == 1.0

    def test_mixed_social_context(self) -> None:
        """Mixed social contexts -> social < 1.0."""
        members = [
            MockContext(social_context="family"),
            MockContext(social_context="family"),
            MockContext(social_context="work"),
            MockContext(social_context="solo"),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.social is not None
        assert result.dimensions.social == pytest.approx(0.5, abs=0.01)

    def test_no_social_returns_none(self) -> None:
        """No social_context -> None."""
        members = [MockContext(), MockContext()]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.social is None


# =============================================================================
# Spatial Coherence
# =============================================================================


class TestSpatialCoherence:
    """Test spatial dimension of coherence."""

    def test_same_geohash_is_coherent(self) -> None:
        """Same geohash_6 -> spatial=1.0."""
        members = [
            MockContext(geohash_6="9q8yyk"),
            MockContext(geohash_6="9q8yyk"),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.spatial == 1.0

    def test_falls_back_to_location_name(self) -> None:
        """Uses location_name when geohash_6 is missing."""
        members = [
            MockContext(location_name="Home"),
            MockContext(location_name="Home"),
            MockContext(location_name="Office"),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.spatial is not None
        assert result.dimensions.spatial == pytest.approx(2 / 3, abs=0.01)


# =============================================================================
# Temporal Coherence
# =============================================================================


class TestTemporalCoherence:
    """Test temporal dimension of coherence."""

    def test_tight_cluster_is_coherent(self) -> None:
        """Events within 1 hour -> high temporal coherence."""
        members = [
            MockContext(observed_at=1000000),
            MockContext(observed_at=1000000 + 60 * 60 * 1000),  # +1 hour
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.temporal is not None
        # 1 hour / 24 hours = 0.0417 spread -> 0.958 coherence
        assert result.dimensions.temporal > 0.9

    def test_spread_cluster_is_less_coherent(self) -> None:
        """Events spread over 12 hours -> lower coherence."""
        members = [
            MockContext(observed_at=1000000),
            MockContext(observed_at=1000000 + 12 * 60 * 60 * 1000),  # +12 hours
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.temporal is not None
        assert result.dimensions.temporal == pytest.approx(0.5, abs=0.01)

    def test_single_event_returns_none(self) -> None:
        """Single event has no temporal spread -> None."""
        members = [MockContext(observed_at=1000000)]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.temporal is None


# =============================================================================
# Affective Coherence
# =============================================================================


class TestAffectiveCoherence:
    """Test affective dimension of coherence."""

    def test_similar_affect_is_coherent(self) -> None:
        """Events with similar valence -> high affective coherence."""
        members = [
            MockContext(affect_valence=0.7),
            MockContext(affect_valence=0.8),
            MockContext(affect_valence=0.75),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.affective is not None
        assert result.dimensions.affective > 0.9

    def test_diverse_affect_is_less_coherent(self) -> None:
        """Events with diverse valence -> lower affective coherence."""
        members = [
            MockContext(affect_valence=-0.8),  # Very negative
            MockContext(affect_valence=0.8),  # Very positive
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.affective is not None
        assert result.dimensions.affective < 0.3

    def test_no_affect_returns_none(self) -> None:
        """No affect_valence -> None."""
        members = [MockContext(), MockContext()]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.dimensions.affective is None


# =============================================================================
# Composite Score
# =============================================================================


class TestCompositeCoherence:
    """Test composite coherence computation."""

    def test_all_dimensions_populated(self) -> None:
        """Composite is equal-weight mean of all dimensions."""
        members = [
            MockContext(
                observed_at=1000000,
                narrative_thread_id="t1",
                social_context="family",
                geohash_6="9q8yyk",
                affect_valence=0.5,
            ),
            MockContext(
                observed_at=1000000 + 60 * 60 * 1000,
                narrative_thread_id="t1",
                social_context="family",
                geohash_6="9q8yyk",
                affect_valence=0.5,
            ),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        assert result.populated_count == 5
        # All dimensions should be high (same context)
        assert result.composite > 0.8

    def test_no_dimensions_populated_returns_neutral(self) -> None:
        """No data at all -> composite=0.5 (neutral fallback)."""
        members = [MockContext(), MockContext()]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        # Temporal needs >= 2 events with timestamps, but observed_at=0
        assert result.composite == pytest.approx(0.5)

    def test_partial_dimensions(self) -> None:
        """Only some dimensions populated -> composite from those only."""
        members = [
            MockContext(social_context="family", affect_valence=0.5),
            MockContext(social_context="family", affect_valence=0.5),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)

        # social=1.0, affective~1.0 (same valence), no narrative/spatial/temporal
        assert result.populated_count == 2
        assert result.composite > 0.9

    def test_empty_members_returns_default(self) -> None:
        """Empty member list returns neutral result."""
        scorer = EpisodicCoherenceScorer()
        result = scorer.compute([])

        assert result.composite == pytest.approx(0.5)
        assert result.member_count == 0

    def test_dimensions_to_dict(self) -> None:
        """CoherenceDimensions serializes correctly."""
        members = [
            MockContext(social_context="family", affect_valence=0.5),
            MockContext(social_context="family", affect_valence=0.5),
        ]

        scorer = EpisodicCoherenceScorer()
        result = scorer.compute(members)
        d = result.dimensions.to_dict()

        assert d["social"] is not None
        assert d["affective"] is not None
        assert d["narrative"] is None
        assert d["spatial"] is None


# =============================================================================
# Batch Aggregation
# =============================================================================


class TestBatchCoherence:
    """Test batch-level coherence aggregation."""

    def test_batch_aggregation(self) -> None:
        """Batch summary computes mean, min, max, std correctly."""
        results = [
            EpisodicCoherenceResult(composite=0.9, populated_count=5, member_count=5),
            EpisodicCoherenceResult(composite=0.5, populated_count=3, member_count=3),
            EpisodicCoherenceResult(composite=0.7, populated_count=4, member_count=4),
        ]

        summary = compute_batch_coherence(results)

        assert summary.episode_count == 3
        assert summary.mean_coherence == pytest.approx(0.7, abs=0.01)
        assert summary.min_coherence == pytest.approx(0.5, abs=0.01)
        assert summary.max_coherence == pytest.approx(0.9, abs=0.01)
        assert summary.std_coherence > 0

    def test_empty_batch(self) -> None:
        """Empty batch returns neutral summary."""
        summary = compute_batch_coherence([])

        assert summary.episode_count == 0
        assert summary.mean_coherence == pytest.approx(0.5)

    def test_batch_summary_to_dict(self) -> None:
        """BatchCoherenceSummary serializes correctly."""
        summary = BatchCoherenceSummary(
            mean_coherence=0.75,
            min_coherence=0.5,
            max_coherence=0.9,
            std_coherence=0.1,
            episode_count=3,
        )

        d = summary.to_dict()
        assert d["mean_coherence"] == 0.75
        assert d["episode_count"] == 3

    def test_per_dimension_means(self) -> None:
        """Batch computes per-dimension means across episodes."""
        from k0.modules.consolidation.algorithms.episodic_coherence import CoherenceDimensions

        results = [
            EpisodicCoherenceResult(
                composite=0.8,
                dimensions=CoherenceDimensions(narrative=1.0, social=0.8),
                populated_count=2,
                member_count=3,
            ),
            EpisodicCoherenceResult(
                composite=0.6,
                dimensions=CoherenceDimensions(narrative=0.6, social=0.4),
                populated_count=2,
                member_count=3,
            ),
        ]

        summary = compute_batch_coherence(results)

        assert "narrative" in summary.per_dimension_means
        assert summary.per_dimension_means["narrative"] == pytest.approx(0.8, abs=0.01)
        assert summary.per_dimension_means["social"] == pytest.approx(0.6, abs=0.01)
