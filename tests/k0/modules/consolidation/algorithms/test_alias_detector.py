"""
Tests for R4 Alias Detector — Entity Coreference and Alias Detection.

GAP-004: Entity Alias Merging Missing
Spec Reference: MEMORY_LAYER_GAPS_FIX_PLAN.md §GAP-004

Tests cover:
1. FirstNameDatabase - nickname lookups
2. FamilyRoleDatabase - kinship term lookups
3. AliasScorer - multi-signal scoring
4. AliasDetector - end-to-end alias detection
"""

import numpy as np

from k0.modules.consolidation.algorithms.alias_detector import (
    AliasCandidate,
    AliasDetector,
    AliasScorer,
    AliasType,
    EntityInfo,
    FamilyRoleDatabase,
    FirstNameDatabase,
)

# =============================================================================
# FirstNameDatabase Tests
# =============================================================================


class TestFirstNameDatabase:
    """Tests for first-name nickname database."""

    def test_get_nicknames_for_robert(self):
        """Robert should have multiple nicknames."""
        nicknames = FirstNameDatabase.get_nicknames("Robert")
        assert "Bob" in nicknames
        assert "Rob" in nicknames
        assert "Bobby" in nicknames

    def test_get_nicknames_for_elizabeth(self):
        """Elizabeth should have multiple nicknames."""
        nicknames = FirstNameDatabase.get_nicknames("Elizabeth")
        assert "Liz" in nicknames
        assert "Beth" in nicknames
        assert "Betty" in nicknames

    def test_get_nicknames_unknown_name_returns_empty(self):
        """Unknown name should return empty list."""
        nicknames = FirstNameDatabase.get_nicknames("Xyzzy")
        assert nicknames == []

    def test_get_formal_names_for_bob(self):
        """Bob should map to Robert."""
        formal_names = FirstNameDatabase.get_formal_names("Bob")
        assert "Robert" in formal_names

    def test_get_formal_names_for_bill(self):
        """Bill should map to William."""
        formal_names = FirstNameDatabase.get_formal_names("Bill")
        assert "William" in formal_names

    def test_are_aliases_bob_robert(self):
        """Bob and Robert should be aliases."""
        assert FirstNameDatabase.are_aliases("Bob", "Robert") is True
        assert FirstNameDatabase.are_aliases("Robert", "Bob") is True

    def test_are_aliases_bill_william(self):
        """Bill and William should be aliases."""
        assert FirstNameDatabase.are_aliases("Bill", "William") is True
        assert FirstNameDatabase.are_aliases("William", "Bill") is True

    def test_are_aliases_liz_elizabeth(self):
        """Liz and Elizabeth should be aliases."""
        assert FirstNameDatabase.are_aliases("Liz", "Elizabeth") is True
        assert FirstNameDatabase.are_aliases("Elizabeth", "Liz") is True

    def test_are_aliases_same_name_returns_false(self):
        """Same name should not be considered alias."""
        assert FirstNameDatabase.are_aliases("Bob", "Bob") is False
        assert FirstNameDatabase.are_aliases("Robert", "Robert") is False

    def test_are_aliases_unrelated_names_returns_false(self):
        """Unrelated names should not be aliases."""
        assert FirstNameDatabase.are_aliases("Bob", "Elizabeth") is False
        assert FirstNameDatabase.are_aliases("John", "Mary") is False

    def test_are_aliases_case_insensitive(self):
        """Nickname matching should be case-insensitive."""
        assert FirstNameDatabase.are_aliases("bob", "Robert") is True
        assert FirstNameDatabase.are_aliases("BOB", "robert") is True

    def test_are_aliases_two_nicknames_same_formal(self):
        """Two nicknames of same formal name should be aliases."""
        # Both Bob and Bobby are nicknames of Robert
        assert FirstNameDatabase.are_aliases("Bob", "Bobby") is True

    def test_get_canonical_name_for_nickname(self):
        """Nickname should return formal name."""
        assert FirstNameDatabase.get_canonical_name("Bob") == "Robert"
        assert FirstNameDatabase.get_canonical_name("Bill") == "William"

    def test_get_canonical_name_for_formal_returns_same(self):
        """Formal name should return itself."""
        assert FirstNameDatabase.get_canonical_name("Robert") == "Robert"


