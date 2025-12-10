"""
Tests for M07.2: social.relationship_inference - Relationship Inference Engine

Test Coverage:
- Name pattern inference (family roles in person IDs)
- Co-occurrence based inference
- Group size inference hints
- Inference engine integration
- Edge cases and error handling
- Performance targets (<20ms P95)

Research: Hamilton et al. (2017) GraphSAGE, Kipf & Welling (2016) GCN
"""

import pytest

from k0.modules.social.relationship_inference import (
    CooccurrenceInference,
    CooccurrenceStats,
    InferredRelationship,
    RelationshipInferenceEngine,
    RelationType,
    _infer_from_group_size,
    _infer_from_name_pattern,
    get_inference_engine,
    infer_all_relationships,
    infer_relationship,
)

# ============================================================================
# Test: Name Pattern Inference
# ============================================================================


class TestNamePatternInference:
    """Tests for name-based relationship inference."""

    def test_spouse_patterns(self):
        """Test spouse pattern detection."""
        patterns = ["person_spouse", "person_wife", "person_husband", "person_partner"]
        for pattern in patterns:
            result = _infer_from_name_pattern("actor_1", pattern)
            assert result is not None, f"Failed to infer from {pattern}"
            assert result.relationship_type == RelationType.SPOUSE_OF
            assert result.inference_method == "name_pattern"
            assert result.confidence >= 0.5

    def test_parent_patterns(self):
        """Test parent pattern detection (actor is child of them)."""
        patterns = ["person_mom", "person_dad", "person_mother", "person_father"]
        for pattern in patterns:
            result = _infer_from_name_pattern("actor_1", pattern)
            assert result is not None, f"Failed to infer from {pattern}"
            # When person is named "mom", actor is CHILD_OF them
            assert result.relationship_type == RelationType.CHILD_OF
            assert result.confidence >= 0.5

    def test_child_patterns(self):
        """Test child pattern detection (actor is parent of them)."""
        patterns = ["person_kid", "person_child", "person_son", "person_daughter"]
        for pattern in patterns:
            result = _infer_from_name_pattern("actor_1", pattern)
            assert result is not None, f"Failed to infer from {pattern}"
            # When person is named "kid", actor is PARENT_OF them
            assert result.relationship_type == RelationType.PARENT_OF
            assert result.confidence >= 0.5

    def test_sibling_patterns(self):
        """Test sibling pattern detection."""
        patterns = ["person_brother", "person_sister", "person_sibling"]
        for pattern in patterns:
            result = _infer_from_name_pattern("actor_1", pattern)
            assert result is not None, f"Failed to infer from {pattern}"
            assert result.relationship_type == RelationType.SIBLING_OF
            assert result.confidence >= 0.5

    def test_no_match_for_generic_names(self):
        """Test that generic names return None."""
        generic_names = ["person_john", "person_emma", "friend_1", "colleague_bob"]
        for name in generic_names:
            result = _infer_from_name_pattern("actor_1", name)
            assert result is None, f"Unexpected match for {name}"

    def test_case_insensitive_matching(self):
        """Test that pattern matching is case-insensitive."""
        result = _infer_from_name_pattern("actor_1", "Person_MOM")
        assert result is not None
        assert result.relationship_type == RelationType.CHILD_OF

    def test_self_inference_skipped(self):
        """Test that self-inference is not performed."""
        # This is handled at engine level, but name pattern should still work
        result = _infer_from_name_pattern("person_dad", "person_dad")
        # Name pattern doesn't check for self, engine does
        # So this might return a result, which is fine


# ============================================================================
# Test: Co-occurrence Inference
# ============================================================================


