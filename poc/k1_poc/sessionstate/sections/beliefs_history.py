"""
BeliefsHistorySection - Demoted Beliefs (WARM)
===============================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.3 Implement WARM TIER Sections
ISSUE: 2.3.1 (beliefs_history)

This section contains beliefs demoted from HOT tier. Uses LRU-based eviction
to LOCAL COLD, max 100 facts. Supports promotion back to HOT based on access.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/beliefs_history_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- facts: [ArchivedFact] - LRU ordered, max 100
- entity_index: [EntityFactIndex]
- total_facts: uint16
- max_facts: uint16 = 100
- oldest_turn: uint16
- newest_turn: uint16
- next_eviction_candidates: [uint16]
- eviction_threshold: float = 0.2
- archived_count: uint32
- archive_pointer: string

Eviction Contract (IEvictable):
- get_eviction_priority() -> int  (returns 2)
- evict_partial(target_kb: int) -> EvictedData
- can_evict() -> bool
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    BeliefsHistorySection as FBBeliefsHistorySection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.ArchivedFact import (
    ArchivedFactAddAccessCount,
    ArchivedFactAddFact,
    ArchivedFactAddIsStale,
    ArchivedFactAddLastAccessedTurn,
    ArchivedFactAddLruScore,
    ArchivedFactAddOriginalTurn,
    ArchivedFactEnd,
    ArchivedFactStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.BeliefsHistorySection import (
    BeliefsHistorySectionAddArchivedCount,
    BeliefsHistorySectionAddArchivePointer,
    BeliefsHistorySectionAddEntityIndex,
    BeliefsHistorySectionAddEvictionThreshold,
    BeliefsHistorySectionAddFacts,
    BeliefsHistorySectionAddHeader,
    BeliefsHistorySectionAddMaxFacts,
    BeliefsHistorySectionAddNewestTurn,
    BeliefsHistorySectionAddNextEvictionCandidates,
    BeliefsHistorySectionAddOldestTurn,
    BeliefsHistorySectionAddTotalFacts,
    BeliefsHistorySectionEnd,
    BeliefsHistorySectionStart,
    BeliefsHistorySectionStartEntityIndexVector,
    BeliefsHistorySectionStartFactsVector,
    BeliefsHistorySectionStartNextEvictionCandidatesVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.EntityFactIndex import (
    EntityFactIndexAddEntityId,
    EntityFactIndexAddFactIndices,
    EntityFactIndexAddLastUpdatedTurn,
    EntityFactIndexEnd,
    EntityFactIndexStart,
    EntityFactIndexStartFactIndicesVector,
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
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)

# =============================================================================
# Enums
# =============================================================================


class PrivacyBand(IntEnum):
    """Privacy classification bands per ADR-0042."""

    GREEN = 0  # Public, non-sensitive
    AMBER = 1  # Internal, sensitive
    RED = 2  # Confidential, PII
    BLACK = 3  # Restricted, regulated


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Fact:
    """
    Core fact structure in SVO format.

    Maps to Fact table in common.fbs.
    """

    id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source: str = ""
    timestamp_ms: int = 0
    privacy_band: PrivacyBand = PrivacyBand.GREEN


@dataclass
class ArchivedFact:
    """
    Fact with history/LRU metadata for WARM tier.

    Maps to ArchivedFact table in beliefs_history_section.fbs.
    """

    # Core fact data
    fact: Fact

    # History metadata
    original_turn: int = 0
    last_accessed_turn: int = 0
    access_count: int = 0
    demoted_at_ms: int = 0

    # LRU tracking
    lru_score: float = 1.0  # Higher = more recently used
    is_stale: bool = False

    def update_lru_score(self, current_turn: int, decay_factor: float = 0.1) -> None:
        """
        Update LRU score based on access pattern.

        Score = base_score * (1 - decay * turns_since_access) + access_bonus
        """
        turns_since_access = max(0, current_turn - self.last_accessed_turn)
        decay = min(1.0, turns_since_access * decay_factor)
        access_bonus = min(0.5, self.access_count * 0.05)
        self.lru_score = max(0.0, (1.0 - decay) + access_bonus)

    def mark_accessed(self, turn: int) -> None:
        """Record an access, updating LRU state."""
        self.last_accessed_turn = turn
        self.access_count += 1
        self.is_stale = False
        self.update_lru_score(turn)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "fact": {
                "id": self.fact.id,
                "subject": self.fact.subject,
                "predicate": self.fact.predicate,
                "object": self.fact.object,
                "confidence": self.fact.confidence,
                "source": self.fact.source,
                "timestamp_ms": self.fact.timestamp_ms,
                "privacy_band": int(self.fact.privacy_band),
            },
            "original_turn": self.original_turn,
            "last_accessed_turn": self.last_accessed_turn,
            "access_count": self.access_count,
            "demoted_at_ms": self.demoted_at_ms,
            "lru_score": self.lru_score,
            "is_stale": self.is_stale,
        }


@dataclass
class EntityFactIndex:
    """
    Index mapping entity to fact indices for fast lookup.

    Maps to EntityFactIndex table in beliefs_history_section.fbs.
    """

    entity_id: str
    fact_indices: List[int] = field(default_factory=list)
    last_updated_turn: int = 0

    def add_fact_index(self, index: int, turn: int) -> None:
        """Add a fact index to this entity."""
        if index not in self.fact_indices:
            self.fact_indices.append(index)
            self.last_updated_turn = turn

    def remove_fact_index(self, index: int) -> None:
        """Remove a fact index from this entity."""
        if index in self.fact_indices:
            self.fact_indices.remove(index)


@dataclass
class EvictedData:
    """Data evicted from WARM tier for archival to LOCAL COLD."""

    facts: List[ArchivedFact]
    bytes_freed: int
    eviction_reason: str = "pressure"


# =============================================================================
# BeliefsHistorySection - Main Implementation
# =============================================================================


class BeliefsHistorySection:
    """
    Historical beliefs section - demoted from HOT (WARM tier).

    Implements ISection and IEvictable protocols.

    Budget: 12KB (12288 bytes)
    Eviction Priority: 2 (second to evict after telemetry)
    Max Facts: 100

    Attributes:
        _facts: List[ArchivedFact] - LRU ordered
        _index: Dict[str, int] - fact_id -> index mapping
        _entity_index: Dict[str, EntityFactIndex]
        _current_turn: int
        _archived_count: int
        _archive_pointer: str

    Example:
        section = BeliefsHistorySection()

        # Accept demoted beliefs from HOT
        section.accept_demoted(beliefs, turn=5)

        # Access belief (updates LRU)
        belief = section.get("belief-123")

        # Get promotion candidates
        candidates = section.get_promotion_candidates(count=3)

        # Evict to LOCAL COLD
        evicted = section.evict_partial(target_kb=4)
    """

    # Section constants
    BUDGET_BYTES = 12288  # 12KB
    TIER = "warm"
    SECTION_NAME = "beliefs_history"
    CAN_EVICT = True
    EVICTION_PRIORITY = 2  # Second to evict (after telemetry)
    MAX_FACTS = 100
    PROMOTION_THRESHOLD = 3  # Access count to consider for promotion
    DEFAULT_EVICTION_THRESHOLD = 0.2  # LRU score below which to evict

    def __init__(
        self,
        max_facts: int = MAX_FACTS,
        eviction_threshold: float = DEFAULT_EVICTION_THRESHOLD,
    ) -> None:
        """
        Initialize empty BeliefsHistorySection.

        Args:
            max_facts: Maximum facts to store (default 100)
            eviction_threshold: LRU score below which facts are eviction candidates
        """
        self._facts: List[ArchivedFact] = []
        self._index: Dict[str, int] = {}  # fact_id -> list index
        self._entity_index: Dict[str, EntityFactIndex] = {}
        self._current_turn: int = 0
        self._oldest_turn: int = 0
        self._newest_turn: int = 0
        self._archived_count: int = 0
        self._archive_pointer: str = ""
        self._max_facts: int = max_facts
        self._eviction_threshold: float = eviction_threshold
        self._integrity_hash: str = ""
        self._fb_cache: Optional[bytes] = None

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

        ArchivedFact: ~100 bytes each
        EntityFactIndex: ~50 bytes each
        Base overhead: ~200 bytes
        """
        base_size = 200
        fact_size = len(self._facts) * 100
        entity_index_size = len(self._entity_index) * 50
        return base_size + fact_size + entity_index_size

    def clear(self) -> None:
        """Clear all data."""
        self._facts.clear()
        self._index.clear()
        self._entity_index.clear()
        self._current_turn = 0
        self._oldest_turn = 0
        self._newest_turn = 0
        self._integrity_hash = ""
        self._invalidate_cache()

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to dictionary representation."""
        return {
            "name": self.name,
            "tier": self.tier,
            "size_bytes": self.get_size_bytes(),
            "budget_bytes": self.budget_bytes,
            "total_facts": len(self._facts),
            "max_facts": self._max_facts,
            "oldest_turn": self._oldest_turn,
            "newest_turn": self._newest_turn,
            "current_turn": self._current_turn,
            "archived_count": self._archived_count,
            "archive_pointer": self._archive_pointer,
            "eviction_threshold": self._eviction_threshold,
            "entity_count": len(self._entity_index),
            "facts": [f.to_dict() for f in self._facts],
        }

    # =========================================================================
    # IEvictable Protocol
    # =========================================================================

    def get_eviction_priority(self) -> int:
        """
        Get eviction priority (lower = evict first).

        Returns:
            int: Priority 2 (evict after telemetry which is 1)
        """
        return self.EVICTION_PRIORITY

    def can_evict(self) -> bool:
        """
        Check if this section can be evicted.

        Returns:
            bool: True if there are facts to evict
        """
        return len(self._facts) > 0

    def evict_partial(self, target_kb: float) -> EvictedData:
        """
        Evict facts to free up space.

        Args:
            target_kb: Target kilobytes to free

        Returns:
            EvictedData: Facts evicted and bytes freed
        """
        target_bytes = int(target_kb * 1024)
        bytes_to_free = min(target_bytes, self.get_size_bytes())

        # Get eviction candidates (lowest LRU scores first)
        candidates = self.get_eviction_candidates()

        evicted_facts: List[ArchivedFact] = []
        bytes_freed = 0

        for candidate in candidates:
            if bytes_freed >= bytes_to_free:
                break

            evicted_facts.append(candidate)
            bytes_freed += 100  # Approximate bytes per fact

            # Remove from section
            self._remove_fact_internal(candidate.fact.id)

        self._archived_count += len(evicted_facts)
        self._invalidate_cache()

        return EvictedData(
            facts=evicted_facts,
            bytes_freed=bytes_freed,
            eviction_reason="pressure",
        )

    def get_eviction_candidates(self, count: Optional[int] = None) -> List[ArchivedFact]:
        """
        Get facts that are candidates for eviction.

        Args:
            count: Maximum candidates to return (None = all)

        Returns:
            List[ArchivedFact]: Candidates sorted by LRU score (lowest first)
        """
        # Update all LRU scores
        for fact in self._facts:
            fact.update_lru_score(self._current_turn)

        # Filter candidates below threshold and sort by LRU score
        candidates = [
            f for f in self._facts if f.lru_score <= self._eviction_threshold or f.is_stale
        ]
        candidates.sort(key=lambda f: (f.lru_score, f.access_count))

        # If not enough below threshold, add more from lowest scores
        if len(candidates) < (count or 10):
            remaining = [f for f in self._facts if f not in candidates]
            remaining.sort(key=lambda f: (f.lru_score, f.access_count))
            candidates.extend(remaining)

        if count is not None:
            return candidates[:count]
        return candidates

    # =========================================================================
    # Demotion API (accept from HOT)
    # =========================================================================

    def accept_demoted(
        self,
        facts: List[Dict[str, Any]],
        turn: int,
    ) -> int:
        """
        Accept facts demoted from HOT tier.

        Args:
            facts: List of fact dicts from HOT tier
            turn: Current turn number

        Returns:
            int: Number of facts accepted
        """
        now_ms = int(time.time() * 1000)
        self._current_turn = max(self._current_turn, turn)
        count = 0

        for fact_dict in facts:
            # Skip if already at max
            if len(self._facts) >= self._max_facts:
                # Evict oldest to make room
                self._evict_one_oldest()

            # Create Fact from dict
            fact = Fact(
                id=fact_dict.get("id", str(uuid.uuid4())),
                subject=fact_dict.get("subject", ""),
                predicate=fact_dict.get("predicate", ""),
                object=fact_dict.get("object", ""),
                confidence=fact_dict.get("confidence", 1.0),
                source=fact_dict.get("source", ""),
                timestamp_ms=fact_dict.get("timestamp_ms", now_ms),
                privacy_band=PrivacyBand(fact_dict.get("privacy_band", 0)),
            )

            # Create ArchivedFact wrapper
            archived = ArchivedFact(
                fact=fact,
                original_turn=fact_dict.get("original_turn", turn),
                last_accessed_turn=fact_dict.get("last_accessed_turn", turn),
                access_count=fact_dict.get("access_count", 0),
                demoted_at_ms=now_ms,
                lru_score=1.0,  # Fresh demotion gets high score
                is_stale=False,
            )

            # Add to storage
            self._facts.append(archived)
            self._index[fact.id] = len(self._facts) - 1

            # Update entity index
            self._update_entity_index(archived, len(self._facts) - 1, turn)

            # Update turn tracking
            if self._oldest_turn == 0 or archived.original_turn < self._oldest_turn:
                self._oldest_turn = archived.original_turn
            if archived.original_turn > self._newest_turn:
                self._newest_turn = archived.original_turn

            count += 1

        self._invalidate_cache()
        return count

    def _evict_one_oldest(self) -> Optional[ArchivedFact]:
        """Evict single oldest fact to make room."""
        if not self._facts:
            return None

        candidates = self.get_eviction_candidates(count=1)
        if candidates:
            self._remove_fact_internal(candidates[0].fact.id)
            self._archived_count += 1
            return candidates[0]
        return None

    def _update_entity_index(
        self,
        archived: ArchivedFact,
        fact_index: int,
        turn: int,
    ) -> None:
        """Update entity index for a fact."""
        # Extract entities from subject and object
        entities = [archived.fact.subject, archived.fact.object]

        for entity in entities:
            if entity:
                if entity not in self._entity_index:
                    self._entity_index[entity] = EntityFactIndex(entity_id=entity)
                self._entity_index[entity].add_fact_index(fact_index, turn)

    # =========================================================================
    # Access API
    # =========================================================================

    def get(self, fact_id: str) -> Optional[ArchivedFact]:
        """
        Get fact by ID (marks as accessed).

        Args:
            fact_id: Fact UUID

        Returns:
            ArchivedFact or None
        """
        if fact_id not in self._index:
            return None

        fact = self._facts[self._index[fact_id]]
        fact.mark_accessed(self._current_turn)
        self._invalidate_cache()
        return fact

    def get_without_access(self, fact_id: str) -> Optional[ArchivedFact]:
        """
        Get fact by ID without marking as accessed.

        Args:
            fact_id: Fact UUID

        Returns:
            ArchivedFact or None
        """
        if fact_id not in self._index:
            return None
        return self._facts[self._index[fact_id]]

    def list_facts(self) -> List[ArchivedFact]:
        """
        List all facts (does not mark as accessed).

        Returns:
            List[ArchivedFact]: All historical facts
        """
        return list(self._facts)

    def count(self) -> int:
        """Get number of facts."""
        return len(self._facts)

    def contains(self, fact_id: str) -> bool:
        """Check if fact exists."""
        return fact_id in self._index

    # =========================================================================
    # Query API
    # =========================================================================

    def get_by_entity(self, entity_id: str) -> List[ArchivedFact]:
        """
        Get facts related to an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List[ArchivedFact]: Facts mentioning this entity
        """
        if entity_id not in self._entity_index:
            return []

        indices = self._entity_index[entity_id].fact_indices
        return [self._facts[i] for i in indices if i < len(self._facts)]

    def get_by_subject(self, subject: str) -> List[ArchivedFact]:
        """Get facts with matching subject."""
        return [f for f in self._facts if f.fact.subject == subject]

    def get_by_predicate(self, predicate: str) -> List[ArchivedFact]:
        """Get facts with matching predicate."""
        return [f for f in self._facts if f.fact.predicate == predicate]

    def get_by_turn_range(
        self,
        start_turn: int,
        end_turn: int,
    ) -> List[ArchivedFact]:
        """Get facts from a turn range."""
        return [f for f in self._facts if start_turn <= f.original_turn <= end_turn]

    def search(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object_value: Optional[str] = None,
    ) -> List[ArchivedFact]:
        """
        Search facts by SVO pattern.

        Args:
            subject: Subject pattern (None = any)
            predicate: Predicate pattern (None = any)
            object_value: Object pattern (None = any)

        Returns:
            List[ArchivedFact]: Matching facts
        """
        results = []
        for fact in self._facts:
            if subject is not None and fact.fact.subject != subject:
                continue
            if predicate is not None and fact.fact.predicate != predicate:
                continue
            if object_value is not None and fact.fact.object != object_value:
                continue
            results.append(fact)
        return results

    # =========================================================================
    # Promotion API
    # =========================================================================

    def get_promotion_candidates(self, count: int = 5) -> List[ArchivedFact]:
        """
        Get facts that should be promoted back to HOT.

        Criteria:
        - access_count >= PROMOTION_THRESHOLD
        - Sorted by access_count descending

        Args:
            count: Maximum candidates to return

        Returns:
            List[ArchivedFact]: Promotion candidates
        """
        candidates = [f for f in self._facts if f.access_count >= self.PROMOTION_THRESHOLD]
        candidates.sort(key=lambda f: f.access_count, reverse=True)
        return candidates[:count]

    def remove_for_promotion(self, fact_ids: List[str]) -> List[ArchivedFact]:
        """
        Remove facts that are being promoted to HOT.

        Args:
            fact_ids: Facts to remove

        Returns:
            List[ArchivedFact]: Removed facts
        """
        removed = []
        for fact_id in fact_ids:
            if fact_id in self._index:
                fact = self._facts[self._index[fact_id]]
                removed.append(fact)
                self._remove_fact_internal(fact_id)

        self._invalidate_cache()
        return removed

    # =========================================================================
    # Removal API
    # =========================================================================

    def remove(self, fact_id: str) -> bool:
        """
        Remove a fact by ID.

        Args:
            fact_id: Fact to remove

        Returns:
            bool: True if found and removed
        """
        if fact_id not in self._index:
            return False

        self._remove_fact_internal(fact_id)
        self._invalidate_cache()
        return True

    def _remove_fact_internal(self, fact_id: str) -> None:
        """Internal fact removal with index updates."""
        if fact_id not in self._index:
            return

        idx = self._index[fact_id]
        fact = self._facts[idx]

        # Remove from entity index
        for entity_id in [fact.fact.subject, fact.fact.object]:
            if entity_id and entity_id in self._entity_index:
                self._entity_index[entity_id].remove_fact_index(idx)
                if not self._entity_index[entity_id].fact_indices:
                    del self._entity_index[entity_id]

        # Remove from facts list and index
        del self._facts[idx]
        del self._index[fact_id]

        # Rebuild indices after removal
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Rebuild internal indices after modification."""
        self._index.clear()
        for i, fact in enumerate(self._facts):
            self._index[fact.fact.id] = i

        # Rebuild entity index
        self._entity_index.clear()
        for i, archived in enumerate(self._facts):
            for entity in [archived.fact.subject, archived.fact.object]:
                if entity:
                    if entity not in self._entity_index:
                        self._entity_index[entity] = EntityFactIndex(entity_id=entity)
                    self._entity_index[entity].add_fact_index(i, self._current_turn)

        # Update turn bounds
        if self._facts:
            turns = [f.original_turn for f in self._facts]
            self._oldest_turn = min(turns)
            self._newest_turn = max(turns)
        else:
            self._oldest_turn = 0
            self._newest_turn = 0

    # =========================================================================
    # Turn Management
    # =========================================================================

    def advance_turn(self, turn: int) -> None:
        """
        Advance to a new turn, updating LRU scores.

        Args:
            turn: New turn number
        """
        self._current_turn = max(self._current_turn, turn)

        # Update all LRU scores
        for fact in self._facts:
            fact.update_lru_score(self._current_turn)

        # Mark stale facts
        for fact in self._facts:
            if fact.lru_score < self._eviction_threshold:
                fact.is_stale = True

        self._invalidate_cache()

    def get_current_turn(self) -> int:
        """Get current turn number."""
        return self._current_turn

    # =========================================================================
    # Archive Management
    # =========================================================================

    def set_archive_pointer(self, pointer: str) -> None:
        """Set pointer to K0 archive location."""
        self._archive_pointer = pointer
        self._invalidate_cache()

    def get_archive_pointer(self) -> str:
        """Get K0 archive pointer."""
        return self._archive_pointer

    def get_archived_count(self) -> int:
        """Get count of facts archived to K0."""
        return self._archived_count

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get section statistics."""
        lru_scores = [f.lru_score for f in self._facts]
        access_counts = [f.access_count for f in self._facts]

        return {
            "total_facts": len(self._facts),
            "max_facts": self._max_facts,
            "entity_count": len(self._entity_index),
            "oldest_turn": self._oldest_turn,
            "newest_turn": self._newest_turn,
            "current_turn": self._current_turn,
            "archived_count": self._archived_count,
            "eviction_threshold": self._eviction_threshold,
            "stale_count": sum(1 for f in self._facts if f.is_stale),
            "avg_lru_score": sum(lru_scores) / len(lru_scores) if lru_scores else 0.0,
            "avg_access_count": sum(access_counts) / len(access_counts) if access_counts else 0.0,
            "promotion_candidates": len(self.get_promotion_candidates()),
            "eviction_candidates": len(
                [f for f in self._facts if f.lru_score <= self._eviction_threshold]
            ),
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

        # Hash facts in order
        for fact in self._facts:
            hasher.update(fact.fact.id.encode("utf-8"))
            hasher.update(fact.fact.subject.encode("utf-8"))
            hasher.update(fact.fact.predicate.encode("utf-8"))
            hasher.update(fact.fact.object.encode("utf-8"))
            hasher.update(str(fact.fact.confidence).encode("utf-8"))
            hasher.update(str(fact.access_count).encode("utf-8"))

        # Hash metadata
        hasher.update(str(self._current_turn).encode("utf-8"))
        hasher.update(str(self._archived_count).encode("utf-8"))

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

        # Build archive pointer
        archive_ptr_offset = None
        if self._archive_pointer:
            archive_ptr_offset = builder.CreateString(self._archive_pointer)

        # Build facts array
        fact_offsets = []
        for archived in reversed(self._facts):
            # Build inner Fact
            id_off = builder.CreateString(archived.fact.id)
            subj_off = builder.CreateString(archived.fact.subject)
            pred_off = builder.CreateString(archived.fact.predicate)
            obj_off = builder.CreateString(archived.fact.object)
            src_off = builder.CreateString(archived.fact.source) if archived.fact.source else None

            FactStart(builder)
            FactAddId(builder, id_off)
            FactAddSubject(builder, subj_off)
            FactAddPredicate(builder, pred_off)
            FactAddObject(builder, obj_off)
            FactAddConfidence(builder, archived.fact.confidence)
            if src_off:
                FactAddSource(builder, src_off)
            FactAddTimestampMs(builder, archived.fact.timestamp_ms)
            FactAddPrivacyBand(builder, int(archived.fact.privacy_band))
            fact_off = FactEnd(builder)

            # Build ArchivedFact
            ArchivedFactStart(builder)
            ArchivedFactAddFact(builder, fact_off)
            ArchivedFactAddOriginalTurn(builder, archived.original_turn)
            ArchivedFactAddLastAccessedTurn(builder, archived.last_accessed_turn)
            ArchivedFactAddAccessCount(builder, archived.access_count)
            # Note: DemotedAt is a struct, need to use CreateTimestamp
            ArchivedFactAddLruScore(builder, archived.lru_score)
            ArchivedFactAddIsStale(builder, archived.is_stale)
            fact_offsets.append(ArchivedFactEnd(builder))

        fact_offsets.reverse()

        # Create facts vector
        BeliefsHistorySectionStartFactsVector(builder, len(fact_offsets))
        for off in reversed(fact_offsets):
            builder.PrependUOffsetTRelative(off)
        facts_vec = builder.EndVector()

        # Build entity index
        entity_offsets = []
        for entity_id, entity_idx in self._entity_index.items():
            eid_off = builder.CreateString(entity_id)

            # Build indices vector
            EntityFactIndexStartFactIndicesVector(builder, len(entity_idx.fact_indices))
            for idx in reversed(entity_idx.fact_indices):
                builder.PrependUint16(idx)
            indices_vec = builder.EndVector()

            EntityFactIndexStart(builder)
            EntityFactIndexAddEntityId(builder, eid_off)
            EntityFactIndexAddFactIndices(builder, indices_vec)
            EntityFactIndexAddLastUpdatedTurn(builder, entity_idx.last_updated_turn)
            entity_offsets.append(EntityFactIndexEnd(builder))

        # Create entity index vector
        BeliefsHistorySectionStartEntityIndexVector(builder, len(entity_offsets))
        for off in reversed(entity_offsets):
            builder.PrependUOffsetTRelative(off)
        entity_vec = builder.EndVector()

        # Build next eviction candidates (indices of stale facts)
        stale_indices = [i for i, f in enumerate(self._facts) if f.is_stale]
        BeliefsHistorySectionStartNextEvictionCandidatesVector(builder, len(stale_indices))
        for idx in reversed(stale_indices):
            builder.PrependUint16(idx)
        eviction_vec = builder.EndVector()

        # Build header
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, int(time.time() * 1000))
        header_offset = SectionHeaderEnd(builder)

        # Build root
        BeliefsHistorySectionStart(builder)
        BeliefsHistorySectionAddHeader(builder, header_offset)
        BeliefsHistorySectionAddFacts(builder, facts_vec)
        BeliefsHistorySectionAddEntityIndex(builder, entity_vec)
        BeliefsHistorySectionAddTotalFacts(builder, len(self._facts))
        BeliefsHistorySectionAddMaxFacts(builder, self._max_facts)
        BeliefsHistorySectionAddOldestTurn(builder, self._oldest_turn)
        BeliefsHistorySectionAddNewestTurn(builder, self._newest_turn)
        BeliefsHistorySectionAddNextEvictionCandidates(builder, eviction_vec)
        BeliefsHistorySectionAddEvictionThreshold(builder, self._eviction_threshold)
        BeliefsHistorySectionAddArchivedCount(builder, self._archived_count)
        if archive_ptr_offset:
            BeliefsHistorySectionAddArchivePointer(builder, archive_ptr_offset)
        root = BeliefsHistorySectionEnd(builder)

        builder.Finish(root)
        self._fb_cache = bytes(builder.Output())
        return self._fb_cache

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize from FlatBuffer bytes (in-place mutation).

        Args:
            data: FlatBuffer bytes
        """
        fb = FBBeliefsHistorySection.GetRootAsBeliefsHistorySection(data, 0)

        # Restore config
        self._max_facts = fb.MaxFacts()
        self._eviction_threshold = fb.EvictionThreshold()
        self._oldest_turn = fb.OldestTurn()
        self._newest_turn = fb.NewestTurn()
        self._archived_count = fb.ArchivedCount()
        self._current_turn = self._newest_turn

        archive_ptr = fb.ArchivePointer()
        if archive_ptr:
            self._archive_pointer = (
                archive_ptr.decode("utf-8") if isinstance(archive_ptr, bytes) else archive_ptr
            )

        # Clear existing data
        self._facts.clear()
        self._index.clear()
        self._entity_index.clear()

        # Restore facts
        for i in range(fb.FactsLength()):
            archived_fb = fb.Facts(i)
            fact_fb = archived_fb.Fact()

            fact = Fact(
                id=fact_fb.Id().decode("utf-8") if fact_fb.Id() else "",
                subject=fact_fb.Subject().decode("utf-8") if fact_fb.Subject() else "",
                predicate=fact_fb.Predicate().decode("utf-8") if fact_fb.Predicate() else "",
                object=fact_fb.Object().decode("utf-8") if fact_fb.Object() else "",
                confidence=fact_fb.Confidence(),
                source=fact_fb.Source().decode("utf-8") if fact_fb.Source() else "",
                timestamp_ms=fact_fb.TimestampMs(),
                privacy_band=PrivacyBand(fact_fb.PrivacyBand()),
            )

            archived = ArchivedFact(
                fact=fact,
                original_turn=archived_fb.OriginalTurn(),
                last_accessed_turn=archived_fb.LastAccessedTurn(),
                access_count=archived_fb.AccessCount(),
                demoted_at_ms=0,  # Would need Timestamp parsing
                lru_score=archived_fb.LruScore(),
                is_stale=archived_fb.IsStale(),
            )

            self._facts.append(archived)
            self._index[fact.id] = len(self._facts) - 1

        # Restore entity index
        for i in range(fb.EntityIndexLength()):
            entity_fb = fb.EntityIndex(i)
            entity_id = entity_fb.EntityId().decode("utf-8") if entity_fb.EntityId() else ""

            indices = [entity_fb.FactIndices(j) for j in range(entity_fb.FactIndicesLength())]

            self._entity_index[entity_id] = EntityFactIndex(
                entity_id=entity_id,
                fact_indices=indices,
                last_updated_turn=entity_fb.LastUpdatedTurn(),
            )

        # Invalidate cache
        self._fb_cache = None

    # =========================================================================
    # Apply Operations (MutationGuard Pattern)
    # =========================================================================

    def apply(self, operation: str, data: Dict[str, Any]) -> Any:
        """
        Apply a mutation operation.

        Supported operations:
        - accept_demoted: Accept facts from HOT tier
        - get: Get fact by ID
        - remove: Remove fact by ID
        - advance_turn: Advance to new turn
        - evict_partial: Evict to free space
        - set_archive_pointer: Set K0 archive pointer
        - clear: Clear all data

        Args:
            operation: Operation name
            data: Operation parameters

        Returns:
            Any: Operation result
        """
        self._invalidate_cache()

        if operation == "accept_demoted":
            return self.accept_demoted(
                facts=data.get("facts", []),
                turn=data.get("turn", self._current_turn),
            )

        elif operation == "get":
            return self.get(data["fact_id"])

        elif operation == "remove":
            return self.remove(data["fact_id"])

        elif operation == "advance_turn":
            return self.advance_turn(data["turn"])

        elif operation == "evict_partial":
            return self.evict_partial(data["target_kb"])

        elif operation == "set_archive_pointer":
            return self.set_archive_pointer(data["pointer"])

        elif operation == "clear":
            return self.clear()

        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Utility
    # =========================================================================

    def __repr__(self) -> str:
        return (
            f"BeliefsHistorySection("
            f"facts={len(self._facts)}/{self._max_facts}, "
            f"entities={len(self._entity_index)}, "
            f"turn={self._current_turn}, "
            f"archived={self._archived_count})"
        )

    def __len__(self) -> int:
        return len(self._facts)


# =============================================================================
# Factory Function
# =============================================================================


def create_beliefs_history_section(
    max_facts: int = BeliefsHistorySection.MAX_FACTS,
    eviction_threshold: float = BeliefsHistorySection.DEFAULT_EVICTION_THRESHOLD,
) -> BeliefsHistorySection:
    """
    Factory function to create BeliefsHistorySection.

    Args:
        max_facts: Maximum facts to store (default 100)
        eviction_threshold: LRU score below which facts are eviction candidates

    Returns:
        BeliefsHistorySection: New section instance
    """
    return BeliefsHistorySection(
        max_facts=max_facts,
        eviction_threshold=eviction_threshold,
    )