# =============================================================================
# FamilyRoleDatabase Tests
# =============================================================================


class TestFamilyRoleDatabase:
    """Tests for family role nickname database."""

    def test_are_aliases_mom_mother(self):
        """Mom and Mother should be aliases."""
        assert FamilyRoleDatabase.are_aliases("mom", "mother") is True
        assert FamilyRoleDatabase.are_aliases("Mother", "Mom") is True

    def test_are_aliases_dad_father(self):
        """Dad and Father should be aliases."""
        assert FamilyRoleDatabase.are_aliases("dad", "father") is True
        assert FamilyRoleDatabase.are_aliases("daddy", "father") is True

    def test_are_aliases_grandma_grandmother(self):
        """Grandma and Grandmother should be aliases."""
        assert FamilyRoleDatabase.are_aliases("grandma", "grandmother") is True
        assert FamilyRoleDatabase.are_aliases("granny", "grandmother") is True
        assert FamilyRoleDatabase.are_aliases("nana", "grandmother") is True

    def test_are_aliases_multiple_informal_forms(self):
        """Multiple informal forms of same role should be aliases."""
        assert FamilyRoleDatabase.are_aliases("mom", "mama") is True
        assert FamilyRoleDatabase.are_aliases("mommy", "ma") is True

    def test_are_aliases_same_role_returns_false(self):
        """Same role should not be alias."""
        assert FamilyRoleDatabase.are_aliases("mother", "mother") is False

    def test_are_aliases_different_roles_returns_false(self):
        """Different roles should not be aliases."""
        assert FamilyRoleDatabase.are_aliases("mom", "dad") is False
        assert FamilyRoleDatabase.are_aliases("grandmother", "grandfather") is False

    def test_get_canonical_for_informal(self):
        """Informal term should return canonical form."""
        assert FamilyRoleDatabase.get_canonical("mom") == "mother"
        assert FamilyRoleDatabase.get_canonical("daddy") == "father"

    def test_get_canonical_for_formal_returns_same(self):
        """Formal term should return itself."""
        assert FamilyRoleDatabase.get_canonical("mother") == "mother"


# =============================================================================
# AliasScorer Tests
# =============================================================================


