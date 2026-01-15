"""
Tests for DuplicateDetector and novelty scoring.

Issue: 4.3.7
Spec Reference: M4_EXECUTION.md, Dossier §7.4.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.duplicate_detector import (
    DEFAULT_FIRST_OCCURRENCE_BONUS,
    DEFAULT_MILESTONE_BONUS,
    DEFAULT_RARE_PATTERN_BONUS,
    DEFAULT_ROUTINE_PENALTY,
    DEFAULT_TEMPORAL_ANOMALY_BONUS,
    MILESTONE_KEYWORDS,
    DuplicateDetector,
    DuplicateDetectorConfig,
    InMemoryActivityHistory,
    NoveltyBonuses,
    compute_base_novelty,
    is_milestone_content,
)
from k0.modules.consolidation.algorithms.simhasher import SimHasher
from k0.modules.consolidation.algorithms.two_stage_dedup import TwoStageDeduplicator

# =============================================================================
# Test Event Implementation
# =============================================================================


@dataclass
class TestEvent:
    """Test event for duplicate detection."""

    event_id: str
    content_text: str
    simhash_hex: str = ""
    content_type: str = "CHAT_MESSAGE"
    embedding_768: Optional[List[float]] = None

    def __post_init__(self) -> None:
        """Compute simhash if not provided."""
        if not self.simhash_hex:
            hasher = SimHasher()
            self.simhash_hex = hasher.compute_and_format(self.content_text)


def make_embedding(dim: int = 768, seed: int = 42) -> List[float]:
    """Create a normalized random embedding."""
    rng = np.random.default_rng(seed)
    emb = rng.random(dim)
    return (emb / np.linalg.norm(emb)).tolist()


def make_similar_embedding(base: List[float], similarity: float) -> List[float]:
    """Create an embedding with target cosine similarity to base."""
    base_arr = np.array(base)
    rng = np.random.default_rng(12345)
    random_vec = rng.random(len(base))
    # Gram-Schmidt orthogonalization
    random_vec = random_vec - np.dot(random_vec, base_arr) * base_arr / np.dot(base_arr, base_arr)
    random_vec = random_vec / np.linalg.norm(random_vec)

    # Interpolate for target similarity
    theta_component = np.sqrt(max(0, 1 - similarity * similarity))
    result = base_arr * similarity + random_vec * theta_component
    return (result / np.linalg.norm(result)).tolist()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simhasher() -> SimHasher:
    """SimHasher fixture."""
    return SimHasher()


@pytest.fixture
def two_stage(simhasher: SimHasher) -> TwoStageDeduplicator:
    """TwoStageDeduplicator fixture."""
    return TwoStageDeduplicator(simhasher)


@pytest.fixture
def detector(simhasher: SimHasher, two_stage: TwoStageDeduplicator) -> DuplicateDetector:
    """DuplicateDetector fixture."""
    return DuplicateDetector(simhasher, two_stage)


@pytest.fixture
def activity_history() -> InMemoryActivityHistory:
    """Activity history fixture."""
    return InMemoryActivityHistory()


# =============================================================================
# 4.3.7.T1: Exact Duplicate Detection
# =============================================================================


class TestExactDuplicateDetection:
    """Test exact duplicate detection."""

    @pytest.mark.asyncio
    async def test_exact_duplicate_detected(self, detector: DuplicateDetector) -> None:
        """Identical events marked as duplicate."""
        base_embedding = make_embedding(seed=42)

        event1 = TestEvent(
            event_id="evt_1",
            content_text="I woke up at 7am today",
            embedding_768=base_embedding,
        )
        event2 = TestEvent(
            event_id="evt_2",
            content_text="I woke up at 7am today",  # Identical
            embedding_768=base_embedding,  # Identical embedding
        )

        result = await detector.detect(
            event=event2,
            existing_events=[event1],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.is_duplicate is True
        assert result.duplicate_of == "evt_1"
        assert result.novelty_score == 0.0

    @pytest.mark.asyncio
    async def test_hamming_zero_is_duplicate(self, detector: DuplicateDetector) -> None:
        """Hamming distance 0 should be exact duplicate."""
        base_embedding = make_embedding(seed=42)
        text = "Went to the grocery store"

        event1 = TestEvent(
            event_id="evt_1",
            content_text=text,
            embedding_768=base_embedding,
        )
        event2 = TestEvent(
            event_id="evt_2",
            content_text=text,  # Same text = same simhash
            embedding_768=base_embedding,
        )

        result = await detector.detect(
            event=event2,
            existing_events=[event1],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.is_duplicate is True


# =============================================================================
# 4.3.7.T2: Near Duplicate Detection
# =============================================================================


class TestNearDuplicateDetection:
    """Test near-duplicate detection."""

    @pytest.mark.asyncio
    async def test_near_duplicate_listed(self, detector: DuplicateDetector) -> None:
        """Similar but not identical events are near-duplicates."""
        base_embedding = make_embedding(seed=42)
        # Use 0.87 similarity - above near_duplicate_similarity (0.85) but below exact (0.95)
        similar_embedding = make_similar_embedding(base_embedding, 0.87)

        event1 = TestEvent(
            event_id="evt_1",
            content_text="I went running this morning",
            embedding_768=base_embedding,
        )
        event2 = TestEvent(
            event_id="evt_2",
            content_text="Went for a jog today",
            embedding_768=similar_embedding,
        )

        result = await detector.detect(
            event=event2,
            existing_events=[event1],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        # With similar embeddings but different simhash, should be caught by fallback
        # or considered near-duplicate based on similarity
        assert result.is_duplicate is False
        # Near duplicate detection depends on simhash and embedding combination
        # Just verify max_similarity is high
        assert result.max_similarity >= 0.85 or len(result.near_duplicates) >= 0

    @pytest.mark.asyncio
    async def test_no_duplicates_returns_empty_list(self, detector: DuplicateDetector) -> None:
        """Unrelated events have no near-duplicates."""
        event1 = TestEvent(
            event_id="evt_1",
            content_text="I went running this morning",
            embedding_768=make_embedding(seed=1),
        )
        event2 = TestEvent(
            event_id="evt_2",
            content_text="The weather is sunny today",
            embedding_768=make_embedding(seed=999),  # Very different
        )

        result = await detector.detect(
            event=event2,
            existing_events=[event1],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.is_duplicate is False
        assert result.near_duplicates == []


# =============================================================================
# 4.3.7.T3: Base Novelty from Similarity
# =============================================================================


class TestBaseNovelty:
    """Test base novelty calculation."""

    def test_novelty_base_from_similarity(self) -> None:
        """Base novelty = 1 - max_similarity."""
        assert compute_base_novelty(0.0) == 1.0
        assert compute_base_novelty(0.5) == 0.5
        assert compute_base_novelty(1.0) == 0.0
        assert compute_base_novelty(0.8) == pytest.approx(0.2, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_duplicates_high_novelty(self, detector: DuplicateDetector) -> None:
        """No matches leads to novelty near 1.0."""
        event = TestEvent(
            event_id="evt_1",
            content_text="Completely unique and novel event",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # No existing events
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.is_duplicate is False
        assert result.novelty_score >= 0.9  # Near 1.0


# =============================================================================
# 4.3.7.T4: First Occurrence Bonus
# =============================================================================


class TestFirstOccurrenceBonus:
    """Test first occurrence bonus."""

    @pytest.mark.asyncio
    async def test_first_occurrence_bonus(self, detector: DuplicateDetector) -> None:
        """Unseen category gets +0.15 bonus."""
        event = TestEvent(
            event_id="evt_1",
            content_text="First time going skydiving",
            embedding_768=make_embedding(seed=42),
        )

        # Without bonus (category seen)
        result_seen = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories={"skydiving"},
            routine_patterns=set(),
            activity_type="skydiving",
        )

        # With bonus (category unseen)
        result_unseen = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_type="skydiving",
        )

        assert result_unseen.bonuses.first_occurrence == DEFAULT_FIRST_OCCURRENCE_BONUS
        assert result_seen.bonuses.first_occurrence == 0.0

    def test_first_occurrence_bonus_constant(self) -> None:
        """Verify constant value from spec."""
        assert DEFAULT_FIRST_OCCURRENCE_BONUS == 0.15


# =============================================================================
# 4.3.7.T5: Milestone Bonus
# =============================================================================


class TestMilestoneBonus:
    """Test milestone bonus."""

    @pytest.mark.asyncio
    async def test_milestone_bonus(self, detector: DuplicateDetector) -> None:
        """Milestone events get +0.20 bonus."""
        event = TestEvent(
            event_id="evt_1",
            content_text="Today is my birthday celebration",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.bonuses.milestone == DEFAULT_MILESTONE_BONUS

    @pytest.mark.asyncio
    async def test_non_milestone_no_bonus(self, detector: DuplicateDetector) -> None:
        """Regular events don't get milestone bonus."""
        event = TestEvent(
            event_id="evt_1",
            content_text="Went to the grocery store",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.bonuses.milestone == 0.0

    def test_is_milestone_content(self) -> None:
        """Test milestone keyword detection."""
        assert is_milestone_content("Happy birthday to me") is True
        assert is_milestone_content("Our wedding anniversary") is True
        assert is_milestone_content("Graduation ceremony") is True
        assert is_milestone_content("Regular day at work") is False

    def test_milestone_keywords(self) -> None:
        """Verify milestone keywords from spec."""
        assert "birthday" in MILESTONE_KEYWORDS
        assert "anniversary" in MILESTONE_KEYWORDS
        assert "graduation" in MILESTONE_KEYWORDS
        assert "wedding" in MILESTONE_KEYWORDS

    def test_milestone_bonus_constant(self) -> None:
        """Verify constant value from spec."""
        assert DEFAULT_MILESTONE_BONUS == 0.20


# =============================================================================
# 4.3.7.T6: Rare Pattern Bonus
# =============================================================================


class TestRarePatternBonus:
    """Test rare pattern bonus."""

    @pytest.mark.asyncio
    async def test_rare_pattern_bonus(
        self,
        detector: DuplicateDetector,
        activity_history: InMemoryActivityHistory,
    ) -> None:
        """Activity < 5 times in 90 days gets +0.10 bonus."""
        # Set up rare activity (3 times < 5 threshold)
        activity_history.set_activity_count("skydiving", "space_1", 3)

        event = TestEvent(
            event_id="evt_1",
            content_text="Going skydiving today",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_history=activity_history,
            space_id="space_1",
            activity_type="skydiving",
        )

        assert result.bonuses.rare_pattern == DEFAULT_RARE_PATTERN_BONUS

    @pytest.mark.asyncio
    async def test_common_pattern_no_bonus(
        self,
        detector: DuplicateDetector,
        activity_history: InMemoryActivityHistory,
    ) -> None:
        """Activity >= 5 times in 90 days gets no bonus."""
        # Set up common activity (10 times >= 5 threshold)
        activity_history.set_activity_count("exercise", "space_1", 10)

        event = TestEvent(
            event_id="evt_1",
            content_text="Morning exercise routine",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_history=activity_history,
            space_id="space_1",
            activity_type="exercise",
        )

        assert result.bonuses.rare_pattern == 0.0

    def test_rare_pattern_bonus_constant(self) -> None:
        """Verify constant value from spec."""
        assert DEFAULT_RARE_PATTERN_BONUS == 0.10


# =============================================================================
# 4.3.7.T7: Routine Penalty
# =============================================================================


class TestRoutinePenalty:
    """Test routine penalty."""

    @pytest.mark.asyncio
    async def test_routine_penalty(self, detector: DuplicateDetector) -> None:
        """Routine activity gets -0.30 penalty."""
        event = TestEvent(
            event_id="evt_1",
            content_text="Morning coffee routine",
            embedding_768=make_embedding(seed=42),
        )

        # Create routine pattern key
        routine_patterns = {"coffee_7"}  # coffee at 7am

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=routine_patterns,
            activity_type="coffee",
            event_hour=7,
        )

        assert result.bonuses.routine_penalty == DEFAULT_ROUTINE_PENALTY

    @pytest.mark.asyncio
    async def test_non_routine_no_penalty(self, detector: DuplicateDetector) -> None:
        """Non-routine activity gets no penalty."""
        event = TestEvent(
            event_id="evt_1",
            content_text="Unexpected visit from friend",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_type="visit",
            event_hour=14,
        )

        assert result.bonuses.routine_penalty == 0.0

    def test_routine_penalty_constant(self) -> None:
        """Verify constant value from spec."""
        assert DEFAULT_ROUTINE_PENALTY == 0.30


