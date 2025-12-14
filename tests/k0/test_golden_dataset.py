"""
Unit tests for Golden Dataset and Benchmark infrastructure.

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

import pytest

from tests.fixtures.golden_dataset import (
    ActivityAnnotation,
    ActivityType,
    EmotionAnnotation,
    EmotionLabel,
    EntityAnnotation,
    EntityType,
    FamilyRole,
    GoldenDataset,
    GoldenMemory,
    GroundTruth,
    SocialAnnotation,
    SocialContext,
    get_golden_memories_by_tag,
    load_golden_dataset,
)
from tests.fixtures.golden_dataset.models import ActivitySubtype, Difficulty, LocationType


class TestGoldenDatasetModels:
    """Tests for Pydantic models."""

    def test_entity_annotation_valid(self):
        """Test valid entity annotation creation."""
        entity = EntityAnnotation(
            text="Sarah",
            type=EntityType.PERSON,
            role=FamilyRole.SPOUSE,
            normalized="Sarah",
        )
        assert entity.text == "Sarah"
        assert entity.type == EntityType.PERSON
        assert entity.role == FamilyRole.SPOUSE

    def test_entity_annotation_span_validation(self):
        """Test span validation (end must be after start)."""
        with pytest.raises(ValueError, match="span_end must be greater than span_start"):
            EntityAnnotation(
                text="test",
                type=EntityType.PERSON,
                span_start=10,
                span_end=5,
            )

    def test_emotion_annotation_valid(self):
        """Test valid emotion annotation creation."""
        emotion = EmotionAnnotation(
            primary=EmotionLabel.JOY,
            secondary=[EmotionLabel.LOVE, EmotionLabel.GRATITUDE],
            valence=0.9,
            arousal=0.7,
        )
        assert emotion.primary == EmotionLabel.JOY
        assert len(emotion.secondary) == 2
        assert emotion.valence == 0.9

    def test_emotion_annotation_valence_bounds(self):
        """Test valence bounds (-1 to 1)."""
        with pytest.raises(ValueError):
            EmotionAnnotation(
                primary=EmotionLabel.JOY,
                valence=1.5,  # Out of bounds
                arousal=0.5,
            )

    def test_activity_annotation_valid(self):
        """Test valid activity annotation creation."""
        activity = ActivityAnnotation(
            type=ActivityType.MEAL,
            subtype=ActivitySubtype.DINNER,
            is_celebration=False,
            location_type=LocationType.RESTAURANT,
        )
        assert activity.type == ActivityType.MEAL
        assert activity.subtype == ActivitySubtype.DINNER

    def test_social_annotation_valid(self):
        """Test valid social annotation creation."""
        social = SocialAnnotation(
            context=SocialContext.NUCLEAR_FAMILY,
            participants=[FamilyRole.SPOUSE, FamilyRole.CHILD],
            participant_count=3,
            is_group_activity=True,
        )
        assert social.context == SocialContext.NUCLEAR_FAMILY
        assert len(social.participants) == 2

    def test_ground_truth_complete(self):
        """Test complete ground truth creation."""
        ground_truth = GroundTruth(
            entities=[
                EntityAnnotation(text="Sarah", type=EntityType.PERSON, role=FamilyRole.SPOUSE),
            ],
            emotions=EmotionAnnotation(
                primary=EmotionLabel.JOY,
                secondary=[],
                valence=0.8,
                arousal=0.6,
            ),
            activity=ActivityAnnotation(
                type=ActivityType.MEAL,
                is_celebration=False,
            ),
            social=SocialAnnotation(
                context=SocialContext.COUPLE,
                participants=[FamilyRole.SPOUSE],
            ),
        )
        assert len(ground_truth.entities) == 1
        assert ground_truth.emotions.primary == EmotionLabel.JOY

    def test_golden_memory_id_pattern(self):
        """Test memory ID pattern validation."""
        with pytest.raises(ValueError):
            GoldenMemory(
                id="invalid_id",  # Must match mem_NNN pattern
                text="Test memory text",
                ground_truth=GroundTruth(
                    entities=[],
                    emotions=EmotionAnnotation(
                        primary=EmotionLabel.NEUTRAL,
                        valence=0.0,
                        arousal=0.5,
                    ),
                    activity=ActivityAnnotation(type=ActivityType.DAILY),
                    social=SocialAnnotation(context=SocialContext.SOLO),
                ),
            )

    def test_golden_memory_text_min_length(self):
        """Test memory text minimum length."""
        with pytest.raises(ValueError):
            GoldenMemory(
                id="mem_001",
                text="Short",  # Too short
                ground_truth=GroundTruth(
                    entities=[],
                    emotions=EmotionAnnotation(
                        primary=EmotionLabel.NEUTRAL,
                        valence=0.0,
                        arousal=0.5,
                    ),
                    activity=ActivityAnnotation(type=ActivityType.DAILY),
                    social=SocialAnnotation(context=SocialContext.SOLO),
                ),
            )


class TestGoldenDatasetLoader:
    """Tests for dataset loading functionality."""

    def test_load_golden_dataset(self):
        """Test loading the built-in golden dataset."""
        dataset = load_golden_dataset()
        assert isinstance(dataset, GoldenDataset)
        assert len(dataset.memories) > 0
        assert dataset.version == "1.0.0"

    def test_dataset_statistics(self):
        """Test computing dataset statistics."""
        dataset = load_golden_dataset()
        stats = dataset.compute_statistics()

        assert stats.total_memories == len(dataset.memories)
        assert stats.avg_entities_per_memory > 0
        assert "easy" in stats.difficulty_counts or "medium" in stats.difficulty_counts

    def test_get_by_id(self):
        """Test getting memory by ID."""
        dataset = load_golden_dataset()
        memory = dataset.get_by_id("mem_001")

        assert memory is not None
        assert memory.id == "mem_001"

    def test_get_by_tag(self):
        """Test filtering by tag."""
        dataset = load_golden_dataset()
        meal_memories = dataset.get_by_tag("meal")

        assert len(meal_memories) > 0
        for mem in meal_memories:
            assert "meal" in mem.metadata.tags

    def test_get_by_difficulty(self):
        """Test filtering by difficulty."""
        dataset = load_golden_dataset()
        easy_memories = dataset.get_by_difficulty(Difficulty.EASY)

        assert len(easy_memories) > 0
        for mem in easy_memories:
            assert mem.metadata.difficulty == Difficulty.EASY

    def test_get_by_activity_type(self):
        """Test filtering by activity type."""
        dataset = load_golden_dataset()
        celebrations = dataset.get_by_activity_type(ActivityType.CELEBRATION)

        assert len(celebrations) > 0
        for mem in celebrations:
            assert mem.ground_truth.activity.type == ActivityType.CELEBRATION

    def test_get_golden_memories_by_tag(self):
        """Test convenience function for tag filtering."""
        memories = get_golden_memories_by_tag("birthday")

        assert len(memories) > 0
        for mem in memories:
            assert "birthday" in mem.metadata.tags


class TestGoldenMemoryHelpers:
    """Tests for GoldenMemory helper methods."""

    def test_get_entity_texts(self):
        """Test getting all entity texts."""
        dataset = load_golden_dataset()
        memory = dataset.get_by_id("mem_001")

        assert memory is not None
        texts = memory.get_entity_texts()
        assert len(texts) > 0
        assert all(isinstance(t, str) for t in texts)

    def test_get_person_entities(self):
        """Test getting only PERSON entities."""
        dataset = load_golden_dataset()
        memory = dataset.get_by_id("mem_001")

        assert memory is not None
        persons = memory.get_person_entities()
        assert len(persons) > 0
        for p in persons:
            assert p.type == EntityType.PERSON

    def test_get_location_entities(self):
        """Test getting location entities."""
        dataset = load_golden_dataset()
        # Find a memory with location
        for memory in dataset.memories:
            locs = memory.get_location_entities()
            if locs:
                for loc in locs:
                    assert loc.type in (EntityType.GPE, EntityType.LOC)
                break


class TestEmotionLabels:
    """Tests for emotion label coverage."""

    def test_all_primary_emotions_valid(self):
        """Test all primary emotions are valid."""
        primary_emotions = [
            EmotionLabel.JOY,
            EmotionLabel.SADNESS,
            EmotionLabel.ANGER,
            EmotionLabel.FEAR,
            EmotionLabel.SURPRISE,
            EmotionLabel.DISGUST,
            EmotionLabel.TRUST,
            EmotionLabel.ANTICIPATION,
            EmotionLabel.NEUTRAL,
        ]
        for emotion in primary_emotions:
            assert emotion.value in [e.value for e in EmotionLabel]

    def test_grief_and_peace_added(self):
        """Test that grief and peace emotions were added."""
        assert EmotionLabel.GRIEF.value == "grief"
        assert EmotionLabel.PEACE.value == "peace"


class TestDatasetCoverage:
    """Tests for dataset content coverage."""

    def test_dataset_has_100_memories(self):
        """Test dataset has at least 100 memories."""
        dataset = load_golden_dataset()
        assert len(dataset.memories) >= 100

    def test_difficulty_distribution(self):
        """Test dataset has all difficulty levels."""
        dataset = load_golden_dataset()
        difficulties = {m.metadata.difficulty for m in dataset.memories}

        assert Difficulty.EASY in difficulties
        assert Difficulty.MEDIUM in difficulties
        assert Difficulty.HARD in difficulties

    def test_activity_type_diversity(self):
        """Test dataset covers multiple activity types."""
        dataset = load_golden_dataset()
        activity_types = {m.ground_truth.activity.type for m in dataset.memories}

        # Should have at least 5 different activity types
        assert len(activity_types) >= 5

    def test_emotion_diversity(self):
        """Test dataset covers multiple primary emotions."""
        dataset = load_golden_dataset()
        emotions = {m.ground_truth.emotions.primary for m in dataset.memories}

        # Should have at least 5 different primary emotions
        assert len(emotions) >= 5

    def test_social_context_diversity(self):
        """Test dataset covers multiple social contexts."""
        dataset = load_golden_dataset()
        contexts = {m.ground_truth.social.context for m in dataset.memories}

        # Should have at least 4 different social contexts
        assert len(contexts) >= 4
