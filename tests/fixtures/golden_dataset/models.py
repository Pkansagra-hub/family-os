"""
Golden Dataset Pydantic Models.

Defines validated data models for golden dataset annotations.
These models are used to:
1. Validate dataset integrity
2. Type-check module outputs against ground truth
3. Calculate accuracy metrics

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Entity Enums
# =============================================================================


class EntityType(str, Enum):
    """Named entity types for NER annotation."""

    # Core spaCy-compatible types
    PERSON = "PERSON"
    ORG = "ORG"
    GPE = "GPE"
    LOC = "LOC"
    DATE = "DATE"
    TIME = "TIME"
    MONEY = "MONEY"
    EVENT = "EVENT"
    PRODUCT = "PRODUCT"
    FOOD = "FOOD"
    ACTIVITY = "ACTIVITY"

    # Family-specific extensions
    PET = "PET"
    NICKNAME = "NICKNAME"


class FamilyRole(str, Enum):
    """Family and social relationship roles."""

    # Immediate family
    SPOUSE = "spouse"
    PARTNER = "partner"
    CHILD = "child"
    PARENT = "parent"
    SELF = "self"

    # Extended family
    SIBLING = "sibling"
    GRANDPARENT = "grandparent"
    GRANDCHILD = "grandchild"
    AUNT_UNCLE = "aunt_uncle"
    COUSIN = "cousin"
    IN_LAW = "in_law"

    # Non-family
    FRIEND = "friend"
    COLLEAGUE = "colleague"
    NEIGHBOR = "neighbor"
    ACQUAINTANCE = "acquaintance"
    PROFESSIONAL = "professional"
    UNKNOWN = "unknown"


# =============================================================================
# Emotion Enums
# =============================================================================


class EmotionLabel(str, Enum):
    """Primary and secondary emotion labels."""

    # Primary emotions (Ekman + extensions)
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    NEUTRAL = "neutral"

    # Secondary/complex emotions
    LOVE = "love"
    GRATITUDE = "gratitude"
    PRIDE = "pride"
    NOSTALGIA = "nostalgia"
    EXCITEMENT = "excitement"
    CONTENTMENT = "contentment"
    RELIEF = "relief"
    HOPE = "hope"
    GUILT = "guilt"
    EMBARRASSMENT = "embarrassment"
    FRUSTRATION = "frustration"
    DISAPPOINTMENT = "disappointment"
    WORRY = "worry"
    LONELINESS = "loneliness"
    JEALOUSY = "jealousy"
    EMPATHY = "empathy"

    # Additional emotions for grief/loss/calm contexts
    GRIEF = "grief"
    PEACE = "peace"


# =============================================================================
# Activity Enums
# =============================================================================


class ActivityType(str, Enum):
    """Activity category types."""

    MEAL = "meal"
    CELEBRATION = "celebration"
    TRAVEL = "travel"
    RECREATION = "recreation"
    FAMILY = "family"
    SOCIAL = "social"
    WORK_SCHOOL = "work_school"
    RELIGIOUS = "religious"
    DAILY = "daily"


class ActivitySubtype(str, Enum):
    """Activity subtypes within categories."""

    # Meals
    BREAKFAST = "breakfast"
    BRUNCH = "brunch"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    PICNIC = "picnic"
    BARBECUE = "barbecue"

    # Celebrations
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    HOLIDAY = "holiday"
    GRADUATION = "graduation"
    WEDDING = "wedding"
    BABY_SHOWER = "baby_shower"
    RETIREMENT = "retirement"
    PROMOTION = "promotion"

    # Travel
    VACATION = "vacation"
    ROAD_TRIP = "road_trip"
    FLIGHT = "flight"
    DAY_TRIP = "day_trip"
    CAMPING = "camping"
    BEACH_TRIP = "beach_trip"
    CITY_VISIT = "city_visit"

    # Recreation
    SPORTS = "sports"
    EXERCISE = "exercise"
    HIKING = "hiking"
    SWIMMING = "swimming"
    GAMING = "gaming"
    MOVIE = "movie"
    CONCERT = "concert"
    MUSEUM = "museum"
    PARK_VISIT = "park_visit"
    SHOPPING = "shopping"

    # Family
    FAMILY_DINNER = "family_dinner"
    GAME_NIGHT = "game_night"
    MOVIE_NIGHT = "movie_night"
    PLAYDATE = "playdate"
    SCHOOL_EVENT = "school_event"
    MEDICAL_VISIT = "medical_visit"
    ERRAND = "errand"

    # Social
    PARTY = "party"
    GATHERING = "gathering"
    VISIT = "visit"
    REUNION = "reunion"
    DATE_NIGHT = "date_night"
    MEETUP = "meetup"

    # Work/School
    WORK_EVENT = "work_event"
    MEETING = "meeting"
    CONFERENCE = "conference"
    PRESENTATION = "presentation"

    # Religious
    SERVICE = "service"
    CEREMONY = "ceremony"
    HOLIDAY_OBSERVANCE = "holiday_observance"

    # Daily Life
    ROUTINE = "routine"
    CHORE = "chore"
    REST = "rest"
    SELF_CARE = "self_care"


class LocationType(str, Enum):
    """Location types where activities occur."""

    HOME = "home"
    RESTAURANT = "restaurant"
    OUTDOOR = "outdoor"
    VENUE = "venue"
    TRAVEL = "travel"
    WORK = "work"
    SCHOOL = "school"
    OTHER = "other"


# =============================================================================
# Social Context Enums
# =============================================================================


class SocialContext(str, Enum):
    """Social configuration context."""

    # Family configurations
    NUCLEAR_FAMILY = "nuclear_family"
    EXTENDED_FAMILY = "extended_family"
    IMMEDIATE_FAMILY = "immediate_family"
    SOLO = "solo"
    COUPLE = "couple"

    # Social configurations
    FRIENDS = "friends"
    COLLEAGUES = "colleagues"
    MIXED = "mixed"
    COMMUNITY = "community"
    PROFESSIONAL = "professional"


class Difficulty(str, Enum):
    """Memory annotation difficulty level."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# =============================================================================
