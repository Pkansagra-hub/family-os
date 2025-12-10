"""
Unit tests for ZeroShotActivityClassifier

Tests:
- Rule-based keyword classification (20+ activity types)
- Multi-label detection (e.g., "birthday dinner")
- Confidence scoring
- Legacy activity mapping
- Performance (<5ms P95 for rule-based)
- Edge cases (empty input, special characters)

Research Foundation:
- Yin et al. (2019) - Benchmarking Zero-shot Text Classification
- Lewis et al. (2020) - BART: Denoising Sequence-to-Sequence Pre-training
"""

import time


class TestActivityClassification:
    """Tests for ActivityClassification dataclass."""

    def test_create_classification(self):
        """Test creating ActivityClassification."""
        from k0.modules.activity.zero_shot_classifier import (
            ActivityClassification,
            ClassificationTier,
        )

        result = ActivityClassification(
            primary_activity="meal",
            confidence=0.85,
            secondary_activities=("celebration",),
            is_multi_activity=True,
        )

        assert result.primary_activity == "meal"
        assert result.confidence == 0.85
        assert result.secondary_activities == ("celebration",)
        assert result.is_multi_activity is True
        assert result.classification_tier == ClassificationTier.RULE_BASED.value

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from k0.modules.activity.zero_shot_classifier import ActivityClassification

        result = ActivityClassification(
            primary_activity="exercise",
            confidence=0.9,
        )

        d = result.to_dict()
        assert d["primary_activity"] == "exercise"
        assert d["confidence"] == 0.9
        assert isinstance(d["secondary_activities"], list)


