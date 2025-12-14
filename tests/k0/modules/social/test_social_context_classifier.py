"""
Tests for M07.3: social.social_context_classifier - Social Context Classification

Test Coverage:
- Dunbar layer classification
- Relationship strength scoring
- Intimacy level determination
- Mixed group handling (family + friends)
- Edge cases (solo, empty participants)
- Performance targets (<5ms P95)

Research: Dunbar (1992), Granovetter (1973), Hamilton (1964)
"""

import pytest

from k0.modules.social.social_context_classifier import (
    DunbarLayer,
    IntimacyLevel,
    SocialContextClassifier,
    SocialContextResult,
    SocialContextType,
    calculate_tie_strength,
    classify_dunbar_layer,
    classify_social_context,
    get_classifier,
    get_relationship_strength,
    get_relationship_strength_for_role,
)

# ============================================================================
# Test: Relationship Strength Scoring
# ============================================================================


class TestRelationshipStrength:
    """Tests for relationship strength scoring based on Hamilton's kin selection."""

    def test_self_highest_strength(self):
        """Test that SELF has highest strength (1.0)."""
        assert get_relationship_strength("SELF") == 1.0

    def test_spouse_very_high_strength(self):
        """Test that SPOUSE has very high strength."""
        strength = get_relationship_strength("SPOUSE")
        assert strength >= 0.85
        assert strength <= 1.0

    def test_nuclear_family_high_strength(self):
        """Test that nuclear family roles have high strength."""
        nuclear = ["SPOUSE", "CHILD", "PARENT"]
        for role in nuclear:
            strength = get_relationship_strength(role)
            assert strength >= 0.8, f"{role} should have high strength"

    def test_extended_family_medium_strength(self):
        """Test that extended family has medium strength."""
        extended = ["SIBLING", "CAREGIVER", "GRANDPARENT"]
        for role in extended:
            strength = get_relationship_strength(role)
            assert 0.4 <= strength <= 0.8, f"{role} should have medium strength"

    def test_friend_moderate_strength(self):
        """Test that friends have moderate strength."""
        assert 0.2 <= get_relationship_strength("FRIEND") <= 0.5

    def test_other_low_strength(self):
        """Test that OTHER/unknown has low strength."""
        strength = get_relationship_strength("OTHER")
        assert strength <= 0.2

    def test_unknown_role_defaults_to_low(self):
        """Test that unknown roles default to low strength."""
        strength = get_relationship_strength("UNKNOWN_ROLE")
        assert strength <= 0.2

    def test_case_insensitive(self):
        """Test that role matching is case-insensitive."""
        assert get_relationship_strength("spouse") == get_relationship_strength("SPOUSE")


# ============================================================================
# Test: Dunbar Layer Classification
# ============================================================================


class TestDunbarLayers:
    """Tests for Dunbar's social layer classification."""

    def test_intimate_layer_small_high_strength(self):
        """Test intimate layer for small, high-strength groups."""
        layer = classify_dunbar_layer(group_size=3, avg_strength=0.8)
        assert layer == DunbarLayer.INTIMATE

    def test_close_layer_medium_size(self):
        """Test close layer for medium-sized groups."""
        layer = classify_dunbar_layer(group_size=10, avg_strength=0.5)
        assert layer == DunbarLayer.CLOSE

    def test_friends_layer_larger_group(self):
        """Test friends layer for larger groups."""
        layer = classify_dunbar_layer(group_size=30, avg_strength=0.3)
        assert layer == DunbarLayer.FRIENDS

    def test_acquaintances_layer(self):
        """Test acquaintances layer for large groups."""
        layer = classify_dunbar_layer(group_size=100, avg_strength=0.2)
        assert layer == DunbarLayer.ACQUAINTANCES

    def test_beyond_layer_very_large(self):
        """Test beyond layer for very large groups (>150)."""
        layer = classify_dunbar_layer(group_size=200, avg_strength=0.1)
        assert layer == DunbarLayer.BEYOND

    def test_small_group_low_strength_not_intimate(self):
        """Test that small groups with low strength aren't intimate."""
        layer = classify_dunbar_layer(group_size=3, avg_strength=0.2)
        assert layer != DunbarLayer.INTIMATE


# ============================================================================
# Test: Social Context Classifier
# ============================================================================


