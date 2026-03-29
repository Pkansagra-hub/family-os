"""
Tests for PersonaSection.

Issue: 2.3.3 (WARM tier - persona)
Budget: 8KB (8192 bytes)
Eviction Priority: 4 (last in WARM)

Tests cover:
- Data classes (PersonalityProfile, VoicePreferences, etc.)
- ISection protocol compliance
- IEvictable protocol compliance
- Personality API
- Voice API
- Vocabulary API
- Response preferences API
- Calibration API
- FlatBuffer serialization
- Apply operations
- Edge cases
"""

import pytest

from k1.sessionstate.sections.persona import (
    EvictedData,
    InteractionStyle,
    PersonalityProfile,
    PersonalityTrait,
    PersonaSection,
    ResponsePreferences,
    VocabularyEntry,
    VoicePreferences,
    create_persona_section,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> PersonaSection:
    """Create fresh PersonaSection."""
    return PersonaSection()


@pytest.fixture
def populated_section(section: PersonaSection) -> PersonaSection:
    """Create section with personality and vocabulary."""
    # Set personality
    section.set_warmth(0.8)
    section.set_formality(0.3)
    section.set_humor(0.7)
    section.add_trait("patience", 0.9)

    # Add vocabulary
    section.add_vocabulary("the cottage", "vacation home in Maine")
    section.add_vocabulary("mom", "Alice Smith", "family context")

    # Set style
    section.set_interaction_style(InteractionStyle.FRIENDLY)

    return section


# =============================================================================
# PersonalityTrait Tests
# =============================================================================


class TestPersonalityTrait:
    """Tests for PersonalityTrait dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating trait with default value."""
        trait = PersonalityTrait(name="warmth")

        assert trait.name == "warmth"
        assert trait.value == 0.5

    def test_create_with_value(self) -> None:
        """Test creating trait with custom value."""
        trait = PersonalityTrait(name="humor", value=0.8)

        assert trait.name == "humor"
        assert trait.value == 0.8

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        trait = PersonalityTrait(name="directness", value=0.7)
        d = trait.to_dict()

        assert d["name"] == "directness"
        assert d["value"] == 0.7


# =============================================================================
# PersonalityProfile Tests
# =============================================================================


class TestPersonalityProfile:
    """Tests for PersonalityProfile dataclass."""

    def test_default_values(self) -> None:
        """Test default personality values."""
        profile = PersonalityProfile()

        assert profile.warmth == 0.5
        assert profile.formality == 0.5
        assert profile.verbosity == 0.5
        assert profile.humor == 0.5
        assert profile.directness == 0.5
        assert profile.traits == []
        assert profile.profile_type == ""

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        profile = PersonalityProfile(warmth=0.8, humor=0.3)
        d = profile.to_dict()

        assert d["warmth"] == 0.8
        assert d["humor"] == 0.3
        assert d["traits"] == []

    def test_get_trait(self) -> None:
        """Test getting custom trait."""
        profile = PersonalityProfile()
        profile.traits.append(PersonalityTrait("patience", 0.9))

        assert profile.get_trait("patience") == 0.9
        assert profile.get_trait("nonexistent") is None

    def test_set_trait_new(self) -> None:
        """Test setting new custom trait."""
        profile = PersonalityProfile()
        profile.set_trait("empathy", 0.8)

        assert len(profile.traits) == 1
        assert profile.get_trait("empathy") == 0.8

    def test_set_trait_existing(self) -> None:
        """Test updating existing trait."""
        profile = PersonalityProfile()
        profile.set_trait("empathy", 0.5)
        profile.set_trait("empathy", 0.9)

        assert len(profile.traits) == 1
        assert profile.get_trait("empathy") == 0.9

    def test_set_trait_clamps_value(self) -> None:
        """Test trait value is clamped to 0-1."""
        profile = PersonalityProfile()
        profile.set_trait("test", 1.5)
        assert profile.get_trait("test") == 1.0

        profile.set_trait("test2", -0.5)
        assert profile.get_trait("test2") == 0.0


# =============================================================================
# VoicePreferences Tests
# =============================================================================


class TestVoicePreferences:
    """Tests for VoicePreferences dataclass."""

    def test_default_values(self) -> None:
        """Test default voice values."""
        voice = VoicePreferences()

        assert voice.speaking_rate == 1.0
        assert voice.pitch == 0.0
        assert voice.volume == 1.0
        assert voice.voice_id == ""
        assert voice.language == "en-US"
        assert voice.accent == ""

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        voice = VoicePreferences(speaking_rate=1.2, pitch=0.5)
        d = voice.to_dict()

        assert d["speaking_rate"] == 1.2
        assert d["pitch"] == 0.5
        assert d["language"] == "en-US"


# =============================================================================
# VocabularyEntry Tests
# =============================================================================


class TestVocabularyEntry:
    """Tests for VocabularyEntry dataclass."""

    def test_create(self) -> None:
        """Test creating vocabulary entry."""
        entry = VocabularyEntry(
            user_term="the cottage",
            system_term="vacation home in Maine",
        )

        assert entry.user_term == "the cottage"
        assert entry.system_term == "vacation home in Maine"
        assert entry.context == ""

    def test_with_context(self) -> None:
        """Test entry with context."""
        entry = VocabularyEntry(
            user_term="mom",
            system_term="Alice Smith",
            context="family context",
        )

        assert entry.context == "family context"

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        entry = VocabularyEntry("the dog", "Max the golden retriever")
        d = entry.to_dict()

        assert d["user_term"] == "the dog"
        assert d["system_term"] == "Max the golden retriever"


# =============================================================================
# ResponsePreferences Tests
# =============================================================================


class TestResponsePreferences:
    """Tests for ResponsePreferences dataclass."""

    def test_default_values(self) -> None:
        """Test default response preferences."""
        prefs = ResponsePreferences()

        assert prefs.style == InteractionStyle.CONCISE
        assert prefs.max_response_length == 0
        assert prefs.use_bullet_points is True
        assert prefs.use_headers is False
        assert prefs.include_examples is True
        assert prefs.explain_reasoning is False

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        prefs = ResponsePreferences(style=InteractionStyle.FRIENDLY)
        d = prefs.to_dict()

        assert d["style"] == "FRIENDLY"
        assert d["use_bullet_points"] is True


# =============================================================================
# InteractionStyle Tests
# =============================================================================


class TestInteractionStyle:
    """Tests for InteractionStyle enum."""

    def test_values(self) -> None:
        """Test enum values."""
        assert InteractionStyle.CONCISE == 0
        assert InteractionStyle.DETAILED == 1
        assert InteractionStyle.CASUAL == 2
        assert InteractionStyle.FORMAL == 3
        assert InteractionStyle.TECHNICAL == 4
        assert InteractionStyle.FRIENDLY == 5

    def test_from_int(self) -> None:
        """Test creating from int."""
        style = InteractionStyle(3)
        assert style == InteractionStyle.FORMAL

    def test_from_name(self) -> None:
        """Test creating from name."""
        style = InteractionStyle["TECHNICAL"]
        assert style == InteractionStyle.TECHNICAL


# =============================================================================
# ISection Protocol Tests
# =============================================================================


class TestISection:
    """Tests for ISection protocol compliance."""

    def test_name(self, section: PersonaSection) -> None:
        """Test section name."""
        assert section.name == "persona"

    def test_tier(self, section: PersonaSection) -> None:
        """Test section tier."""
        assert section.tier == "warm"

    def test_budget_bytes(self, section: PersonaSection) -> None:
        """Test budget bytes."""
        assert section.budget_bytes == 8192  # 8KB

    def test_get_size_bytes_empty(self, section: PersonaSection) -> None:
        """Test size of empty section."""
        size = section.get_size_bytes()
        # Base size ~650 bytes
        assert 600 <= size <= 700

    def test_get_size_bytes_with_data(self, populated_section: PersonaSection) -> None:
        """Test size with data."""
        size = populated_section.get_size_bytes()
        # Base + 2 vocab entries * 100 + 1 trait * 50
        assert size > 800
        assert size < 2000

    def test_clear(self, populated_section: PersonaSection) -> None:
        """Test clearing section."""
        populated_section.clear()

        assert populated_section.vocabulary_count() == 0
        assert populated_section.is_personalized() is False
        assert populated_section.get_personality().warmth == 0.5

    def test_to_dict(self, populated_section: PersonaSection) -> None:
        """Test to_dict conversion."""
        d = populated_section.to_dict()

        assert d["name"] == "persona"
        assert d["tier"] == "warm"
        assert d["personality"]["warmth"] == 0.8
        assert len(d["vocabulary"]) == 2
        assert d["interaction_style"] == "FRIENDLY"


# =============================================================================
# IEvictable Protocol Tests
# =============================================================================


class TestIEvictable:
    """Tests for IEvictable protocol compliance."""

    def test_get_eviction_priority(self, section: PersonaSection) -> None:
        """Test eviction priority."""
        assert section.get_eviction_priority() == 4

    def test_can_evict_empty(self, section: PersonaSection) -> None:
        """Test empty section cannot evict."""
        assert section.can_evict() is False

    def test_can_evict_with_vocabulary(self, section: PersonaSection) -> None:
        """Test section with vocabulary can evict."""
        section.add_vocabulary("test", "test meaning")
        assert section.can_evict() is True

    def test_can_evict_with_traits(self, section: PersonaSection) -> None:
        """Test section with traits can evict."""
        section.add_trait("custom", 0.5)
        assert section.can_evict() is True

    def test_evict_partial_vocabulary_first(self, populated_section: PersonaSection) -> None:
        """Test eviction evicts vocabulary first."""
        initial_vocab = populated_section.vocabulary_count()

        evicted = populated_section.evict_partial(target_kb=0.2)

        assert len(evicted.vocabulary_entries) > 0
        assert populated_section.vocabulary_count() < initial_vocab

    def test_evict_partial_traits_after_vocabulary(self, section: PersonaSection) -> None:
        """Test eviction evicts traits after vocabulary exhausted."""
        # Add only traits
        section.add_trait("trait1", 0.5)
        section.add_trait("trait2", 0.6)

        evicted = section.evict_partial(target_kb=0.1)

        assert len(evicted.custom_traits) > 0
        assert len(evicted.vocabulary_entries) == 0

    def test_evict_tracks_bytes(self, populated_section: PersonaSection) -> None:
        """Test eviction tracks bytes freed."""
        evicted = populated_section.evict_partial(target_kb=0.5)

        assert evicted.bytes_freed > 0

    def test_evicted_data_structure(self, populated_section: PersonaSection) -> None:
        """Test EvictedData structure."""
        evicted = populated_section.evict_partial(target_kb=0.2)

        assert isinstance(evicted, EvictedData)
        assert isinstance(evicted.vocabulary_entries, list)
        assert isinstance(evicted.custom_traits, list)
        assert evicted.eviction_reason == "pressure"


# =============================================================================
# Personality API Tests
# =============================================================================


class TestPersonalityAPI:
    """Tests for personality API."""

    def test_set_warmth(self, section: PersonaSection) -> None:
        """Test setting warmth."""
        section.set_warmth(0.8)

        assert section.get_personality().warmth == 0.8
        assert section.is_personalized() is True

    def test_set_warmth_clamps(self, section: PersonaSection) -> None:
        """Test warmth is clamped to 0-1."""
        section.set_warmth(1.5)
        assert section.get_personality().warmth == 1.0

        section.set_warmth(-0.5)
        assert section.get_personality().warmth == 0.0

    def test_set_formality(self, section: PersonaSection) -> None:
        """Test setting formality."""
        section.set_formality(0.2)
        assert section.get_personality().formality == 0.2

    def test_set_verbosity(self, section: PersonaSection) -> None:
        """Test setting verbosity."""
        section.set_verbosity(0.9)
        assert section.get_personality().verbosity == 0.9

    def test_set_humor(self, section: PersonaSection) -> None:
        """Test setting humor."""
        section.set_humor(0.6)
        assert section.get_personality().humor == 0.6

    def test_set_directness(self, section: PersonaSection) -> None:
        """Test setting directness."""
        section.set_directness(0.7)
        assert section.get_personality().directness == 0.7

    def test_set_profile_type(self, section: PersonaSection) -> None:
        """Test setting profile type."""
        section.set_profile_type("professional")
        assert section.get_personality().profile_type == "professional"

    def test_add_trait(self, section: PersonaSection) -> None:
        """Test adding custom trait."""
        result = section.add_trait("patience", 0.9)

        assert result is True
        assert section.get_trait("patience") == 0.9

    def test_add_trait_capacity(self, section: PersonaSection) -> None:
        """Test trait capacity limit."""
        for i in range(section.MAX_CUSTOM_TRAITS):
            section.add_trait(f"trait_{i}", 0.5)

        result = section.add_trait("overflow", 0.5)
        assert result is False

    def test_remove_trait(self, section: PersonaSection) -> None:
        """Test removing trait."""
        section.add_trait("test", 0.5)

        result = section.remove_trait("test")

        assert result is True
        assert section.get_trait("test") is None

    def test_remove_trait_not_found(self, section: PersonaSection) -> None:
        """Test removing non-existent trait."""
        result = section.remove_trait("nonexistent")
        assert result is False


# =============================================================================
# Voice API Tests
# =============================================================================


class TestVoiceAPI:
    """Tests for voice API."""

    def test_set_speaking_rate(self, section: PersonaSection) -> None:
        """Test setting speaking rate."""
        section.set_speaking_rate(1.5)
        assert section.get_voice().speaking_rate == 1.5

    def test_set_speaking_rate_clamps(self, section: PersonaSection) -> None:
        """Test speaking rate is clamped to 0.5-2.0."""
        section.set_speaking_rate(3.0)
        assert section.get_voice().speaking_rate == 2.0

        section.set_speaking_rate(0.1)
        assert section.get_voice().speaking_rate == 0.5

    def test_set_pitch(self, section: PersonaSection) -> None:
        """Test setting pitch."""
        section.set_pitch(0.5)
        assert section.get_voice().pitch == 0.5

    def test_set_pitch_clamps(self, section: PersonaSection) -> None:
        """Test pitch is clamped to -1 to 1."""
        section.set_pitch(2.0)
        assert section.get_voice().pitch == 1.0

        section.set_pitch(-2.0)
        assert section.get_voice().pitch == -1.0

    def test_set_volume(self, section: PersonaSection) -> None:
        """Test setting volume."""
        section.set_volume(0.8)
        assert section.get_voice().volume == 0.8

    def test_set_voice_id(self, section: PersonaSection) -> None:
        """Test setting voice ID."""
        section.set_voice_id("voice-abc123")
        assert section.get_voice().voice_id == "voice-abc123"

    def test_set_language(self, section: PersonaSection) -> None:
        """Test setting language."""
        section.set_language("es-ES")
        assert section.get_voice().language == "es-ES"

    def test_set_accent(self, section: PersonaSection) -> None:
        """Test setting accent."""
        section.set_accent("british")
        assert section.get_voice().accent == "british"


# =============================================================================
# Vocabulary API Tests
# =============================================================================


class TestVocabularyAPI:
    """Tests for vocabulary API."""

    def test_add_vocabulary(self, section: PersonaSection) -> None:
        """Test adding vocabulary."""
        result = section.add_vocabulary("the cottage", "vacation home")

        assert result is True
        assert section.vocabulary_count() == 1

    def test_add_vocabulary_with_context(self, section: PersonaSection) -> None:
        """Test adding vocabulary with context."""
        section.add_vocabulary("mom", "Alice", "family")

        entries = section.list_vocabulary()
        assert entries[0].context == "family"

    def test_add_vocabulary_updates_existing(self, section: PersonaSection) -> None:
        """Test adding existing vocabulary updates it."""
        section.add_vocabulary("test", "meaning1")
        section.add_vocabulary("test", "meaning2")

        assert section.vocabulary_count() == 1
        assert section.get_vocabulary("test") == "meaning2"

    def test_add_vocabulary_capacity(self, section: PersonaSection) -> None:
        """Test vocabulary capacity limit."""
        for i in range(section.MAX_VOCABULARY_ENTRIES):
            section.add_vocabulary(f"term_{i}", f"meaning_{i}")

        result = section.add_vocabulary("overflow", "meaning")
        assert result is False

    def test_get_vocabulary(self, section: PersonaSection) -> None:
        """Test getting vocabulary."""
        section.add_vocabulary("the dog", "Max")

        assert section.get_vocabulary("the dog") == "Max"
        assert section.get_vocabulary("nonexistent") is None

    def test_remove_vocabulary(self, section: PersonaSection) -> None:
        """Test removing vocabulary."""
        section.add_vocabulary("test", "meaning")

        result = section.remove_vocabulary("test")

        assert result is True
        assert section.vocabulary_count() == 0

    def test_remove_vocabulary_not_found(self, section: PersonaSection) -> None:
        """Test removing non-existent vocabulary."""
        result = section.remove_vocabulary("nonexistent")
        assert result is False

    def test_list_vocabulary(self, populated_section: PersonaSection) -> None:
        """Test listing vocabulary."""
        entries = populated_section.list_vocabulary()

        assert len(entries) == 2
        assert any(e.user_term == "the cottage" for e in entries)

    def test_translate_text(self, section: PersonaSection) -> None:
        """Test translating text."""
        section.add_vocabulary("the cottage", "vacation home in Maine")

        result = section.translate_text("Let's go to the cottage")

        assert result == "Let's go to vacation home in Maine"

    def test_translate_text_multiple(self, section: PersonaSection) -> None:
        """Test translating multiple terms."""
        section.add_vocabulary("mom", "Alice")
        section.add_vocabulary("dad", "Bob")

        result = section.translate_text("Call mom and dad")

        assert result == "Call Alice and Bob"


# =============================================================================
# Response Preferences API Tests
# =============================================================================


class TestResponsePreferencesAPI:
    """Tests for response preferences API."""

    def test_set_interaction_style(self, section: PersonaSection) -> None:
        """Test setting interaction style."""
        section.set_interaction_style(InteractionStyle.TECHNICAL)

        assert section.get_interaction_style() == InteractionStyle.TECHNICAL
        assert section.get_response_prefs().style == InteractionStyle.TECHNICAL

    def test_set_max_response_length(self, section: PersonaSection) -> None:
        """Test setting max response length."""
        section.set_max_response_length(500)
        assert section.get_response_prefs().max_response_length == 500

    def test_set_use_bullet_points(self, section: PersonaSection) -> None:
        """Test setting bullet points preference."""
        section.set_use_bullet_points(False)
        assert section.get_response_prefs().use_bullet_points is False

    def test_set_use_headers(self, section: PersonaSection) -> None:
        """Test setting headers preference."""
        section.set_use_headers(True)
        assert section.get_response_prefs().use_headers is True

    def test_set_include_examples(self, section: PersonaSection) -> None:
        """Test setting examples preference."""
        section.set_include_examples(False)
        assert section.get_response_prefs().include_examples is False

    def test_set_explain_reasoning(self, section: PersonaSection) -> None:
        """Test setting reasoning preference."""
        section.set_explain_reasoning(True)
        assert section.get_response_prefs().explain_reasoning is True


# =============================================================================
# Calibration API Tests
# =============================================================================


class TestCalibrationAPI:
    """Tests for calibration API."""

    def test_is_personalized_initial(self, section: PersonaSection) -> None:
        """Test initial personalized state."""
        assert section.is_personalized() is False

    def test_is_personalized_after_change(self, section: PersonaSection) -> None:
        """Test personalized after making changes."""
        section.set_warmth(0.8)
        assert section.is_personalized() is True

    def test_get_calibration_confidence_initial(self, section: PersonaSection) -> None:
        """Test initial calibration confidence."""
        assert section.get_calibration_confidence() == 0.5

    def test_set_calibration_confidence(self, section: PersonaSection) -> None:
        """Test setting calibration confidence."""
        section.set_calibration_confidence(0.9)
        assert section.get_calibration_confidence() == 0.9

    def test_set_calibration_confidence_clamps(self, section: PersonaSection) -> None:
        """Test calibration confidence is clamped."""
        section.set_calibration_confidence(1.5)
        assert section.get_calibration_confidence() == 1.0

    def test_mark_calibrated(self, section: PersonaSection) -> None:
        """Test marking as calibrated."""
        section.mark_calibrated(turn_number=15, confidence=0.85)

        assert section.get_last_calibrated_turn() == 15
        assert section.get_calibration_confidence() == 0.85
        assert section.is_personalized() is True


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests for statistics API."""

    def test_get_statistics(self, populated_section: PersonaSection) -> None:
        """Test getting statistics."""
        stats = populated_section.get_statistics()

        assert stats["vocabulary_count"] == 2
        assert stats["custom_traits_count"] == 1
        assert stats["max_vocabulary"] == 30
        assert stats["max_traits"] == 20
        assert stats["is_personalized"] is True
        assert stats["interaction_style"] == "FRIENDLY"

    def test_statistics_empty(self, section: PersonaSection) -> None:
        """Test statistics for empty section."""
        stats = section.get_statistics()

        assert stats["vocabulary_count"] == 0
        assert stats["custom_traits_count"] == 0
        assert stats["is_personalized"] is False


# =============================================================================
# Integrity Tests
# =============================================================================


class TestIntegrity:
    """Tests for integrity verification."""

    def test_compute_integrity(self, populated_section: PersonaSection) -> None:
        """Test computing integrity hash."""
        hash1 = populated_section.compute_integrity()

        assert len(hash1) == 64  # SHA256 hex
        assert hash1 == populated_section.compute_integrity()  # Deterministic

    def test_verify_integrity(self, populated_section: PersonaSection) -> None:
        """Test verifying integrity."""
        populated_section.update_integrity()

        assert populated_section.verify_integrity() is True

    def test_verify_integrity_after_modification(self, populated_section: PersonaSection) -> None:
        """Test integrity fails after modification."""
        populated_section.update_integrity()

        # Modify
        populated_section.set_warmth(0.1)

        assert populated_section.verify_integrity() is False

    def test_verify_no_hash(self, section: PersonaSection) -> None:
        """Test verification passes with no hash set."""
        assert section.verify_integrity() is True


# =============================================================================
# FlatBuffer Serialization Tests
# =============================================================================


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_to_flatbuffer(self, populated_section: PersonaSection) -> None:
        """Test serializing to FlatBuffer."""
        data = populated_section.to_flatbuffer()

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_from_flatbuffer(self, populated_section: PersonaSection) -> None:
        """Test deserializing from FlatBuffer."""
        data = populated_section.to_flatbuffer()

        restored = PersonaSection()
        restored.from_flatbuffer(data)

        assert restored.vocabulary_count() == populated_section.vocabulary_count()
        assert restored.is_personalized() == populated_section.is_personalized()
        assert restored.get_interaction_style() == populated_section.get_interaction_style()

    def test_roundtrip_personality(self, section: PersonaSection) -> None:
        """Test roundtrip preserves personality."""
        section.set_warmth(0.8)
        section.set_formality(0.2)
        section.set_profile_type("professional")
        section.add_trait("patience", 0.9)

        data = section.to_flatbuffer()
        restored = PersonaSection()
        restored.from_flatbuffer(data)

        # Float32 precision from FlatBuffer
        assert abs(restored.get_personality().warmth - 0.8) < 1e-6
        assert abs(restored.get_personality().formality - 0.2) < 1e-6
        assert restored.get_personality().profile_type == "professional"
        # Trait values also float32
        trait_val = restored.get_trait("patience")
        assert trait_val is not None
        assert abs(trait_val - 0.9) < 1e-6

    def test_roundtrip_voice(self, section: PersonaSection) -> None:
        """Test roundtrip preserves voice preferences."""
        section.set_speaking_rate(1.5)
        section.set_pitch(0.3)
        section.set_voice_id("voice-123")
        section.set_language("es-ES")

        data = section.to_flatbuffer()
        restored = PersonaSection()
        restored.from_flatbuffer(data)

        assert restored.get_voice().speaking_rate == 1.5
        # Float32 precision from FlatBuffer
        assert abs(restored.get_voice().pitch - 0.3) < 1e-6
        assert restored.get_voice().voice_id == "voice-123"
        assert restored.get_voice().language == "es-ES"

    def test_roundtrip_vocabulary(self, section: PersonaSection) -> None:
        """Test roundtrip preserves vocabulary."""
        section.add_vocabulary("the cottage", "vacation home", "context1")
        section.add_vocabulary("mom", "Alice Smith")

        data = section.to_flatbuffer()
        restored = PersonaSection()
        restored.from_flatbuffer(data)

        assert restored.vocabulary_count() == 2
        assert restored.get_vocabulary("the cottage") == "vacation home"
        assert restored.get_vocabulary("mom") == "Alice Smith"

    def test_roundtrip_response_prefs(self, section: PersonaSection) -> None:
        """Test roundtrip preserves response preferences."""
        section.set_interaction_style(InteractionStyle.TECHNICAL)
        section.set_max_response_length(500)
        section.set_use_bullet_points(False)
        section.set_explain_reasoning(True)

        data = section.to_flatbuffer()
        restored = PersonaSection()
        restored.from_flatbuffer(data)

        prefs = restored.get_response_prefs()
        assert prefs.style == InteractionStyle.TECHNICAL
        assert prefs.max_response_length == 500
        assert prefs.use_bullet_points is False
        assert prefs.explain_reasoning is True

    def test_roundtrip_calibration(self, section: PersonaSection) -> None:
        """Test roundtrip preserves calibration data."""
        section.mark_calibrated(turn_number=25, confidence=0.9)

        data = section.to_flatbuffer()
        restored = PersonaSection()
        restored.from_flatbuffer(data)

        assert restored.get_last_calibrated_turn() == 25
        # Float32 precision from FlatBuffer
        assert abs(restored.get_calibration_confidence() - 0.9) < 1e-6
        assert restored.is_personalized() is True

    def test_caching(self, populated_section: PersonaSection) -> None:
        """Test FlatBuffer caching."""
        data1 = populated_section.to_flatbuffer()
        data2 = populated_section.to_flatbuffer()

        # Same reference (cached)
        assert data1 is data2

    def test_cache_invalidation(self, section: PersonaSection) -> None:
        """Test cache invalidated on modification."""
        section.add_vocabulary("test", "meaning")
        data1 = section.to_flatbuffer()

        section.set_warmth(0.9)
        data2 = section.to_flatbuffer()

        assert data1 is not data2


# =============================================================================
# Apply Operations Tests
# =============================================================================


class TestApplyOperations:
    """Tests for apply operations (MutationGuard pattern)."""

    def test_apply_set_warmth(self, section: PersonaSection) -> None:
        """Test apply set_warmth."""
        section.apply("set_warmth", {"value": 0.8})
        assert section.get_personality().warmth == 0.8

    def test_apply_set_formality(self, section: PersonaSection) -> None:
        """Test apply set_formality."""
        section.apply("set_formality", {"value": 0.3})
        assert section.get_personality().formality == 0.3

    def test_apply_add_trait(self, section: PersonaSection) -> None:
        """Test apply add_trait."""
        result = section.apply("add_trait", {"name": "test", "value": 0.7})
        assert result is True
        assert section.get_trait("test") == 0.7

    def test_apply_add_vocabulary(self, section: PersonaSection) -> None:
        """Test apply add_vocabulary."""
        result = section.apply(
            "add_vocabulary",
            {"user_term": "test", "system_term": "meaning"},
        )
        assert result is True
        assert section.vocabulary_count() == 1

    def test_apply_set_interaction_style_int(self, section: PersonaSection) -> None:
        """Test apply set_interaction_style with int."""
        section.apply("set_interaction_style", {"style": 4})
        assert section.get_interaction_style() == InteractionStyle.TECHNICAL

    def test_apply_set_interaction_style_str(self, section: PersonaSection) -> None:
        """Test apply set_interaction_style with string."""
        section.apply("set_interaction_style", {"style": "FRIENDLY"})
        assert section.get_interaction_style() == InteractionStyle.FRIENDLY

    def test_apply_set_interaction_style_enum(self, section: PersonaSection) -> None:
        """Test apply set_interaction_style with enum."""
        section.apply("set_interaction_style", {"style": InteractionStyle.FORMAL})
        assert section.get_interaction_style() == InteractionStyle.FORMAL

    def test_apply_mark_calibrated(self, section: PersonaSection) -> None:
        """Test apply mark_calibrated."""
        section.apply("mark_calibrated", {"turn_number": 10, "confidence": 0.85})

        assert section.get_last_calibrated_turn() == 10
        assert section.get_calibration_confidence() == 0.85

    def test_apply_evict_partial(self, populated_section: PersonaSection) -> None:
        """Test apply evict_partial."""
        result = populated_section.apply("evict_partial", {"target_kb": 0.2})

        assert isinstance(result, EvictedData)
        assert result.bytes_freed > 0

    def test_apply_clear(self, populated_section: PersonaSection) -> None:
        """Test apply clear."""
        populated_section.apply("clear", {})

        assert populated_section.vocabulary_count() == 0
        assert populated_section.is_personalized() is False

    def test_apply_unknown_operation(self, section: PersonaSection) -> None:
        """Test apply with unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown", {})


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_persona_section(self) -> None:
        """Test factory creates empty section."""
        section = create_persona_section()

        assert isinstance(section, PersonaSection)
        assert section.vocabulary_count() == 0
        assert section.is_personalized() is False


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_len(self, populated_section: PersonaSection) -> None:
        """Test __len__ returns vocab + traits count."""
        # 2 vocab + 1 trait
        assert len(populated_section) == 3

    def test_repr(self, populated_section: PersonaSection) -> None:
        """Test __repr__."""
        r = repr(populated_section)

        assert "PersonaSection" in r
        assert "FRIENDLY" in r
        assert "personalized=True" in r

    def test_unicode_content(self, section: PersonaSection) -> None:
        """Test unicode in content."""
        section.add_vocabulary("die Katze", "the cat named Müller")
        section.set_profile_type("freundlich")  # German for friendly
        section.add_trait("Geduld", 0.9)  # German for patience

        data = section.to_flatbuffer()
        restored = PersonaSection()
        restored.from_flatbuffer(data)

        assert restored.get_vocabulary("die Katze") == "the cat named Müller"
        assert restored.get_personality().profile_type == "freundlich"
        # Float32 precision from FlatBuffer
        trait_val = restored.get_trait("Geduld")
        assert trait_val is not None
        assert abs(trait_val - 0.9) < 1e-6

    def test_constants(self) -> None:
        """Test class constants."""
        assert PersonaSection.BUDGET_BYTES == 8192
        assert PersonaSection.TIER == "warm"
        assert PersonaSection.SECTION_NAME == "persona"
        assert PersonaSection.CAN_EVICT is True
        assert PersonaSection.EVICTION_PRIORITY == 4
        assert PersonaSection.MAX_VOCABULARY_ENTRIES == 30
        assert PersonaSection.MAX_CUSTOM_TRAITS == 20