class TestRuleBasedClassification:
    """Tests for rule-based keyword classification."""

    def test_meal_classification(self):
        """Test meal activity detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        # Various meal keywords
        texts = [
            "Had breakfast with the family",
            "Went out for lunch at the cafe",
            "Dinner was delicious",
            "We ate at Olive Garden",
            "Cooking a special recipe",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "meal", f"Failed for: {text}"
            assert result.confidence >= 0.5

    def test_celebration_classification(self):
        """Test celebration/milestone detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Happy birthday celebration!",
            "Our 10th anniversary dinner",
            "Graduation ceremony today",
            "Wedding was beautiful",
            "Got a promotion at work!",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "celebration", f"Failed for: {text}"

    def test_exercise_classification(self):
        """Test exercise/fitness detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        # Core exercise keywords
        texts = [
            "Great workout at the gym",
            "Yoga class was relaxing",
            "Swimming laps in the pool",
            "Fitness training session",
            "Cardio workout this morning",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "exercise", f"Failed for: {text}"

    def test_outdoor_recreation_classification(self):
        """Test outdoor recreation detection (may overlap with exercise)."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        # These match outdoor recreation before exercise
        texts = [
            "Morning run in the park",
            "Went hiking on the trail",
            "Nature walk in the forest",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity in [
                "outdoor_recreation",
                "exercise",
            ], f"Failed for: {text}"

    def test_work_meeting_classification(self):
        """Test work/meeting detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Team meeting this morning",
            "Client presentation went well",
            "Working on the project deadline",
            "1:1 with my manager",
            "Conference call with stakeholders",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "work_meeting", f"Failed for: {text}"

    def test_social_event_classification(self):
        """Test social event detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        # Core social event keywords
        texts = [
            "Party at Sarah's house",
            "BBQ with the neighbors",
            "Hangout at the cafe",
            "Potluck gathering with friends",
            "Get-together at the park",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "social_event", f"Failed for: {text}"

    def test_game_night_is_entertainment(self):
        """Test game night classified as entertainment (multi-activity)."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Game night with friends")
        # Game matches entertainment first; multi-activity pattern adds social
        assert result.primary_activity in ["entertainment", "social_event"]

    def test_family_gathering_classification(self):
        """Test family gathering detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        # Family gathering keywords (without meal keywords)
        texts = [
            "Family reunion at grandma's",
            "Holiday gathering with relatives",
            "Family time at the park",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "family_gathering", f"Failed for: {text}"

    def test_family_dinner_is_multi_activity(self):
        """Test family dinner is multi-activity (meal + family)."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Family dinner on Sunday",
            "Thanksgiving dinner with the relatives",
            "Christmas dinner with extended family",
        ]

        for text in texts:
            result = classify_activity(text)
            # Meal takes priority but family is secondary
            assert result.primary_activity in ["meal", "family_gathering"], f"Failed for: {text}"

    def test_medical_appointment_classification(self):
        """Test medical appointment detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Doctor's appointment today",
            "Dentist checkup",
            "Therapy session was helpful",
            "Hospital visit for mom",
            "Picked up prescription from pharmacy",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "medical_appointment", f"Failed for: {text}"

    def test_travel_classification(self):
        """Test travel detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Beach vacation in Hawaii",
            "Road trip to the mountains",
            "Flight to New York",
            "Hotel was amazing",
            "Sightseeing in Paris",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "travel", f"Failed for: {text}"

    def test_shopping_classification(self):
        """Test shopping detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        # Core shopping keywords
        texts = [
            "Grocery shopping at Costco",
            "Bought new clothes at the mall",
            "Quick errand to the store",
            "Amazon delivery arrived",
            "Shopping at the market",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "shopping", f"Failed for: {text}"

    def test_birthday_shopping_is_celebration(self):
        """Test birthday shopping prioritizes celebration keyword."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Shopping for birthday presents")
        # Birthday matches celebration first (higher priority)
        assert result.primary_activity in ["celebration", "shopping"]

    def test_entertainment_classification(self):
        """Test entertainment detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Watched a movie at the cinema",
            "Concert was incredible",
            "Binge watching Netflix",
            "Streaming the new show",
            "Going to see a performance",
        ]

        for text in texts:
            result = classify_activity(text)
            assert result.primary_activity == "entertainment", f"Failed for: {text}"

    def test_video_games_is_entertainment(self):
        """Test video games classified as entertainment."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("video game session all evening")
        assert result.primary_activity == "entertainment"


class TestMultiActivityDetection:
    """Tests for multi-label activity detection."""

    def test_birthday_dinner(self):
        """Test birthday + meal combination."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Birthday dinner at the restaurant")

        assert result.is_multi_activity is True
        assert result.primary_activity in ["celebration", "meal"]
        assert len(result.secondary_activities) > 0

    def test_anniversary_dinner(self):
        """Test anniversary + meal combination."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Anniversary dinner celebration")

        assert result.is_multi_activity is True

    def test_work_lunch(self):
        """Test work + meal combination."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Work lunch with colleagues")

        assert result.is_multi_activity is True

    def test_family_bbq(self):
        """Test family gathering + outdoor combination."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Family BBQ in the backyard")

        assert result.is_multi_activity is True

    def test_game_night(self):
        """Test game night detection."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Game night with friends")

        assert result.is_multi_activity is True


class TestConfidenceScoring:
    """Tests for confidence score calculation."""

    def test_high_confidence_single_keyword(self):
        """Test high confidence for clear matches."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Had breakfast")
        assert result.confidence >= 0.5

    def test_higher_confidence_multiple_keywords(self):
        """Test higher confidence with multiple matching keywords."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result1 = classify_activity("Dinner")
        result2 = classify_activity("Delicious dinner at the restaurant")

        # More keywords should increase confidence
        assert result2.confidence >= result1.confidence

    def test_low_confidence_no_match(self):
        """Test low confidence for ambiguous text."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Something happened today")
        assert result.confidence <= 0.5


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_string(self):
        """Test classification of empty string."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("")
        assert result.primary_activity == "routine"
        assert result.confidence == 0.3

    def test_none_input(self):
        """Test classification of None input."""
        from k0.modules.activity.zero_shot_classifier import ZeroShotActivityClassifier

        classifier = ZeroShotActivityClassifier()
        result = classifier.classify(None)  # type: ignore
        assert result.primary_activity == "routine"

    def test_whitespace_only(self):
        """Test classification of whitespace-only string."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("   \n\t  ")
        assert result.primary_activity == "routine"

    def test_special_characters(self):
        """Test classification with special characters."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Had dinner!!! @ the restaurant... #yummy")
        assert result.primary_activity == "meal"

    def test_case_insensitivity(self):
        """Test case-insensitive matching."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result1 = classify_activity("DINNER")
        result2 = classify_activity("Dinner")
        result3 = classify_activity("dinner")

        assert result1.primary_activity == result2.primary_activity == result3.primary_activity

    def test_unicode_text(self):
        """Test classification with unicode characters."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Had dinner at the cafe")
        assert result.primary_activity == "meal"