class TestSocialContextClassifier:
    """Tests for the main social context classifier."""

    @pytest.fixture
    def classifier(self):
        return SocialContextClassifier()

    def test_solo_event_no_participants(self, classifier):
        """Test solo classification with no participants."""
        result = classifier.classify(
            participants=[],
            participant_roles={},
            actor_id="actor_1",
        )

        assert result.context == SocialContextType.SOLO
        assert result.intimacy == IntimacyLevel.LOW
        assert result.group_size == 1

    def test_solo_event_actor_only(self, classifier):
        """Test solo classification with only actor in participants."""
        result = classifier.classify(
            participants=["actor_1"],
            participant_roles={"actor_1": "SELF"},
            actor_id="actor_1",
        )

        assert result.context == SocialContextType.SOLO

    def test_nuclear_family_spouse(self, classifier):
        """Test nuclear family with spouse."""
        result = classifier.classify(
            participants=["actor_1", "person_spouse"],
            participant_roles={"actor_1": "SELF", "person_spouse": "SPOUSE"},
            actor_id="actor_1",
        )

        assert result.context == SocialContextType.NUCLEAR_FAMILY
        assert result.intimacy == IntimacyLevel.HIGH

    def test_nuclear_family_with_children(self, classifier):
        """Test nuclear family with children."""
        result = classifier.classify(
            participants=["actor_1", "person_spouse", "person_child1", "person_child2"],
            participant_roles={
                "actor_1": "SELF",
                "person_spouse": "SPOUSE",
                "person_child1": "CHILD",
                "person_child2": "CHILD",
            },
            actor_id="actor_1",
        )

        assert result.context == SocialContextType.NUCLEAR_FAMILY
        assert result.intimacy == IntimacyLevel.HIGH
        assert result.group_size == 4

    def test_extended_family_siblings(self, classifier):
        """Test extended family with siblings."""
        result = classifier.classify(
            participants=["actor_1", "person_brother", "person_sister"],
            participant_roles={
                "actor_1": "SELF",
                "person_brother": "SIBLING",
                "person_sister": "SIBLING",
            },
            actor_id="actor_1",
        )

        assert result.context == SocialContextType.EXTENDED_FAMILY
        assert result.intimacy == IntimacyLevel.MEDIUM

    def test_friends_group(self, classifier):
        """Test friends group (no family)."""
        result = classifier.classify(
            participants=["actor_1", "friend_1", "friend_2"],
            participant_roles={
                "actor_1": "SELF",
                "friend_1": "OTHER",
                "friend_2": "OTHER",
            },
            actor_id="actor_1",
        )

        # Should be FRIENDS or ACQUAINTANCES based on strength
        assert result.context in (
            SocialContextType.FRIENDS,
            SocialContextType.ACQUAINTANCES,
        )
        assert result.intimacy == IntimacyLevel.LOW

    def test_mixed_group_mostly_family(self, classifier):
        """Test mixed group with mostly family members."""
        result = classifier.classify(
            participants=["actor_1", "person_spouse", "person_child", "friend_1"],
            participant_roles={
                "actor_1": "SELF",
                "person_spouse": "SPOUSE",
                "person_child": "CHILD",
                "friend_1": "OTHER",
            },
            actor_id="actor_1",
        )

        # 2/3 family = 66%, classified as MIXED (threshold is 70% for pure family)
        # But still has nuclear family members present
        assert result.context in (SocialContextType.NUCLEAR_FAMILY, SocialContextType.MIXED)
        assert result.breakdown["nuclear_family_present"] is True
        assert result.breakdown["non_family_count"] == 1

    def test_mixed_group_mostly_friends(self, classifier):
        """Test mixed group with mostly friends."""
        result = classifier.classify(
            participants=["actor_1", "person_sibling", "friend_1", "friend_2", "friend_3"],
            participant_roles={
                "actor_1": "SELF",
                "person_sibling": "SIBLING",
                "friend_1": "OTHER",
                "friend_2": "OTHER",
                "friend_3": "OTHER",
            },
            actor_id="actor_1",
        )

        # 1/4 family = 25%, mostly friends
        assert result.family_ratio < 0.5


class TestSocialContextResult:
    """Tests for SocialContextResult dataclass."""

    def test_result_contains_all_fields(self):
        """Test that result contains expected fields."""
        classifier = SocialContextClassifier()
        result = classifier.classify(
            participants=["a", "b"],
            participant_roles={"a": "SELF", "b": "SPOUSE"},
            actor_id="a",
        )

        assert hasattr(result, "context")
        assert hasattr(result, "intimacy")
        assert hasattr(result, "dunbar_layer")
        assert hasattr(result, "group_size")
        assert hasattr(result, "average_relationship_strength")
        assert hasattr(result, "family_ratio")
        assert hasattr(result, "explanation")
        assert hasattr(result, "breakdown")

    def test_breakdown_contains_counts(self):
        """Test that breakdown contains role counts."""
        classifier = SocialContextClassifier()
        result = classifier.classify(
            participants=["a", "b", "c"],
            participant_roles={"a": "SELF", "b": "SPOUSE", "c": "OTHER"},
            actor_id="a",
        )

        breakdown = result.breakdown
        assert "nuclear_family_present" in breakdown
        assert "family_count" in breakdown
        assert "non_family_count" in breakdown
        assert "roles_distribution" in breakdown


# ============================================================================
# Test: Tie Strength Calculation (Granovetter)
# ============================================================================


