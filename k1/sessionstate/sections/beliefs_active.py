"""
BeliefsActiveSection - Active Beliefs Store (HOT CORE)
=======================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.2 (beliefs_active)

This section contains current session beliefs - active facts about user and
context. Uses Subject-Verb-Object (SVO) structure with confidence scores.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/beliefs_active_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- turn_id: string (required)
- current_turn_facts: [Fact] - Max ~50 facts
- mentioned_entities: [EntityRef]
- mentioned_time: MentionedTime
- mentioned_location: MentionedLocation
- pinned_fact_ids: [string]
- fact_count: uint16
- entity_count: uint16
- last_updated_ms: int64

Lifecycle: After turn completion, facts demote to beliefs_history
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types - import class types from package
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    BeliefsActiveSection as FBBeliefsActiveSection,
)

# Import builder functions from individual files
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.BeliefsActiveSection import (
    BeliefsActiveSectionAddCurrentTurnFacts,
    BeliefsActiveSectionAddEntityCount,
    BeliefsActiveSectionAddFactCount,
    BeliefsActiveSectionAddHeader,
    BeliefsActiveSectionAddLastUpdatedMs,
    BeliefsActiveSectionAddMentionedEntities,
    BeliefsActiveSectionAddMentionedLocation,
    BeliefsActiveSectionAddMentionedTime,
    BeliefsActiveSectionAddPinnedFactIds,
    BeliefsActiveSectionAddTurnId,
    BeliefsActiveSectionEnd,
    BeliefsActiveSectionStart,
    BeliefsActiveSectionStartCurrentTurnFactsVector,
    BeliefsActiveSectionStartMentionedEntitiesVector,
    BeliefsActiveSectionStartPinnedFactIdsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.EntityRef import (
    EntityRefAddConfidence,
    EntityRefAddDisplayName,
    EntityRefAddId,
    EntityRefAddType,
    EntityRefEnd,
    EntityRefStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.Fact import (
    FactAddConfidence,
    FactAddId,
    FactAddObject,
    FactAddPredicate,
    FactAddPrivacyBand,
    FactAddSource,
    FactAddSubject,
    FactAddTimestampMs,
    FactEnd,
    FactStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.MentionedLocation import (
    MentionedLocationAddConfidence,
    MentionedLocationAddEntityId,
    MentionedLocationAddLocationType,
    MentionedLocationAddRawText,
    MentionedLocationEnd,
    MentionedLocationStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.MentionedTime import (
    MentionedTimeAddConfidence,
    MentionedTimeAddIsRelative,
    MentionedTimeAddRawText,
    MentionedTimeAddResolvedMs,
    MentionedTimeEnd,
    MentionedTimeStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)

# =============================================================================
# Enums matching FlatBuffer schema (common.fbs)
# =============================================================================


class PrivacyBand(IntEnum):
    """Privacy classification bands per ADR-0042."""

    GREEN = 0  # Public, non-sensitive
    AMBER = 1  # Internal, sensitive
    RED = 2  # Confidential, PII
    BLACK = 3  # Restricted, regulated


# =============================================================================
# Data Classes matching FlatBuffer schema
# =============================================================================


@dataclass
class Fact:
    """
    Single belief/fact in SVO format.

    Maps to Fact table in common.fbs:
    - id: string (required)
    - subject: string (required)
    - predicate: string (required)
    - object: string (required)
    - confidence: float = 1.0
    - source: string
    - timestamp_ms: int64
    - privacy_band: PrivacyBand = GREEN
    """

    id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source: str = ""
    timestamp_ms: int = 0
    privacy_band: PrivacyBand = PrivacyBand.GREEN

    # Runtime-only fields (not serialized)
    is_pinned: bool = False
    last_accessed_ms: int = 0
    access_count: int = 0


@dataclass
class EntityRef:
    """
    Entity reference from NER (UltraBERT).

    Maps to EntityRef table in common.fbs:
    - id: string (required)
    - type: string (required)
    - display_name: string
    - confidence: float = 1.0
    """

    id: str
    type: str
    display_name: str = ""
    confidence: float = 1.0


@dataclass
class MentionedTime:
    """
    Time reference mentioned in current turn.

    Maps to MentionedTime table in beliefs_active_section.fbs:
    - raw_text: string ("tomorrow", "next week", "3pm")
    - resolved_ms: int64 (Resolved Unix timestamp)
    - confidence: float = 1.0
    - is_relative: bool = true
    """

    raw_text: str
    resolved_ms: int = 0
    confidence: float = 1.0
    is_relative: bool = True


@dataclass
class MentionedLocation:
    """
    Location reference mentioned in current turn.

    Maps to MentionedLocation table in beliefs_active_section.fbs:
    - raw_text: string ("the kitchen", "mom's house")
    - location_type: string ("room", "address", "zone")
    - entity_id: string (Link to entity if resolved)
    - confidence: float = 1.0
    """

    raw_text: str
    location_type: str = ""
    entity_id: str = ""
    confidence: float = 1.0


# =============================================================================
# BeliefsActiveSection Implementation
# =============================================================================


class BeliefsActiveSection:
    """
    Beliefs Active Section - facts needed for the current turn.

    This section contains beliefs/facts extracted during the current turn.
    After turn completion, facts are demoted to beliefs_history.

    Budget: 8KB (8192 bytes)
    Tier: HOT CORE
    Eviction: Section stays, items demote to beliefs_history

    FlatBuffer Schema: beliefs_active_section.fbs
    Serialization Target: <100 microseconds

    Contents per schema:
    - current_turn_facts: [Fact] - Max ~50 facts for 8KB budget
    - mentioned_entities: [EntityRef] - From NER
    - mentioned_time: MentionedTime - Temporal context
    - mentioned_location: MentionedLocation - Spatial context
    - pinned_fact_ids: [string] - Facts protected from demotion

    Example:
        section = BeliefsActiveSection(session_id="sess-123")

        # Add fact in SVO format
        fact = section.add_fact(
            subject="user",
            predicate="prefers",
            obj="dark mode",
            confidence=0.9,
        )

        # Add entity from NER
        section.add_entity("entity-1", "person", "John Smith")

        # Set temporal context
        section.set_mentioned_time("tomorrow at 3pm", 1700000000000)

        # Serialize for persistence
        data = section.to_flatbuffer()
    """

    BUDGET_BYTES = 8192  # 8KB
    TIER = "hot"
    CAN_EVICT = False  # Section stays, items demote
    SECTION_NAME = "beliefs_active"
    SCHEMA_VERSION = "1.0.0"
    MAX_FACTS = 50  # Per schema budget notes

    def __init__(
        self,
        session_id: str = "",
        turn_id: str = "",
        schema_version: str = "",
    ) -> None:
        """
        Initialize BeliefsActiveSection.

        Args:
            session_id: Session UUID (generated if empty)
            turn_id: Turn UUID (generated if empty)
            schema_version: Schema version (uses default if empty)
        """
        now_ms = int(time.time() * 1000)

        self._session_id = session_id or str(uuid.uuid4())
        self._turn_id = turn_id or str(uuid.uuid4())
        self._schema_version = schema_version or self.SCHEMA_VERSION
        self._last_updated_ms = now_ms

        # Core state per schema
        self._facts: Dict[str, Fact] = {}
        self._entities: Dict[str, EntityRef] = {}
        self._mentioned_time: Optional[MentionedTime] = None
        self._mentioned_location: Optional[MentionedLocation] = None
        self._pinned_fact_ids: set[str] = set()

        # Indexes for fast lookup (not in schema, runtime optimization)
        self._by_subject: Dict[str, List[str]] = {}
        self._by_predicate: Dict[str, List[str]] = {}
        self._by_object: Dict[str, List[str]] = {}

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
    def turn_id(self) -> str:
        """Current turn identifier (required per schema)."""
        return self._turn_id  # type: ignore

    @property
    def last_updated_ms(self) -> int:
        """Last update timestamp in milliseconds."""
        return self._last_updated_ms

    @property
    def schema_version(self) -> str:
        """Schema version string."""
        return self._schema_version

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
        """Whether section can be evicted. Items can demote, section stays."""
        return self.CAN_EVICT

    def get_size_bytes(self) -> int:
        """
        Get current serialized size in bytes.

        Uses cached value if available, otherwise computes estimate.
        Size budget breakdown per schema:
        - Header: ~100 bytes
        - turn_id: ~50 bytes
        - Fact: ~150 bytes each x 50 facts = 7.5KB max
        - EntityRef: ~80 bytes each x 10 entities = 800 bytes
        - MentionedTime: ~100 bytes
        - MentionedLocation: ~100 bytes
        - Pinned IDs + stats: ~200 bytes
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 100  # Header overhead
        size += 50  # turn_id
        size += len(self._facts) * 150  # ~150 bytes per fact
        size += len(self._entities) * 80  # ~80 bytes per entity
        size += 100 if self._mentioned_time else 0
        size += 100 if self._mentioned_location else 0
        size += len(self._pinned_fact_ids) * 40  # ~40 bytes per pinned ID
        size += 16  # fact_count + entity_count + last_updated_ms

        return min(size, self.BUDGET_BYTES)

    def clear(self) -> None:
        """Clear all section data."""
        self._facts.clear()
        self._entities.clear()
        self._mentioned_time = None
        self._mentioned_location = None
        self._pinned_fact_ids.clear()
        self._by_subject.clear()
        self._by_predicate.clear()
        self._by_object.clear()
        self._invalidate_cache()
        self._touch()

    def get_metadata(self) -> Dict[str, Any]:
        """Get section metadata for telemetry/debugging."""
        return {
            "name": self.name,
            "tier": self.tier,
            "budget_bytes": self.budget_bytes,
            "current_size_bytes": self.get_size_bytes(),
            "utilization_pct": round(self.get_size_bytes() / self.budget_bytes * 100, 1),
            "session_id": self._session_id,
            "turn_id": self._turn_id,
            "schema_version": self._schema_version,
            "fact_count": len(self._facts),
            "entity_count": len(self._entities),
            "pinned_fact_count": len(self._pinned_fact_ids),
            "has_time_context": self._mentioned_time is not None,
            "has_location_context": self._mentioned_location is not None,
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Fact Management (current_turn_facts per schema)
    # =========================================================================

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source: str = "",
        privacy_band: PrivacyBand = PrivacyBand.GREEN,
        fact_id: str = "",
    ) -> Fact:
        """
        Add a new fact in SVO format.

        Args:
            subject: Subject of the fact (e.g., "user")
            predicate: Predicate/verb (e.g., "prefers")
            obj: Object of the fact (e.g., "dark mode")
            confidence: Confidence score 0-1
            source: Source agent/process
            privacy_band: Privacy classification
            fact_id: Optional custom ID (generated if empty)

        Returns:
            Created Fact object
        """
        now_ms = int(time.time() * 1000)
        fid = fact_id or str(uuid.uuid4())

        fact = Fact(
            id=fid,
            subject=subject,
            predicate=predicate,
            object=obj,
            confidence=confidence,
            source=source,
            timestamp_ms=now_ms,
            privacy_band=privacy_band,
            last_accessed_ms=now_ms,
        )

        self._facts[fid] = fact

        # Update indexes
        self._by_subject.setdefault(subject, []).append(fid)
        self._by_predicate.setdefault(predicate, []).append(fid)
        self._by_object.setdefault(obj, []).append(fid)

        self._invalidate_cache()
        self._touch()
        return fact

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        """Get fact by ID, updating access tracking."""
        fact = self._facts.get(fact_id)
        if fact:
            now_ms = int(time.time() * 1000)
            fact.last_accessed_ms = now_ms
            fact.access_count += 1
        return fact

    def list_facts(self) -> List[Fact]:
        """List all current turn facts."""
        return list(self._facts.values())

    def get_fact_count(self) -> int:
        """Get fact_count per schema."""
        return len(self._facts)

    def remove_fact(self, fact_id: str) -> bool:
        """Remove a fact by ID."""
        if fact_id not in self._facts:
            return False

        fact = self._facts.pop(fact_id)

        # Update indexes
        if fact.subject in self._by_subject:
            self._by_subject[fact.subject] = [
                fid for fid in self._by_subject[fact.subject] if fid != fact_id
            ]
        if fact.predicate in self._by_predicate:
            self._by_predicate[fact.predicate] = [
                fid for fid in self._by_predicate[fact.predicate] if fid != fact_id
            ]
        if fact.object in self._by_object:
            self._by_object[fact.object] = [
                fid for fid in self._by_object[fact.object] if fid != fact_id
            ]

        self._pinned_fact_ids.discard(fact_id)
        self._invalidate_cache()
        self._touch()
        return True

    def find_by_subject(self, subject: str) -> List[Fact]:
        """Find facts by subject."""
        fact_ids = self._by_subject.get(subject, [])
        return [self._facts[fid] for fid in fact_ids if fid in self._facts]

    def find_by_predicate(self, predicate: str) -> List[Fact]:
        """Find facts by predicate."""
        fact_ids = self._by_predicate.get(predicate, [])
        return [self._facts[fid] for fid in fact_ids if fid in self._facts]

    def find_by_object(self, obj: str) -> List[Fact]:
        """Find facts by object."""
        fact_ids = self._by_object.get(obj, [])
        return [self._facts[fid] for fid in fact_ids if fid in self._facts]

    def update_confidence(self, fact_id: str, confidence: float) -> bool:
        """Update fact confidence."""
        if fact_id not in self._facts:
            return False
        self._facts[fact_id].confidence = confidence
        self._invalidate_cache()
        self._touch()
        return True

    # =========================================================================
    # Pinning (pinned_fact_ids per schema)
    # =========================================================================

    def pin_fact(self, fact_id: str) -> bool:
        """Pin a fact to prevent demotion to beliefs_history."""
        if fact_id not in self._facts:
            return False
        self._facts[fact_id].is_pinned = True
        self._pinned_fact_ids.add(fact_id)
        self._invalidate_cache()
        return True

    def unpin_fact(self, fact_id: str) -> bool:
        """Unpin a fact."""
        if fact_id not in self._facts:
            return False
        self._facts[fact_id].is_pinned = False
        self._pinned_fact_ids.discard(fact_id)
        self._invalidate_cache()
        return True

    def get_pinned_fact_ids(self) -> List[str]:
        """Get list of pinned fact IDs per schema."""
        return list(self._pinned_fact_ids)

    def get_demotable_facts(self, max_count: int = 10) -> List[Fact]:
        """
        Get facts eligible for demotion to beliefs_history.

        Returns unpinned facts in LRU order (oldest access first).
        """
        demotable = [f for f in self._facts.values() if not f.is_pinned]
        demotable.sort(key=lambda f: f.last_accessed_ms)
        return demotable[:max_count]

    def demote_facts(self, count: int) -> List[Fact]:
        """
        Demote oldest non-pinned facts (for migration to beliefs_history).

        Returns demoted facts for archival.
        """
        demotable = self.get_demotable_facts(count)
        for fact in demotable:
            self.remove_fact(fact.id)
        return demotable

    def get_demotion_candidates(
        self,
        current_turn: int = 0,
        confidence_threshold: float = 0.5,
        age_turns: int = 20,
        turn_duration_ms: int = 30_000,
    ) -> List[Fact]:
        """Return facts eligible for demotion to beliefs_history.

        Criteria: confidence < threshold AND estimated turn age > age_turns
        AND not pinned.

        Args:
            current_turn: Current conversation turn number.
            confidence_threshold: Facts below this confidence are candidates.
            age_turns: Minimum turn age for demotion eligibility.
            turn_duration_ms: Estimated ms per turn (for age approximation
                when turn numbers are unavailable; default 30s).

        Returns:
            List of Fact objects eligible for demotion, sorted by confidence
            ascending (lowest confidence first).
        """
        now_ms = int(time.time() * 1000)
        age_cutoff_ms = now_ms - (age_turns * turn_duration_ms)

        candidates: List[Fact] = []
        for fact in self._facts.values():
            if fact.is_pinned:
                continue
            if fact.confidence >= confidence_threshold:
                continue
            if fact.timestamp_ms > age_cutoff_ms:
                continue
            candidates.append(fact)

        candidates.sort(key=lambda f: f.confidence)
        return candidates

    # =========================================================================
    # Entity Management (mentioned_entities per schema)
    # =========================================================================

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        display_name: str = "",
        confidence: float = 1.0,
    ) -> EntityRef:
        """
        Add an entity reference from NER.

        Args:
            entity_id: Unique entity ID
            entity_type: Entity type ("person", "place", "device", etc.)
            display_name: Human-readable name
            confidence: NER confidence score

        Returns:
            Created EntityRef object
        """
        entity = EntityRef(
            id=entity_id,
            type=entity_type,
            display_name=display_name,
            confidence=confidence,
        )

        self._entities[entity_id] = entity
        self._invalidate_cache()
        self._touch()
        return entity

    def get_entity(self, entity_id: str) -> Optional[EntityRef]:
        """Get entity by ID."""
        return self._entities.get(entity_id)

    def list_entities(self) -> List[EntityRef]:
        """List all mentioned entities."""
        return list(self._entities.values())

    def get_entity_count(self) -> int:
        """Get entity_count per schema."""
        return len(self._entities)

    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity."""
        if entity_id not in self._entities:
            return False
        del self._entities[entity_id]
        self._invalidate_cache()
        self._touch()
        return True

    # =========================================================================
    # Temporal Context (mentioned_time per schema)
    # =========================================================================

    def set_mentioned_time(
        self,
        raw_text: str,
        resolved_ms: int = 0,
        confidence: float = 1.0,
        is_relative: bool = True,
    ) -> None:
        """
        Set temporal context mentioned in current turn.

        Args:
            raw_text: Original text ("tomorrow", "next week", "3pm")
            resolved_ms: Resolved Unix timestamp in milliseconds
            confidence: Resolution confidence
            is_relative: Whether time is relative vs absolute
        """
        self._mentioned_time = MentionedTime(
            raw_text=raw_text,
            resolved_ms=resolved_ms,
            confidence=confidence,
            is_relative=is_relative,
        )
        self._invalidate_cache()
        self._touch()

    def get_mentioned_time(self) -> Optional[MentionedTime]:
        """Get temporal context."""
        return self._mentioned_time

    def clear_mentioned_time(self) -> None:
        """Clear temporal context."""
        self._mentioned_time = None
        self._invalidate_cache()
        self._touch()

    # =========================================================================
    # Spatial Context (mentioned_location per schema)
    # =========================================================================

    def set_mentioned_location(
        self,
        raw_text: str,
        location_type: str = "",
        entity_id: str = "",
        confidence: float = 1.0,
    ) -> None:
        """
        Set spatial context mentioned in current turn.

        Args:
            raw_text: Original text ("the kitchen", "mom's house")
            location_type: Type ("room", "address", "zone")
            entity_id: Link to entity if resolved
            confidence: Resolution confidence
        """
        self._mentioned_location = MentionedLocation(
            raw_text=raw_text,
            location_type=location_type,
            entity_id=entity_id,
            confidence=confidence,
        )
        self._invalidate_cache()
        self._touch()

    def get_mentioned_location(self) -> Optional[MentionedLocation]:
        """Get spatial context."""
        return self._mentioned_location

    def clear_mentioned_location(self) -> None:
        """Clear spatial context."""
        self._mentioned_location = None
        self._invalidate_cache()
        self._touch()

    # =========================================================================
    # Turn Lifecycle
    # =========================================================================

    def start_new_turn(self, new_turn_id: str = "", clear_facts: bool = True) -> str:
        """
        Start a new turn (called after turn completion).

        Per schema lifecycle: After turn completion, facts should be
        demoted to beliefs_history. This method clears current turn state.

        Args:
            new_turn_id: New turn ID (generated if empty)
            clear_facts: Whether to clear facts (default True per lifecycle)

        Returns:
            New turn ID
        """
        self._turn_id = new_turn_id or str(uuid.uuid4())

        if clear_facts:
            self._facts.clear()
            self._pinned_fact_ids.clear()
            self._by_subject.clear()
            self._by_predicate.clear()
            self._by_object.clear()

        # Keep entities across turns (they represent resolved references)
        # Clear temporal/spatial context for new turn
        self._mentioned_time = None
        self._mentioned_location = None

        self._invalidate_cache()
        self._touch()
        return self._turn_id

    # =========================================================================
    # FlatBuffer Serialization
    # =========================================================================

    def to_flatbuffer(self) -> bytes:
        """
        Serialize section to FlatBuffer bytes.

        Returns:
            bytes: FlatBuffer-encoded data per beliefs_active_section.fbs

        Performance Target: <100 microseconds
        """
        if self._cache_valid and self._cached_bytes:
            return self._cached_bytes

        builder = flatbuffers.Builder(self.BUDGET_BYTES)

        # Build nested objects first (FlatBuffers requirement)

        # 1. Build turn_id string (required per schema)
        turn_id_offset = builder.CreateString(self._turn_id)

        # 2. Build section name for header
        section_name_offset = builder.CreateString(self.SECTION_NAME)

        # 3. Build facts vector (current_turn_facts per schema)
        fact_offsets = []
        for fact in self._facts.values():
            id_off = builder.CreateString(fact.id)
            subj_off = builder.CreateString(fact.subject)
            pred_off = builder.CreateString(fact.predicate)
            obj_off = builder.CreateString(fact.object)
            source_off = builder.CreateString(fact.source)

            FactStart(builder)
            FactAddId(builder, id_off)
            FactAddSubject(builder, subj_off)
            FactAddPredicate(builder, pred_off)
            FactAddObject(builder, obj_off)
            FactAddConfidence(builder, fact.confidence)
            FactAddSource(builder, source_off)
            FactAddTimestampMs(builder, fact.timestamp_ms)
            FactAddPrivacyBand(builder, int(fact.privacy_band))
            fact_offsets.append(FactEnd(builder))

        if fact_offsets:
            BeliefsActiveSectionStartCurrentTurnFactsVector(builder, len(fact_offsets))
            for offset in reversed(fact_offsets):
                builder.PrependUOffsetTRelative(offset)
            facts_vector = builder.EndVector()
        else:
            facts_vector = 0

        # 4. Build entities vector (mentioned_entities per schema)
        entity_offsets = []
        for entity in self._entities.values():
            id_off = builder.CreateString(entity.id)
            type_off = builder.CreateString(entity.type)
            name_off = builder.CreateString(entity.display_name)

            EntityRefStart(builder)
            EntityRefAddId(builder, id_off)
            EntityRefAddType(builder, type_off)
            EntityRefAddDisplayName(builder, name_off)
            EntityRefAddConfidence(builder, entity.confidence)
            entity_offsets.append(EntityRefEnd(builder))

        if entity_offsets:
            BeliefsActiveSectionStartMentionedEntitiesVector(builder, len(entity_offsets))
            for offset in reversed(entity_offsets):
                builder.PrependUOffsetTRelative(offset)
            entities_vector = builder.EndVector()
        else:
            entities_vector = 0

        # 5. Build mentioned_time (optional per schema)
        time_offset = 0
        if self._mentioned_time:
            raw_text_off = builder.CreateString(self._mentioned_time.raw_text)
            MentionedTimeStart(builder)
            MentionedTimeAddRawText(builder, raw_text_off)
            MentionedTimeAddResolvedMs(builder, self._mentioned_time.resolved_ms)
            MentionedTimeAddConfidence(builder, self._mentioned_time.confidence)
            MentionedTimeAddIsRelative(builder, self._mentioned_time.is_relative)
            time_offset = MentionedTimeEnd(builder)

        # 6. Build mentioned_location (optional per schema)
        location_offset = 0
        if self._mentioned_location:
            raw_text_off = builder.CreateString(self._mentioned_location.raw_text)
            type_off = builder.CreateString(self._mentioned_location.location_type)
            entity_id_off = builder.CreateString(self._mentioned_location.entity_id)
            MentionedLocationStart(builder)
            MentionedLocationAddRawText(builder, raw_text_off)
            MentionedLocationAddLocationType(builder, type_off)
            MentionedLocationAddEntityId(builder, entity_id_off)
            MentionedLocationAddConfidence(builder, self._mentioned_location.confidence)
            location_offset = MentionedLocationEnd(builder)

        # 7. Build pinned_fact_ids vector
        pinned_offsets = [builder.CreateString(fid) for fid in self._pinned_fact_ids]
        if pinned_offsets:
            BeliefsActiveSectionStartPinnedFactIdsVector(builder, len(pinned_offsets))
            for offset in reversed(pinned_offsets):
                builder.PrependUOffsetTRelative(offset)
            pinned_vector = builder.EndVector()
        else:
            pinned_vector = 0

        # 8. Build header
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # 9. Build BeliefsActiveSection root
        BeliefsActiveSectionStart(builder)
        BeliefsActiveSectionAddHeader(builder, header_offset)
        BeliefsActiveSectionAddTurnId(builder, turn_id_offset)
        if facts_vector:
            BeliefsActiveSectionAddCurrentTurnFacts(builder, facts_vector)
        if entities_vector:
            BeliefsActiveSectionAddMentionedEntities(builder, entities_vector)
        if time_offset:
            BeliefsActiveSectionAddMentionedTime(builder, time_offset)
        if location_offset:
            BeliefsActiveSectionAddMentionedLocation(builder, location_offset)
        if pinned_vector:
            BeliefsActiveSectionAddPinnedFactIds(builder, pinned_vector)
        BeliefsActiveSectionAddFactCount(builder, len(self._facts))
        BeliefsActiveSectionAddEntityCount(builder, len(self._entities))
        BeliefsActiveSectionAddLastUpdatedMs(builder, self._last_updated_ms)
        section_offset = BeliefsActiveSectionEnd(builder)

        builder.Finish(section_offset)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize section from FlatBuffer bytes.

        Args:
            data: FlatBuffer-encoded data per beliefs_active_section.fbs
        """
        fb = FBBeliefsActiveSection.GetRootAsBeliefsActiveSection(data, 0)

        # Clear current state
        self._facts.clear()
        self._entities.clear()
        self._by_subject.clear()
        self._by_predicate.clear()
        self._by_object.clear()
        self._pinned_fact_ids.clear()

        # Load turn_id (required per schema)
        turn_id = fb.TurnId()
        if turn_id:
            self._turn_id = turn_id.decode() if isinstance(turn_id, bytes) else turn_id

        # Load last_updated_ms
        self._last_updated_ms = fb.LastUpdatedMs()

        # Load facts (current_turn_facts per schema)
        for i in range(fb.CurrentTurnFactsLength()):
            fact_fb = fb.CurrentTurnFacts(i)
            if fact_fb:
                fact_id = self._decode_string(fact_fb.Id())
                fact = Fact(
                    id=fact_id or str(uuid.uuid4()),
                    subject=self._decode_string(fact_fb.Subject()) or "",
                    predicate=self._decode_string(fact_fb.Predicate()) or "",
                    object=self._decode_string(fact_fb.Object()) or "",
                    confidence=fact_fb.Confidence(),
                    source=self._decode_string(fact_fb.Source()) or "",
                    timestamp_ms=fact_fb.TimestampMs(),
                    privacy_band=PrivacyBand(fact_fb.PrivacyBand()),
                )
                self._facts[fact.id] = fact

                # Rebuild indexes
                self._by_subject.setdefault(fact.subject, []).append(fact.id)
                self._by_predicate.setdefault(fact.predicate, []).append(fact.id)
                self._by_object.setdefault(fact.object, []).append(fact.id)

        # Load entities (mentioned_entities per schema)
        for i in range(fb.MentionedEntitiesLength()):
            entity_fb = fb.MentionedEntities(i)
            if entity_fb:
                entity = EntityRef(
                    id=self._decode_string(entity_fb.Id()) or str(uuid.uuid4()),
                    type=self._decode_string(entity_fb.Type()) or "",
                    display_name=self._decode_string(entity_fb.DisplayName()) or "",
                    confidence=entity_fb.Confidence(),
                )
                self._entities[entity.id] = entity

        # Load mentioned_time (optional per schema)
        time_fb = fb.MentionedTime()
        if time_fb:
            self._mentioned_time = MentionedTime(
                raw_text=self._decode_string(time_fb.RawText()) or "",
                resolved_ms=time_fb.ResolvedMs(),
                confidence=time_fb.Confidence(),
                is_relative=time_fb.IsRelative(),
            )
        else:
            self._mentioned_time = None

        # Load mentioned_location (optional per schema)
        loc_fb = fb.MentionedLocation()
        if loc_fb:
            self._mentioned_location = MentionedLocation(
                raw_text=self._decode_string(loc_fb.RawText()) or "",
                location_type=self._decode_string(loc_fb.LocationType()) or "",
                entity_id=self._decode_string(loc_fb.EntityId()) or "",
                confidence=loc_fb.Confidence(),
            )
        else:
            self._mentioned_location = None

        # Load pinned_fact_ids
        for i in range(fb.PinnedFactIdsLength()):
            fid = self._decode_string(fb.PinnedFactIds(i))
            if fid and fid in self._facts:
                self._pinned_fact_ids.add(fid)
                self._facts[fid].is_pinned = True

        self._cache_valid = False

    # =========================================================================
    # Legacy API Aliases
    # =========================================================================

    def serialize(self) -> bytes:
        """Legacy alias for to_flatbuffer."""
        return self.to_flatbuffer()

    def deserialize(self, data: bytes) -> None:
        """Legacy alias for from_flatbuffer."""
        self.from_flatbuffer(data)

    def get(self) -> Dict[str, Any]:
        """Get section state as dictionary (legacy API)."""
        mentioned_entities = [
            {
                "id": e.id,
                "type": e.type,
                "display_name": e.display_name,
                "confidence": e.confidence,
            }
            for e in self._entities.values()
        ]
        return {
            "session_id": self._session_id,
            "turn_id": self._turn_id,
            "schema_version": self._schema_version,
            "last_updated_ms": self._last_updated_ms,
            "fact_count": len(self._facts),
            "entity_count": len(self._entities),
            "facts": [
                {
                    "id": f.id,
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "object": f.object,
                    "confidence": f.confidence,
                }
                for f in self._facts.values()
            ],
            "entities": [
                {
                    "id": e.id,
                    "type": e.type,
                    "display_name": e.display_name,
                }
                for e in self._entities.values()
            ],
            "mentioned_entities": mentioned_entities,
            "mentioned_time": (
                {
                    "raw_text": self._mentioned_time.raw_text,
                    "resolved_ms": self._mentioned_time.resolved_ms,
                }
                if self._mentioned_time
                else None
            ),
            "mentioned_location": (
                {
                    "raw_text": self._mentioned_location.raw_text,
                    "location_type": self._mentioned_location.location_type,
                }
                if self._mentioned_location
                else None
            ),
        }

    def touch(self) -> None:
        """Update last_updated_ms timestamp (legacy API)."""
        self._touch()

    def apply(self, operation: str, data: dict) -> Any:
        """Apply mutation operation dispatched via manager.mutate().

        Supports:
        - add_fact: Add a new SPO triple
        - update / update_confidence: Update confidence of existing fact
        - pin_fact: Pin a fact
        - unpin_fact: Unpin a fact
        - clear: Reset all beliefs
        """
        if operation == "add_fact":
            return self.add_fact(
                subject=data.get("subject", ""),
                predicate=data.get("predicate", ""),
                obj=data.get("obj", ""),
                confidence=data.get("confidence", 1.0),
                source=data.get("source", ""),
            )
        elif operation in ("update", "update_confidence"):
            return self.update_confidence(
                fact_id=data.get("id", ""),
                confidence=data.get("confidence", 1.0),
            )
        elif operation == "pin_fact":
            return self.pin_fact(data.get("id", ""))
        elif operation == "unpin_fact":
            return self.unpin_fact(data.get("id", ""))
        elif operation == "clear":
            self.clear()
            return True
        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _touch(self) -> None:
        """Update last_updated_ms timestamp."""
        self._last_updated_ms = int(time.time() * 1000)

    def _invalidate_cache(self) -> None:
        """Invalidate serialization cache."""
        self._cache_valid = False
        self._cached_bytes = None

    @staticmethod
    def _decode_string(value) -> Optional[str]:
        """Decode bytes to string if needed."""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value
