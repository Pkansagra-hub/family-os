"""Tests for ExtractionValidator (E-MW-2.2).

30 tests in 7 classes covering:
  - Text length truncation (MW-04)
  - Required field validation
  - Participant resolution via PersonResolver
  - Confidence threshold filtering
  - temporal_links validation (MW-12)
  - Full atom construction with enum normalization
  - Integrated multi-extraction scenarios (MW-05)
"""

from __future__ import annotations

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.person_resolver import PersonResolver
from k1.memory_writer.extraction.extraction_validator import ExtractionValidator, _safe_enum
from k1.memory_writer.extraction.raw_extraction import RawExtraction
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ArcPosition,
    CompressedTurn,
    ElaborationDepth,
    ExtractionContext,
    IntentType,
    LocationType,
    MemoryAtom,
    Narrative,
    NoveltyLevel,
    SentimentLabel,
    SocialContext,
    SocialIntimacy,
    SourceType,
    TemporalLink,
    TemporalLinkType,
    TemporalOrientation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_config(**overrides) -> MWConfig:
    """Build MWConfig with optional overrides."""
    return MWConfig(**overrides)


def _default_context(**overrides) -> ExtractionContext:
    """Build ExtractionContext with sensible defaults."""
    defaults = dict(
        session_id="sess-001",
        conversation_turn=3,
        turn_timestamp_ms=1700000000000,
        active_persons={
            "Mom": {"person_id": "person_mom", "type": "PERSON", "confidence": 1.0},
            "Dad": {"person_id": "person_dad", "type": "PERSON", "confidence": 1.0},
        },
        persona_context={"aliases": {"Mom": ["Mother", "Mama"]}},
    )
    defaults.update(overrides)
    return ExtractionContext(**defaults)


def _make_extraction(**overrides) -> RawExtraction:
    """Build a valid RawExtraction with defaults that pass all checks."""
    defaults = dict(
        text="Had dinner with Mom at the Italian place",
        topics=["family", "food"],
        categories=["daily_life"],
        participants=["Mom"],
        sentiment_label="positive",
        confidence=0.8,
        session_id="sess-001",
        conversation_turn=3,
        extraction_sequence=0,
        trace_id="trace-abc",
    )
    defaults.update(overrides)
    return RawExtraction(**defaults)


def _make_validator(config: MWConfig | None = None) -> ExtractionValidator:
    """Build ExtractionValidator with PersonResolver and config."""
    return ExtractionValidator(
        person_resolver=PersonResolver(),
        config=config or _default_config(),
    )


# ===========================================================================
# TestTextLengthCheck — 4 tests
# ===========================================================================


class TestTextLengthCheck:
    """MW-04: Text truncated to config.max_text_words, never dropped for length."""

    def test_short_text_passes(self):
        """10 words → unchanged."""
        ext = _make_extraction(text="one two three four five six seven eight nine ten")
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert atoms[0].text == "one two three four five six seven eight nine ten"

    def test_50_words_passes(self):
        """Exactly 50 words → unchanged."""
        text = " ".join(f"word{i}" for i in range(50))
        ext = _make_extraction(text=text)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].text.split()) == 50

    def test_51_words_truncated(self):
        """51 words → truncated to 50."""
        text = " ".join(f"word{i}" for i in range(51))
        ext = _make_extraction(text=text)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].text.split()) == 50

    def test_100_words_truncated(self):
        """100 words → truncated to 50."""
        text = " ".join(f"word{i}" for i in range(100))
        ext = _make_extraction(text=text)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].text.split()) == 50
        # First 50 words preserved
        assert atoms[0].text.startswith("word0 word1 word2")


# ===========================================================================
# TestRequiredFieldsCheck — 4 tests
# ===========================================================================


