"""
Unit tests for Accuracy Benchmark Runner.

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from tests.benchmarks import (
    AccuracyBenchmark,
    BenchmarkResult,
    EmotionScore,
    EntityScore,
    ModuleScores,
    empty_baseline_processor,
    random_baseline_processor,
    run_accuracy_benchmark,
)
from tests.benchmarks.accuracy_benchmark import (
    score_activity,
    score_emotions,
    score_entities,
    score_social,
)
from tests.fixtures.golden_dataset import (
    ActivityAnnotation,
    ActivityType,
    EmotionAnnotation,
    EmotionLabel,
    EntityAnnotation,
    EntityType,
    FamilyRole,
    SocialAnnotation,
    SocialContext,
)
from tests.fixtures.golden_dataset.models import ActivitySubtype, LocationType


class TestEntityScoring:
    """Tests for entity extraction scoring."""

    def test_score_entities_perfect_match(self):
        """Test perfect entity match scoring."""
        ground_truth = [
            EntityAnnotation(text="Sarah", type=EntityType.PERSON),
            EntityAnnotation(text="Olive Garden", type=EntityType.ORG),
        ]
        predicted = [
            {"text": "Sarah", "type": "PERSON"},
            {"text": "Olive Garden", "type": "ORG"},
        ]

        score = score_entities(predicted, ground_truth)

        assert score.precision == 1.0
        assert score.recall == 1.0
        assert score.f1 == 1.0
        assert score.true_positives == 2

    def test_score_entities_partial_match(self):
        """Test partial entity match scoring."""
        ground_truth = [
            EntityAnnotation(text="Sarah", type=EntityType.PERSON),
            EntityAnnotation(text="Emma", type=EntityType.PERSON),
        ]
        predicted = [
            {"text": "Sarah", "type": "PERSON"},
            {"text": "Unknown", "type": "PERSON"},
        ]

        score = score_entities(predicted, ground_truth)

        assert score.true_positives == 1
        assert score.false_positives == 1
        assert score.false_negatives == 1
        assert score.precision == 0.5
        assert score.recall == 0.5

    def test_score_entities_no_predictions(self):
        """Test scoring when no entities predicted."""
        ground_truth = [
            EntityAnnotation(text="Sarah", type=EntityType.PERSON),
        ]
        predicted = []

        score = score_entities(predicted, ground_truth)

        assert score.precision == 0.0
        assert score.recall == 0.0
        assert score.f1 == 0.0

    def test_score_entities_empty_ground_truth(self):
        """Test scoring when no ground truth entities."""
        ground_truth = []
        predicted = []

        score = score_entities(predicted, ground_truth)

        assert score.precision == 1.0
        assert score.recall == 1.0
        assert score.f1 == 1.0

    def test_score_entities_case_insensitive(self):
        """Test that entity matching is case insensitive."""
        ground_truth = [
            EntityAnnotation(text="SARAH", type=EntityType.PERSON),
        ]
        predicted = [
            {"text": "sarah", "type": "PERSON"},
        ]

        score = score_entities(predicted, ground_truth)

        assert score.true_positives == 1
        assert score.f1 == 1.0


class TestEmotionScoring:
    """Tests for emotion detection scoring."""

    def test_score_emotions_perfect_match(self):
        """Test perfect emotion match scoring."""
        ground_truth = EmotionAnnotation(
            primary=EmotionLabel.JOY,
            secondary=[EmotionLabel.LOVE],
            valence=0.9,
            arousal=0.7,
        )
        predicted = {
            "primary": "joy",
            "secondary": ["love"],
            "valence": 0.9,
            "arousal": 0.7,
        }

        score = score_emotions(predicted, ground_truth)

        assert score.primary_accuracy == 1.0
        assert score.valence_mae == 0.0
        assert score.arousal_mae == 0.0
        assert score.secondary_f1 == 1.0

    def test_score_emotions_wrong_primary(self):
        """Test scoring when primary emotion is wrong."""
        ground_truth = EmotionAnnotation(
            primary=EmotionLabel.JOY,
            secondary=[],
            valence=0.9,
            arousal=0.7,
        )
        predicted = {
            "primary": "sadness",
            "secondary": [],
            "valence": 0.9,
            "arousal": 0.7,
        }

        score = score_emotions(predicted, ground_truth)

        assert score.primary_accuracy == 0.0
        assert score.correct_primary == 0

    def test_score_emotions_valence_error(self):
        """Test valence MAE calculation."""
        ground_truth = EmotionAnnotation(
            primary=EmotionLabel.JOY,
            secondary=[],
            valence=0.8,
            arousal=0.5,
        )
        predicted = {
            "primary": "joy",
            "secondary": [],
            "valence": 0.3,  # Error of 0.5
            "arousal": 0.5,
        }

        score = score_emotions(predicted, ground_truth)

        assert abs(score.valence_mae - 0.5) < 0.001


class TestActivityScoring:
    """Tests for activity classification scoring."""

    def test_score_activity_perfect_match(self):
        """Test perfect activity match scoring."""
        ground_truth = ActivityAnnotation(
            type=ActivityType.MEAL,
            subtype=ActivitySubtype.DINNER,
            is_celebration=False,
            location_type=LocationType.RESTAURANT,
        )
        predicted = {
            "type": "meal",
            "subtype": "dinner",
            "is_celebration": False,
            "location_type": "restaurant",
        }

        score = score_activity(predicted, ground_truth)

        assert score.type_accuracy == 1.0
        assert score.subtype_accuracy == 1.0
        assert score.celebration_accuracy == 1.0
        assert score.location_accuracy == 1.0

    def test_score_activity_wrong_type(self):
        """Test scoring when activity type is wrong."""
        ground_truth = ActivityAnnotation(
            type=ActivityType.MEAL,
            is_celebration=False,
        )
        predicted = {
            "type": "travel",
            "is_celebration": False,
        }

        score = score_activity(predicted, ground_truth)

        assert score.type_accuracy == 0.0
        assert score.correct_type == 0

    def test_score_activity_celebration_flag(self):
        """Test celebration flag accuracy."""
        ground_truth = ActivityAnnotation(
            type=ActivityType.CELEBRATION,
            is_celebration=True,
        )
        predicted = {
            "type": "celebration",
            "is_celebration": False,  # Wrong
        }

        score = score_activity(predicted, ground_truth)

        assert score.celebration_accuracy == 0.0


class TestSocialScoring:
    """Tests for social context scoring."""

    def test_score_social_perfect_match(self):
        """Test perfect social context match scoring."""
        ground_truth = SocialAnnotation(
            context=SocialContext.NUCLEAR_FAMILY,
            participants=[FamilyRole.SPOUSE, FamilyRole.CHILD],
            participant_count=3,
        )
        predicted = {
            "context": "nuclear_family",
            "participants": ["spouse", "child"],
            "participant_count": 3,
        }

        score = score_social(predicted, ground_truth)

        assert score.context_accuracy == 1.0
        assert score.participant_f1 == 1.0
        assert score.count_mae == 0

    def test_score_social_wrong_context(self):
        """Test scoring when context is wrong."""
        ground_truth = SocialAnnotation(
            context=SocialContext.NUCLEAR_FAMILY,
            participants=[],
        )
        predicted = {
            "context": "solo",
            "participants": [],
        }

        score = score_social(predicted, ground_truth)

        assert score.context_accuracy == 0.0
        assert score.correct_context == 0


class TestBenchmarkRunner:
    """Tests for the benchmark runner class."""

    def test_benchmark_initialization(self):
        """Test benchmark initializes correctly."""
        benchmark = AccuracyBenchmark()

        assert len(benchmark.memories) > 0
        assert benchmark.dataset is not None

    def test_benchmark_with_filter_difficulty(self):
        """Test benchmark filtering by difficulty."""
        benchmark = AccuracyBenchmark(filter_difficulty=["easy"])

        for memory in benchmark.memories:
            assert memory.metadata.difficulty.value == "easy"

    def test_benchmark_with_filter_tags(self):
        """Test benchmark filtering by tags."""
        benchmark = AccuracyBenchmark(filter_tags=["birthday"])

        for memory in benchmark.memories:
            assert "birthday" in memory.metadata.tags

    def test_benchmark_run_empty_baseline(self):
        """Test running benchmark with empty baseline."""
        benchmark = AccuracyBenchmark()
        result = benchmark.run(empty_baseline_processor)

        assert isinstance(result, BenchmarkResult)
        assert result.memories_evaluated == len(benchmark.memories)
        assert result.dataset_version == "1.0.0"
        assert result.evaluation_time_seconds >= 0

    def test_benchmark_result_summary(self):
        """Test benchmark result summary generation."""
        benchmark = AccuracyBenchmark()
        result = benchmark.run(empty_baseline_processor)

        summary = result.summary()

        assert "ACCURACY BENCHMARK RESULTS" in summary
        assert "Dataset Version" in summary
        assert "Memories Evaluated" in summary

    def test_benchmark_scores_by_difficulty(self):
        """Test that scores are broken down by difficulty."""
        benchmark = AccuracyBenchmark()
        result = benchmark.run(empty_baseline_processor)

        assert len(result.scores_by_difficulty) > 0
        for diff, scores in result.scores_by_difficulty.items():
            assert diff in ["easy", "medium", "hard"]
            assert isinstance(scores, ModuleScores)


class TestConvenienceFunction:
    """Tests for the run_accuracy_benchmark convenience function."""

    def test_run_accuracy_benchmark_basic(self):
        """Test basic benchmark run via convenience function."""
        result = run_accuracy_benchmark(empty_baseline_processor)

        assert isinstance(result, BenchmarkResult)
        assert result.memories_evaluated > 0

    def test_run_accuracy_benchmark_with_filters(self):
        """Test benchmark with filters via convenience function."""
        result = run_accuracy_benchmark(
            empty_baseline_processor,
            filter_difficulty=["easy"],
        )

        # Should have fewer memories than total
        full_result = run_accuracy_benchmark(empty_baseline_processor)
        assert result.memories_evaluated <= full_result.memories_evaluated


class TestBaselineProcessors:
    """Tests for baseline processors."""

    def test_empty_baseline_processor_returns_valid_structure(self):
        """Test empty baseline returns expected structure."""
        output = empty_baseline_processor("Test memory text")

        assert "entities" in output
        assert "emotions" in output
        assert "activity" in output
        assert "social" in output
        assert isinstance(output["entities"], list)
        assert "primary" in output["emotions"]

    def test_random_baseline_processor_returns_valid_structure(self):
        """Test random baseline returns expected structure."""
        output = random_baseline_processor("Test memory text")

        assert "entities" in output
        assert "emotions" in output
        assert "activity" in output
        assert "social" in output


class TestModuleScores:
    """Tests for ModuleScores dataclass."""

    def test_overall_score_calculation(self):
        """Test overall score weighted average."""
        scores = ModuleScores()
        scores.entity.f1 = 0.8
        scores.emotion.primary_accuracy = 0.7
        scores.activity.type_accuracy = 0.9
        scores.social.context_accuracy = 0.6

        # Weights: entity=0.3, emotion=0.25, activity=0.25, social=0.2
        expected = 0.3 * 0.8 + 0.25 * 0.7 + 0.25 * 0.9 + 0.2 * 0.6

        assert abs(scores.overall_score - expected) < 0.001


class TestScoreDataclasses:
    """Tests for individual score dataclasses."""

    def test_entity_score_str(self):
        """Test EntityScore string representation."""
        score = EntityScore(precision=0.9, recall=0.8, f1=0.85)
        str_repr = str(score)

        assert "0.900" in str_repr
        assert "0.800" in str_repr

    def test_emotion_score_str(self):
        """Test EmotionScore string representation."""
        score = EmotionScore(primary_accuracy=0.75, valence_mae=0.2)
        str_repr = str(score)

        assert "0.750" in str_repr
        assert "0.200" in str_repr
