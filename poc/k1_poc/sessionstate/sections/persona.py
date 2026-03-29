"""
PersonaSection - Stable User Persona (WARM)
============================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.3 Implement WARM TIER Sections
ISSUE: 2.3.3 (persona)

This section contains stable user personality, voice preferences, and style controls.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/persona_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- personality: PersonalityProfile (warmth, formality, verbosity, humor, directness)
- voice: ProsodyControls (speaking_rate, pitch, volume, voice_id, language)
- vocabulary: [VocabularyEntry] (user_term -> system_term mappings)
- response_prefs: ResponsePreferences (style, max_length, formatting)
- interaction_style: InteractionStyle enum
- is_personalized: bool
- last_calibrated_turn: uint16
- calibration_confidence: float

Eviction Contract (IEvictable):
- get_eviction_priority() -> int  (returns 4, last to evict)
- evict_partial(target_kb: int) -> EvictedData
- can_evict() -> bool
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    PersonaSection as FBPersonaSection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.PersonalityProfile import (
    PersonalityProfileAddDirectness,
    PersonalityProfileAddFormality,
    PersonalityProfileAddHumor,
    PersonalityProfileAddProfileType,
    PersonalityProfileAddTraits,
    PersonalityProfileAddVerbosity,
    PersonalityProfileAddWarmth,
    PersonalityProfileEnd,
    PersonalityProfileStart,
    PersonalityProfileStartTraitsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.PersonalityTrait import (
    PersonalityTraitAddName,
    PersonalityTraitAddValue,
    PersonalityTraitEnd,
    PersonalityTraitStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.PersonaSection import (
    PersonaSectionAddCalibrationConfidence,
    PersonaSectionAddHeader,
    PersonaSectionAddInteractionStyle,
    PersonaSectionAddIsPersonalized,
    PersonaSectionAddLastCalibratedTurn,
    PersonaSectionAddPersonality,
    PersonaSectionAddResponsePrefs,
    PersonaSectionAddVocabulary,
    PersonaSectionAddVoice,
    PersonaSectionEnd,
    PersonaSectionStart,
    PersonaSectionStartVocabularyVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.ProsodyControls import (
    ProsodyControlsAddAccent,
    ProsodyControlsAddLanguage,
    ProsodyControlsAddPitch,
    ProsodyControlsAddSpeakingRate,
    ProsodyControlsAddVoiceId,
    ProsodyControlsAddVolume,
    ProsodyControlsEnd,
    ProsodyControlsStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.ResponsePreferences import (
    ResponsePreferencesAddExplainReasoning,
    ResponsePreferencesAddIncludeExamples,
    ResponsePreferencesAddMaxResponseLength,
    ResponsePreferencesAddStyle,
    ResponsePreferencesAddUseBulletPoints,
    ResponsePreferencesAddUseHeaders,
    ResponsePreferencesEnd,
    ResponsePreferencesStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.VocabularyEntry import (
    VocabularyEntryAddContext,
    VocabularyEntryAddSystemTerm,
    VocabularyEntryAddUserTerm,
    VocabularyEntryEnd,
    VocabularyEntryStart,
)

# =============================================================================
# Enums
# =============================================================================


class InteractionStyle(IntEnum):
    """Interaction style preferences."""

    CONCISE = 0
    DETAILED = 1
    CASUAL = 2
    FORMAL = 3
    TECHNICAL = 4
    FRIENDLY = 5


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PersonalityTrait:
    """Named personality trait with value 0.0-1.0."""

    name: str
    value: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"name": self.name, "value": self.value}


@dataclass
class PersonalityProfile:
    """User personality profile."""

    # Core traits (0.0 to 1.0)
    warmth: float = 0.5
    formality: float = 0.5
    verbosity: float = 0.5
    humor: float = 0.5
    directness: float = 0.5

    # Custom traits
    traits: List[PersonalityTrait] = field(default_factory=list)

    # Derived profile type
    profile_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "warmth": self.warmth,
            "formality": self.formality,
            "verbosity": self.verbosity,
            "humor": self.humor,
            "directness": self.directness,
            "traits": [t.to_dict() for t in self.traits],
            "profile_type": self.profile_type,
        }

    def get_trait(self, name: str) -> Optional[float]:
        """Get custom trait value by name."""
        for trait in self.traits:
            if trait.name == name:
                return trait.value
        return None

    def set_trait(self, name: str, value: float) -> None:
        """Set custom trait value."""
        value = max(0.0, min(1.0, value))
        for trait in self.traits:
            if trait.name == name:
                trait.value = value
                return
        self.traits.append(PersonalityTrait(name=name, value=value))


@dataclass
class VoicePreferences:
    """Voice/prosody controls."""

    speaking_rate: float = 1.0  # 0.5 to 2.0
    pitch: float = 0.0  # -1.0 to 1.0
    volume: float = 1.0  # 0.0 to 1.0
    voice_id: str = ""
    language: str = "en-US"
    accent: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "speaking_rate": self.speaking_rate,
            "pitch": self.pitch,
            "volume": self.volume,
            "voice_id": self.voice_id,
            "language": self.language,
            "accent": self.accent,
        }


@dataclass
class VocabularyEntry:
    """Custom vocabulary mapping."""

    user_term: str  # What user says
    system_term: str  # What it means
    context: str = ""  # When to apply

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_term": self.user_term,
            "system_term": self.system_term,
            "context": self.context,
        }


@dataclass
class ResponsePreferences:
    """Response format preferences."""

    style: InteractionStyle = InteractionStyle.CONCISE
    max_response_length: int = 0  # 0 = no limit
    use_bullet_points: bool = True
    use_headers: bool = False
    include_examples: bool = True
    explain_reasoning: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "style": self.style.name,
            "max_response_length": self.max_response_length,
            "use_bullet_points": self.use_bullet_points,
            "use_headers": self.use_headers,
            "include_examples": self.include_examples,
            "explain_reasoning": self.explain_reasoning,
        }


@dataclass
class EvictedData:
    """Data evicted from persona section."""

    vocabulary_entries: List[VocabularyEntry] = field(default_factory=list)
    custom_traits: List[PersonalityTrait] = field(default_factory=list)
    bytes_freed: int = 0
    eviction_reason: str = "pressure"


# =============================================================================
# PersonaSection - Main Implementation
# =============================================================================


class PersonaSection:
    """
    Persona section - stable user personality and preferences (WARM tier).

    Implements ISection and IEvictable protocols.

    Budget: 8KB (8192 bytes)
    Eviction Priority: 4 (last to evict in WARM tier)

    Contains:
    - Personality profile (warmth, formality, verbosity, humor, directness)
    - Voice preferences (rate, pitch, volume, language)
    - Custom vocabulary (user terms -> system terms)
    - Response preferences (style, formatting)

    Attributes:
        _personality: PersonalityProfile
        _voice: VoicePreferences
        _vocabulary: List[VocabularyEntry]
        _response_prefs: ResponsePreferences
        _interaction_style: InteractionStyle
        _is_personalized: bool

    Example:
        section = PersonaSection()

        # Set personality
        section.set_warmth(0.8)
        section.set_formality(0.3)

        # Add vocabulary
        section.add_vocabulary("the cottage", "vacation home in Maine")

        # Set response style
        section.set_interaction_style(InteractionStyle.FRIENDLY)
    """

    # Section constants
    BUDGET_BYTES = 8192  # 8KB
    TIER = "warm"
    SECTION_NAME = "persona"
    CAN_EVICT = True
    EVICTION_PRIORITY = 4  # Last to evict in WARM

    # Capacity limits
    MAX_VOCABULARY_ENTRIES = 30
    MAX_CUSTOM_TRAITS = 20

    def __init__(self) -> None:
        """Initialize empty PersonaSection."""
        self._personality = PersonalityProfile()
        self._voice = VoicePreferences()
        self._vocabulary: List[VocabularyEntry] = []
        self._response_prefs = ResponsePreferences()
        self._interaction_style = InteractionStyle.CONCISE
        self._is_personalized = False
        self._last_calibrated_turn: int = 0
        self._calibration_confidence: float = 0.5
        self._updated_at_ms: int = int(time.time() * 1000)
        self._integrity_hash: str = ""
        self._fb_cache: Optional[bytes] = None
        self._preferences: Dict[str, Any] = {}
        self._frozen: bool = False

    # =========================================================================
    # ISection Protocol
    # =========================================================================

    @property
    def name(self) -> str:
        """Section name identifier."""
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        """Section tier (warm)."""
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        """Size budget in bytes."""
        return self.BUDGET_BYTES

    def get_size_bytes(self) -> int:
        """
        Get current size in bytes.

        PersonalityProfile: ~300 bytes
        VoicePreferences: ~100 bytes
        VocabularyEntry: ~100 bytes each
        ResponsePreferences: ~50 bytes
        Header + metadata: ~200 bytes
        """
        base_size = 650  # Profile + voice + prefs + header
        vocab_size = len(self._vocabulary) * 100
        traits_size = len(self._personality.traits) * 50
        return base_size + vocab_size + traits_size

    def clear(self) -> None:
        """Clear all data."""
        self._personality = PersonalityProfile()
        self._voice = VoicePreferences()
        self._vocabulary.clear()
        self._response_prefs = ResponsePreferences()
        self._interaction_style = InteractionStyle.CONCISE
        self._is_personalized = False
        self._last_calibrated_turn = 0
        self._calibration_confidence = 0.5
        self._updated_at_ms = int(time.time() * 1000)
        self._integrity_hash = ""
        self._invalidate_cache()

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to dictionary representation."""
        return {
            "name": self.name,
            "tier": self.tier,
            "size_bytes": self.get_size_bytes(),
            "budget_bytes": self.budget_bytes,
            "personality": self._personality.to_dict(),
            "voice": self._voice.to_dict(),
            "vocabulary": [v.to_dict() for v in self._vocabulary],
            "response_prefs": self._response_prefs.to_dict(),
            "interaction_style": self._interaction_style.name,
            "is_personalized": self._is_personalized,
            "last_calibrated_turn": self._last_calibrated_turn,
            "calibration_confidence": self._calibration_confidence,
        }

    # =========================================================================
    # IEvictable Protocol
    # =========================================================================

    def get_eviction_priority(self) -> int:
        """
        Get eviction priority (lower = evict first).

        Returns:
            int: Priority 4 (last to evict)
        """
        return self.EVICTION_PRIORITY

    def can_evict(self) -> bool:
        """
        Check if this section can be evicted.

        Returns:
            bool: True if there's vocabulary or custom traits to evict
        """
        return len(self._vocabulary) > 0 or len(self._personality.traits) > 0

    def evict_partial(self, target_kb: float) -> EvictedData:
        """
        Evict vocabulary and traits to free up space.

        Eviction order:
        1. Vocabulary entries (oldest first)
        2. Custom traits (least used first)

        Args:
            target_kb: Target kilobytes to free

        Returns:
            EvictedData: Data evicted and bytes freed
        """
        target_bytes = int(target_kb * 1024)
        bytes_freed = 0

        evicted_vocab: List[VocabularyEntry] = []
        evicted_traits: List[PersonalityTrait] = []

        # First evict vocabulary (oldest first)
        while self._vocabulary and bytes_freed < target_bytes:
            entry = self._vocabulary.pop(0)
            evicted_vocab.append(entry)
            bytes_freed += 100

        # Then evict custom traits if needed
        while self._personality.traits and bytes_freed < target_bytes:
            trait = self._personality.traits.pop(0)
            evicted_traits.append(trait)
            bytes_freed += 50

        self._updated_at_ms = int(time.time() * 1000)
        self._invalidate_cache()

        return EvictedData(
            vocabulary_entries=evicted_vocab,
            custom_traits=evicted_traits,
            bytes_freed=bytes_freed,
            eviction_reason="pressure",
        )

    # =========================================================================
    # Personality API
    # =========================================================================

    def get_personality(self) -> PersonalityProfile:
        """Get personality profile."""
        return self._personality

    def set_warmth(self, value: float) -> None:
        """Set warmth (0.0-1.0)."""
        self._personality.warmth = max(0.0, min(1.0, value))
        self._mark_personalized()

    def set_formality(self, value: float) -> None:
        """Set formality (0.0-1.0)."""
        self._personality.formality = max(0.0, min(1.0, value))
        self._mark_personalized()

    def set_verbosity(self, value: float) -> None:
        """Set verbosity (0.0-1.0)."""
        self._personality.verbosity = max(0.0, min(1.0, value))
        self._mark_personalized()

    def set_humor(self, value: float) -> None:
        """Set humor (0.0-1.0)."""
        self._personality.humor = max(0.0, min(1.0, value))
        self._mark_personalized()

    def set_directness(self, value: float) -> None:
        """Set directness (0.0-1.0)."""
        self._personality.directness = max(0.0, min(1.0, value))
        self._mark_personalized()

    def set_profile_type(self, profile_type: str) -> None:
        """Set derived profile type."""
        self._personality.profile_type = profile_type
        self._mark_personalized()

    def add_trait(self, name: str, value: float) -> bool:
        """
        Add custom personality trait.

        Args:
            name: Trait name
            value: Trait value (0.0-1.0)

        Returns:
            bool: True if added
        """
        if len(self._personality.traits) >= self.MAX_CUSTOM_TRAITS:
            return False

        self._personality.set_trait(name, value)
        self._mark_personalized()
        return True

    def get_trait(self, name: str) -> Optional[float]:
        """Get custom trait value."""
        return self._personality.get_trait(name)

    def remove_trait(self, name: str) -> bool:
        """Remove custom trait."""
        for i, trait in enumerate(self._personality.traits):
            if trait.name == name:
                self._personality.traits.pop(i)
                self._invalidate_cache()
                return True
        return False

    # =========================================================================
    # Voice API
    # =========================================================================

    def get_voice(self) -> VoicePreferences:
        """Get voice preferences."""
        return self._voice

    def set_speaking_rate(self, rate: float) -> None:
        """Set speaking rate (0.5-2.0)."""
        self._voice.speaking_rate = max(0.5, min(2.0, rate))
        self._mark_personalized()

    def set_pitch(self, pitch: float) -> None:
        """Set pitch (-1.0 to 1.0)."""
        self._voice.pitch = max(-1.0, min(1.0, pitch))
        self._mark_personalized()

    def set_volume(self, volume: float) -> None:
        """Set volume (0.0-1.0)."""
        self._voice.volume = max(0.0, min(1.0, volume))
        self._mark_personalized()

    def set_voice_id(self, voice_id: str) -> None:
        """Set TTS voice identifier."""
        self._voice.voice_id = voice_id
        self._mark_personalized()

    def set_language(self, language: str) -> None:
        """Set language code."""
        self._voice.language = language
        self._mark_personalized()

    def set_accent(self, accent: str) -> None:
        """Set accent."""
        self._voice.accent = accent
        self._mark_personalized()

    # =========================================================================
    # Vocabulary API
    # =========================================================================

    def add_vocabulary(self, user_term: str, system_term: str, context: str = "") -> bool:
        """
        Add vocabulary mapping.

        Args:
            user_term: What user says
            system_term: What it means
            context: When to apply (optional)

        Returns:
            bool: True if added
        """
        # Check for existing entry
        for entry in self._vocabulary:
            if entry.user_term == user_term:
                # Update existing
                entry.system_term = system_term
                entry.context = context
                self._mark_personalized()
                return True

        if len(self._vocabulary) >= self.MAX_VOCABULARY_ENTRIES:
            return False

        self._vocabulary.append(
            VocabularyEntry(
                user_term=user_term,
                system_term=system_term,
                context=context,
            )
        )
        self._mark_personalized()
        return True

    def get_vocabulary(self, user_term: str) -> Optional[str]:
        """
        Get system term for user term.

        Args:
            user_term: User's term

        Returns:
            str: System term or None
        """
        for entry in self._vocabulary:
            if entry.user_term == user_term:
                return entry.system_term
        return None

    def remove_vocabulary(self, user_term: str) -> bool:
        """Remove vocabulary entry."""
        for i, entry in enumerate(self._vocabulary):
            if entry.user_term == user_term:
                self._vocabulary.pop(i)
                self._invalidate_cache()
                return True
        return False

    def list_vocabulary(self) -> List[VocabularyEntry]:
        """List all vocabulary entries."""
        return list(self._vocabulary)

    def vocabulary_count(self) -> int:
        """Get vocabulary count."""
        return len(self._vocabulary)

    def translate_text(self, text: str) -> str:
        """
        Translate user terms to system terms in text.

        Args:
            text: Text with potential user terms

        Returns:
            str: Text with translations applied
        """
        result = text
        for entry in self._vocabulary:
            if entry.user_term in result:
                result = result.replace(entry.user_term, entry.system_term)
        return result

    # =========================================================================
    # Response Preferences API
    # =========================================================================

    def get_response_prefs(self) -> ResponsePreferences:
        """Get response preferences."""
        return self._response_prefs

    def set_interaction_style(self, style: InteractionStyle) -> None:
        """Set interaction style."""
        self._interaction_style = style
        self._response_prefs.style = style
        self._mark_personalized()

    def get_interaction_style(self) -> InteractionStyle:
        """Get interaction style."""
        return self._interaction_style

    def set_max_response_length(self, length: int) -> None:
        """Set max response length (0 = no limit)."""
        self._response_prefs.max_response_length = max(0, length)
        self._mark_personalized()

    def set_use_bullet_points(self, use: bool) -> None:
        """Set whether to use bullet points."""
        self._response_prefs.use_bullet_points = use
        self._mark_personalized()

    def set_use_headers(self, use: bool) -> None:
        """Set whether to use headers."""
        self._response_prefs.use_headers = use
        self._mark_personalized()

    def set_include_examples(self, include: bool) -> None:
        """Set whether to include examples."""
        self._response_prefs.include_examples = include
        self._mark_personalized()

    def set_explain_reasoning(self, explain: bool) -> None:
        """Set whether to explain reasoning."""
        self._response_prefs.explain_reasoning = explain
        self._mark_personalized()

    # =========================================================================
    # Calibration API
    # =========================================================================

    def is_personalized(self) -> bool:
        """Check if persona has been customized."""
        return self._is_personalized

    def get_calibration_confidence(self) -> float:
        """Get calibration confidence (0.0-1.0)."""
        return self._calibration_confidence

    def set_calibration_confidence(self, confidence: float) -> None:
        """Set calibration confidence."""
        self._calibration_confidence = max(0.0, min(1.0, confidence))
        self._invalidate_cache()

    def get_last_calibrated_turn(self) -> int:
        """Get last calibrated turn number."""
        return self._last_calibrated_turn

    def mark_calibrated(self, turn_number: int, confidence: float = 0.8) -> None:
        """
        Mark persona as calibrated at turn.

        Args:
            turn_number: Current turn number
            confidence: Calibration confidence
        """
        self._last_calibrated_turn = turn_number
        self._calibration_confidence = max(0.0, min(1.0, confidence))
        self._is_personalized = True
        self._invalidate_cache()

    def _mark_personalized(self) -> None:
        """Mark section as personalized."""
        if self._frozen:
            raise RuntimeError("PersonaSection is frozen; mutations are rejected after init.")
        self._is_personalized = True
        self._updated_at_ms = int(time.time() * 1000)
        self._invalidate_cache()

    # =========================================================================
    # Freeze API (Immutability after session init)
    # =========================================================================

    def freeze(self) -> None:
        """Freeze the persona. All mutations after this raise RuntimeError."""
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        """Whether persona is frozen (immutable)."""
        return self._frozen

    # =========================================================================
    # Preferences API (for Back LLM capability params)
    # =========================================================================

    def set_preference(self, key: str, value: Any) -> None:
        """Store a preference key-value pair.

        Args:
            key: Preference name (e.g. "payment_method", "dietary", "timezone").
            value: Preference value (any JSON-serializable type).

        Raises:
            RuntimeError: If persona is frozen.
        """
        if self._frozen:
            raise RuntimeError("PersonaSection is frozen; mutations are rejected after init.")
        self._preferences[key] = value
        self._updated_at_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Read a preference value.

        Args:
            key: Preference name.
            default: Default value if key not found.

        Returns:
            Stored value or default.
        """
        return self._preferences.get(key, default)

    def get_all_preferences(self) -> Dict[str, Any]:
        """Return a shallow copy of all preferences."""
        return dict(self._preferences)

    # =========================================================================
    # Query API
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get section statistics."""
        return {
            "vocabulary_count": len(self._vocabulary),
            "custom_traits_count": len(self._personality.traits),
            "max_vocabulary": self.MAX_VOCABULARY_ENTRIES,
            "max_traits": self.MAX_CUSTOM_TRAITS,
            "is_personalized": self._is_personalized,
            "calibration_confidence": self._calibration_confidence,
            "last_calibrated_turn": self._last_calibrated_turn,
            "interaction_style": self._interaction_style.name,
            "size_bytes": self.get_size_bytes(),
        }

    # =========================================================================
    # Integrity API
    # =========================================================================

    def compute_integrity(self) -> str:
        """
        Compute SHA256 hash of section content.

        Returns:
            str: Hex-encoded hash
        """
        hasher = hashlib.sha256()

        # Hash personality
        hasher.update(str(self._personality.warmth).encode("utf-8"))
        hasher.update(str(self._personality.formality).encode("utf-8"))
        hasher.update(str(self._personality.verbosity).encode("utf-8"))
        hasher.update(str(self._personality.humor).encode("utf-8"))
        hasher.update(str(self._personality.directness).encode("utf-8"))

        for trait in self._personality.traits:
            hasher.update(trait.name.encode("utf-8"))
            hasher.update(str(trait.value).encode("utf-8"))

        # Hash vocabulary
        for entry in self._vocabulary:
            hasher.update(entry.user_term.encode("utf-8"))
            hasher.update(entry.system_term.encode("utf-8"))

        # Hash style
        hasher.update(str(self._interaction_style.value).encode("utf-8"))

        return hasher.hexdigest()

    def set_integrity(self, hash_value: str) -> None:
        """Set integrity hash."""
        self._integrity_hash = hash_value

    def get_integrity(self) -> str:
        """Get stored integrity hash."""
        return self._integrity_hash

    def verify_integrity(self) -> bool:
        """
        Verify section integrity.

        Returns:
            bool: True if hash matches or no hash set
        """
        if not self._integrity_hash:
            return True
        return self.compute_integrity() == self._integrity_hash

    def update_integrity(self) -> str:
        """Compute and store integrity hash."""
        self._integrity_hash = self.compute_integrity()
        return self._integrity_hash

    # =========================================================================
    # FlatBuffer Serialization
    # =========================================================================

    def _invalidate_cache(self) -> None:
        """Invalidate FlatBuffer cache."""
        self._fb_cache = None

    def to_flatbuffer(self) -> bytes:
        """
        Serialize to FlatBuffer bytes.

        Returns:
            bytes: Serialized FlatBuffer
        """
        if self._fb_cache is not None:
            return self._fb_cache

        builder = flatbuffers.Builder(4096)

        # Build section name
        name_offset = builder.CreateString(self.SECTION_NAME)

        # Build personality traits
        trait_offsets = []
        for trait in reversed(self._personality.traits):
            trait_name = builder.CreateString(trait.name)
            PersonalityTraitStart(builder)
            PersonalityTraitAddName(builder, trait_name)
            PersonalityTraitAddValue(builder, trait.value)
            trait_offsets.append(PersonalityTraitEnd(builder))
        trait_offsets.reverse()

        PersonalityProfileStartTraitsVector(builder, len(trait_offsets))
        for off in reversed(trait_offsets):
            builder.PrependUOffsetTRelative(off)
        traits_vec = builder.EndVector()

        # Build profile type
        profile_type_off = None
        if self._personality.profile_type:
            profile_type_off = builder.CreateString(self._personality.profile_type)

        # Build personality profile
        PersonalityProfileStart(builder)
        PersonalityProfileAddTraits(builder, traits_vec)
        PersonalityProfileAddWarmth(builder, self._personality.warmth)
        PersonalityProfileAddFormality(builder, self._personality.formality)
        PersonalityProfileAddVerbosity(builder, self._personality.verbosity)
        PersonalityProfileAddHumor(builder, self._personality.humor)
        PersonalityProfileAddDirectness(builder, self._personality.directness)
        if profile_type_off:
            PersonalityProfileAddProfileType(builder, profile_type_off)
        personality_off = PersonalityProfileEnd(builder)

        # Build voice preferences
        voice_id_off = None
        if self._voice.voice_id:
            voice_id_off = builder.CreateString(self._voice.voice_id)
        language_off = builder.CreateString(self._voice.language)
        accent_off = None
        if self._voice.accent:
            accent_off = builder.CreateString(self._voice.accent)

        ProsodyControlsStart(builder)
        ProsodyControlsAddSpeakingRate(builder, self._voice.speaking_rate)
        ProsodyControlsAddPitch(builder, self._voice.pitch)
        ProsodyControlsAddVolume(builder, self._voice.volume)
        if voice_id_off:
            ProsodyControlsAddVoiceId(builder, voice_id_off)
        ProsodyControlsAddLanguage(builder, language_off)
        if accent_off:
            ProsodyControlsAddAccent(builder, accent_off)
        voice_off = ProsodyControlsEnd(builder)

        # Build vocabulary
        vocab_offsets = []
        for entry in reversed(self._vocabulary):
            user_term = builder.CreateString(entry.user_term)
            system_term = builder.CreateString(entry.system_term)
            context_off = None
            if entry.context:
                context_off = builder.CreateString(entry.context)

            VocabularyEntryStart(builder)
            VocabularyEntryAddUserTerm(builder, user_term)
            VocabularyEntryAddSystemTerm(builder, system_term)
            if context_off:
                VocabularyEntryAddContext(builder, context_off)
            vocab_offsets.append(VocabularyEntryEnd(builder))
        vocab_offsets.reverse()

        PersonaSectionStartVocabularyVector(builder, len(vocab_offsets))
        for off in reversed(vocab_offsets):
            builder.PrependUOffsetTRelative(off)
        vocab_vec = builder.EndVector()

        # Build response preferences
        ResponsePreferencesStart(builder)
        ResponsePreferencesAddStyle(builder, self._response_prefs.style.value)
        ResponsePreferencesAddMaxResponseLength(builder, self._response_prefs.max_response_length)
        ResponsePreferencesAddUseBulletPoints(builder, self._response_prefs.use_bullet_points)
        ResponsePreferencesAddUseHeaders(builder, self._response_prefs.use_headers)
        ResponsePreferencesAddIncludeExamples(builder, self._response_prefs.include_examples)
        ResponsePreferencesAddExplainReasoning(builder, self._response_prefs.explain_reasoning)
        prefs_off = ResponsePreferencesEnd(builder)

        # Build header
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._updated_at_ms)
        header_offset = SectionHeaderEnd(builder)

        # Build root
        PersonaSectionStart(builder)
        PersonaSectionAddHeader(builder, header_offset)
        PersonaSectionAddPersonality(builder, personality_off)
        PersonaSectionAddVoice(builder, voice_off)
        PersonaSectionAddVocabulary(builder, vocab_vec)
        PersonaSectionAddResponsePrefs(builder, prefs_off)
        PersonaSectionAddInteractionStyle(builder, self._interaction_style.value)
        PersonaSectionAddIsPersonalized(builder, self._is_personalized)
        PersonaSectionAddLastCalibratedTurn(builder, self._last_calibrated_turn)
        PersonaSectionAddCalibrationConfidence(builder, self._calibration_confidence)
        root = PersonaSectionEnd(builder)

        builder.Finish(root)
        self._fb_cache = bytes(builder.Output())
        return self._fb_cache

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize from FlatBuffer bytes (in-place mutation).

        Args:
            data: FlatBuffer bytes
        """
        fb = FBPersonaSection.GetRootAsPersonaSection(data, 0)

        # Restore metadata
        self._is_personalized = fb.IsPersonalized()
        self._last_calibrated_turn = fb.LastCalibratedTurn()
        self._calibration_confidence = fb.CalibrationConfidence()
        self._interaction_style = InteractionStyle(fb.InteractionStyle())

        # Restore personality
        personality = fb.Personality()
        if personality:
            self._personality.warmth = personality.Warmth()
            self._personality.formality = personality.Formality()
            self._personality.verbosity = personality.Verbosity()
            self._personality.humor = personality.Humor()
            self._personality.directness = personality.Directness()

            profile_type = personality.ProfileType()
            if profile_type:
                self._personality.profile_type = (
                    profile_type.decode("utf-8")
                    if isinstance(profile_type, bytes)
                    else str(profile_type)
                )

            self._personality.traits.clear()
            for i in range(personality.TraitsLength()):
                trait = personality.Traits(i)
                if trait:
                    name_raw = trait.Name()
                    name = (
                        name_raw.decode("utf-8")
                        if isinstance(name_raw, bytes)
                        else str(name_raw) if name_raw else ""
                    )
                    self._personality.traits.append(
                        PersonalityTrait(name=name, value=trait.Value())
                    )

        # Restore voice
        voice = fb.Voice()
        if voice:
            self._voice.speaking_rate = voice.SpeakingRate()
            self._voice.pitch = voice.Pitch()
            self._voice.volume = voice.Volume()

            voice_id = voice.VoiceId()
            if voice_id:
                self._voice.voice_id = (
                    voice_id.decode("utf-8") if isinstance(voice_id, bytes) else str(voice_id)
                )

            language = voice.Language()
            if language:
                self._voice.language = (
                    language.decode("utf-8") if isinstance(language, bytes) else str(language)
                )

            accent = voice.Accent()
            if accent:
                self._voice.accent = (
                    accent.decode("utf-8") if isinstance(accent, bytes) else str(accent)
                )

        # Restore vocabulary
        self._vocabulary.clear()
        for i in range(fb.VocabularyLength()):
            entry = fb.Vocabulary(i)
            if entry:
                user_term_raw = entry.UserTerm()
                user_term = (
                    user_term_raw.decode("utf-8")
                    if isinstance(user_term_raw, bytes)
                    else str(user_term_raw) if user_term_raw else ""
                )

                system_term_raw = entry.SystemTerm()
                system_term = (
                    system_term_raw.decode("utf-8")
                    if isinstance(system_term_raw, bytes)
                    else str(system_term_raw) if system_term_raw else ""
                )

                context_raw = entry.Context()
                context = ""
                if context_raw:
                    context = (
                        context_raw.decode("utf-8")
                        if isinstance(context_raw, bytes)
                        else str(context_raw)
                    )

                self._vocabulary.append(
                    VocabularyEntry(
                        user_term=user_term,
                        system_term=system_term,
                        context=context,
                    )
                )

        # Restore response preferences
        prefs = fb.ResponsePrefs()
        if prefs:
            self._response_prefs.style = InteractionStyle(prefs.Style())
            self._response_prefs.max_response_length = prefs.MaxResponseLength()
            self._response_prefs.use_bullet_points = prefs.UseBulletPoints()
            self._response_prefs.use_headers = prefs.UseHeaders()
            self._response_prefs.include_examples = prefs.IncludeExamples()
            self._response_prefs.explain_reasoning = prefs.ExplainReasoning()

        # Invalidate cache
        self._fb_cache = None

    # =========================================================================
    # Apply Operations (MutationGuard Pattern)
    # =========================================================================

    def apply(self, operation: str, data: Dict[str, Any]) -> Any:
        """
        Apply a mutation operation.

        Supported operations:
        - set_warmth, set_formality, set_verbosity, set_humor, set_directness
        - add_trait, remove_trait
        - set_voice_* (speaking_rate, pitch, volume, voice_id, language)
        - add_vocabulary, remove_vocabulary
        - set_interaction_style
        - set_response_* (max_length, bullet_points, headers, examples, reasoning)
        - mark_calibrated
        - clear

        Args:
            operation: Operation name
            data: Operation parameters

        Returns:
            Any: Operation result
        """
        self._invalidate_cache()

        if operation == "set_warmth":
            self.set_warmth(data["value"])
        elif operation == "set_formality":
            self.set_formality(data["value"])
        elif operation == "set_verbosity":
            self.set_verbosity(data["value"])
        elif operation == "set_humor":
            self.set_humor(data["value"])
        elif operation == "set_directness":
            self.set_directness(data["value"])
        elif operation == "set_profile_type":
            self.set_profile_type(data["profile_type"])
        elif operation == "add_trait":
            return self.add_trait(data["name"], data["value"])
        elif operation == "remove_trait":
            return self.remove_trait(data["name"])
        elif operation == "set_speaking_rate":
            self.set_speaking_rate(data["value"])
        elif operation == "set_pitch":
            self.set_pitch(data["value"])
        elif operation == "set_volume":
            self.set_volume(data["value"])
        elif operation == "set_voice_id":
            self.set_voice_id(data["voice_id"])
        elif operation == "set_language":
            self.set_language(data["language"])
        elif operation == "add_vocabulary":
            return self.add_vocabulary(
                data["user_term"],
                data["system_term"],
                data.get("context", ""),
            )
        elif operation == "remove_vocabulary":
            return self.remove_vocabulary(data["user_term"])
        elif operation == "set_interaction_style":
            style = data.get("style")
            if isinstance(style, int):
                self.set_interaction_style(InteractionStyle(style))
            elif isinstance(style, str):
                self.set_interaction_style(InteractionStyle[style])
            elif isinstance(style, InteractionStyle):
                self.set_interaction_style(style)
        elif operation == "set_max_response_length":
            self.set_max_response_length(data["value"])
        elif operation == "set_use_bullet_points":
            self.set_use_bullet_points(data["value"])
        elif operation == "set_use_headers":
            self.set_use_headers(data["value"])
        elif operation == "set_include_examples":
            self.set_include_examples(data["value"])
        elif operation == "set_explain_reasoning":
            self.set_explain_reasoning(data["value"])
        elif operation == "mark_calibrated":
            self.mark_calibrated(data["turn_number"], data.get("confidence", 0.8))
        elif operation == "evict_partial":
            return self.evict_partial(data["target_kb"])
        elif operation == "clear":
            self.clear()
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return None

    # =========================================================================
    # Utility
    # =========================================================================

    def __repr__(self) -> str:
        return (
            f"PersonaSection("
            f"style={self._interaction_style.name}, "
            f"personalized={self._is_personalized}, "
            f"vocab={len(self._vocabulary)}/{self.MAX_VOCABULARY_ENTRIES})"
        )

    def __len__(self) -> int:
        return len(self._vocabulary) + len(self._personality.traits)


# =============================================================================
# Factory Function
# =============================================================================


def create_persona_section() -> PersonaSection:
    """
    Factory function to create PersonaSection.

    Returns:
        PersonaSection: New section instance
    """
    return PersonaSection()


def initialize_persona(
    family_profile: Dict[str, Any],
    session_config: Optional[Dict[str, Any]] = None,
) -> PersonaSection:
    """Initialize persona from family profile. Called ONCE at session start.

    Args:
        family_profile: Dict with keys:
            family_name: str
            members: List[{name, relation, age, preferences}]
            default_payment: str
            dietary_restrictions: List[str]
            accessibility_needs: List[str] (optional)
            preferred_language: str (optional, default "en")
            timezone: str (optional, default "UTC")
        session_config: Optional dict with keys:
            tone: str (default "warm")
            formality: str (default "casual")
            verbosity: str (default "concise")

    Returns:
        PersonaSection populated with family context. Call .freeze() to make
        immutable after return.

    Writer: Session Init (one-time). Not an LLM writer.
    Readers: Front LLM (tone, personality), Back LLM (preferences for params),
             ExperienceLayer AffectiveMirror (mirroring style).
    """
    if session_config is None:
        session_config = {}

    persona = PersonaSection()

    # Core personality
    warmth_map = {"warm": 0.8, "neutral": 0.5, "formal": 0.3}
    formality_map = {"casual": 0.3, "neutral": 0.5, "formal": 0.8}
    verbosity_map = {"concise": 0.3, "balanced": 0.5, "detailed": 0.8}

    persona.set_warmth(warmth_map.get(session_config.get("tone", "warm"), 0.5))
    persona.set_formality(formality_map.get(session_config.get("formality", "casual"), 0.5))
    persona.set_verbosity(verbosity_map.get(session_config.get("verbosity", "concise"), 0.5))

    # Family members as vocabulary entries
    for member in family_profile.get("members", []):
        age = member.get("age", "unknown")
        relation = member.get("relation", "member")
        persona.add_vocabulary(
            user_term=member["name"],
            system_term=f"{relation} (age {age})",
            context="family_member",
        )

    # Preferences for Back LLM capability params
    persona.set_preference("payment_method", family_profile.get("default_payment", ""))
    persona.set_preference("dietary", family_profile.get("dietary_restrictions", []))
    persona.set_preference("accessibility", family_profile.get("accessibility_needs", []))
    persona.set_preference("language", family_profile.get("preferred_language", "en"))
    persona.set_preference("timezone", family_profile.get("timezone", "UTC"))
    persona.set_preference("family_name", family_profile.get("family_name", ""))

    return persona

    return persona
