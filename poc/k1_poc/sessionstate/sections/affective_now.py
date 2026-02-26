"""
AffectiveNowSection - Current Emotional State (HOT CORE)
=========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.6 (affective_now)

This section tracks the current emotional state of the conversation using
Russell's circumplex model (valence, arousal, dominance). Used for empathetic
response generation, tone adjustment, and user experience optimization.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/affective_now_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- current_emotion: string ("happy", "frustrated", "curious", etc.)
- intensity: float (0.0 to 1.0)
- dimensions: EmotionDimensions (valence, arousal, dominance)
- trajectory: EmotionTrajectory (INCREASING, STABLE, DECREASING)
- recent_emotions: [EmotionSnapshot] - Last 5 turns for trajectory calc
- confidence: float
- source: string ("ultrabert", "explicit", "inferred")
- last_updated_ms: int64
- last_significant_change_ms: int64
- empathy_needed: bool
- celebration_appropriate: bool
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    AffectiveNowSection as FBAffectiveNowSection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.AffectiveNowSection import (
    AffectiveNowSectionAddCelebrationAppropriate,
    AffectiveNowSectionAddConfidence,
    AffectiveNowSectionAddCurrentEmotion,
    AffectiveNowSectionAddDimensions,
    AffectiveNowSectionAddEmpathyNeeded,
    AffectiveNowSectionAddHeader,
    AffectiveNowSectionAddIntensity,
    AffectiveNowSectionAddLastSignificantChangeMs,
    AffectiveNowSectionAddLastUpdatedMs,
    AffectiveNowSectionAddRecentEmotions,
    AffectiveNowSectionAddSource,
    AffectiveNowSectionAddTrajectory,
    AffectiveNowSectionEnd,
    AffectiveNowSectionStart,
    AffectiveNowSectionStartRecentEmotionsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.EmotionDimensions import (
    EmotionDimensionsAddArousal,
    EmotionDimensionsAddDominance,
    EmotionDimensionsAddValence,
    EmotionDimensionsEnd,
    EmotionDimensionsStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.EmotionSnapshot import (
    EmotionSnapshotAddArousal,
    EmotionSnapshotAddEmotion,
    EmotionSnapshotAddIntensity,
    EmotionSnapshotAddTimestampMs,
    EmotionSnapshotAddTurnNumber,
    EmotionSnapshotAddValence,
    EmotionSnapshotEnd,
    EmotionSnapshotStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)

# =============================================================================
# Enums (matching FlatBuffer schema)
# =============================================================================


class EmotionTrajectory(IntEnum):
    """Emotional trajectory direction (matches common.fbs)."""

    INCREASING = 0
    STABLE = 1
    DECREASING = 2


# =============================================================================
# Data Classes matching FlatBuffer schema
# =============================================================================


@dataclass
class EmotionDimensions:
    """
    Core emotion dimensions (Russell's circumplex model).

    Maps to EmotionDimensions table in affective_now_section.fbs:
    - valence: float (-1.0 to +1.0) - negative to positive
    - arousal: float (0.0 to 1.0) - calm to excited
    - dominance: float (0.0 to 1.0) - submissive to dominant (optional)
    """

    valence: float = 0.0  # -1.0 (negative) to +1.0 (positive)
    arousal: float = 0.5  # 0.0 (calm) to 1.0 (excited)
    dominance: float = 0.5  # 0.0 (submissive) to 1.0 (dominant)

    def __post_init__(self):
        """Clamp values to valid ranges."""
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))
        self.dominance = max(0.0, min(1.0, self.dominance))

    @property
    def quadrant(self) -> str:
        """
        Get emotion quadrant based on valence and arousal.

        Returns:
            Quadrant name: "happy-excited", "calm-content", "sad-depressed", "angry-anxious"
        """
        if self.valence >= 0:
            return "happy-excited" if self.arousal >= 0.5 else "calm-content"
        else:
            return "angry-anxious" if self.arousal >= 0.5 else "sad-depressed"


@dataclass
class EmotionSnapshot:
    """
    Historical emotion snapshot for trajectory calculation.

    Maps to EmotionSnapshot table in affective_now_section.fbs:
    - turn_number: uint16
    - emotion: string
    - intensity: float
    - valence: float
    - arousal: float
    - timestamp_ms: int64
    """

    turn_number: int
    emotion: str
    intensity: float = 0.5
    valence: float = 0.0
    arousal: float = 0.5
    timestamp_ms: int = 0

    def __post_init__(self):
        """Clamp values and set defaults."""
        self.intensity = max(0.0, min(1.0, self.intensity))
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))
        if self.timestamp_ms == 0:
            self.timestamp_ms = int(time.time() * 1000)


# =============================================================================
# Known Emotion Categories
# =============================================================================

# Basic emotions from UltraBERT and common classification systems
KNOWN_EMOTIONS = frozenset(
    {
        # Positive
        "happy",
        "joyful",
        "excited",
        "content",
        "grateful",
        "hopeful",
        "proud",
        "amused",
        "loving",
        "relieved",
        # Negative
        "sad",
        "frustrated",
        "angry",
        "anxious",
        "fearful",
        "disappointed",
        "disgusted",
        "embarrassed",
        "guilty",
        "jealous",
        # Neutral/Cognitive
        "neutral",
        "curious",
        "confused",
        "surprised",
        "bored",
        "interested",
        "skeptical",
        "contemplative",
        # Intensity modifiers
        "urgent",
        "calm",
        "stressed",
        "relaxed",
    }
)

# Emotions that indicate empathy is needed
EMPATHY_EMOTIONS = frozenset(
    {
        "frustrated",
        "angry",
        "sad",
        "disappointed",
        "anxious",
        "fearful",
        "embarrassed",
        "guilty",
        "stressed",
        "confused",
    }
)

# Emotions that indicate celebration is appropriate
CELEBRATION_EMOTIONS = frozenset(
    {
        "happy",
        "joyful",
        "excited",
        "proud",
        "grateful",
        "relieved",
    }
)


# =============================================================================
# AffectiveNowSection Implementation
# =============================================================================


class AffectiveNowSection:
    """
    Affective Now Section - current emotional state.

    This section tracks the user's current emotional state based on sentiment
    analysis and explicit signals. Used for empathetic response generation
    and conversation tone adjustment.

    Budget: 4KB (4096 bytes)
    Tier: HOT CORE
    Eviction: Never (section stays, but resets on session end)

    FlatBuffer Schema: affective_now_section.fbs
    Serialization Target: <100 microseconds

    Contents per schema:
    - current_emotion: string - Primary detected emotion
    - intensity: float (0-1) - Emotion strength
    - dimensions: EmotionDimensions - Valence, arousal, dominance
    - trajectory: EmotionTrajectory - Direction of change
    - recent_emotions: [EmotionSnapshot] - Last 5 turns
    - confidence: float - Detection confidence
    - source: string - Detection source
    - last_updated_ms: int64 - Last update time
    - last_significant_change_ms: int64 - Last major shift
    - empathy_needed: bool - Negative trajectory flag
    - celebration_appropriate: bool - Positive achievement flag

    Example:
        section = AffectiveNowSection(session_id="sess-123")

        # Update from sentiment analysis
        section.update(
            emotion="frustrated",
            intensity=0.7,
            valence=-0.5,
            arousal=0.6,
            source="ultrabert",
        )

        # Check if empathy is needed
        if section.empathy_needed:
            # Adjust response tone

        # Get trajectory for trend detection
        trajectory = section.trajectory
    """

    BUDGET_BYTES = 4096  # 4KB
    TIER = "hot"
    CAN_EVICT = False  # Section stays, resets on session end
    SECTION_NAME = "affective_now"
    SCHEMA_VERSION = "1.0.0"
    MAX_RECENT_EMOTIONS = 5  # Per schema: last 5 turns
    SIGNIFICANT_CHANGE_THRESHOLD = 0.3  # Valence change threshold

    def __init__(
        self,
        session_id: str = "",
        schema_version: str = "",
    ) -> None:
        """
        Initialize AffectiveNowSection.

        Args:
            session_id: Session UUID (generated if empty)
            schema_version: Schema version (uses default if empty)
        """
        now_ms = int(time.time() * 1000)

        self._session_id = session_id or str(uuid.uuid4())
        self._schema_version = schema_version or self.SCHEMA_VERSION
        self._last_updated_ms = now_ms
        self._last_significant_change_ms = now_ms

        # Current emotional state
        self._current_emotion = "neutral"
        self._intensity = 0.5
        self._dimensions = EmotionDimensions()
        self._trajectory = EmotionTrajectory.STABLE
        self._confidence = 0.8
        self._source = "initial"

        # Derived flags
        self._empathy_needed = False
        self._celebration_appropriate = False

        # History for trajectory calculation
        self._recent_emotions: List[EmotionSnapshot] = []
        self._current_turn = 0

        # Cached serialization
        self._cached_bytes: Optional[bytes] = None
        self._cache_valid = False

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    @property
    def last_updated_ms(self) -> int:
        """Last update timestamp in milliseconds."""
        return self._last_updated_ms

    @property
    def last_significant_change_ms(self) -> int:
        """Last significant emotional shift timestamp."""
        return self._last_significant_change_ms

    @property
    def schema_version(self) -> str:
        """Schema version string."""
        return self._schema_version

    @property
    def current_emotion(self) -> str:
        """Current primary emotion label."""
        return self._current_emotion

    @property
    def intensity(self) -> float:
        """Current emotion intensity (0.0 to 1.0)."""
        return self._intensity

    @property
    def dimensions(self) -> EmotionDimensions:
        """Current emotion dimensions (valence, arousal, dominance)."""
        return self._dimensions

    @property
    def valence(self) -> float:
        """Current valence (-1.0 negative to +1.0 positive)."""
        return self._dimensions.valence

    @property
    def arousal(self) -> float:
        """Current arousal (0.0 calm to 1.0 excited)."""
        return self._dimensions.arousal

    @property
    def dominance(self) -> float:
        """Current dominance (0.0 submissive to 1.0 dominant)."""
        return self._dimensions.dominance

    @property
    def trajectory(self) -> EmotionTrajectory:
        """Current emotional trajectory direction."""
        return self._trajectory

    @property
    def confidence(self) -> float:
        """Detection confidence (0.0 to 1.0)."""
        return self._confidence

    @property
    def source(self) -> str:
        """Detection source (ultrabert, explicit, inferred)."""
        return self._source

    @property
    def empathy_needed(self) -> bool:
        """Whether empathy is needed (negative trajectory detected)."""
        return self._empathy_needed

    @property
    def celebration_appropriate(self) -> bool:
        """Whether celebration is appropriate (positive achievement)."""
        return self._celebration_appropriate

    @property
    def current_turn(self) -> int:
        """Current turn number."""
        return self._current_turn

    @property
    def recent_emotions(self) -> List[EmotionSnapshot]:
        """Recent emotion snapshots (last 5 turns)."""
        return list(self._recent_emotions)

    # =========================================================================
    # ISection Protocol Implementation
    # =========================================================================

    @property
    def name(self) -> str:
        """Section identifier name."""
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        """Section tier (hot, warm, cold)."""
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        """Maximum size budget in bytes."""
        return self.BUDGET_BYTES

    @property
    def can_evict(self) -> bool:
        """Whether section can be evicted."""
        return self.CAN_EVICT

    def get_size_bytes(self) -> int:
        """
        Get current serialized size in bytes.

        Size budget breakdown per schema:
        - Header: ~100 bytes
        - Current state: ~150 bytes
        - Dimensions: ~20 bytes
        - Recent emotions: ~100 bytes each x 5 = ~500 bytes
        - Total: ~800 bytes typical
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 100  # Header overhead
        size += len(self._current_emotion.encode("utf-8")) + 50  # emotion + metadata
        size += 50  # dimensions, trajectory, flags
        size += len(self._recent_emotions) * 100  # snapshots
        size += len(self._source.encode("utf-8")) + 20  # source

        return min(size, self.BUDGET_BYTES)

    def clear(self) -> None:
        """Clear all section data, reset to initial state."""
        now_ms = int(time.time() * 1000)

        self._current_emotion = "neutral"
        self._intensity = 0.5
        self._dimensions = EmotionDimensions()
        self._trajectory = EmotionTrajectory.STABLE
        self._confidence = 0.8
        self._source = "initial"
        self._empathy_needed = False
        self._celebration_appropriate = False
        self._recent_emotions.clear()
        self._current_turn = 0
        self._last_updated_ms = now_ms
        self._last_significant_change_ms = now_ms
        self._invalidate_cache()

    def get_metadata(self) -> Dict[str, Any]:
        """Get section metadata for telemetry/debugging."""
        return {
            "name": self.name,
            "tier": self.tier,
            "budget_bytes": self.budget_bytes,
            "current_size_bytes": self.get_size_bytes(),
            "utilization_pct": round(self.get_size_bytes() / self.budget_bytes * 100, 1),
            "session_id": self._session_id,
            "schema_version": self._schema_version,
            "current_emotion": self._current_emotion,
            "intensity": self._intensity,
            "valence": self._dimensions.valence,
            "arousal": self._dimensions.arousal,
            "dominance": self._dimensions.dominance,
            "trajectory": self._trajectory.name,
            "confidence": self._confidence,
            "source": self._source,
            "empathy_needed": self._empathy_needed,
            "celebration_appropriate": self._celebration_appropriate,
            "recent_emotion_count": len(self._recent_emotions),
            "current_turn": self._current_turn,
            "last_updated_ms": self._last_updated_ms,
            "last_significant_change_ms": self._last_significant_change_ms,
        }

    # =========================================================================
    # State Update Operations
    # =========================================================================

    def update(
        self,
        emotion: str,
        intensity: float = 0.5,
        valence: Optional[float] = None,
        arousal: Optional[float] = None,
        dominance: Optional[float] = None,
        confidence: float = 0.8,
        source: str = "inferred",
        turn_number: Optional[int] = None,
    ) -> None:
        """
        Update emotional state.

        Args:
            emotion: Primary emotion label
            intensity: Emotion intensity (0.0 to 1.0)
            valence: Valence override (-1.0 to +1.0), inferred from emotion if None
            arousal: Arousal override (0.0 to 1.0), inferred from emotion if None
            dominance: Dominance override (0.0 to 1.0), default 0.5 if None
            confidence: Detection confidence
            source: Detection source (ultrabert, explicit, inferred)
            turn_number: Turn number (auto-increments if None)

        Note:
            Automatically updates trajectory based on recent history.
            Sets empathy_needed and celebration_appropriate flags.
        """
        now_ms = int(time.time() * 1000)

        # Normalize emotion to lowercase
        emotion = emotion.lower().strip()

        # Get old valence for change detection
        old_valence = self._dimensions.valence

        # Infer dimensions if not provided
        if valence is None:
            valence = self._infer_valence(emotion, intensity)
        if arousal is None:
            arousal = self._infer_arousal(emotion, intensity)
        if dominance is None:
            dominance = self._dimensions.dominance  # Keep current

        # Update turn number
        if turn_number is not None:
            self._current_turn = turn_number
        else:
            self._current_turn += 1

        # Create snapshot of current state before update
        snapshot = EmotionSnapshot(
            turn_number=self._current_turn,
            emotion=emotion,
            intensity=intensity,
            valence=valence,
            arousal=arousal,
            timestamp_ms=now_ms,
        )

        # Update current state
        self._current_emotion = emotion
        self._intensity = max(0.0, min(1.0, intensity))
        self._dimensions = EmotionDimensions(
            valence=valence,
            arousal=arousal,
            dominance=dominance,
        )
        self._confidence = max(0.0, min(1.0, confidence))
        self._source = source
        self._last_updated_ms = now_ms

        # Add to history
        self._recent_emotions.append(snapshot)
        if len(self._recent_emotions) > self.MAX_RECENT_EMOTIONS:
            self._recent_emotions = self._recent_emotions[-self.MAX_RECENT_EMOTIONS :]

        # Detect significant change
        valence_change = abs(valence - old_valence)
        if valence_change >= self.SIGNIFICANT_CHANGE_THRESHOLD:
            self._last_significant_change_ms = now_ms

        # Update trajectory
        self._trajectory = self._calculate_trajectory()

        # Update flags
        self._update_flags()

        self._invalidate_cache()

    def update_emotion(self, emotion: str, intensity: float = 0.5) -> None:
        """
        Simplified update with just emotion and intensity.

        Args:
            emotion: Primary emotion label
            intensity: Emotion intensity (0.0 to 1.0)
        """
        self.update(emotion=emotion, intensity=intensity)

    def update_dimensions(
        self,
        valence: float,
        arousal: float,
        dominance: float = 0.5,
    ) -> None:
        """
        Update dimensions directly without changing emotion label.

        Args:
            valence: Valence (-1.0 to +1.0)
            arousal: Arousal (0.0 to 1.0)
            dominance: Dominance (0.0 to 1.0)
        """
        old_valence = self._dimensions.valence
        now_ms = int(time.time() * 1000)

        self._dimensions = EmotionDimensions(
            valence=valence,
            arousal=arousal,
            dominance=dominance,
        )
        self._last_updated_ms = now_ms

        # Detect significant change
        if abs(valence - old_valence) >= self.SIGNIFICANT_CHANGE_THRESHOLD:
            self._last_significant_change_ms = now_ms

        # Infer emotion from dimensions
        self._current_emotion = self._infer_emotion_from_dimensions()

        # Update trajectory and flags
        self._trajectory = self._calculate_trajectory()
        self._update_flags()
        self._invalidate_cache()

    def set_empathy_needed(self, needed: bool) -> None:
        """
        Manually set empathy needed flag.

        Args:
            needed: Whether empathy is needed
        """
        self._empathy_needed = needed
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def set_celebration_appropriate(self, appropriate: bool) -> None:
        """
        Manually set celebration appropriate flag.

        Args:
            appropriate: Whether celebration is appropriate
        """
        self._celebration_appropriate = appropriate
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_emotion_history(self, n: int = 5) -> List[EmotionSnapshot]:
        """
        Get last N emotion snapshots.

        Args:
            n: Number of snapshots to retrieve

        Returns:
            List of EmotionSnapshot objects
        """
        return self._recent_emotions[-n:] if n > 0 else []

    def get_average_valence(self, n: int = 5) -> float:
        """
        Get average valence over last N turns.

        Args:
            n: Number of turns to average

        Returns:
            Average valence (-1.0 to +1.0)
        """
        recent = self._recent_emotions[-n:] if n > 0 else []
        if not recent:
            return self._dimensions.valence
        return sum(s.valence for s in recent) / len(recent)

    def get_average_arousal(self, n: int = 5) -> float:
        """
        Get average arousal over last N turns.

        Args:
            n: Number of turns to average

        Returns:
            Average arousal (0.0 to 1.0)
        """
        recent = self._recent_emotions[-n:] if n > 0 else []
        if not recent:
            return self._dimensions.arousal
        return sum(s.arousal for s in recent) / len(recent)

    def get_valence_trend(self, n: int = 5) -> float:
        """
        Get valence trend over last N turns.

        Args:
            n: Number of turns to analyze

        Returns:
            Trend slope (positive = improving, negative = declining)
        """
        recent = self._recent_emotions[-n:] if n > 0 else []
        if len(recent) < 2:
            return 0.0

        # Simple linear regression
        n_points = len(recent)
        sum_x = sum(range(n_points))
        sum_y = sum(s.valence for s in recent)
        sum_xy = sum(i * s.valence for i, s in enumerate(recent))
        sum_x2 = sum(i * i for i in range(n_points))

        denominator = n_points * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0

        return (n_points * sum_xy - sum_x * sum_y) / denominator

    def is_negative(self) -> bool:
        """Check if current emotional state is negative."""
        return self._dimensions.valence < 0 or self._current_emotion in EMPATHY_EMOTIONS

    def is_positive(self) -> bool:
        """Check if current emotional state is positive."""
        return self._dimensions.valence > 0.3 or self._current_emotion in CELEBRATION_EMOTIONS

    def is_neutral(self) -> bool:
        """Check if current emotional state is neutral."""
        return -0.2 <= self._dimensions.valence <= 0.2 and self._current_emotion == "neutral"

    def is_high_arousal(self) -> bool:
        """Check if current state is high arousal (excited, agitated)."""
        return self._dimensions.arousal >= 0.7

    def is_low_arousal(self) -> bool:
        """Check if current state is low arousal (calm, tired)."""
        return self._dimensions.arousal <= 0.3

    def get_quadrant(self) -> str:
        """Get emotion quadrant based on valence and arousal."""
        return self._dimensions.quadrant

    # =========================================================================
    # FlatBuffer Serialization
    # =========================================================================

    def to_flatbuffer(self) -> bytes:
        """
        Serialize to FlatBuffer bytes.

        Returns:
            FlatBuffer binary data
        """
        if self._cache_valid and self._cached_bytes:
            return self._cached_bytes

        builder = flatbuffers.Builder(2048)

        # Build header
        name_offset = builder.CreateString(self.SECTION_NAME)
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # Build dimensions
        EmotionDimensionsStart(builder)
        EmotionDimensionsAddValence(builder, self._dimensions.valence)
        EmotionDimensionsAddArousal(builder, self._dimensions.arousal)
        EmotionDimensionsAddDominance(builder, self._dimensions.dominance)
        dimensions_offset = EmotionDimensionsEnd(builder)

        # Build recent emotions vector
        emotion_offsets = []
        for snap in reversed(self._recent_emotions):  # Reverse for FlatBuffer
            emotion_str = builder.CreateString(snap.emotion)
            EmotionSnapshotStart(builder)
            EmotionSnapshotAddTurnNumber(builder, snap.turn_number)
            EmotionSnapshotAddEmotion(builder, emotion_str)
            EmotionSnapshotAddIntensity(builder, snap.intensity)
            EmotionSnapshotAddValence(builder, snap.valence)
            EmotionSnapshotAddArousal(builder, snap.arousal)
            EmotionSnapshotAddTimestampMs(builder, snap.timestamp_ms)
            emotion_offsets.append(EmotionSnapshotEnd(builder))

        # Create vector (reverse back to original order)
        AffectiveNowSectionStartRecentEmotionsVector(builder, len(emotion_offsets))
        for offset in emotion_offsets:  # Already reversed
            builder.PrependUOffsetTRelative(offset)
        recent_vector = builder.EndVector()

        # Build strings
        current_emotion_offset = builder.CreateString(self._current_emotion)
        source_offset = builder.CreateString(self._source)

        # Build AffectiveNowSection
        AffectiveNowSectionStart(builder)
        AffectiveNowSectionAddHeader(builder, header_offset)
        AffectiveNowSectionAddCurrentEmotion(builder, current_emotion_offset)
        AffectiveNowSectionAddIntensity(builder, self._intensity)
        AffectiveNowSectionAddDimensions(builder, dimensions_offset)
        AffectiveNowSectionAddTrajectory(builder, int(self._trajectory))
        AffectiveNowSectionAddRecentEmotions(builder, recent_vector)
        AffectiveNowSectionAddConfidence(builder, self._confidence)
        AffectiveNowSectionAddSource(builder, source_offset)
        AffectiveNowSectionAddLastUpdatedMs(builder, self._last_updated_ms)
        AffectiveNowSectionAddLastSignificantChangeMs(builder, self._last_significant_change_ms)
        AffectiveNowSectionAddEmpathyNeeded(builder, self._empathy_needed)
        AffectiveNowSectionAddCelebrationAppropriate(builder, self._celebration_appropriate)
        section_offset = AffectiveNowSectionEnd(builder)

        builder.Finish(section_offset)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize from FlatBuffer bytes.

        Args:
            data: FlatBuffer binary data
        """
        fb = FBAffectiveNowSection.GetRootAsAffectiveNowSection(data, 0)

        # Restore current emotion
        current_emotion = fb.CurrentEmotion()
        self._current_emotion = current_emotion.decode("utf-8") if current_emotion else "neutral"

        self._intensity = fb.Intensity()
        self._trajectory = EmotionTrajectory(fb.Trajectory())
        self._confidence = fb.Confidence()

        source = fb.Source()
        self._source = source.decode("utf-8") if source else "unknown"

        self._last_updated_ms = fb.LastUpdatedMs()
        self._last_significant_change_ms = fb.LastSignificantChangeMs()
        self._empathy_needed = fb.EmpathyNeeded()
        self._celebration_appropriate = fb.CelebrationAppropriate()

        # Restore dimensions
        dims = fb.Dimensions()
        if dims:
            self._dimensions = EmotionDimensions(
                valence=dims.Valence(),
                arousal=dims.Arousal(),
                dominance=dims.Dominance(),
            )
        else:
            self._dimensions = EmotionDimensions()

        # Restore recent emotions
        self._recent_emotions.clear()
        for i in range(fb.RecentEmotionsLength()):
            snap_fb = fb.RecentEmotions(i)
            if snap_fb:
                emotion = snap_fb.Emotion()
                self._recent_emotions.append(
                    EmotionSnapshot(
                        turn_number=snap_fb.TurnNumber(),
                        emotion=emotion.decode("utf-8") if emotion else "",
                        intensity=snap_fb.Intensity(),
                        valence=snap_fb.Valence(),
                        arousal=snap_fb.Arousal(),
                        timestamp_ms=snap_fb.TimestampMs(),
                    )
                )

        # Update turn number from history
        if self._recent_emotions:
            self._current_turn = max(s.turn_number for s in self._recent_emotions)

        self._cached_bytes = data
        self._cache_valid = True

    # Aliases for compatibility
    def serialize(self) -> bytes:
        """Alias for to_flatbuffer()."""
        return self.to_flatbuffer()

    def deserialize(self, data: bytes) -> None:
        """Alias for from_flatbuffer()."""
        self.from_flatbuffer(data)

    # =========================================================================
    # Apply Operations (for MutationGuard pattern)
    # =========================================================================

    def apply(self, operation: str, data: Dict[str, Any]) -> Any:
        """
        Apply a mutation operation.

        Args:
            operation: Operation name
            data: Operation data

        Returns:
            Operation result

        Supported operations:
        - update: Full state update
        - update_emotion: Simple emotion update
        - update_dimensions: Dimensions only update
        - set_empathy_needed: Set empathy flag
        - set_celebration_appropriate: Set celebration flag
        - clear: Reset to initial state
        """
        if operation == "update":
            self.update(
                emotion=data.get("emotion", "neutral"),
                intensity=data.get("intensity", 0.5),
                valence=data.get("valence"),
                arousal=data.get("arousal"),
                dominance=data.get("dominance"),
                confidence=data.get("confidence", 0.8),
                source=data.get("source", "inferred"),
                turn_number=data.get("turn_number"),
            )
            return True

        elif operation == "update_emotion":
            self.update_emotion(
                emotion=data.get("emotion", "neutral"),
                intensity=data.get("intensity", 0.5),
            )
            return True

        elif operation == "update_dimensions":
            self.update_dimensions(
                valence=data.get("valence", 0.0),
                arousal=data.get("arousal", 0.5),
                dominance=data.get("dominance", 0.5),
            )
            return True

        elif operation == "set_empathy_needed":
            self.set_empathy_needed(data.get("needed", False))
            return True

        elif operation == "set_celebration_appropriate":
            self.set_celebration_appropriate(data.get("appropriate", False))
            return True

        elif operation == "clear":
            self.clear()
            return True

        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _invalidate_cache(self) -> None:
        """Invalidate serialization cache."""
        self._cache_valid = False
        self._cached_bytes = None

    def _infer_valence(self, emotion: str, intensity: float) -> float:
        """
        Infer valence from emotion label and intensity.

        Args:
            emotion: Emotion label
            intensity: Emotion intensity

        Returns:
            Valence value (-1.0 to +1.0)
        """
        # Positive emotions
        positive = {
            "happy": 0.7,
            "joyful": 0.9,
            "excited": 0.6,
            "content": 0.5,
            "grateful": 0.6,
            "hopeful": 0.4,
            "proud": 0.7,
            "amused": 0.5,
            "loving": 0.8,
            "relieved": 0.5,
            "interested": 0.3,
            "curious": 0.2,
            "relaxed": 0.3,
            "calm": 0.2,
        }

        # Negative emotions
        negative = {
            "sad": -0.6,
            "frustrated": -0.5,
            "angry": -0.7,
            "anxious": -0.4,
            "fearful": -0.6,
            "disappointed": -0.5,
            "disgusted": -0.6,
            "embarrassed": -0.4,
            "guilty": -0.5,
            "jealous": -0.4,
            "stressed": -0.4,
            "bored": -0.2,
            "skeptical": -0.1,
            "confused": -0.2,
            "urgent": -0.2,
        }

        if emotion in positive:
            return positive[emotion] * intensity
        elif emotion in negative:
            return negative[emotion] * intensity
        else:
            return 0.0  # Neutral

    def _infer_arousal(self, emotion: str, intensity: float) -> float:
        """
        Infer arousal from emotion label and intensity.

        Args:
            emotion: Emotion label
            intensity: Emotion intensity

        Returns:
            Arousal value (0.0 to 1.0)
        """
        # High arousal emotions
        high_arousal = {
            "excited": 0.9,
            "angry": 0.8,
            "anxious": 0.7,
            "fearful": 0.8,
            "joyful": 0.7,
            "surprised": 0.8,
            "urgent": 0.8,
            "stressed": 0.7,
        }

        # Low arousal emotions
        low_arousal = {
            "sad": 0.3,
            "content": 0.3,
            "calm": 0.2,
            "relaxed": 0.2,
            "bored": 0.2,
            "tired": 0.1,
            "contemplative": 0.3,
        }

        if emotion in high_arousal:
            return min(1.0, high_arousal[emotion] * intensity + 0.2)
        elif emotion in low_arousal:
            return max(0.0, low_arousal[emotion] * intensity)
        else:
            return 0.5 * intensity  # Moderate arousal for neutral/unknown

    def _infer_emotion_from_dimensions(self) -> str:
        """
        Infer emotion label from dimensions.

        Returns:
            Emotion label
        """
        v = self._dimensions.valence
        a = self._dimensions.arousal

        # Quadrant-based inference
        if v >= 0.3:
            if a >= 0.6:
                return "excited"
            elif a >= 0.3:
                return "happy"
            else:
                return "content"
        elif v <= -0.3:
            if a >= 0.6:
                return "angry"
            elif a >= 0.3:
                return "frustrated"
            else:
                return "sad"
        else:
            if a >= 0.6:
                return "surprised"
            elif a >= 0.3:
                return "neutral"
            else:
                return "calm"

    def _calculate_trajectory(self) -> EmotionTrajectory:
        """
        Calculate emotional trajectory from recent history.

        Returns:
            EmotionTrajectory enum value
        """
        if len(self._recent_emotions) < 2:
            return EmotionTrajectory.STABLE

        trend = self.get_valence_trend(self.MAX_RECENT_EMOTIONS)

        if trend > 0.1:
            return EmotionTrajectory.INCREASING
        elif trend < -0.1:
            return EmotionTrajectory.DECREASING
        else:
            return EmotionTrajectory.STABLE

    def _update_flags(self) -> None:
        """Update empathy_needed and celebration_appropriate flags."""
        # Empathy needed: negative emotion or declining trajectory
        self._empathy_needed = (
            self._current_emotion in EMPATHY_EMOTIONS
            or self._dimensions.valence < -0.3
            or self._trajectory == EmotionTrajectory.DECREASING
        )

        # Celebration appropriate: positive emotion with high intensity
        self._celebration_appropriate = (
            self._current_emotion in CELEBRATION_EMOTIONS
            and self._intensity >= 0.6
            and self._dimensions.valence >= 0.3
        )


# =============================================================================
# Factory function
# =============================================================================


def create_affective_now_section(
    session_id: str = "",
    initial_emotion: str = "neutral",
    initial_valence: float = 0.0,
    initial_arousal: float = 0.5,
) -> AffectiveNowSection:
    """
    Factory function to create AffectiveNowSection with initial state.

    Args:
        session_id: Session UUID (generated if empty)
        initial_emotion: Starting emotion
        initial_valence: Starting valence
        initial_arousal: Starting arousal

    Returns:
        Configured AffectiveNowSection
    """
    section = AffectiveNowSection(session_id=session_id)

    if initial_emotion != "neutral" or initial_valence != 0.0 or initial_arousal != 0.5:
        section.update(
            emotion=initial_emotion,
            intensity=0.5,
            valence=initial_valence,
            arousal=initial_arousal,
            source="initial",
        )

    return section