class TestAliasScorer:
    """Tests for multi-signal alias scoring."""

    def test_string_similarity_exact_match(self):
        """Exact match should return score close to 1.0."""
        scorer = AliasScorer()
        score, algo = scorer.compute_string_similarity("John", "John")
        assert score >= 0.99

    def test_string_similarity_similar_names(self):
        """Similar names should have high score."""
        scorer = AliasScorer()
        score, algo = scorer.compute_string_similarity("John", "Johnny")
        assert score >= 0.7

    def test_string_similarity_different_names(self):
        """Different names should have low score."""
        scorer = AliasScorer()
        score, algo = scorer.compute_string_similarity("John", "Elizabeth")
        assert score < 0.5

    def test_string_similarity_case_insensitive(self):
        """String similarity should be case-insensitive."""
        scorer = AliasScorer()
        score1, _ = scorer.compute_string_similarity("JOHN", "john")
        score2, _ = scorer.compute_string_similarity("John", "John")
        assert abs(score1 - score2) < 0.01

    def test_embedding_similarity_identical(self):
        """Identical embeddings should have similarity 1.0."""
        scorer = AliasScorer()
        embedding = np.array([1.0, 0.0, 0.0])
        score = scorer.compute_embedding_similarity(embedding, embedding.copy())
        assert abs(score - 1.0) < 0.001

    def test_embedding_similarity_orthogonal(self):
        """Orthogonal embeddings should have similarity 0.0."""
        scorer = AliasScorer()
        e1 = np.array([1.0, 0.0, 0.0])
        e2 = np.array([0.0, 1.0, 0.0])
        score = scorer.compute_embedding_similarity(e1, e2)
        assert abs(score) < 0.001

    def test_embedding_similarity_none_returns_zero(self):
        """None embeddings should return 0.0."""
        scorer = AliasScorer()
        e1 = np.array([1.0, 0.0, 0.0])
        assert scorer.compute_embedding_similarity(e1, None) == 0.0
        assert scorer.compute_embedding_similarity(None, e1) == 0.0
        assert scorer.compute_embedding_similarity(None, None) == 0.0

    def test_check_nickname_match_true(self):
        """Known nickname pairs should match."""
        scorer = AliasScorer()
        assert scorer.check_nickname_match("Bob", "Robert", "PERSON") is True
        assert scorer.check_nickname_match("mom", "mother", "FAMILY_MEMBER") is True

    def test_check_nickname_match_false(self):
        """Unrelated names should not match."""
        scorer = AliasScorer()
        assert scorer.check_nickname_match("Bob", "Elizabeth", "PERSON") is False

    def test_co_occurrence_no_overlap(self):
        """No event overlap should give high exclusion score."""
        scorer = AliasScorer()
        events1 = ["e1", "e2", "e3"]
        events2 = ["e4", "e5", "e6"]
        score = scorer.compute_co_occurrence_score(events1, events2)
        assert score == 1.0  # Never co-occur

    def test_co_occurrence_full_overlap(self):
        """Full overlap should give low exclusion score."""
        scorer = AliasScorer()
        events1 = ["e1", "e2", "e3"]
        events2 = ["e1", "e2", "e3"]
        score = scorer.compute_co_occurrence_score(events1, events2)
        assert score == 0.0  # Always co-occur

    def test_co_occurrence_partial_overlap(self):
        """Partial overlap should give intermediate score."""
        scorer = AliasScorer()
        events1 = ["e1", "e2", "e3"]
        events2 = ["e2", "e3", "e4"]
        score = scorer.compute_co_occurrence_score(events1, events2)
        # Overlap = 2, Union = 4, Jaccard = 0.5, Exclusion = 0.5
        assert 0.4 < score < 0.6

    def test_combined_score_with_nickname_boost(self):
        """Nickname match should boost combined score."""
        scorer = AliasScorer()

        # Without nickname
        score1 = scorer.compute_combined_score(
            string_score=0.7,
            embedding_score=0.8,
            nickname_match=False,
            co_occurrence_score=0.5,
        )

        # With nickname
        score2 = scorer.compute_combined_score(
            string_score=0.7,
            embedding_score=0.8,
            nickname_match=True,
            co_occurrence_score=0.5,
        )

        assert score2 > score1


# =============================================================================
# AliasDetector Tests
# =============================================================================


