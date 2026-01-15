"""
Tests for R4 Entity Disambiguator - Per-Entity-Type Weighted Similarity.

Issue: 4.4.2 - Implement per-entity-type disambiguation weights
Spec Reference: Dossier §4.5.1.1, M4_EXECUTION.md

Tests cover:
- Weight matrix by entity type
- Fuzzy string matching algorithms
- Cosine similarity
- Combined weighted scoring
- Merge threshold decisions
- Database loading
"""

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.entity_disambiguator import (
    P03_DISAMBIGUATION_THRESHOLD,
    P03_DISAMBIGUATION_WEIGHT_MAX,
    P03_DISAMBIGUATION_WEIGHT_MIN,
    DisambiguationBreakdown,
    DisambiguationWeights,
    EntityDisambiguator,
    clamp_weight,
    get_entity_disambiguator,
    normalize_weights,
)

# =============================================================================
# DisambiguationWeights Tests
# =============================================================================


class TestDisambiguationWeights:
    """Test DisambiguationWeights dataclass."""

    def test_valid_weights(self):
        """Test creating weights that sum to 1.0."""
        weights = DisambiguationWeights(0.5, 0.5)
        assert weights.embedding_weight == 0.5
        assert weights.string_weight == 0.5

    def test_weights_sum_validation(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            DisambiguationWeights(0.5, 0.4)

    def test_negative_weights_rejected(self):
        """Test that negative weights are rejected."""
        with pytest.raises(ValueError, match="non-negative"):
            DisambiguationWeights(-0.1, 1.1)

    def test_weights_to_dict(self):
        """Test serialization to dict."""
        weights = DisambiguationWeights(0.3, 0.7)
        d = weights.to_dict()
        assert d == {"embedding_weight": 0.3, "string_weight": 0.7}

    def test_weights_frozen(self):
        """Test that weights are immutable."""
        weights = DisambiguationWeights(0.5, 0.5)
        with pytest.raises(Exception):  # dataclass(frozen=True)
            weights.embedding_weight = 0.6  # type: ignore


# =============================================================================
# Default Weight Matrix Tests
# =============================================================================


class TestDefaultWeightMatrix:
    """Test per-entity-type default weight matrix."""

    def test_person_weights_balanced(self):
        """Test PERSON uses balanced weights (0.50/0.50)."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("PERSON")
        assert weights.embedding_weight == 0.50
        assert weights.string_weight == 0.50

    def test_family_member_balanced(self):
        """Test FAMILY_MEMBER uses balanced weights (0.55/0.45) for nickname handling."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("FAMILY_MEMBER")
        assert weights.embedding_weight == 0.55
        assert weights.string_weight == 0.45

    def test_concept_embedding_heavy(self):
        """Test CONCEPT favors embedding similarity (0.85/0.15)."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("CONCEPT")
        assert weights.embedding_weight == 0.85
        assert weights.string_weight == 0.15

    def test_place_weights(self):
        """Test PLACE entity type weights (0.60/0.40)."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("PLACE")
        assert weights.embedding_weight == 0.60
        assert weights.string_weight == 0.40

    def test_location_alias_weights(self):
        """Test LOCATION as alias for PLACE."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("LOCATION")
        assert weights.embedding_weight == 0.60
        assert weights.string_weight == 0.40

    def test_organization_weights(self):
        """Test ORGANIZATION entity type weights."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("ORGANIZATION")
        assert weights.embedding_weight == 0.55
        assert weights.string_weight == 0.45

    def test_event_weights(self):
        """Test EVENT entity type weights."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("EVENT")
        assert weights.embedding_weight == 0.70
        assert weights.string_weight == 0.30

    def test_unknown_type_default(self):
        """Test unknown entity type uses balanced defaults."""
        disambiguator = EntityDisambiguator()
        weights = disambiguator.get_weights("UNKNOWN_TYPE")
        assert weights.embedding_weight == 0.50
        assert weights.string_weight == 0.50

    def test_case_insensitive_lookup(self):
        """Test type lookup is case-insensitive."""
        disambiguator = EntityDisambiguator()
        upper = disambiguator.get_weights("PERSON")
        lower = disambiguator.get_weights("person")
        mixed = disambiguator.get_weights("Person")
        assert upper == lower == mixed


# =============================================================================
# Fuzzy String Matching Tests
# =============================================================================


class TestFuzzyStringMatch:
    """Test fuzzy string matching using best-of-three algorithms."""

    def test_fuzzy_match_exact(self):
        """Test exact match returns 1.0."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("John Smith", "John Smith")
        assert score == 1.0

    def test_fuzzy_match_case_insensitive(self):
        """Test matching is case-insensitive."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("JOHN SMITH", "john smith")
        assert score == 1.0

    def test_fuzzy_match_typo(self):
        """Test Levenshtein catches minor typos."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("Jonh Smith", "John Smith")
        # Should be high similarity despite transposition
        assert score >= 0.9

    def test_fuzzy_match_reorder(self):
        """Test token_sort handles word reordering."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("John Smith", "Smith, John")
        # Token sort ratio should give high score
        assert score >= 0.9

    def test_fuzzy_match_partial(self):
        """Test partial ratio for substrings."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("NYC", "New York City NYC")
        # Partial ratio finds substring
        assert score >= 0.9

    def test_fuzzy_match_empty_string(self):
        """Test empty string returns 0.0."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("", "John")
        assert score == 0.0

    def test_fuzzy_match_algorithm_tracking(self):
        """Test that algorithm is tracked."""
        disambiguator = EntityDisambiguator()
        score, algo = disambiguator.fuzzy_string_match_with_algorithm("John Smith", "Smith, John")
        assert algo in ["levenshtein", "token_sort", "partial", "exact"]
        assert score >= 0.9

    def test_fuzzy_match_abbreviation(self):
        """Test abbreviation matching."""
        disambiguator = EntityDisambiguator()
        score = disambiguator.fuzzy_string_match("US", "United States")
        # Low score expected - abbreviations are challenging
        assert 0.0 <= score <= 1.0


# =============================================================================
# Cosine Similarity Tests
# =============================================================================


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_cosine_similarity_identical(self):
        """Test identical vectors return 1.0."""
        disambiguator = EntityDisambiguator()
        vec = [1.0, 2.0, 3.0]
        score = disambiguator._cosine_similarity(vec, vec)
        assert abs(score - 1.0) < 0.001

    def test_cosine_similarity_orthogonal(self):
        """Test orthogonal vectors return 0.0."""
        disambiguator = EntityDisambiguator()
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        score = disambiguator._cosine_similarity(vec1, vec2)
        assert abs(score) < 0.001

    def test_cosine_similarity_opposite(self):
        """Test opposite vectors return 0.0 (clamped from -1)."""
        disambiguator = EntityDisambiguator()
        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        score = disambiguator._cosine_similarity(vec1, vec2)
        # Should be clamped to 0.0
        assert score == 0.0

    def test_cosine_similarity_zero_vector(self):
        """Test zero vector returns 0.0."""
        disambiguator = EntityDisambiguator()
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [0.0, 0.0, 0.0]
        score = disambiguator._cosine_similarity(vec1, vec2)
        assert score == 0.0

    def test_cosine_similarity_numpy_arrays(self):
        """Test with numpy arrays."""
        disambiguator = EntityDisambiguator()
        vec1 = np.array([1.0, 2.0, 3.0])
        vec2 = np.array([1.0, 2.0, 3.0])
        score = disambiguator._cosine_similarity(vec1, vec2)
        assert abs(score - 1.0) < 0.001


# =============================================================================
# Combined Score Tests
# =============================================================================


class TestCombinedScore:
    """Test weighted combined scoring."""

    def test_combined_score_weighted(self):
        """Test weighted combination of embedding and string scores."""
        disambiguator = EntityDisambiguator()

        # Create identical embeddings (cosine = 1.0)
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [1.0, 0.0, 0.0]

        # Create similar names (string ~ 0.9)
        name1 = "John Smith"
        name2 = "Jon Smith"

        score, breakdown = disambiguator.compute_similarity(
            embedding1, name1, embedding2, name2, "PERSON"
        )

        # PERSON is 0.50/0.50
        # Combined = 0.50 * 1.0 + 0.50 * string_sim
        assert breakdown.embedding_weight == 0.50
        assert breakdown.string_weight == 0.50
        assert breakdown.embedding_similarity == 1.0
        assert breakdown.string_similarity > 0.8  # Should be high

        expected = 0.50 * 1.0 + 0.50 * breakdown.string_similarity
        assert abs(score - expected) < 0.01

    def test_combined_score_concept_embedding_heavy(self):
        """Test CONCEPT favors embedding similarity."""
        disambiguator = EntityDisambiguator()

        # Good embedding, poor string match
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.9, 0.1, 0.0]  # Very similar

        name1 = "car"
        name2 = "automobile"  # Different strings, same meaning

        score, breakdown = disambiguator.compute_similarity(
            embedding1, name1, embedding2, name2, "CONCEPT"
        )

        # CONCEPT is 0.85/0.15 - embedding should dominate
        assert breakdown.embedding_weight == 0.85
        assert breakdown.string_weight == 0.15

        # Score should be pulled up by embedding
        assert score > breakdown.string_similarity

    def test_combined_score_family_member_balanced(self):
        """Test FAMILY_MEMBER uses balanced weights for nicknames."""
        disambiguator = EntityDisambiguator()

        # Orthogonal embeddings (cosine = 0)
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.0, 1.0, 0.0]

        # Identical names
        name1 = "mom"
        name2 = "mom"

        score, breakdown = disambiguator.compute_similarity(
            embedding1, name1, embedding2, name2, "FAMILY_MEMBER"
        )

        # FAMILY_MEMBER is 0.55/0.45 - balanced for nickname handling
        assert breakdown.embedding_weight == 0.55
        assert breakdown.string_weight == 0.45
        assert breakdown.string_similarity == 1.0

        # Score: 0.55*0 + 0.45*1.0 = 0.45
        expected = 0.45
        assert abs(score - expected) < 0.01


# =============================================================================
# Should Merge Tests
# =============================================================================


class TestShouldMerge:
    """Test merge threshold decisions."""

    def test_should_merge_above_threshold(self):
        """Test entities above threshold should merge."""
        disambiguator = EntityDisambiguator(threshold=0.85)

        # Identical everything
        embedding = [1.0, 0.0, 0.0]
        name1 = "John Smith"
        name2 = "John Smith"

        should_merge, score, breakdown = disambiguator.should_merge(
            embedding, name1, embedding, name2, "PERSON"
        )

        assert should_merge is True
        assert score == 1.0

    def test_should_merge_below_threshold(self):
        """Test entities below threshold should not merge."""
        disambiguator = EntityDisambiguator(threshold=0.85)

        # Orthogonal embeddings, different names
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.0, 1.0, 0.0]
        name1 = "John"
        name2 = "Mary"

        should_merge, score, breakdown = disambiguator.should_merge(
            embedding1, name1, embedding2, name2, "PERSON"
        )

        assert should_merge is False
        assert score < 0.85

    def test_should_merge_custom_threshold(self):
        """Test custom threshold override."""
        disambiguator = EntityDisambiguator(threshold=0.85)

        embedding = [1.0, 0.0, 0.0]
        name1 = "John Smith"
        name2 = "Jon Smith"

        # With high threshold, may not merge
        result1, score1, _ = disambiguator.should_merge(
            embedding, name1, embedding, name2, "PERSON", threshold=0.99
        )

        # With low threshold, should merge
        result2, score2, _ = disambiguator.should_merge(
            embedding, name1, embedding, name2, "PERSON", threshold=0.50
        )

        assert result1 is False or score1 >= 0.99
        assert result2 is True

    def test_should_merge_metrics_tracking(self):
        """Test that merges are tracked in metrics."""
        disambiguator = EntityDisambiguator(threshold=0.50)
        disambiguator.reset_metrics()

        embedding = [1.0, 0.0, 0.0]
        name = "John"

        # Perform merge
        disambiguator.should_merge(embedding, name, embedding, name, "PERSON")

        metrics = disambiguator.get_metrics()
        assert metrics.comparisons == 1
        assert metrics.merges == 1
        assert metrics.merges_by_type.get("PERSON", 0) == 1


# =============================================================================
# Threshold Property Tests
# =============================================================================


class TestThreshold:
    """Test threshold property."""

    def test_default_threshold(self):
        """Test default threshold value."""
        disambiguator = EntityDisambiguator()
        assert disambiguator.threshold == P03_DISAMBIGUATION_THRESHOLD

    def test_set_threshold(self):
        """Test setting threshold."""
        disambiguator = EntityDisambiguator()
        disambiguator.threshold = 0.90
        assert disambiguator.threshold == 0.90

    def test_invalid_threshold_rejected(self):
        """Test invalid threshold values rejected."""
        disambiguator = EntityDisambiguator()

        with pytest.raises(ValueError):
            disambiguator.threshold = 1.5

        with pytest.raises(ValueError):
            disambiguator.threshold = -0.1


# =============================================================================
# Learned Weights Tests
# =============================================================================


class TestLearnedWeights:
    """Test learned weights override defaults."""

    def test_learned_weights_override(self):
        """Test learned weights override defaults."""
        learned = {
            "PERSON": DisambiguationWeights(0.60, 0.40),  # Different from default
        }
        disambiguator = EntityDisambiguator(learned_weights=learned)

        weights = disambiguator.get_weights("PERSON")
        assert weights.embedding_weight == 0.60  # Not default 0.50
        assert weights.string_weight == 0.40

    def test_learned_weights_preserve_others(self):
        """Test learned weights don't affect other types."""
        learned = {
            "PERSON": DisambiguationWeights(0.60, 0.40),
        }
        disambiguator = EntityDisambiguator(learned_weights=learned)

        # CONCEPT should still have defaults
        weights = disambiguator.get_weights("CONCEPT")
        assert weights.embedding_weight == 0.85  # Default
        assert weights.string_weight == 0.15

    def test_set_weights(self):
        """Test setting weights dynamically."""
        disambiguator = EntityDisambiguator()

        new_weights = DisambiguationWeights(0.70, 0.30)
        disambiguator.set_weights("PERSON", new_weights)

        weights = disambiguator.get_weights("PERSON")
        assert weights.embedding_weight == 0.70

    def test_get_all_weights(self):
        """Test getting all weights."""
        disambiguator = EntityDisambiguator()
        all_weights = disambiguator.get_all_weights()

        assert "PERSON" in all_weights
        assert "CONCEPT" in all_weights
        assert isinstance(all_weights["PERSON"], DisambiguationWeights)


# =============================================================================
# Load from Database Tests
# =============================================================================


class TestLoadFromDatabase:
    """Test loading weights from st_learned_weights."""

    @pytest.mark.asyncio
    async def test_load_from_database_empty(self):
        """Test loading from empty database uses defaults."""

        class MockConnection:
            async def fetch(self, query: str, *args) -> list:
                return []

        conn = MockConnection()
        disambiguator = await EntityDisambiguator.load_from_database(conn)

        # Should have default weights
        weights = disambiguator.get_weights("PERSON")
        assert weights.embedding_weight == 0.50

    @pytest.mark.asyncio
    async def test_load_from_database_with_weights(self):
        """Test loading learned weights from database."""

        class MockConnection:
            async def fetch(self, query: str, *args) -> list:
                return [
                    {"param_key": "disambiguation_PERSON_embedding", "current_value": 0.60},
                    {"param_key": "disambiguation_PERSON_string", "current_value": 0.40},
                ]

        conn = MockConnection()
        disambiguator = await EntityDisambiguator.load_from_database(conn)

        # Should have learned weights
        weights = disambiguator.get_weights("PERSON")
        assert weights.embedding_weight == 0.60
        assert weights.string_weight == 0.40

    @pytest.mark.asyncio
    async def test_load_from_database_invalid_weights(self):
        """Test loading invalid weights falls back to defaults."""

        class MockConnection:
            async def fetch(self, query: str, *args) -> list:
                # These don't sum to 1.0
                return [
                    {"param_key": "disambiguation_PERSON_embedding", "current_value": 0.60},
                    {"param_key": "disambiguation_PERSON_string", "current_value": 0.60},
                ]

        conn = MockConnection()
        disambiguator = await EntityDisambiguator.load_from_database(conn)

        # Should fall back to defaults
        weights = disambiguator.get_weights("PERSON")
        assert weights.embedding_weight == 0.50  # Default


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactory:
    """Test factory function."""

    def test_get_entity_disambiguator(self):
        """Test factory creates disambiguator."""
        disambiguator = get_entity_disambiguator()
        assert isinstance(disambiguator, EntityDisambiguator)
        assert disambiguator.threshold == P03_DISAMBIGUATION_THRESHOLD

    def test_get_entity_disambiguator_with_params(self):
        """Test factory with custom parameters."""
        learned = {"PERSON": DisambiguationWeights(0.60, 0.40)}
        disambiguator = get_entity_disambiguator(
            learned_weights=learned,
            threshold=0.90,
        )
        assert disambiguator.threshold == 0.90
        assert disambiguator.get_weights("PERSON").embedding_weight == 0.60


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestUtilityFunctions:
    """Test utility functions."""

    def test_clamp_weight_below_min(self):
        """Test clamping below minimum."""
        clamped = clamp_weight(0.05)
        assert clamped == P03_DISAMBIGUATION_WEIGHT_MIN

    def test_clamp_weight_above_max(self):
        """Test clamping above maximum."""
        clamped = clamp_weight(0.95)
        assert clamped == P03_DISAMBIGUATION_WEIGHT_MAX

    def test_clamp_weight_in_range(self):
        """Test value in range unchanged."""
        clamped = clamp_weight(0.50)
        assert clamped == 0.50

    def test_normalize_weights(self):
        """Test normalizing weights."""
        emb, string = normalize_weights(60, 40)
        assert abs(emb + string - 1.0) < 0.01

    def test_normalize_weights_zero(self):
        """Test normalizing zero weights."""
        emb, string = normalize_weights(0, 0)
        assert emb == 0.5
        assert string == 0.5


# =============================================================================
# Breakdown Tests
# =============================================================================


class TestDisambiguationBreakdown:
    """Test DisambiguationBreakdown."""

    def test_breakdown_to_dict(self):
        """Test serialization to dict."""
        breakdown = DisambiguationBreakdown(
            embedding_similarity=0.9123456,
            string_similarity=0.8765432,
            embedding_weight=0.50,
            string_weight=0.50,
            combined_score=0.8944444,
            entity_type="PERSON",
            string_algorithm_used="levenshtein",
        )
        d = breakdown.to_dict()

        assert d["embedding_similarity"] == 0.9123
        assert d["string_similarity"] == 0.8765
        assert d["combined_score"] == 0.8944
        assert d["entity_type"] == "PERSON"
        assert d["string_algorithm_used"] == "levenshtein"


# =============================================================================
# Metrics Tests
# =============================================================================


class TestMetrics:
    """Test metrics tracking."""

    def test_metrics_reset(self):
        """Test metrics reset."""
        disambiguator = EntityDisambiguator()

        embedding = [1.0, 0.0, 0.0]
        disambiguator.compute_similarity(embedding, "test", embedding, "test", "PERSON")

        disambiguator.reset_metrics()
        metrics = disambiguator.get_metrics()

        assert metrics.comparisons == 0
        assert metrics.merges == 0

    def test_algorithm_wins_tracking(self):
        """Test tracking which algorithm produces best score."""
        disambiguator = EntityDisambiguator()
        disambiguator.reset_metrics()

        embedding = [1.0, 0.0, 0.0]

        # Exact match
        disambiguator.compute_similarity(embedding, "John", embedding, "John", "PERSON")

        # Reordered (token_sort should win)
        disambiguator.compute_similarity(embedding, "Smith John", embedding, "John Smith", "PERSON")

        metrics = disambiguator.get_metrics()
        assert metrics.comparisons == 2
        assert "exact" in metrics.algorithm_wins or "token_sort" in metrics.algorithm_wins