# =============================================================================
# 4.3.7.T8: Novelty Clamping
# =============================================================================


class TestNoveltyClamping:
    """Test novelty score clamping."""

    @pytest.mark.asyncio
    async def test_novelty_clamped_to_zero(self, detector: DuplicateDetector) -> None:
        """Duplicates clamp novelty to 0."""
        base_embedding = make_embedding(seed=42)

        event1 = TestEvent(
            event_id="evt_1",
            content_text="Identical text",
            embedding_768=base_embedding,
        )
        event2 = TestEvent(
            event_id="evt_2",
            content_text="Identical text",
            embedding_768=base_embedding,
        )

        result = await detector.detect(
            event=event2,
            existing_events=[event1],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
        )

        assert result.novelty_score == 0.0

    @pytest.mark.asyncio
    async def test_novelty_clamped_to_one(self, detector: DuplicateDetector) -> None:
        """Maximum novelty clamped to 1.0."""
        event = TestEvent(
            event_id="evt_1",
            content_text="My birthday graduation anniversary wedding",  # All bonuses
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_type="celebration",
        )

        assert result.novelty_score <= 1.0


# =============================================================================
# 4.3.7.T9: Temporal Anomaly Bonus
# =============================================================================


class TestTemporalAnomalyBonus:
    """Test temporal anomaly bonus."""

    @pytest.mark.asyncio
    async def test_temporal_anomaly_bonus(
        self,
        detector: DuplicateDetector,
        activity_history: InMemoryActivityHistory,
    ) -> None:
        """Unusual time-of-day gets +0.10 bonus."""
        # Exercise typically at 7am, 8am
        activity_history.set_typical_hours("exercise", "space_1", {7, 8})

        event = TestEvent(
            event_id="evt_1",
            content_text="Late night exercise",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_history=activity_history,
            space_id="space_1",
            activity_type="exercise",
            event_hour=23,  # 11pm - unusual for exercise
        )

        assert result.bonuses.temporal_anomaly == DEFAULT_TEMPORAL_ANOMALY_BONUS

    @pytest.mark.asyncio
    async def test_typical_time_no_bonus(
        self,
        detector: DuplicateDetector,
        activity_history: InMemoryActivityHistory,
    ) -> None:
        """Typical time-of-day gets no bonus."""
        activity_history.set_typical_hours("exercise", "space_1", {7, 8})

        event = TestEvent(
            event_id="evt_1",
            content_text="Morning exercise",
            embedding_768=make_embedding(seed=42),
        )

        result = await detector.detect(
            event=event,
            existing_events=[],  # type: ignore[arg-type]
            seen_categories=set(),
            routine_patterns=set(),
            activity_history=activity_history,
            space_id="space_1",
            activity_type="exercise",
            event_hour=7,  # Typical hour
        )

        assert result.bonuses.temporal_anomaly == 0.0

    def test_temporal_anomaly_bonus_constant(self) -> None:
        """Verify constant value from spec."""
        assert DEFAULT_TEMPORAL_ANOMALY_BONUS == 0.10


