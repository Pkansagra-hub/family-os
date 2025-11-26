"""
Pytest fixtures for golden dataset and benchmark integration.

This module provides fixtures for:
- Loading the golden dataset
- Running accuracy benchmarks in tests
- Regression testing baseline scores

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import pytest

from tests.benchmarks import AccuracyBenchmark, BenchmarkResult, empty_baseline_processor
from tests.fixtures.golden_dataset import GoldenDataset, GoldenMemory, load_golden_dataset

if TYPE_CHECKING:
    pass


# =============================================================================
# Dataset Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def golden_dataset() -> GoldenDataset:
    """
    Load the golden dataset once per test session.

    Usage:
        def test_something(golden_dataset):
            assert len(golden_dataset.memories) > 0
    """
    return load_golden_dataset()


@pytest.fixture(scope="session")
def golden_memories(golden_dataset: GoldenDataset) -> list[GoldenMemory]:
    """
    Get all golden memories as a list.

    Usage:
        def test_something(golden_memories):
            for memory in golden_memories:
                process(memory.text)
    """
    return golden_dataset.memories


@pytest.fixture
def easy_memories(golden_dataset: GoldenDataset) -> list[GoldenMemory]:
    """Get only easy difficulty memories."""
    from tests.fixtures.golden_dataset.models import Difficulty
    return golden_dataset.get_by_difficulty(Difficulty.EASY)


@pytest.fixture
def medium_memories(golden_dataset: GoldenDataset) -> list[GoldenMemory]:
    """Get only medium difficulty memories."""
    from tests.fixtures.golden_dataset.models import Difficulty
    return golden_dataset.get_by_difficulty(Difficulty.MEDIUM)


@pytest.fixture
def hard_memories(golden_dataset: GoldenDataset) -> list[GoldenMemory]:
    """Get only hard difficulty memories."""
    from tests.fixtures.golden_dataset.models import Difficulty
    return golden_dataset.get_by_difficulty(Difficulty.HARD)


# =============================================================================
# Benchmark Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def accuracy_benchmark() -> AccuracyBenchmark:
    """
    Create an accuracy benchmark instance.

    Usage:
        def test_module_accuracy(accuracy_benchmark):
            result = accuracy_benchmark.run(my_processor)
            assert result.scores.overall_score > 0.5
    """
    return AccuracyBenchmark()


@pytest.fixture(scope="session")
def baseline_result(accuracy_benchmark: AccuracyBenchmark) -> BenchmarkResult:
    """
    Get baseline benchmark result using empty processor.

    Useful for comparing against a minimum baseline.
    """
    return accuracy_benchmark.run(empty_baseline_processor)


# =============================================================================
# Regression Testing Fixtures
# =============================================================================


# Minimum acceptable scores for regression testing
# These should be updated as modules improve
REGRESSION_THRESHOLDS = {
    "entity_f1": 0.0,  # Start at 0, increase as modules improve
    "emotion_primary_accuracy": 0.0,
    "activity_type_accuracy": 0.0,
    "social_context_accuracy": 0.0,
    "overall_score": 0.0,
}


@pytest.fixture
def regression_thresholds() -> dict[str, float]:
    """
    Get regression testing thresholds.

    These are minimum acceptable scores. Tests should fail
    if scores drop below these thresholds.
    """
    return REGRESSION_THRESHOLDS.copy()


def assert_no_regression(
    result: BenchmarkResult,
    thresholds: dict[str, float] | None = None,
) -> None:
    """
    Assert that benchmark results don't regress below thresholds.

    Args:
        result: Benchmark result to check.
        thresholds: Optional custom thresholds. Uses defaults if not provided.

    Raises:
        AssertionError: If any score is below its threshold.
    """
    if thresholds is None:
        thresholds = REGRESSION_THRESHOLDS

    scores = result.scores

    if "entity_f1" in thresholds:
        assert scores.entity.f1 >= thresholds["entity_f1"], (
            f"Entity F1 regressed: {scores.entity.f1:.3f} < {thresholds['entity_f1']:.3f}"
        )

    if "emotion_primary_accuracy" in thresholds:
        assert scores.emotion.primary_accuracy >= thresholds["emotion_primary_accuracy"], (
            f"Emotion accuracy regressed: {scores.emotion.primary_accuracy:.3f} < "
            f"{thresholds['emotion_primary_accuracy']:.3f}"
        )

    if "activity_type_accuracy" in thresholds:
        assert scores.activity.type_accuracy >= thresholds["activity_type_accuracy"], (
            f"Activity accuracy regressed: {scores.activity.type_accuracy:.3f} < "
            f"{thresholds['activity_type_accuracy']:.3f}"
        )

    if "social_context_accuracy" in thresholds:
        assert scores.social.context_accuracy >= thresholds["social_context_accuracy"], (
            f"Social accuracy regressed: {scores.social.context_accuracy:.3f} < "
            f"{thresholds['social_context_accuracy']:.3f}"
        )

    if "overall_score" in thresholds:
        assert scores.overall_score >= thresholds["overall_score"], (
            f"Overall score regressed: {scores.overall_score:.3f} < "
            f"{thresholds['overall_score']:.3f}"
        )


# =============================================================================
# Test Helpers
# =============================================================================


def make_processor(
    entity_fn: Callable[[str], list[dict[str, Any]]] | None = None,
    emotion_fn: Callable[[str], dict[str, Any]] | None = None,
    activity_fn: Callable[[str], dict[str, Any]] | None = None,
    social_fn: Callable[[str], dict[str, Any]] | None = None,
) -> Callable[[str], dict[str, Any]]:
    """
    Create a test processor from component functions.

    Useful for testing individual modules in isolation.

    Args:
        entity_fn: Function to extract entities.
        emotion_fn: Function to detect emotions.
        activity_fn: Function to classify activity.
        social_fn: Function to extract social context.

    Returns:
        Combined processor function.
    """
    def processor(text: str) -> dict[str, Any]:
        return {
            "entities": entity_fn(text) if entity_fn else [],
            "emotions": emotion_fn(text) if emotion_fn else {
                "primary": "neutral",
                "valence": 0.0,
                "arousal": 0.5,
                "secondary": [],
            },
            "activity": activity_fn(text) if activity_fn else {
                "type": "daily",
                "subtype": None,
                "is_celebration": False,
            },
            "social": social_fn(text) if social_fn else {
                "context": "solo",
                "participants": [],
                "participant_count": 1,
            },
        }

    return processor
            },
        }

    return processor