class TestLegacyMapping:
    """Tests for legacy activity type mapping."""

    def test_map_celebration_to_milestone(self):
        """Test mapping celebration to legacy milestone."""
        from k0.modules.activity.zero_shot_classifier import map_legacy_activity

        assert map_legacy_activity("celebration") == "milestone"

    def test_map_work_meeting_to_work(self):
        """Test mapping work_meeting to legacy work."""
        from k0.modules.activity.zero_shot_classifier import map_legacy_activity

        assert map_legacy_activity("work_meeting") == "work"

    def test_map_social_events(self):
        """Test mapping social events to legacy social."""
        from k0.modules.activity.zero_shot_classifier import map_legacy_activity

        assert map_legacy_activity("social_event") == "social"
        assert map_legacy_activity("family_gathering") == "social"

    def test_meal_stays_meal(self):
        """Test meal maps to meal (unchanged)."""
        from k0.modules.activity.zero_shot_classifier import map_legacy_activity

        assert map_legacy_activity("meal") == "meal"

    def test_unmapped_returns_unknown(self):
        """Test unmapped activity returns unknown."""
        from k0.modules.activity.zero_shot_classifier import map_legacy_activity

        # Activities not in the legacy map return 'unknown'
        assert map_legacy_activity("some_random_activity") == "unknown"
        assert map_legacy_activity("xyz_nonexistent") == "unknown"


class TestClassifierTiers:
    """Tests for classification tier selection."""

    def test_rule_based_tier(self):
        """Test rule-based classification tier."""
        from k0.modules.activity.zero_shot_classifier import (
            ClassificationTier,
            ZeroShotActivityClassifier,
        )

        classifier = ZeroShotActivityClassifier(tier=ClassificationTier.RULE_BASED)
        result = classifier.classify("Had dinner")

        assert result.classification_tier == "rule_based"

    def test_hybrid_tier_with_high_confidence(self):
        """Test hybrid tier uses rule-based for high confidence."""
        from k0.modules.activity.zero_shot_classifier import (
            ClassificationTier,
            ZeroShotActivityClassifier,
        )

        classifier = ZeroShotActivityClassifier(tier=ClassificationTier.HYBRID)
        result = classifier.classify("Had delicious dinner at the restaurant")

        # Should use rule-based (hybrid tier) since confidence is high
        assert result.classification_tier == "hybrid"