# Annotation Models
# =============================================================================


class EntityAnnotation(BaseModel):
    """A single entity annotation within a memory."""

    text: str = Field(..., min_length=1, description="Entity text as it appears")
    type: EntityType = Field(..., description="Entity type classification")
    role: Optional[FamilyRole] = Field(None, description="Family role (for PERSON)")
    normalized: Optional[str] = Field(None, description="Normalized form (e.g., 'mom' -> 'Mother')")
    span_start: Optional[int] = Field(None, ge=0, description="Character offset start")
    span_end: Optional[int] = Field(None, ge=0, description="Character offset end")

    @field_validator("span_end")
    @classmethod
    def span_end_after_start(cls, v: Optional[int], info) -> Optional[int]:
        """Ensure span_end > span_start if both provided."""
        span_start = info.data.get("span_start")
        if v is not None and span_start is not None and v <= span_start:
            raise ValueError("span_end must be greater than span_start")
        return v


class EmotionAnnotation(BaseModel):
    """Emotion annotation for a memory."""

    primary: EmotionLabel = Field(..., description="Dominant emotion")
    secondary: list[EmotionLabel] = Field(
        default_factory=list, max_length=3, description="Additional emotions (max 3)"
    )
    valence: float = Field(
        ..., ge=-1.0, le=1.0, description="Sentiment: -1 (negative) to 1 (positive)"
    )
    arousal: float = Field(..., ge=0.0, le=1.0, description="Intensity: 0 (calm) to 1 (excited)")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Annotator confidence")


class ActivityAnnotation(BaseModel):
    """Activity classification annotation."""

    type: ActivityType = Field(..., description="Activity category")
    subtype: Optional[ActivitySubtype] = Field(None, description="Specific subtype")
    is_celebration: bool = Field(False, description="Involves a celebration")
    is_recurring: bool = Field(False, description="Is a recurring activity")
    location_type: Optional[LocationType] = Field(None, description="Location type")


class SocialAnnotation(BaseModel):
    """Social context annotation."""

    context: SocialContext = Field(..., description="Social configuration")
    participants: list[FamilyRole] = Field(default_factory=list, description="Participant roles")
    participant_count: Optional[int] = Field(None, ge=1, description="Total participant count")
    is_group_activity: Optional[bool] = Field(None, description="3+ people involved")


# =============================================================================
# Ground Truth Model
# =============================================================================


class GroundTruth(BaseModel):
    """Complete ground truth annotations for a memory."""

    entities: list[EntityAnnotation] = Field(default_factory=list, description="Entity annotations")
    emotions: EmotionAnnotation = Field(..., description="Emotion annotations")
    activity: ActivityAnnotation = Field(..., description="Activity annotations")
    social: SocialAnnotation = Field(..., description="Social context annotations")


# =============================================================================
# Memory Metadata
# =============================================================================


class MemoryMetadata(BaseModel):
    """Optional metadata for a golden memory."""

    author: Optional[str] = Field(None, description="Memory author/narrator")
    date_written: Optional[str] = Field(None, description="Date memory was recorded")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    difficulty: Difficulty = Field(Difficulty.MEDIUM, description="ML difficulty")