class TestRequiredFieldsCheck:
    """Drop extractions with empty text or topics."""

    def test_empty_text_dropped(self):
        """text='' → dropped."""
        ext = _make_extraction(text="")
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert atoms == []

    def test_whitespace_text_dropped(self):
        """text='   ' → dropped."""
        ext = _make_extraction(text="   ")
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert atoms == []

    def test_empty_topics_dropped(self):
        """topics=[] → dropped."""
        ext = _make_extraction(topics=[])
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert atoms == []

    def test_valid_text_and_topics_passes(self):
        """text='fact', topics=['family'] → passes."""
        ext = _make_extraction(text="a real fact", topics=["family"])
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1


# ===========================================================================
# TestParticipantResolution — 5 tests
# ===========================================================================


class TestParticipantResolution:
    """PersonResolver resolves natural names → person_ids."""

    def test_natural_names_resolved_to_person_ids(self):
        """['Mom', 'Dad'] → ['person_mom', 'person_dad']."""
        ext = _make_extraction(participants=["Mom", "Dad"])
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert "person_mom" in atoms[0].participants
        assert "person_dad" in atoms[0].participants

    def test_unknown_name_gets_provisional_id(self):
        """['Zara'] → ['person_zara'] (provisional)."""
        ext = _make_extraction(participants=["Zara"])
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert "person_zara" in atoms[0].participants

    def test_empty_participants_stays_empty(self):
        """[] → []."""
        ext = _make_extraction(participants=[])
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert atoms[0].participants == []

    def test_dedup_after_resolution(self):
        """['Mom', 'Mother'] both resolve to person_mom → deduped."""
        ext = _make_extraction(participants=["Mom", "Mother"])
        ctx = _default_context()
        v = _make_validator()
        atoms = v.validate([ext], ctx)
        assert len(atoms) == 1
        # PersonResolver.resolve_all deduplicates by person_id
        assert atoms[0].participants.count("person_mom") == 1

    def test_person_resolver_receives_context(self):
        """PersonResolver.resolve_all() called with correct ExtractionContext."""
        ext = _make_extraction(participants=["Mom"])
        ctx = _default_context()
        v = _make_validator()
        atoms = v.validate([ext], ctx)
        assert len(atoms) == 1
        # Correct resolution proves context was passed
        assert "person_mom" in atoms[0].participants


# ===========================================================================
# TestConfidenceThreshold — 4 tests
# ===========================================================================


class TestConfidenceThreshold:
    """Drop extractions below config.confidence_floor (default 0.30)."""

    def test_above_floor_passes(self):
        """confidence=0.5 > 0.3 → passes."""
        ext = _make_extraction(confidence=0.5)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1

    def test_at_floor_passes(self):
        """confidence=0.3 → passes (not strictly below)."""
        ext = _make_extraction(confidence=0.3)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1

    def test_below_floor_dropped(self):
        """confidence=0.2 < 0.3 → dropped."""
        ext = _make_extraction(confidence=0.2)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert atoms == []

    def test_zero_confidence_dropped(self):
        """confidence=0.0 → dropped."""
        ext = _make_extraction(confidence=0.0)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert atoms == []


# ===========================================================================
# TestTemporalLinksValidation — 5 tests
# ===========================================================================