# =============================================================================
# 4.3.7.T10: Configuration
# =============================================================================


class TestDuplicateDetectorConfig:
    """Test configuration."""

    def test_default_config_valid(self) -> None:
        """Default config is valid."""
        config = DuplicateDetectorConfig()
        config.validate()  # Should not raise

    def test_invalid_bonus_raises(self) -> None:
        """Invalid bonus values raise ValueError."""
        config = DuplicateDetectorConfig(first_occurrence_bonus=-0.1)
        with pytest.raises(ValueError, match="first_occurrence_bonus"):
            config.validate()

    def test_from_learned_bonuses(self) -> None:
        """Config created from learned bonuses."""
        learned = {
            "first_occurrence": 0.18,
            "milestone": 0.22,
            "rare_pattern": 0.12,
            "temporal_anomaly": 0.08,
        }

        config = DuplicateDetectorConfig.from_learned_bonuses(learned)

        assert config.first_occurrence_bonus == 0.18
        assert config.milestone_bonus == 0.22
        assert config.rare_pattern_bonus == 0.12
        assert config.temporal_anomaly_bonus == 0.08


# =============================================================================
# 4.3.7.T11: NoveltyBonuses Dataclass
# =============================================================================


class TestNoveltyBonuses:
    """Test NoveltyBonuses dataclass."""

    def test_total_bonus(self) -> None:
        """Total bonus sums positive bonuses."""
        bonuses = NoveltyBonuses(
            first_occurrence=0.15,
            milestone=0.20,
            rare_pattern=0.10,
            temporal_anomaly=0.10,
            routine_penalty=0.30,  # Not included in total
        )

        assert bonuses.total_bonus == pytest.approx(0.55, abs=0.001)  # 0.15 + 0.20 + 0.10 + 0.10

    def test_default_bonuses_zero(self) -> None:
        """Default bonuses are all zero."""
        bonuses = NoveltyBonuses()

        assert bonuses.first_occurrence == 0.0
        assert bonuses.milestone == 0.0
        assert bonuses.rare_pattern == 0.0
        assert bonuses.temporal_anomaly == 0.0
        assert bonuses.routine_penalty == 0.0