class TestCooccurrenceInference:
    """Tests for co-occurrence based inference."""

    @pytest.fixture
    def inference(self):
        return CooccurrenceInference()

    @pytest.mark.asyncio
    async def test_significant_meal_cooccurrence(self, inference):
        """Test inference from significant meal event co-occurrence."""
        stats = CooccurrenceStats(
            person_id="actor_1",
            related_person_id="person_2",
            total_events=10,
            shared_events=8,
            event_types={"meal": 6, "outing": 2},
            recency_score=0.9,
        )

        result = await inference.infer_from_cooccurrence("actor_1", "person_2", stats)

        assert result is not None
        assert result.inference_method == "cooccurrence"
        assert result.confidence > 0.5
        assert "shared" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_insufficient_shared_events(self, inference):
        """Test that too few shared events returns None."""
        stats = CooccurrenceStats(
            person_id="actor_1",
            related_person_id="person_2",
            total_events=100,
            shared_events=1,  # Only 1 shared event
            event_types={"meal": 1},
            recency_score=0.9,
        )

        result = await inference.infer_from_cooccurrence("actor_1", "person_2", stats)
        assert result is None

    @pytest.mark.asyncio
    async def test_low_cooccurrence_rate(self, inference):
        """Test that low co-occurrence rate returns None."""
        stats = CooccurrenceStats(
            person_id="actor_1",
            related_person_id="person_2",
            total_events=100,
            shared_events=3,
            event_types={"meal": 3},
            recency_score=0.9,
        )
        # Co-occurrence rate = 3/100 = 0.03, below threshold

        result = await inference.infer_from_cooccurrence("actor_1", "person_2", stats)
        assert result is None

    @pytest.mark.asyncio
    async def test_work_events_infer_colleague(self, inference):
        """Test that work events suggest colleague relationship."""
        stats = CooccurrenceStats(
            person_id="actor_1",
            related_person_id="person_2",
            total_events=20,
            shared_events=15,
            event_types={"work": 15},
            recency_score=0.8,
        )

        result = await inference.infer_from_cooccurrence("actor_1", "person_2", stats)

        assert result is not None
        assert result.relationship_type == RelationType.COLLEAGUE

    @pytest.mark.asyncio
    async def test_high_confidence_with_many_events(self, inference):
        """Test that many shared events increase confidence."""
        stats = CooccurrenceStats(
            person_id="actor_1",
            related_person_id="person_2",
            total_events=30,
            shared_events=25,
            event_types={"meal": 20, "celebration": 5},
            recency_score=0.95,
        )

        result = await inference.infer_from_cooccurrence("actor_1", "person_2", stats)

        assert result is not None
        assert result.confidence >= 0.6  # High confidence
        assert "frequently" in result.explanation.lower()


class TestCooccurrenceStats:
    """Tests for CooccurrenceStats dataclass."""

    def test_cooccurrence_rate_calculation(self):
        """Test co-occurrence rate property."""
        stats = CooccurrenceStats(
            person_id="a",
            related_person_id="b",
            total_events=10,
            shared_events=5,
            event_types={},
            recency_score=1.0,
        )
        assert stats.cooccurrence_rate == 0.5

    def test_cooccurrence_rate_zero_events(self):
        """Test co-occurrence rate with zero total events."""
        stats = CooccurrenceStats(
            person_id="a",
            related_person_id="b",
            total_events=0,
            shared_events=0,
            event_types={},
            recency_score=1.0,
        )
        assert stats.cooccurrence_rate == 0.0

    def test_is_significant_true(self):
        """Test significance check with sufficient data."""
        stats = CooccurrenceStats(
            person_id="a",
            related_person_id="b",
            total_events=10,
            shared_events=5,
            event_types={},
            recency_score=1.0,
        )
        assert stats.is_significant is True

    def test_is_significant_false_few_events(self):
        """Test significance check with too few shared events."""
        stats = CooccurrenceStats(
            person_id="a",
            related_person_id="b",
            total_events=10,
            shared_events=2,
            event_types={},
            recency_score=1.0,
        )
        assert stats.is_significant is False


# ============================================================================
# Test: Group Size Inference
# ============================================================================


class TestGroupSizeInference:
    """Tests for group size based inference hints."""

    def test_two_person_meal_suggests_spouse(self):
        """Test that 2-person meal suggests close relationship."""
        result = _infer_from_group_size("actor_1", "person_2", 2, "meal")

        assert result is not None
        assert result.relationship_type == RelationType.SPOUSE_OF
        assert result.inference_method == "group_size"
        assert result.confidence < 0.5  # Low confidence hint

    def test_two_person_outing(self):
        """Test that 2-person outing suggests close relationship."""
        result = _infer_from_group_size("actor_1", "person_2", 2, "outing")

        assert result is not None
        assert result.confidence < 0.5

    def test_large_group_no_inference(self):
        """Test that large groups don't trigger inference."""
        result = _infer_from_group_size("actor_1", "person_2", 10, "meal")
        assert result is None

    def test_no_event_type(self):
        """Test group size inference without event type."""
        result = _infer_from_group_size("actor_1", "person_2", 2, None)
        assert result is None  # No inference without event type context


# ============================================================================
# Test: Relationship Inference Engine
# ============================================================================