class TestTieStrength:
    """Tests for Granovetter's tie strength calculation."""

    def test_high_frequency_high_strength(self):
        """Test that high frequency increases tie strength."""
        strength = calculate_tie_strength(
            frequency=25,
            recency_days=1,
            emotional_intensity=0.8,
            reciprocity=True,
        )
        assert strength >= 0.7

    def test_low_frequency_lower_strength(self):
        """Test that low frequency decreases tie strength."""
        high_freq = calculate_tie_strength(
            frequency=20, recency_days=1, emotional_intensity=0.5, reciprocity=True
        )
        low_freq = calculate_tie_strength(
            frequency=2, recency_days=1, emotional_intensity=0.5, reciprocity=True
        )
        assert high_freq > low_freq

    def test_recency_decay(self):
        """Test that recent interactions have higher strength."""
        recent = calculate_tie_strength(
            frequency=10, recency_days=1, emotional_intensity=0.5, reciprocity=True
        )
        old = calculate_tie_strength(
            frequency=10, recency_days=30, emotional_intensity=0.5, reciprocity=True
        )
        assert recent > old

    def test_reciprocity_bonus(self):
        """Test that reciprocal relationships have higher strength."""
        reciprocal = calculate_tie_strength(
            frequency=10, recency_days=5, emotional_intensity=0.5, reciprocity=True
        )
        one_way = calculate_tie_strength(
            frequency=10, recency_days=5, emotional_intensity=0.5, reciprocity=False
        )
        assert reciprocal > one_way

    def test_strength_bounded_zero_to_one(self):
        """Test that strength is always between 0 and 1."""
        # Very high values
        strength = calculate_tie_strength(
            frequency=100, recency_days=0, emotional_intensity=1.0, reciprocity=True
        )
        assert 0.0 <= strength <= 1.0

        # Very low values
        strength = calculate_tie_strength(
            frequency=0, recency_days=365, emotional_intensity=0.0, reciprocity=False
        )
        assert 0.0 <= strength <= 1.0


# ============================================================================
# Test: Module-Level API
# ============================================================================


class TestModuleAPI:
    """Tests for module-level convenience functions."""

    def test_get_classifier_singleton(self):
        """Test that get_classifier returns singleton."""
        c1 = get_classifier()
        c2 = get_classifier()
        assert c1 is c2

    def test_classify_social_context_function(self):
        """Test convenience function."""
        result = classify_social_context(
            participants=["a", "b"],
            participant_roles={"a": "SELF", "b": "SPOUSE"},
            actor_id="a",
        )
        assert isinstance(result, SocialContextResult)
        assert result.context == SocialContextType.NUCLEAR_FAMILY

    def test_get_relationship_strength_for_role(self):
        """Test role strength lookup function."""
        strength = get_relationship_strength_for_role("SPOUSE")
        assert strength >= 0.85


# ============================================================================
# Test: Performance
# ============================================================================


class TestPerformance:
    """Performance tests for social context classifier."""

    def test_classification_latency(self):
        """Test that classification is fast (<5ms P95)."""
        import time

        classifier = SocialContextClassifier()
        participants = ["a", "b", "c", "d", "e"]
        roles = {"a": "SELF", "b": "SPOUSE", "c": "CHILD", "d": "SIBLING", "e": "OTHER"}

        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            classifier.classify(
                participants=participants,
                participant_roles=roles,
                actor_id="a",
            )
            latencies.append((time.perf_counter() - start) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        assert p95 < 5, f"Classification P95 latency {p95}ms exceeds 5ms target"

    def test_large_group_classification(self):
        """Test classification with large group (20 participants)."""
        import time

        classifier = SocialContextClassifier()
        participants = [f"person_{i}" for i in range(20)]
        roles = {p: "OTHER" for p in participants}
        roles["person_0"] = "SELF"
        roles["person_1"] = "SPOUSE"

        start = time.perf_counter()
        result = classifier.classify(
            participants=participants,
            participant_roles=roles,
            actor_id="person_0",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 10, f"Large group classification took {elapsed_ms}ms"
        assert result.group_size == 20


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_participant_roles(self):
        """Test handling of empty participant roles dict."""
        classifier = SocialContextClassifier()
        result = classifier.classify(
            participants=["a", "b"],
            participant_roles={},  # Empty roles
            actor_id="a",
        )
        # Should handle gracefully
        assert result is not None

    def test_actor_not_in_participants(self):
        """Test when actor is not in participant list."""
        classifier = SocialContextClassifier()
        result = classifier.classify(
            participants=["b", "c"],  # Actor 'a' not included
            participant_roles={"b": "SPOUSE", "c": "CHILD"},
            actor_id="a",
        )
        # Should still classify based on roles
        assert result is not None

    def test_duplicate_participants(self):
        """Test handling of duplicate participants."""
        classifier = SocialContextClassifier()
        result = classifier.classify(
            participants=["a", "b", "b"],  # Duplicate 'b'
            participant_roles={"a": "SELF", "b": "SPOUSE"},
            actor_id="a",
        )
        assert result is not None