class TestPerformance:
    """Performance tests for classification latency."""

    def test_rule_based_latency_single(self):
        """Test single classification latency (<5ms)."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        start = time.perf_counter()
        classify_activity("Had dinner with the family")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        assert elapsed < 5, f"Single classification took {elapsed:.2f}ms (target: <5ms)"

    def test_rule_based_latency_batch(self):
        """Test batch classification latency."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        texts = [
            "Had breakfast",
            "Went to the gym",
            "Team meeting",
            "Birthday party",
            "Shopping at the mall",
        ] * 20  # 100 classifications

        start = time.perf_counter()
        for text in texts:
            classify_activity(text)
        elapsed = (time.perf_counter() - start) * 1000  # ms

        avg_latency = elapsed / len(texts)
        assert avg_latency < 5, f"Avg latency {avg_latency:.2f}ms (target: <5ms)"

    def test_p95_latency(self):
        """Test P95 latency is under 5ms."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        latencies = []
        texts = [
            "Had breakfast with family",
            "Morning workout at the gym",
            "Important client meeting",
            "Birthday celebration dinner",
            "Grocery shopping",
            "Doctor's appointment",
            "Road trip vacation",
            "Netflix movie night",
            "Yoga class",
            "Family reunion",
        ]

        for _ in range(10):
            for text in texts:
                start = time.perf_counter()
                classify_activity(text)
                latencies.append((time.perf_counter() - start) * 1000)

        latencies.sort()
        p95_idx = int(len(latencies) * 0.95)
        p95_latency = latencies[p95_idx]

        assert p95_latency < 5, f"P95 latency {p95_latency:.2f}ms (target: <5ms)"


class TestMetrics:
    """Tests for metrics collection."""

    def test_metrics_incremented(self):
        """Test that metrics are incremented on classification."""
        from k0.modules.activity.zero_shot_classifier import (
            classify_activity,
            get_metrics,
            reset_metrics,
        )

        reset_metrics()
        initial = get_metrics()["total_classifications"]

        classify_activity("Had dinner")
        classify_activity("Morning workout")

        final = get_metrics()["total_classifications"]
        assert final == initial + 2

    def test_reset_metrics(self):
        """Test metrics reset."""
        from k0.modules.activity.zero_shot_classifier import (
            classify_activity,
            get_metrics,
            reset_metrics,
        )

        classify_activity("Had dinner")
        reset_metrics()

        metrics = get_metrics()
        assert metrics["total_classifications"] == 0


class TestCategoryMapping:
    """Tests for activity to category mapping."""

    def test_meal_maps_to_sustenance(self):
        """Test meal maps to sustenance category."""
        from k0.modules.activity.zero_shot_classifier import ACTIVITY_TO_CATEGORY

        assert ACTIVITY_TO_CATEGORY["meal"] == "sustenance"

    def test_exercise_maps_to_wellness(self):
        """Test exercise maps to wellness category."""
        from k0.modules.activity.zero_shot_classifier import ACTIVITY_TO_CATEGORY

        assert ACTIVITY_TO_CATEGORY["exercise"] == "wellness"
        assert ACTIVITY_TO_CATEGORY["medical_appointment"] == "wellness"

    def test_work_meeting_maps_to_work(self):
        """Test work_meeting maps to work category."""
        from k0.modules.activity.zero_shot_classifier import ACTIVITY_TO_CATEGORY

        assert ACTIVITY_TO_CATEGORY["work_meeting"] == "work"
        assert ACTIVITY_TO_CATEGORY["commute"] == "work"


class TestZeroShotLabels:
    """Tests for zero-shot classification labels."""

    def test_labels_cover_20_plus_activities(self):
        """Test that zero-shot labels cover 20+ activities."""
        from k0.modules.activity.zero_shot_classifier import ZERO_SHOT_LABELS

        assert len(ZERO_SHOT_LABELS) >= 20

    def test_labels_include_common_activities(self):
        """Test labels include common activities."""
        from k0.modules.activity.zero_shot_classifier import ZERO_SHOT_LABELS

        expected = ["meal", "exercise", "work meeting", "celebration", "travel"]
        for activity in expected:
            assert activity in ZERO_SHOT_LABELS


class TestModuleAPI:
    """Tests for module-level API functions."""

    def test_get_classifier_singleton(self):
        """Test classifier singleton pattern."""
        from k0.modules.activity.zero_shot_classifier import get_classifier

        c1 = get_classifier()
        c2 = get_classifier()
        assert c1 is c2

    def test_classify_activity_function(self):
        """Test convenience function."""
        from k0.modules.activity.zero_shot_classifier import classify_activity

        result = classify_activity("Had dinner")
        assert result.primary_activity == "meal"