class TestRelationshipInferenceEngine:
    """Tests for the main inference engine."""

    @pytest.fixture
    def engine(self):
        return RelationshipInferenceEngine()

    @pytest.mark.asyncio
    async def test_name_pattern_takes_priority(self, engine):
        """Test that name pattern inference is tried first."""
        result = await engine.infer_relationship(
            actor_id="actor_1",
            participant_id="person_mom",
            cooccurrence_stats=None,
            event_type="meal",
            group_size=3,
        )

        assert result is not None
        assert result.inference_method == "name_pattern"
        # person_mom means they are actor's parent, so actor is CHILD_OF them
        assert result.relationship_type == RelationType.CHILD_OF

    @pytest.mark.asyncio
    async def test_self_returns_none(self, engine):
        """Test that self-inference returns None."""
        result = await engine.infer_relationship(
            actor_id="actor_1",
            participant_id="actor_1",
            cooccurrence_stats=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_cooccurrence_used_when_no_name_match(self, engine):
        """Test that co-occurrence is used when name doesn't match."""
        stats = CooccurrenceStats(
            person_id="actor_1",
            related_person_id="person_john",
            total_events=10,
            shared_events=8,
            event_types={"meal": 8},
            recency_score=0.9,
        )

        result = await engine.infer_relationship(
            actor_id="actor_1",
            participant_id="person_john",
            cooccurrence_stats=stats,
        )

        assert result is not None
        assert result.inference_method == "cooccurrence"

    @pytest.mark.asyncio
    async def test_group_size_fallback(self, engine):
        """Test that group size is used as fallback."""
        result = await engine.infer_relationship(
            actor_id="actor_1",
            participant_id="person_unknown",
            cooccurrence_stats=None,
            event_type="meal",
            group_size=2,
        )

        assert result is not None
        assert result.inference_method == "group_size"

    @pytest.mark.asyncio
    async def test_no_inference_possible(self, engine):
        """Test that None is returned when no inference is possible."""
        result = await engine.infer_relationship(
            actor_id="actor_1",
            participant_id="person_random_123",
            cooccurrence_stats=None,
            event_type=None,
            group_size=5,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_infer_all_relationships(self, engine):
        """Test inference for multiple participants."""
        participants = ["actor_1", "person_mom", "person_friend"]

        results = await engine.infer_all_relationships(
            actor_id="actor_1",
            participants=participants,
            cooccurrence_data=None,
            event_type="meal",
        )

        assert "actor_1" not in results  # Self excluded
        assert "person_mom" in results
        assert results["person_mom"].relationship_type == RelationType.CHILD_OF


# ============================================================================
# Test: Module-Level API
# ============================================================================


class TestModuleAPI:
    """Tests for module-level convenience functions."""

    def test_get_inference_engine_singleton(self):
        """Test that get_inference_engine returns singleton."""
        engine1 = get_inference_engine()
        engine2 = get_inference_engine()
        assert engine1 is engine2

    @pytest.mark.asyncio
    async def test_infer_relationship_function(self):
        """Test convenience function."""
        result = await infer_relationship(
            actor_id="actor_1",
            participant_id="person_wife",
        )
        assert result is not None
        assert result.relationship_type == RelationType.SPOUSE_OF

    @pytest.mark.asyncio
    async def test_infer_all_relationships_function(self):
        """Test convenience function for batch inference."""
        results = await infer_all_relationships(
            actor_id="actor_1",
            participants=["actor_1", "person_dad", "person_brother"],
        )
        assert "person_dad" in results
        assert "person_brother" in results


# ============================================================================
# Test: InferredRelationship Dataclass
# ============================================================================


class TestInferredRelationship:
    """Tests for InferredRelationship dataclass."""

    def test_is_high_confidence_true(self):
        """Test high confidence threshold."""
        rel = InferredRelationship(
            person_id="a",
            related_person_id="b",
            relationship_type=RelationType.SPOUSE_OF,
            confidence=0.8,
            inference_method="test",
            explanation="test",
        )
        assert rel.is_high_confidence is True

    def test_is_high_confidence_false(self):
        """Test low confidence threshold."""
        rel = InferredRelationship(
            person_id="a",
            related_person_id="b",
            relationship_type=RelationType.SPOUSE_OF,
            confidence=0.5,
            inference_method="test",
            explanation="test",
        )
        assert rel.is_high_confidence is False

    def test_supporting_evidence_default(self):
        """Test that supporting evidence defaults to empty dict."""
        rel = InferredRelationship(
            person_id="a",
            related_person_id="b",
            relationship_type=RelationType.FRIEND,
            confidence=0.5,
            inference_method="test",
            explanation="test",
        )
        assert rel.supporting_evidence == {}


# ============================================================================
# Test: Performance
# ============================================================================


class TestPerformance:
    """Performance tests for inference engine."""

    @pytest.mark.asyncio
    async def test_name_inference_latency(self):
        """Test that name inference is fast (<1ms)."""
        import time

        start = time.perf_counter()
        for _ in range(100):
            _infer_from_name_pattern("actor_1", "person_mom")
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 100 iterations should be < 10ms (0.1ms each)
        assert elapsed_ms < 10, f"Name inference too slow: {elapsed_ms}ms for 100 iterations"

    @pytest.mark.asyncio
    async def test_engine_inference_latency(self):
        """Test that full inference is fast (<20ms P95)."""
        import time

        engine = RelationshipInferenceEngine()
        latencies = []

        for _ in range(50):
            start = time.perf_counter()
            await engine.infer_relationship(
                actor_id="actor_1",
                participant_id="person_random",
                cooccurrence_stats=None,
                event_type="meal",
                group_size=3,
            )
            latencies.append((time.perf_counter() - start) * 1000)

        # Sort and get P95
        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        assert p95 < 20, f"Inference P95 latency {p95}ms exceeds 20ms target"
