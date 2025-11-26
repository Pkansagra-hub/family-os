"""
Accuracy Benchmark Runner for K0 Modules.

Compares module output against golden dataset ground truth annotations
to calculate accuracy metrics for:
- M02: Entity extraction (NER)
- M04: Emotion detection (affect analysis)
- M07: Activity classification (trip enrichment)
- M10: Social context extraction (social graph)

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from tests.fixtures.golden_dataset import (
    ActivityAnnotation,
    EmotionAnnotation,
    EntityAnnotation,
    GoldenMemory,
    SocialAnnotation,
    load_golden_dataset,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Score Dataclasses
# =============================================================================


@dataclass
class EntityScore:
    """Entity extraction accuracy scores."""

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    type_accuracy: float = 0.0  # Entity type classification accuracy
    role_accuracy: float = 0.0  # Family role accuracy (for PERSON entities)

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    def __str__(self) -> str:
        return (
            f"EntityScore(P={self.precision:.3f}, R={self.recall:.3f}, "
            f"F1={self.f1:.3f}, type_acc={self.type_accuracy:.3f})"
        )


@dataclass
class EmotionScore:
    """Emotion detection accuracy scores."""

    primary_accuracy: float = 0.0  # Exact match on primary emotion
    valence_mae: float = 0.0  # Mean absolute error on valence (-1 to 1)
    arousal_mae: float = 0.0  # Mean absolute error on arousal (0 to 1)
    secondary_f1: float = 0.0  # F1 for secondary emotions

    correct_primary: int = 0
    total_primary: int = 0

    def __str__(self) -> str:
        return (
            f"EmotionScore(primary_acc={self.primary_accuracy:.3f}, "
            f"valence_MAE={self.valence_mae:.3f}, arousal_MAE={self.arousal_mae:.3f})"
        )


@dataclass
class ActivityScore:
    """Activity classification accuracy scores."""

    type_accuracy: float = 0.0  # Activity type accuracy
    subtype_accuracy: float = 0.0  # Activity subtype accuracy
    celebration_accuracy: float = 0.0  # is_celebration flag accuracy
    location_accuracy: float = 0.0  # location_type accuracy

    correct_type: int = 0
    correct_subtype: int = 0
    total: int = 0

    def __str__(self) -> str:
        return (
            f"ActivityScore(type_acc={self.type_accuracy:.3f}, "
            f"subtype_acc={self.subtype_accuracy:.3f})"
        )


@dataclass
class SocialScore:
    """Social context extraction accuracy scores."""

    context_accuracy: float = 0.0  # Social context classification
    participant_f1: float = 0.0  # F1 for participant roles
    count_mae: float = 0.0  # Mean absolute error on participant count

    correct_context: int = 0
    total_context: int = 0

    def __str__(self) -> str:
        return (
            f"SocialScore(context_acc={self.context_accuracy:.3f}, "
            f"participant_F1={self.participant_f1:.3f})"
        )


@dataclass
class ModuleScores:
    """Combined scores for all module types."""

    entity: EntityScore = field(default_factory=EntityScore)
    emotion: EmotionScore = field(default_factory=EmotionScore)
    activity: ActivityScore = field(default_factory=ActivityScore)
    social: SocialScore = field(default_factory=SocialScore)

    @property
    def overall_score(self) -> float:
        """Weighted average of all module scores."""
        weights = {
            "entity": 0.3,
            "emotion": 0.25,
            "activity": 0.25,
            "social": 0.2,
        }
        return (
            weights["entity"] * self.entity.f1
            + weights["emotion"] * self.emotion.primary_accuracy
            + weights["activity"] * self.activity.type_accuracy
            + weights["social"] * self.social.context_accuracy
        )


@dataclass
class BenchmarkResult:
    """Complete benchmark result including scores and metadata."""

    scores: ModuleScores
    dataset_version: str
    memories_evaluated: int
    evaluation_time_seconds: float
    timestamp: str

    # Per-difficulty breakdowns
    scores_by_difficulty: dict[str, ModuleScores] = field(default_factory=dict)

    # Individual memory results for debugging
    memory_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            "=" * 60,
            "ACCURACY BENCHMARK RESULTS",
            "=" * 60,
            f"Dataset Version: {self.dataset_version}",
            f"Memories Evaluated: {self.memories_evaluated}",
            f"Evaluation Time: {self.evaluation_time_seconds:.2f}s",
            "",
            "OVERALL SCORES:",
            f"  Overall Score: {self.scores.overall_score:.3f}",
            f"  Entity F1: {self.scores.entity.f1:.3f}",
            f"  Emotion Primary Acc: {self.scores.emotion.primary_accuracy:.3f}",
            f"  Activity Type Acc: {self.scores.activity.type_accuracy:.3f}",
            f"  Social Context Acc: {self.scores.social.context_accuracy:.3f}",
            "",
        ]

        if self.scores_by_difficulty:
            lines.append("SCORES BY DIFFICULTY:")
            for diff, scores in self.scores_by_difficulty.items():
                lines.append(f"  {diff}: overall={scores.overall_score:.3f}")

        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# Module Output Protocol
# =============================================================================


class ModuleOutput(Protocol):
    """Protocol for module output that can be scored against ground truth."""

    entities: list[dict[str, Any]]
    emotions: dict[str, Any]
    activity: dict[str, Any]
    social: dict[str, Any]


# =============================================================================
# Scoring Functions
# =============================================================================


def score_entities(
    predicted: list[dict[str, Any]],
    ground_truth: list[EntityAnnotation],
) -> EntityScore:
    """
    Score entity extraction against ground truth.

    Uses fuzzy matching on entity text and exact matching on type.
    """
    score = EntityScore()

    if not ground_truth:
        if not predicted:
            score.precision = 1.0
            score.recall = 1.0
            score.f1 = 1.0
        return score

    gt_texts = {e.text.lower() for e in ground_truth}
    pred_texts = {e.get("text", "").lower() for e in predicted}

    # Calculate matches using fuzzy text matching
    true_positives = gt_texts & pred_texts
    false_positives = pred_texts - gt_texts
    false_negatives = gt_texts - pred_texts

    score.true_positives = len(true_positives)
    score.false_positives = len(false_positives)
    score.false_negatives = len(false_negatives)

    if score.true_positives + score.false_positives > 0:
        score.precision = score.true_positives / (score.true_positives + score.false_positives)

    if score.true_positives + score.false_negatives > 0:
        score.recall = score.true_positives / (score.true_positives + score.false_negatives)

    if score.precision + score.recall > 0:
        score.f1 = 2 * (score.precision * score.recall) / (score.precision + score.recall)

    # Type accuracy for matched entities
    type_correct = 0
    for gt_ent in ground_truth:
        for pred_ent in predicted:
            if gt_ent.text.lower() == pred_ent.get("text", "").lower():
                if gt_ent.type.value == pred_ent.get("type"):
                    type_correct += 1
                break

    if score.true_positives > 0:
        score.type_accuracy = type_correct / score.true_positives

    return score


def score_emotions(
    predicted: dict[str, Any],
    ground_truth: EmotionAnnotation,
) -> EmotionScore:
    """Score emotion detection against ground truth."""
    score = EmotionScore()
    score.total_primary = 1

    # Primary emotion accuracy
    pred_primary = predicted.get("primary", "").lower()
    if pred_primary == ground_truth.primary.value:
        score.correct_primary = 1
        score.primary_accuracy = 1.0

    # Valence MAE
    pred_valence = predicted.get("valence", 0.0)
    score.valence_mae = abs(pred_valence - ground_truth.valence)

    # Arousal MAE
    pred_arousal = predicted.get("arousal", 0.5)
    score.arousal_mae = abs(pred_arousal - ground_truth.arousal)

    # Secondary emotions F1
    pred_secondary = set(s.lower() for s in predicted.get("secondary", []))
    gt_secondary = set(s.value for s in ground_truth.secondary)

    if gt_secondary or pred_secondary:
        intersection = pred_secondary & gt_secondary
        if intersection:
            precision = len(intersection) / len(pred_secondary) if pred_secondary else 0
            recall = len(intersection) / len(gt_secondary) if gt_secondary else 0
            if precision + recall > 0:
                score.secondary_f1 = 2 * (precision * recall) / (precision + recall)

    return score


def score_activity(
    predicted: dict[str, Any],
    ground_truth: ActivityAnnotation,
) -> ActivityScore:
    """Score activity classification against ground truth."""
    score = ActivityScore()
    score.total = 1

    # Type accuracy
    pred_type = (predicted.get("type") or "").lower()
    if pred_type == ground_truth.type.value:
        score.correct_type = 1
        score.type_accuracy = 1.0

    # Subtype accuracy
    if ground_truth.subtype:
        pred_subtype = (predicted.get("subtype") or "").lower()
        if pred_subtype == ground_truth.subtype.value:
            score.correct_subtype = 1
            score.subtype_accuracy = 1.0

    # Celebration flag accuracy
    pred_celebration = predicted.get("is_celebration", False)
    if pred_celebration == ground_truth.is_celebration:
        score.celebration_accuracy = 1.0

    # Location type accuracy
    if ground_truth.location_type:
        pred_location = (predicted.get("location_type") or "").lower()
        if pred_location == ground_truth.location_type.value:
            score.location_accuracy = 1.0

    return score


def score_social(
    predicted: dict[str, Any],
    ground_truth: SocialAnnotation,
) -> SocialScore:
    """Score social context extraction against ground truth."""
    score = SocialScore()
    score.total_context = 1

    # Context accuracy
    pred_context = (predicted.get("context") or "").lower()
    if pred_context == ground_truth.context.value:
        score.correct_context = 1
        score.context_accuracy = 1.0

    # Participants F1
    pred_participants = set(p.lower() for p in predicted.get("participants", []) if p)
    gt_participants = set(p.value for p in ground_truth.participants)

    if gt_participants or pred_participants:
        intersection = pred_participants & gt_participants
        if intersection:
            precision = len(intersection) / len(pred_participants) if pred_participants else 0
            recall = len(intersection) / len(gt_participants) if gt_participants else 0
            if precision + recall > 0:
                score.participant_f1 = 2 * (precision * recall) / (precision + recall)

    # Participant count MAE
    pred_count = predicted.get("participant_count", 1)
    if ground_truth.participant_count:
        score.count_mae = abs(pred_count - ground_truth.participant_count)

    return score


# =============================================================================
# Main Benchmark Runner
# =============================================================================


class AccuracyBenchmark:
    """
    Benchmark runner for evaluating module accuracy against golden dataset.

    Usage:
        benchmark = AccuracyBenchmark()
        result = benchmark.run(module_processor_fn)
        print(result.summary())
    """

    def __init__(
        self,
        dataset_path: Path | None = None,
        filter_tags: list[str] | None = None,
        filter_difficulty: list[str] | None = None,
    ):
        """
        Initialize benchmark with optional filters.

        Args:
            dataset_path: Path to golden dataset file.
            filter_tags: Only include memories with these tags.
            filter_difficulty: Only include memories with these difficulties.
        """
        self.dataset = load_golden_dataset(dataset_path)
        self.filter_tags = filter_tags
        self.filter_difficulty = filter_difficulty

        # Apply filters
        self.memories = self._filter_memories()

        logger.info(
            f"Initialized benchmark with {len(self.memories)} memories "
            f"(of {len(self.dataset.memories)} total)"
        )

    def _filter_memories(self) -> list[GoldenMemory]:
        """Filter dataset based on configured criteria."""
        memories = self.dataset.memories

        if self.filter_tags:
            memories = [
                m for m in memories if any(tag in m.metadata.tags for tag in self.filter_tags)
            ]

        if self.filter_difficulty:
            memories = [
                m for m in memories if m.metadata.difficulty.value in self.filter_difficulty
            ]

        return memories

    def run(
        self,
        processor: Callable[[str], dict[str, Any]],
    ) -> BenchmarkResult:
        """
        Run benchmark using the provided processor function.

        Args:
            processor: Function that takes memory text and returns
                       dict with keys: entities, emotions, activity, social

        Returns:
            BenchmarkResult with scores and metadata.
        """
        from datetime import datetime, timezone

        start_time = time.time()

        # Aggregate scores
        all_entity_scores: list[EntityScore] = []
        all_emotion_scores: list[EmotionScore] = []
        all_activity_scores: list[ActivityScore] = []
        all_social_scores: list[SocialScore] = []

        # Per-difficulty tracking
        difficulty_scores: dict[
            str, list[tuple[EntityScore, EmotionScore, ActivityScore, SocialScore]]
        ] = {
            "easy": [],
            "medium": [],
            "hard": [],
        }

        memory_results: dict[str, dict[str, Any]] = {}

        for memory in self.memories:
            try:
                # Run processor
                output = processor(memory.text)

                # Score each component
                entity_score = score_entities(
                    output.get("entities", []),
                    memory.ground_truth.entities,
                )
                emotion_score = score_emotions(
                    output.get("emotions", {}),
                    memory.ground_truth.emotions,
                )
                activity_score = score_activity(
                    output.get("activity", {}),
                    memory.ground_truth.activity,
                )
                social_score = score_social(
                    output.get("social", {}),
                    memory.ground_truth.social,
                )

                all_entity_scores.append(entity_score)
                all_emotion_scores.append(emotion_score)
                all_activity_scores.append(activity_score)
                all_social_scores.append(social_score)

                # Track by difficulty
                diff = memory.metadata.difficulty.value
                difficulty_scores[diff].append(
                    (entity_score, emotion_score, activity_score, social_score)
                )

                # Store individual results
                memory_results[memory.id] = {
                    "entity": entity_score,
                    "emotion": emotion_score,
                    "activity": activity_score,
                    "social": social_score,
                }

            except Exception as e:
                logger.error(f"Error processing memory {memory.id}: {e}")
                memory_results[memory.id] = {"error": str(e)}

        # Aggregate scores
        overall_scores = self._aggregate_scores(
            all_entity_scores,
            all_emotion_scores,
            all_activity_scores,
            all_social_scores,
        )

        # Aggregate by difficulty
        scores_by_difficulty = {}
        for diff, scores_list in difficulty_scores.items():
            if scores_list:
                e_scores = [s[0] for s in scores_list]
                em_scores = [s[1] for s in scores_list]
                a_scores = [s[2] for s in scores_list]
                so_scores = [s[3] for s in scores_list]
                scores_by_difficulty[diff] = self._aggregate_scores(
                    e_scores, em_scores, a_scores, so_scores
                )

        elapsed = time.time() - start_time

        return BenchmarkResult(
            scores=overall_scores,
            dataset_version=self.dataset.version,
            memories_evaluated=len(self.memories),
            evaluation_time_seconds=elapsed,
            timestamp=datetime.now(timezone.utc).isoformat(),
            scores_by_difficulty=scores_by_difficulty,
            memory_results=memory_results,
        )

    def _aggregate_scores(
        self,
        entity_scores: list[EntityScore],
        emotion_scores: list[EmotionScore],
        activity_scores: list[ActivityScore],
        social_scores: list[SocialScore],
    ) -> ModuleScores:
        """Aggregate individual scores into module scores."""
        scores = ModuleScores()

        if entity_scores:
            n = len(entity_scores)
            scores.entity.precision = sum(s.precision for s in entity_scores) / n
            scores.entity.recall = sum(s.recall for s in entity_scores) / n
            scores.entity.f1 = sum(s.f1 for s in entity_scores) / n
            scores.entity.type_accuracy = sum(s.type_accuracy for s in entity_scores) / n
            scores.entity.true_positives = sum(s.true_positives for s in entity_scores)
            scores.entity.false_positives = sum(s.false_positives for s in entity_scores)
            scores.entity.false_negatives = sum(s.false_negatives for s in entity_scores)

        if emotion_scores:
            n = len(emotion_scores)
            scores.emotion.primary_accuracy = sum(s.primary_accuracy for s in emotion_scores) / n
            scores.emotion.valence_mae = sum(s.valence_mae for s in emotion_scores) / n
            scores.emotion.arousal_mae = sum(s.arousal_mae for s in emotion_scores) / n
            scores.emotion.secondary_f1 = sum(s.secondary_f1 for s in emotion_scores) / n
            scores.emotion.correct_primary = sum(s.correct_primary for s in emotion_scores)
            scores.emotion.total_primary = sum(s.total_primary for s in emotion_scores)

        if activity_scores:
            n = len(activity_scores)
            scores.activity.type_accuracy = sum(s.type_accuracy for s in activity_scores) / n
            scores.activity.subtype_accuracy = sum(s.subtype_accuracy for s in activity_scores) / n
            scores.activity.celebration_accuracy = (
                sum(s.celebration_accuracy for s in activity_scores) / n
            )
            scores.activity.location_accuracy = (
                sum(s.location_accuracy for s in activity_scores) / n
            )
            scores.activity.correct_type = sum(s.correct_type for s in activity_scores)
            scores.activity.total = sum(s.total for s in activity_scores)

        if social_scores:
            n = len(social_scores)
            scores.social.context_accuracy = sum(s.context_accuracy for s in social_scores) / n
            scores.social.participant_f1 = sum(s.participant_f1 for s in social_scores) / n
            scores.social.count_mae = sum(s.count_mae for s in social_scores) / n
            scores.social.correct_context = sum(s.correct_context for s in social_scores)
            scores.social.total_context = sum(s.total_context for s in social_scores)

        return scores


def run_accuracy_benchmark(
    processor: Callable[[str], dict[str, Any]],
    dataset_path: Path | None = None,
    filter_tags: list[str] | None = None,
    filter_difficulty: list[str] | None = None,
) -> BenchmarkResult:
    """
    Convenience function to run accuracy benchmark.

    Args:
        processor: Function that processes memory text and returns structured output.
        dataset_path: Optional path to custom dataset.
        filter_tags: Filter memories by tags.
        filter_difficulty: Filter memories by difficulty.

    Returns:
        BenchmarkResult with all scores.
    """
    benchmark = AccuracyBenchmark(
        dataset_path=dataset_path,
        filter_tags=filter_tags,
        filter_difficulty=filter_difficulty,
    )
    return benchmark.run(processor)


# =============================================================================
# Baseline Processors for Testing
# =============================================================================


def random_baseline_processor(text: str) -> dict[str, Any]:
    """Random baseline processor for sanity checking."""
    import random

    return {
        "entities": [],
        "emotions": {
            "primary": random.choice(["joy", "sadness", "neutral"]),
            "valence": random.uniform(-1, 1),
            "arousal": random.uniform(0, 1),
            "secondary": [],
        },
        "activity": {
            "type": random.choice(["meal", "travel", "celebration"]),
            "subtype": None,
            "is_celebration": random.choice([True, False]),
        },
        "social": {
            "context": random.choice(["nuclear_family", "couple", "solo"]),
            "participants": [],
            "participant_count": random.randint(1, 5),
        },
    }


def empty_baseline_processor(text: str) -> dict[str, Any]:
    """Empty baseline processor for worst-case scoring."""
    return {
        "entities": [],
        "emotions": {
            "primary": "neutral",
            "valence": 0.0,
            "arousal": 0.5,
            "secondary": [],
        },
        "activity": {
            "type": "daily",
            "subtype": None,
            "is_celebration": False,
        },
        "social": {
            "context": "solo",
            "participants": [],
            "participant_count": 1,
        },
    }