class TestAliasDetector:
    """Tests for end-to-end alias detection."""

    def test_detect_empty_list_returns_empty(self):
        """Empty entity list should return empty candidates."""
        detector = AliasDetector()
        result = detector.detect([])
        assert result == []

    def test_detect_single_entity_returns_empty(self):
        """Single entity should return empty candidates."""
        detector = AliasDetector()
        entity = EntityInfo(
            entity_id="e1",
            canonical_name="John",
            entity_type="PERSON",
            observation_count=5,
        )
        result = detector.detect([entity])
        assert result == []

    def test_detect_bob_robert_as_aliases(self):
        """Bob and Robert should be detected as aliases."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Bob",
                entity_type="PERSON",
                observation_count=10,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Robert",
                entity_type="PERSON",
                observation_count=5,
            ),
        ]

        result = detector.detect(entities)
        assert len(result) >= 1

        candidate = result[0]
        assert candidate.nickname_match is True
        assert candidate.alias_type == AliasType.NICKNAME

    def test_detect_mom_mother_as_aliases(self):
        """Mom and Mother should be detected as aliases."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Mom",
                entity_type="FAMILY_MEMBER",
                observation_count=20,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Mother",
                entity_type="FAMILY_MEMBER",
                observation_count=5,
            ),
        ]

        result = detector.detect(entities)
        assert len(result) >= 1

        candidate = result[0]
        assert candidate.nickname_match is True
        assert candidate.alias_type == AliasType.FAMILY_ROLE

    def test_detect_different_types_no_aliases(self):
        """Different entity types should not be detected as aliases."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Apple",
                entity_type="ORGANIZATION",
                observation_count=10,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Apple",
                entity_type="OBJECT",
                observation_count=10,
            ),
        ]

        result = detector.detect(entities)
        # Should not match because different types
        assert len(result) == 0

    def test_detect_unrelated_names_no_aliases(self):
        """Completely unrelated names should not be aliases."""
        detector = AliasDetector(threshold=0.7, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="John",
                entity_type="PERSON",
                observation_count=10,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Elizabeth",
                entity_type="PERSON",
                observation_count=10,
            ),
        ]

        result = detector.detect(entities)
        assert len(result) == 0

    def test_detect_similar_spellings(self):
        """Similar spellings should be detected as aliases."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Cathy",
                entity_type="PERSON",
                observation_count=10,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Kathy",
                entity_type="PERSON",
                observation_count=5,
            ),
        ]

        result = detector.detect(entities)
        # High string similarity should trigger detection
        # Cathy/Kathy are in nickname database, so it's detected as NICKNAME
        assert len(result) >= 1
        assert result[0].alias_type in (AliasType.SPELLING_VARIANT, AliasType.NICKNAME)

    def test_detect_with_embeddings(self):
        """Similar embeddings should boost alias score."""
        # Use a very low threshold to ensure we see the embedding effect
        detector = AliasDetector(threshold=0.3, min_observations=1)

        # Use deterministic embeddings for reliable test
        np.random.seed(42)
        embedding1 = np.random.randn(768)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        # Create very similar embedding by adding minimal noise
        embedding2 = embedding1.copy()
        embedding2[:10] = embedding2[:10] + 0.01  # Tiny change to first 10 dims
        embedding2 = embedding2 / np.linalg.norm(embedding2)

        # Use names with high string similarity
        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="John Smith",
                entity_type="PERSON",
                observation_count=10,
                embedding=embedding1,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="John Smyth",
                entity_type="PERSON",
                observation_count=5,
                embedding=embedding2,
            ),
        ]

        result = detector.detect(entities)
        assert len(result) >= 1
        # These nearly-identical embeddings should have high similarity
        assert result[0].embedding_score > 0.99

    def test_detect_recommends_primary_by_observation_count(self):
        """Higher observation count should be recommended as primary."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Bob",
                entity_type="PERSON",
                observation_count=5,  # Fewer observations
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Robert",
                entity_type="PERSON",
                observation_count=20,  # More observations
            ),
        ]

        result = detector.detect(entities)
        assert len(result) >= 1

        candidate = result[0]
        # Robert (e2) should be primary due to higher observation count
        assert candidate.recommended_primary == "e2"
        assert "Bob" in candidate.recommended_aliases

    def test_detect_min_observations_filter(self):
        """Entities below min_observations should be filtered."""
        detector = AliasDetector(threshold=0.5, min_observations=5)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Bob",
                entity_type="PERSON",
                observation_count=3,  # Below threshold
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Robert",
                entity_type="PERSON",
                observation_count=10,
            ),
        ]

        result = detector.detect(entities)
        # e1 should be filtered out, so no pairs to compare
        assert len(result) == 0

    def test_detect_from_dicts(self):
        """detect_from_dicts should work with dictionary input."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entity_dicts = [
            {
                "entity_id": "e1",
                "canonical_name": "Bob",
                "entity_type": "PERSON",
                "observation_count": 10,
            },
            {
                "entity_id": "e2",
                "canonical_name": "Robert",
                "entity_type": "PERSON",
                "observation_count": 5,
            },
        ]

        result = detector.detect_from_dicts(entity_dicts)
        assert len(result) >= 1
        assert result[0].nickname_match is True

    def test_detect_multiple_alias_groups(self):
        """Should detect multiple alias groups."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Bob",
                entity_type="PERSON",
                observation_count=10,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Robert",
                entity_type="PERSON",
                observation_count=5,
            ),
            EntityInfo(
                entity_id="e3",
                canonical_name="Mom",
                entity_type="FAMILY_MEMBER",
                observation_count=20,
            ),
            EntityInfo(
                entity_id="e4",
                canonical_name="Mother",
                entity_type="FAMILY_MEMBER",
                observation_count=10,
            ),
        ]

        result = detector.detect(entities)
        # Should find at least 2 alias pairs
        assert len(result) >= 2

    def test_candidate_to_dict(self):
        """AliasCandidate should serialize to dict."""
        candidate = AliasCandidate(
            entity1_id="e1",
            entity1_name="Bob",
            entity2_id="e2",
            entity2_name="Robert",
            entity_type="PERSON",
            alias_type=AliasType.NICKNAME,
            combined_score=0.85,
            string_score=0.65,
            embedding_score=0.90,
            nickname_match=True,
            co_occurrence_score=0.80,
            recommended_primary="e2",
            recommended_aliases=["Bob"],
        )

        d = candidate.to_dict()
        assert d["entity1_id"] == "e1"
        assert d["alias_type"] == "NICKNAME"
        assert d["nickname_match"] is True

    def test_metrics_tracked(self):
        """Detection metrics should be tracked."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Bob",
                entity_type="PERSON",
                observation_count=10,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Robert",
                entity_type="PERSON",
                observation_count=5,
            ),
        ]

        detector.detect(entities)

        metrics = detector.metrics
        assert metrics.entities_analyzed == 2
        assert metrics.pairs_compared == 1
        assert metrics.candidates_found >= 1
        assert metrics.nickname_matches >= 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestAliasDetectorIntegration:
    """Integration tests for alias detection scenarios."""

    def test_family_member_disambiguation(self):
        """Test disambiguation of family member references."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="Mom",
                entity_type="FAMILY_MEMBER",
                observation_count=45,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Mother",
                entity_type="FAMILY_MEMBER",
                observation_count=12,
            ),
            EntityInfo(
                entity_id="e3",
                canonical_name="Mama",
                entity_type="FAMILY_MEMBER",
                observation_count=8,
            ),
        ]

        result = detector.detect(entities)

        # Should find at least 2 pairs (Mom-Mother, Mom-Mama, possibly Mother-Mama)
        assert len(result) >= 2

        # All should be family role matches
        for candidate in result:
            assert candidate.nickname_match is True
            assert candidate.alias_type == AliasType.FAMILY_ROLE

    def test_person_nickname_resolution(self):
        """Test resolution of person nicknames."""
        detector = AliasDetector(threshold=0.5, min_observations=1)

        entities = [
            EntityInfo(
                entity_id="e1",
                canonical_name="William",
                entity_type="PERSON",
                observation_count=30,
            ),
            EntityInfo(
                entity_id="e2",
                canonical_name="Bill",
                entity_type="PERSON",
                observation_count=25,
            ),
            EntityInfo(
                entity_id="e3",
                canonical_name="Billy",
                entity_type="PERSON",
                observation_count=5,
            ),
        ]

        result = detector.detect(entities)

        # Should find William-Bill, William-Billy, possibly Bill-Billy
        assert len(result) >= 2

        # All should be nickname matches
        for candidate in result:
            assert candidate.nickname_match is True