class TestTemporalLinksValidation:
    """MW-12: temporal_links capped at 5, invalid types dropped."""

    def test_valid_links_preserved(self):
        """3 valid links → 3 TemporalLink objects."""
        links = [
            {"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE", "confidence": 0.9},
            {"mentioned_time": "next Friday", "link_type": "PROSPECTIVE", "confidence": 0.8},
            {"mentioned_time": "right now", "link_type": "CONCURRENT", "confidence": 1.0},
        ]
        ext = _make_extraction(temporal_links=links)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].temporal_links) == 3
        assert all(isinstance(tl, TemporalLink) for tl in atoms[0].temporal_links)

    def test_caps_at_5_links(self):
        """7 links → only first 5 (MW-12)."""
        links = [
            {"mentioned_time": f"time{i}", "link_type": "CONCURRENT", "confidence": 1.0}
            for i in range(7)
        ]
        ext = _make_extraction(temporal_links=links)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].temporal_links) == 5

    def test_invalid_link_type_dropped(self):
        """link_type='INVALID' → dropped."""
        links = [
            {"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE", "confidence": 0.9},
            {"mentioned_time": "sometime", "link_type": "INVALID", "confidence": 0.5},
            {"mentioned_time": "tomorrow", "link_type": "PROSPECTIVE", "confidence": 0.8},
        ]
        ext = _make_extraction(temporal_links=links)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].temporal_links) == 2  # INVALID dropped
        types = [tl.link_type for tl in atoms[0].temporal_links]
        assert "INVALID" not in types

    def test_missing_mentioned_time_kept_with_default(self):
        """mentioned_time='' → kept (empty is valid per _validate_temporal_links)."""
        links = [
            {"link_type": "CONCURRENT", "confidence": 1.0},
        ]
        ext = _make_extraction(temporal_links=links)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert len(atoms[0].temporal_links) == 1
        assert atoms[0].temporal_links[0].mentioned_time == ""

    def test_links_converted_to_frozen_tuple(self):
        """Returns tuple[TemporalLink, ...] (immutable)."""
        links = [
            {"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE", "confidence": 0.9},
        ]
        ext = _make_extraction(temporal_links=links)
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert isinstance(atoms[0].temporal_links, tuple)


# ===========================================================================
# TestAtomConstruction — 4 tests
# ===========================================================================


class TestAtomConstruction:
    """Full atom construction with enum normalization."""

    def test_all_fields_populated(self):
        """Full RawExtraction → MemoryAtom with all relevant fields."""
        ext = _make_extraction(
            text="Mom made pasta for dinner",
            topics=["family", "food"],
            categories=["daily_life"],
            activity_type="MEAL",
            participants=["Mom"],
            social_context="nuclear_family",
            social_intimacy="HIGH",
            location_name="Home",
            location_type="home",
            sentiment_label="positive",
            emotion_tags=["happy", "content"],
            affect={"valence": 0.7, "arousal": 0.3, "dominance": 0.6},
            temporal_links=[
                {"mentioned_time": "tonight", "link_type": "CONCURRENT", "confidence": 1.0}
            ],
            temporal_orientation="ONGOING",
            source_type="user_stated",
            novelty="EXPECTED",
            elaboration_depth="DISCUSSED",
            intent_type="log_memory",
            identity_domains=["parent"],
            confidence=0.9,
            narrative={
                "thread_id": "thread-1",
                "arc_position": "EXPOSITION",
                "is_goal_event": False,
            },
            correction_signal=False,
            contradiction_signal=False,
            session_id="sess-001",
            conversation_turn=3,
            extraction_sequence=0,
            trace_id="trace-full",
        )
        v = _make_validator()
        ctx = _default_context()
        atoms = v.validate([ext], ctx)
        assert len(atoms) == 1
        a = atoms[0]
        assert isinstance(a, MemoryAtom)
        assert a.text == "Mom made pasta for dinner"
        assert a.topics == ["family", "food"]
        assert a.activity_type == ActivityType.MEAL
        assert "person_mom" in a.participants
        assert a.social_context == SocialContext.NUCLEAR_FAMILY
        assert a.social_intimacy == SocialIntimacy.HIGH
        assert a.location_name == "Home"
        assert a.location_type == LocationType.HOME
        assert a.sentiment_label == SentimentLabel.POSITIVE
        assert a.emotion_tags == ["happy", "content"]
        assert a.affect.valence == 0.7
        assert a.affect.arousal == 0.3
        assert a.affect.dominance == 0.6
        assert len(a.temporal_links) == 1
        assert a.temporal_orientation == TemporalOrientation.ONGOING
        assert a.source_type == SourceType.USER_STATED
        assert a.novelty == NoveltyLevel.EXPECTED
        assert a.elaboration_depth == ElaborationDepth.DISCUSSED
        assert a.intent_type == IntentType.LOG_MEMORY
        assert a.identity_domains == ["parent"]
        assert a.confidence == 0.9
        assert a.narrative is not None
        assert a.narrative.thread_id == "thread-1"
        assert a.narrative.arc_position == ArcPosition.EXPOSITION
        assert a.session_id == "sess-001"
        assert a.conversation_turn == 3
        assert a.conversation_anchor_ms == ctx.turn_timestamp_ms
        assert a.language == "en"

    def test_invalid_enum_values_use_defaults(self):
        """sentiment_label='INVALID' → SentimentLabel.NEUTRAL."""
        ext = _make_extraction(
            sentiment_label="INVALID",
            source_type="BOGUS",
            novelty="NOPE",
            elaboration_depth="WRONG",
            temporal_orientation="NADA",
        )
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        a = atoms[0]
        assert a.sentiment_label == SentimentLabel.NEUTRAL
        assert a.source_type == SourceType.USER_STATED
        assert a.novelty == NoveltyLevel.EXPECTED
        assert a.elaboration_depth == ElaborationDepth.MENTION
        assert a.temporal_orientation == TemporalOrientation.PAST

    def test_affect_from_dict(self):
        """{'valence': 0.7, 'arousal': 0.3} → Affect(0.7, 0.3, 0.5)."""
        ext = _make_extraction(affect={"valence": 0.7, "arousal": 0.3})
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        assert atoms[0].affect == Affect(0.7, 0.3, 0.5)

    def test_correction_signals_passed_through(self):
        """correction_signal=True → MemoryAtom.correction_signal=True."""
        ext = _make_extraction(
            correction_signal=True,
            contradiction_signal=True,
            supersedes_concept="cuisine_preference:italian",
            correction_source="user_explicit",
        )
        v = _make_validator()
        atoms = v.validate([ext], _default_context())
        assert len(atoms) == 1
        a = atoms[0]
        assert a.correction_signal is True
        assert a.contradiction_signal is True
        assert a.supersedes_concept == "cuisine_preference:italian"
        assert a.correction_source == "user_explicit"