# =============================================================================
# Complete Memory Model
# =============================================================================


class GoldenMemory(BaseModel):
    """A single annotated memory in the golden dataset."""

    id: str = Field(
        ...,
        pattern=r"^mem_[0-9]{3,6}$",
        description="Unique memory ID (e.g., mem_001)",
    )
    text: str = Field(..., min_length=10, max_length=2000, description="Memory text to analyze")
    metadata: MemoryMetadata = Field(
        default_factory=MemoryMetadata, description="Optional metadata"
    )
    ground_truth: GroundTruth = Field(..., description="Human-annotated ground truth")

    def get_entity_texts(self) -> list[str]:
        """Get all entity texts."""
        return [e.text for e in self.ground_truth.entities]

    def get_person_entities(self) -> list[EntityAnnotation]:
        """Get only PERSON entities."""
        return [e for e in self.ground_truth.entities if e.type == EntityType.PERSON]

    def get_location_entities(self) -> list[EntityAnnotation]:
        """Get location entities (GPE, LOC)."""
        return [e for e in self.ground_truth.entities if e.type in (EntityType.GPE, EntityType.LOC)]


# =============================================================================
# Dataset Container
# =============================================================================


class DatasetStatistics(BaseModel):
    """Statistics about the golden dataset."""

    total_memories: int = Field(..., ge=0)
    difficulty_counts: dict[str, int] = Field(default_factory=dict)
    activity_type_counts: dict[str, int] = Field(default_factory=dict)
    emotion_primary_counts: dict[str, int] = Field(default_factory=dict)
    avg_entities_per_memory: float = Field(0.0, ge=0.0)
    avg_participants_per_memory: float = Field(0.0, ge=0.0)


class GoldenDataset(BaseModel):
    """Container for the complete golden dataset."""

    version: str = Field("1.0.0", description="Dataset version")
    description: str = Field(
        "Golden dataset for K0 module accuracy benchmarking",
        description="Dataset description",
    )
    memories: list[GoldenMemory] = Field(default_factory=list, description="All annotated memories")

    def get_by_id(self, memory_id: str) -> Optional[GoldenMemory]:
        """Get a memory by its ID."""
        for memory in self.memories:
            if memory.id == memory_id:
                return memory
        return None

    def get_by_tag(self, tag: str) -> list[GoldenMemory]:
        """Get all memories with a specific tag."""
        return [m for m in self.memories if tag in m.metadata.tags]

    def get_by_difficulty(self, difficulty: Difficulty) -> list[GoldenMemory]:
        """Get all memories of a specific difficulty."""
        return [m for m in self.memories if m.metadata.difficulty == difficulty]

    def get_by_activity_type(self, activity_type: ActivityType) -> list[GoldenMemory]:
        """Get all memories with a specific activity type."""
        return [m for m in self.memories if m.ground_truth.activity.type == activity_type]

    def get_by_emotion(self, emotion: EmotionLabel) -> list[GoldenMemory]:
        """Get all memories with a specific primary emotion."""
        return [m for m in self.memories if m.ground_truth.emotions.primary == emotion]

    def compute_statistics(self) -> DatasetStatistics:
        """Compute statistics about the dataset."""
        if not self.memories:
            return DatasetStatistics(total_memories=0)

        difficulty_counts: dict[str, int] = {}
        activity_counts: dict[str, int] = {}
        emotion_counts: dict[str, int] = {}
        total_entities = 0
        total_participants = 0

        for memory in self.memories:
            # Difficulty distribution
            diff = memory.metadata.difficulty.value
            difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1

            # Activity distribution
            act = memory.ground_truth.activity.type.value
            activity_counts[act] = activity_counts.get(act, 0) + 1

            # Emotion distribution
            emo = memory.ground_truth.emotions.primary.value
            emotion_counts[emo] = emotion_counts.get(emo, 0) + 1

            # Aggregates
            total_entities += len(memory.ground_truth.entities)
            if memory.ground_truth.social.participant_count:
                total_participants += memory.ground_truth.social.participant_count

        return DatasetStatistics(
            total_memories=len(self.memories),
            difficulty_counts=difficulty_counts,
            activity_type_counts=activity_counts,
            emotion_primary_counts=emotion_counts,
            avg_entities_per_memory=total_entities / len(self.memories),
            avg_participants_per_memory=(
                total_participants / len(self.memories) if total_participants > 0 else 0.0
            ),
        )
