"""
Tests for AffectiveNowSection (Issue 2.2.6)
============================================

Tests for the affective now section implementation including:
- ISection protocol compliance
- Emotion updates and tracking
- Dimensional model (valence, arousal, dominance)
- Trajectory calculation
- Empathy/celebration flag detection
- FlatBuffer serialization roundtrip
- Edge cases and error handling
"""

import time

import pytest

from k1.sessionstate.sections.affective_now import (
    CELEBRATION_EMOTIONS,
    EMPATHY_EMOTIONS,
    KNOWN_EMOTIONS,
    AffectiveNowSection,
    EmotionDimensions,
    EmotionSnapshot,
    EmotionTrajectory,
    create_affective_now_section,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def section() -> AffectiveNowSection:
    """Create a fresh AffectiveNowSection for each test."""
    return AffectiveNowSection(session_id="test-session-123")


@pytest.fixture
def populated_section() -> AffectiveNowSection:
    """Create section with emotion history."""
    section = AffectiveNowSection(session_id="test-session-456")
    emotions = [
        ("neutral", 0.5, 0.0, 0.5),
        ("curious", 0.6, 0.2, 0.6),
        ("happy", 0.7, 0.5, 0.6),
        ("excited", 0.8, 0.7, 0.8),
    ]
    for emotion, intensity, valence, arousal in emotions:
        section.update(
            emotion=emotion,
            intensity=intensity,
            valence=valence,
            arousal=arousal,
            source="test",
        )
    return section


# =============================================================================
# Test: Initialization
# =============================================================================


class TestAffectiveNowSectionInit:
    """Tests for AffectiveNowSection initialization."""

    def test_init_default(self):
        """Test default initialization."""
        section = AffectiveNowSection()
        assert section.session_id != ""
        assert section.current_emotion == "neutral"
        assert section.intensity == 0.5
        assert section.confidence == 0.8
        assert section.source == "initial"

    def test_init_with_session_id(self):
        """Test initialization with session ID."""
        section = AffectiveNowSection(session_id="my-session")
        assert section.session_id == "my-session"

    def test_init_with_schema_version(self):
        """Test initialization with schema version."""
        section = AffectiveNowSection(schema_version="2.0.0")
        assert section.schema_version == "2.0.0"

    def test_initial_state(self, section):
        """Test initial state is neutral."""
        assert section.current_emotion == "neutral"
        assert section.intensity == 0.5
        assert section.valence == 0.0
        assert section.arousal == 0.5
        assert section.dominance == 0.5
        assert section.trajectory == EmotionTrajectory.STABLE
        assert section.empathy_needed is False
        assert section.celebration_appropriate is False

    def test_initial_timestamps(self, section):
        """Test timestamps are set on init."""
        assert section.last_updated_ms > 0
        assert section.last_significant_change_ms > 0


# =============================================================================
# Test: ISection Protocol
# =============================================================================


class TestISectionProtocol:
    """Tests for ISection protocol compliance."""

    def test_name(self, section):
        """Test section name."""
        assert section.name == "affective_now"

    def test_tier(self, section):
        """Test section tier."""
        assert section.tier == "hot"

    def test_budget_bytes(self, section):
        """Test budget bytes."""
        assert section.budget_bytes == 4096

    def test_can_evict(self, section):
        """Test can_evict is False."""
        assert section.can_evict is False

    def test_get_size_bytes_empty(self, section):
        """Test size for empty section."""
        size = section.get_size_bytes()
        assert size > 0
        assert size <= section.budget_bytes

    def test_get_size_bytes_with_data(self, populated_section):
        """Test size increases with data."""
        size = populated_section.get_size_bytes()
        assert size > 0
        assert size <= populated_section.budget_bytes

    def test_clear(self, populated_section):
        """Test clearing section."""
        populated_section.clear()
        assert populated_section.current_emotion == "neutral"
        assert populated_section.intensity == 0.5
        assert populated_section.valence == 0.0
        assert len(populated_section.recent_emotions) == 0
        assert populated_section.current_turn == 0

    def test_get_metadata(self, section):
        """Test metadata includes required fields."""
        meta = section.get_metadata()
        assert meta["name"] == "affective_now"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 4096
        assert "current_size_bytes" in meta
        assert "utilization_pct" in meta
        assert "current_emotion" in meta
        assert "valence" in meta
        assert "arousal" in meta
        assert "trajectory" in meta


# =============================================================================
# Test: Emotion Dimensions
# =============================================================================


class TestEmotionDimensions:
    """Tests for EmotionDimensions dataclass."""

    def test_default_values(self):
        """Test default dimension values."""
        dims = EmotionDimensions()
        assert dims.valence == 0.0
        assert dims.arousal == 0.5
        assert dims.dominance == 0.5

    def test_clamping_valence(self):
        """Test valence is clamped to -1 to +1."""
        dims = EmotionDimensions(valence=2.0)
        assert dims.valence == 1.0

        dims = EmotionDimensions(valence=-2.0)
        assert dims.valence == -1.0

    def test_clamping_arousal(self):
        """Test arousal is clamped to 0 to 1."""
        dims = EmotionDimensions(arousal=1.5)
        assert dims.arousal == 1.0

        dims = EmotionDimensions(arousal=-0.5)
        assert dims.arousal == 0.0

    def test_quadrant_happy_excited(self):
        """Test quadrant detection for positive high arousal."""
        dims = EmotionDimensions(valence=0.7, arousal=0.8)
        assert dims.quadrant == "happy-excited"

    def test_quadrant_calm_content(self):
        """Test quadrant detection for positive low arousal."""
        dims = EmotionDimensions(valence=0.5, arousal=0.3)
        assert dims.quadrant == "calm-content"

    def test_quadrant_sad_depressed(self):
        """Test quadrant detection for negative low arousal."""
        dims = EmotionDimensions(valence=-0.5, arousal=0.3)
        assert dims.quadrant == "sad-depressed"

    def test_quadrant_angry_anxious(self):
        """Test quadrant detection for negative high arousal."""
        dims = EmotionDimensions(valence=-0.5, arousal=0.8)
        assert dims.quadrant == "angry-anxious"


# =============================================================================
# Test: Emotion Snapshot
# =============================================================================


class TestEmotionSnapshot:
    """Tests for EmotionSnapshot dataclass."""

    def test_default_values(self):
        """Test default snapshot values."""
        snap = EmotionSnapshot(turn_number=1, emotion="happy")
        assert snap.turn_number == 1
        assert snap.emotion == "happy"
        assert snap.intensity == 0.5
        assert snap.valence == 0.0
        assert snap.arousal == 0.5
        assert snap.timestamp_ms > 0

    def test_value_clamping(self):
        """Test values are clamped."""
        snap = EmotionSnapshot(
            turn_number=1,
            emotion="test",
            intensity=2.0,
            valence=3.0,
            arousal=-1.0,
        )
        assert snap.intensity == 1.0
        assert snap.valence == 1.0
        assert snap.arousal == 0.0

    def test_explicit_timestamp(self):
        """Test explicit timestamp."""
        snap = EmotionSnapshot(
            turn_number=1,
            emotion="test",
            timestamp_ms=12345,
        )
        assert snap.timestamp_ms == 12345


# =============================================================================
# Test: Update Operations
# =============================================================================


class TestUpdateOperations:
    """Tests for emotion update operations."""

    def test_update_basic(self, section):
        """Test basic update."""
        section.update(
            emotion="happy",
            intensity=0.8,
            valence=0.6,
            arousal=0.7,
        )
        assert section.current_emotion == "happy"
        assert section.intensity == 0.8
        assert section.valence == 0.6
        assert section.arousal == 0.7

    def test_update_with_source(self, section):
        """Test update with source."""
        section.update(emotion="frustrated", source="front_llm")
        assert section.source == "front_llm"

    def test_update_with_confidence(self, section):
        """Test update with confidence."""
        section.update(emotion="happy", confidence=0.95)
        assert section.confidence == 0.95

    def test_update_increments_turn(self, section):
        """Test update increments turn number."""
        assert section.current_turn == 0
        section.update(emotion="happy")
        assert section.current_turn == 1
        section.update(emotion="curious")
        assert section.current_turn == 2

    def test_update_explicit_turn(self, section):
        """Test update with explicit turn number."""
        section.update(emotion="happy", turn_number=5)
        assert section.current_turn == 5

    def test_update_adds_to_history(self, section):
        """Test update adds to recent emotions."""
        section.update(emotion="happy")
        section.update(emotion="curious")
        section.update(emotion="excited")

        history = section.recent_emotions
        assert len(history) == 3
        assert history[0].emotion == "happy"
        assert history[1].emotion == "curious"
        assert history[2].emotion == "excited"

    def test_update_trims_history(self, section):
        """Test history is trimmed to max 5."""
        for i in range(7):
            section.update(emotion=f"emotion_{i}")

        history = section.recent_emotions
        assert len(history) == 5
        assert history[0].emotion == "emotion_2"
        assert history[-1].emotion == "emotion_6"

    def test_update_normalizes_emotion(self, section):
        """Test emotion is normalized to lowercase."""
        section.update(emotion="HAPPY  ")
        assert section.current_emotion == "happy"

    def test_update_infers_valence(self, section):
        """Test valence is inferred from emotion."""
        section.update(emotion="happy", intensity=1.0)
        assert section.valence > 0

        section.update(emotion="sad", intensity=1.0)
        assert section.valence < 0

    def test_update_infers_arousal(self, section):
        """Test arousal is inferred from emotion."""
        section.update(emotion="excited", intensity=1.0)
        assert section.arousal > 0.6

        section.update(emotion="calm", intensity=1.0)
        assert section.arousal < 0.4

    def test_update_emotion_simple(self, section):
        """Test simple emotion update."""
        section.update_emotion("frustrated", 0.7)
        assert section.current_emotion == "frustrated"
        assert section.intensity == 0.7

    def test_update_dimensions_only(self, section):
        """Test dimensions-only update."""
        section.update_dimensions(valence=-0.5, arousal=0.8, dominance=0.3)
        assert section.valence == -0.5
        assert section.arousal == 0.8
        assert section.dominance == 0.3
        # Emotion should be inferred
        assert section.current_emotion in ["angry", "frustrated"]

    def test_update_timestamps(self, section):
        """Test timestamps are updated."""
        old_updated = section.last_updated_ms
        time.sleep(0.01)
        section.update(emotion="happy")
        assert section.last_updated_ms > old_updated


# =============================================================================
# Test: Trajectory
# =============================================================================


class TestTrajectory:
    """Tests for emotional trajectory calculation."""

    def test_trajectory_stable_initial(self, section):
        """Test initial trajectory is stable."""
        assert section.trajectory == EmotionTrajectory.STABLE

    def test_trajectory_stable_single_update(self, section):
        """Test stable trajectory with single update."""
        section.update(emotion="happy")
        assert section.trajectory == EmotionTrajectory.STABLE

    def test_trajectory_increasing(self, section):
        """Test increasing trajectory detection."""
        valences = [-0.5, -0.3, 0.0, 0.3, 0.5]
        for v in valences:
            section.update(emotion="test", valence=v)

        assert section.trajectory == EmotionTrajectory.INCREASING

    def test_trajectory_decreasing(self, section):
        """Test decreasing trajectory detection."""
        valences = [0.5, 0.3, 0.0, -0.3, -0.5]
        for v in valences:
            section.update(emotion="test", valence=v)

        assert section.trajectory == EmotionTrajectory.DECREASING

    def test_trajectory_stable_flat(self, section):
        """Test stable trajectory with flat valence."""
        for _ in range(5):
            section.update(emotion="neutral", valence=0.0)

        assert section.trajectory == EmotionTrajectory.STABLE

    def test_get_valence_trend(self, section):
        """Test valence trend calculation."""
        valences = [0.0, 0.2, 0.4, 0.6, 0.8]
        for v in valences:
            section.update(emotion="test", valence=v)

        trend = section.get_valence_trend()
        assert trend > 0  # Positive trend


# =============================================================================
# Test: Flags
# =============================================================================


class TestFlags:
    """Tests for empathy and celebration flags."""

    def test_empathy_needed_negative_emotion(self, section):
        """Test empathy needed for negative emotions."""
        section.update(emotion="frustrated", intensity=0.7)
        assert section.empathy_needed is True

    def test_empathy_needed_negative_valence(self, section):
        """Test empathy needed for negative valence."""
        section.update(emotion="test", valence=-0.5)
        assert section.empathy_needed is True

    def test_empathy_needed_decreasing(self, section):
        """Test empathy needed for decreasing trajectory."""
        valences = [0.5, 0.3, 0.0, -0.2, -0.4]
        for v in valences:
            section.update(emotion="test", valence=v)

        assert section.trajectory == EmotionTrajectory.DECREASING
        assert section.empathy_needed is True

    def test_empathy_not_needed_positive(self, section):
        """Test empathy not needed for positive emotions."""
        section.update(emotion="happy", intensity=0.8, valence=0.6)
        assert section.empathy_needed is False

    def test_celebration_appropriate_positive(self, section):
        """Test celebration for positive emotions."""
        section.update(emotion="excited", intensity=0.8, valence=0.7)
        assert section.celebration_appropriate is True

    def test_celebration_not_appropriate_low_intensity(self, section):
        """Test celebration not appropriate with low intensity."""
        section.update(emotion="happy", intensity=0.4, valence=0.5)
        assert section.celebration_appropriate is False

    def test_celebration_not_appropriate_negative(self, section):
        """Test celebration not appropriate for negative emotions."""
        section.update(emotion="sad", intensity=0.8, valence=-0.5)
        assert section.celebration_appropriate is False

    def test_set_empathy_needed(self, section):
        """Test manual empathy flag setting."""
        section.set_empathy_needed(True)
        assert section.empathy_needed is True

        section.set_empathy_needed(False)
        assert section.empathy_needed is False

    def test_set_celebration_appropriate(self, section):
        """Test manual celebration flag setting."""
        section.set_celebration_appropriate(True)
        assert section.celebration_appropriate is True

        section.set_celebration_appropriate(False)
        assert section.celebration_appropriate is False


# =============================================================================
# Test: Query Operations
# =============================================================================


class TestQueryOperations:
    """Tests for query operations."""

    def test_get_emotion_history(self, populated_section):
        """Test getting emotion history."""
        history = populated_section.get_emotion_history(3)
        assert len(history) == 3

    def test_get_emotion_history_empty(self, section):
        """Test getting history when empty."""
        history = section.get_emotion_history(3)
        assert len(history) == 0

    def test_get_average_valence(self, populated_section):
        """Test average valence calculation."""
        avg = populated_section.get_average_valence()
        assert isinstance(avg, float)
        assert -1.0 <= avg <= 1.0

    def test_get_average_valence_empty(self, section):
        """Test average valence when empty."""
        avg = section.get_average_valence()
        assert avg == section.valence

    def test_get_average_arousal(self, populated_section):
        """Test average arousal calculation."""
        avg = populated_section.get_average_arousal()
        assert isinstance(avg, float)
        assert 0.0 <= avg <= 1.0

    def test_is_negative(self, section):
        """Test negative detection."""
        section.update(emotion="frustrated", valence=-0.5)
        assert section.is_negative() is True

        section.update(emotion="happy", valence=0.5)
        assert section.is_negative() is False

    def test_is_positive(self, section):
        """Test positive detection."""
        section.update(emotion="happy", valence=0.5)
        assert section.is_positive() is True

        section.update(emotion="sad", valence=-0.5)
        assert section.is_positive() is False

    def test_is_neutral(self, section):
        """Test neutral detection."""
        assert section.is_neutral() is True

        section.update(emotion="happy", valence=0.5)
        assert section.is_neutral() is False

    def test_is_high_arousal(self, section):
        """Test high arousal detection."""
        section.update(emotion="excited", arousal=0.8)
        assert section.is_high_arousal() is True

        section.update(emotion="calm", arousal=0.2)
        assert section.is_high_arousal() is False

    def test_is_low_arousal(self, section):
        """Test low arousal detection."""
        section.update(emotion="calm", arousal=0.2)
        assert section.is_low_arousal() is True

        section.update(emotion="excited", arousal=0.8)
        assert section.is_low_arousal() is False

    def test_get_quadrant(self, section):
        """Test quadrant retrieval."""
        section.update(emotion="happy", valence=0.5, arousal=0.7)
        assert section.get_quadrant() == "happy-excited"


# =============================================================================
# Test: FlatBuffer Serialization
# =============================================================================


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_roundtrip_empty(self, section):
        """Test serialization roundtrip with empty section."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

        new_section = AffectiveNowSection()
        new_section.from_flatbuffer(data)

        assert new_section.current_emotion == section.current_emotion
        assert new_section.intensity == section.intensity

    def test_roundtrip_with_data(self, populated_section):
        """Test serialization roundtrip with data."""
        data = populated_section.to_flatbuffer()

        new_section = AffectiveNowSection()
        new_section.from_flatbuffer(data)

        assert new_section.current_emotion == populated_section.current_emotion
        assert abs(new_section.intensity - populated_section.intensity) < 0.001
        assert abs(new_section.valence - populated_section.valence) < 0.001
        assert abs(new_section.arousal - populated_section.arousal) < 0.001
        assert abs(new_section.dominance - populated_section.dominance) < 0.001
        assert new_section.trajectory == populated_section.trajectory
        assert abs(new_section.confidence - populated_section.confidence) < 0.001
        assert new_section.source == populated_section.source

    def test_roundtrip_flags(self, section):
        """Test flags survive roundtrip."""
        section.update(emotion="frustrated", valence=-0.5)
        section.set_celebration_appropriate(True)  # Manually override

        data = section.to_flatbuffer()

        new_section = AffectiveNowSection()
        new_section.from_flatbuffer(data)

        assert new_section.empathy_needed == section.empathy_needed
        assert new_section.celebration_appropriate == section.celebration_appropriate

    def test_roundtrip_history(self, populated_section):
        """Test history survives roundtrip."""
        original_history = populated_section.recent_emotions

        data = populated_section.to_flatbuffer()

        new_section = AffectiveNowSection()
        new_section.from_flatbuffer(data)

        restored_history = new_section.recent_emotions
        assert len(restored_history) == len(original_history)

        for orig, restored in zip(original_history, restored_history):
            assert restored.turn_number == orig.turn_number
            assert restored.emotion == orig.emotion
            assert abs(restored.intensity - orig.intensity) < 0.001
            assert abs(restored.valence - orig.valence) < 0.001
            assert abs(restored.arousal - orig.arousal) < 0.001

    def test_roundtrip_timestamps(self, section):
        """Test timestamps survive roundtrip."""
        section.update(emotion="happy")
        original_updated = section.last_updated_ms
        original_significant = section.last_significant_change_ms

        data = section.to_flatbuffer()

        new_section = AffectiveNowSection()
        new_section.from_flatbuffer(data)

        assert new_section.last_updated_ms == original_updated
        assert new_section.last_significant_change_ms == original_significant

    def test_serialize_alias(self, section):
        """Test serialize is alias for to_flatbuffer."""
        data1 = section.to_flatbuffer()
        section._invalidate_cache()
        data2 = section.serialize()
        assert data1 == data2

    def test_deserialize_alias(self, section):
        """Test deserialize is alias for from_flatbuffer."""
        section.update(emotion="happy")
        data = section.to_flatbuffer()

        new_section = AffectiveNowSection()
        new_section.deserialize(data)

        assert new_section.current_emotion == "happy"

    def test_cache_invalidation(self, section):
        """Test cache is invalidated on update."""
        data1 = section.to_flatbuffer()
        assert section._cache_valid is True

        section.update(emotion="happy")
        assert section._cache_valid is False

        data2 = section.to_flatbuffer()
        assert data1 != data2


# =============================================================================
# Test: Apply Operations
# =============================================================================


class TestApplyOperations:
    """Tests for apply operation pattern."""

    def test_apply_update(self, section):
        """Test apply update operation."""
        result = section.apply(
            "update",
            {
                "emotion": "happy",
                "intensity": 0.8,
                "valence": 0.6,
                "source": "test",
            },
        )
        assert result is True
        assert section.current_emotion == "happy"
        assert section.intensity == 0.8

    def test_apply_update_emotion(self, section):
        """Test apply update_emotion operation."""
        result = section.apply(
            "update_emotion",
            {"emotion": "curious", "intensity": 0.6},
        )
        assert result is True
        assert section.current_emotion == "curious"

    def test_apply_update_dimensions(self, section):
        """Test apply update_dimensions operation."""
        result = section.apply(
            "update_dimensions",
            {"valence": -0.3, "arousal": 0.7, "dominance": 0.4},
        )
        assert result is True
        assert section.valence == -0.3
        assert section.arousal == 0.7
        assert section.dominance == 0.4

    def test_apply_set_empathy_needed(self, section):
        """Test apply set_empathy_needed operation."""
        result = section.apply("set_empathy_needed", {"needed": True})
        assert result is True
        assert section.empathy_needed is True

    def test_apply_set_celebration_appropriate(self, section):
        """Test apply set_celebration_appropriate operation."""
        result = section.apply("set_celebration_appropriate", {"appropriate": True})
        assert result is True
        assert section.celebration_appropriate is True

    def test_apply_clear(self, populated_section):
        """Test apply clear operation."""
        result = populated_section.apply("clear", {})
        assert result is True
        assert populated_section.current_emotion == "neutral"
        assert len(populated_section.recent_emotions) == 0

    def test_apply_unknown_operation(self, section):
        """Test apply with unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown_op", {})


# =============================================================================
# Test: Known Emotions
# =============================================================================


class TestKnownEmotions:
    """Tests for emotion categories."""

    def test_known_emotions_not_empty(self):
        """Test known emotions set is populated."""
        assert len(KNOWN_EMOTIONS) > 0
        assert "happy" in KNOWN_EMOTIONS
        assert "sad" in KNOWN_EMOTIONS
        assert "neutral" in KNOWN_EMOTIONS

    def test_empathy_emotions_subset(self):
        """Test empathy emotions are subset of known."""
        assert len(EMPATHY_EMOTIONS) > 0
        assert "frustrated" in EMPATHY_EMOTIONS
        assert "anxious" in EMPATHY_EMOTIONS

    def test_celebration_emotions_subset(self):
        """Test celebration emotions are subset of known."""
        assert len(CELEBRATION_EMOTIONS) > 0
        assert "happy" in CELEBRATION_EMOTIONS
        assert "excited" in CELEBRATION_EMOTIONS

    def test_empathy_celebration_disjoint(self):
        """Test empathy and celebration emotions are disjoint."""
        overlap = EMPATHY_EMOTIONS & CELEBRATION_EMOTIONS
        assert len(overlap) == 0


# =============================================================================
# Test: Significant Change Detection
# =============================================================================


class TestSignificantChange:
    """Tests for significant change detection."""

    def test_significant_change_detected(self, section):
        """Test significant change updates timestamp."""
        initial_change = section.last_significant_change_ms
        time.sleep(0.01)

        # Small change - no update
        section.update(emotion="neutral", valence=0.1)
        assert section.last_significant_change_ms == initial_change

        time.sleep(0.01)

        # Large change - should update
        section.update(emotion="angry", valence=-0.5)
        assert section.last_significant_change_ms > initial_change


# =============================================================================
# Test: Factory Function
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_default(self):
        """Test factory with defaults."""
        section = create_affective_now_section()
        assert section.current_emotion == "neutral"
        assert section.valence == 0.0

    def test_create_with_session_id(self):
        """Test factory with session ID."""
        section = create_affective_now_section(session_id="my-session")
        assert section.session_id == "my-session"

    def test_create_with_initial_emotion(self):
        """Test factory with initial emotion."""
        section = create_affective_now_section(initial_emotion="happy")
        assert section.current_emotion == "happy"

    def test_create_with_initial_valence(self):
        """Test factory with initial valence."""
        section = create_affective_now_section(initial_valence=0.7)
        assert section.valence == 0.7

    def test_create_with_initial_arousal(self):
        """Test factory with initial arousal."""
        section = create_affective_now_section(initial_arousal=0.8)
        assert section.arousal == 0.8


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_emotion(self, section):
        """Test empty emotion string."""
        section.update(emotion="")
        assert section.current_emotion == ""

    def test_unicode_emotion(self, section):
        """Test unicode emotion string."""
        section.update(emotion="喜び")  # Japanese for "joy"
        assert section.current_emotion == "喜び"

    def test_unicode_roundtrip(self, section):
        """Test unicode survives serialization."""
        section.update(emotion="幸せ")

        data = section.to_flatbuffer()
        new_section = AffectiveNowSection()
        new_section.from_flatbuffer(data)

        assert new_section.current_emotion == "幸せ"

    def test_extreme_values(self, section):
        """Test extreme dimension values are clamped."""
        section.update(
            emotion="test",
            intensity=10.0,
            valence=5.0,
            arousal=-5.0,
        )
        assert section.intensity == 1.0
        assert section.valence == 1.0
        assert section.arousal == 0.0

    def test_zero_intensity(self, section):
        """Test zero intensity."""
        section.update(emotion="happy", intensity=0.0)
        assert section.intensity == 0.0

    def test_negative_turn_number(self, section):
        """Test negative turn number."""
        section.update(emotion="happy", turn_number=-1)
        assert section.current_turn == -1

    def test_many_updates(self, section):
        """Test many sequential updates."""
        for i in range(100):
            section.update(emotion=f"emotion_{i % 10}")

        assert len(section.recent_emotions) == 5
        assert section.current_turn == 100

    def test_rapid_updates(self, section):
        """Test rapid updates don't break state."""
        for _ in range(10):
            section.update(emotion="happy", valence=0.5)
            section.update(emotion="sad", valence=-0.5)

        assert section.current_emotion == "sad"
        assert len(section.recent_emotions) == 5

    def test_concurrent_serialization(self, section):
        """Test serialization during update doesn't corrupt."""
        section.update(emotion="happy")
        data1 = section.to_flatbuffer()

        section.update(emotion="curious")
        data2 = section.to_flatbuffer()

        # Both should be valid
        s1 = AffectiveNowSection()
        s1.from_flatbuffer(data1)
        assert s1.current_emotion == "happy"

        s2 = AffectiveNowSection()
        s2.from_flatbuffer(data2)
        assert s2.current_emotion == "curious"


# =============================================================================
# Test: Dimension Inference
# =============================================================================


class TestDimensionInference:
    """Tests for dimension inference from emotions."""

    def test_infer_valence_positive(self, section):
        """Test positive emotion infers positive valence."""
        section.update(emotion="joyful", intensity=1.0)
        assert section.valence > 0

    def test_infer_valence_negative(self, section):
        """Test negative emotion infers negative valence."""
        section.update(emotion="angry", intensity=1.0)
        assert section.valence < 0

    def test_infer_valence_neutral(self, section):
        """Test neutral emotion infers zero valence."""
        section.update(emotion="neutral", intensity=1.0)
        assert section.valence == 0.0

    def test_infer_arousal_high(self, section):
        """Test high arousal emotions."""
        section.update(emotion="excited", intensity=1.0)
        assert section.arousal > 0.7

    def test_infer_arousal_low(self, section):
        """Test low arousal emotions."""
        section.update(emotion="calm", intensity=1.0)
        assert section.arousal < 0.4

    def test_infer_emotion_from_dimensions(self, section):
        """Test emotion inference from dimensions."""
        section.update_dimensions(valence=0.8, arousal=0.8)
        assert section.current_emotion == "excited"

        section.update_dimensions(valence=-0.8, arousal=0.8)
        assert section.current_emotion == "angry"

        section.update_dimensions(valence=-0.8, arousal=0.2)
        assert section.current_emotion == "sad"

        section.update_dimensions(valence=0.0, arousal=0.5)
        assert section.current_emotion == "neutral"


# =============================================================================
# Test: Constants
# =============================================================================


class TestConstants:
    """Tests for section constants."""

    def test_budget_bytes(self):
        """Test budget constant."""
        assert AffectiveNowSection.BUDGET_BYTES == 4096

    def test_tier(self):
        """Test tier constant."""
        assert AffectiveNowSection.TIER == "hot"

    def test_can_evict(self):
        """Test can_evict constant."""
        assert AffectiveNowSection.CAN_EVICT is False

    def test_max_recent_emotions(self):
        """Test max history constant."""
        assert AffectiveNowSection.MAX_RECENT_EMOTIONS == 5

    def test_significant_change_threshold(self):
        """Test change threshold constant."""
        assert AffectiveNowSection.SIGNIFICANT_CHANGE_THRESHOLD == 0.3