# ===========================================================================
# TestValidatorIntegrated — 4 tests
# ===========================================================================


class TestValidatorIntegrated:
    """End-to-end validation with mixed valid/invalid extractions."""

    def test_mixed_valid_invalid_extractions(self):
        """5 extractions, 2 invalid → 3 MemoryAtom."""
        exts = [
            _make_extraction(text="Valid fact one", confidence=0.8, extraction_sequence=0),
            _make_extraction(text="", confidence=0.9, extraction_sequence=1),  # empty text → drop
            _make_extraction(text="Valid fact two", confidence=0.7, extraction_sequence=2),
            _make_extraction(
                text="Low confidence", confidence=0.1, extraction_sequence=3
            ),  # below floor → drop
            _make_extraction(text="Valid fact three", confidence=0.6, extraction_sequence=4),
        ]
        v = _make_validator()
        atoms = v.validate(exts, _default_context())
        assert len(atoms) == 3
        assert atoms[0].text == "Valid fact one"
        assert atoms[1].text == "Valid fact two"
        assert atoms[2].text == "Valid fact three"

    def test_mw05_cap_at_6_atoms(self):
        """8 valid extractions → 6 MemoryAtom (MW-05)."""
        exts = [
            _make_extraction(
                text=f"Valid extraction number {i}",
                confidence=0.9,
                extraction_sequence=i,
            )
            for i in range(8)
        ]
        v = _make_validator()
        atoms = v.validate(exts, _default_context())
        assert len(atoms) == 6

    def test_empty_input_returns_empty(self):
        """[] → []."""
        v = _make_validator()
        atoms = v.validate([], _default_context())
        assert atoms == []

    def test_all_dropped_returns_empty(self):
        """3 extractions all below confidence → []."""
        exts = [_make_extraction(confidence=0.1, extraction_sequence=i) for i in range(3)]
        v = _make_validator()
        atoms = v.validate(exts, _default_context())
        assert atoms == []
