"""
HistoryRecentSection - Recent History (WARM)
=============================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.3 Implement WARM TIER Sections
ISSUE: 2.3.2 (history_recent)

This section contains turns 11-40 with two-stage lossy compression:
- Compressed turns (11-30): entities + intents + key phrases only
- Summarized turns (31-40): LLM-generated single sentence

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/history_recent_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- compressed_turns: [CompressedTurn] - Max 20 turns
- summarized_turns: [SummarizedTurn] - Max 10 turns
- session_summary: string - ~200 chars max
- archived_turn_ids: [string]
- total_turns_archived: uint32
- oldest/newest_compressed_turn: uint16
- oldest/newest_summarized_turn: uint16
- eviction_priority: uint8 = 3
- last_eviction_ms: int64
- bytes_evicted_total: uint32

Eviction Contract (IEvictable):
- get_eviction_priority() -> int  (returns 3)
- evict_partial(target_kb: int) -> EvictedData
- can_evict() -> bool
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types
from k1.sessionstate.generated.flatbuffers.K1.SessionState import (
    HistoryRecentSection as FBHistoryRecentSection,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.CompressedTurn import (
    CompressedTurnAddArchivedToLocalCold,
    CompressedTurnAddArchiveId,
    CompressedTurnAddEmotion,
    CompressedTurnAddEntities,
    CompressedTurnAddIntents,
    CompressedTurnAddKeyPhrases,
    CompressedTurnAddResponseTokens,
    CompressedTurnAddTimestampMs,
    CompressedTurnAddTurnId,
    CompressedTurnAddTurnNumber,
    CompressedTurnAddUserTokens,
    CompressedTurnEnd,
    CompressedTurnStart,
    CompressedTurnStartEntitiesVector,
    CompressedTurnStartIntentsVector,
    CompressedTurnStartKeyPhrasesVector,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.HistoryRecentSection import (
    HistoryRecentSectionAddArchivedTurnIds,
    HistoryRecentSectionAddBytesEvictedTotal,
    HistoryRecentSectionAddCompressedTurns,
    HistoryRecentSectionAddEvictionPriority,
    HistoryRecentSectionAddHeader,
    HistoryRecentSectionAddLastEvictionMs,
    HistoryRecentSectionAddNewestCompressedTurn,
    HistoryRecentSectionAddNewestSummarizedTurn,
    HistoryRecentSectionAddOldestCompressedTurn,
    HistoryRecentSectionAddOldestSummarizedTurn,
    HistoryRecentSectionAddSessionSummary,
    HistoryRecentSectionAddSummarizedTurns,
    HistoryRecentSectionAddTotalTurnsArchived,
    HistoryRecentSectionEnd,
    HistoryRecentSectionStart,
    HistoryRecentSectionStartArchivedTurnIdsVector,
    HistoryRecentSectionStartCompressedTurnsVector,
    HistoryRecentSectionStartSummarizedTurnsVector,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SummarizedTurn import (
    SummarizedTurnAddArchivedToLocalCold,
    SummarizedTurnAddArchiveId,
    SummarizedTurnAddPrimaryEntity,
    SummarizedTurnAddPrimaryIntent,
    SummarizedTurnAddSummary,
    SummarizedTurnAddTimestampMs,
    SummarizedTurnAddTurnId,
    SummarizedTurnAddTurnNumber,
    SummarizedTurnEnd,
    SummarizedTurnStart,
)

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CompressedTurn:
    """
    Compressed turn - structural compression, no full text.

    Used for turns 11-30 (entities + intents + key phrases only).
    Maps to CompressedTurn table in history_recent_section.fbs.
    """

    turn_id: str
    turn_number: int

    # Structural extraction (no full text)
    entities: List[str] = field(default_factory=list)
    intents: List[str] = field(default_factory=list)
    key_phrases: List[str] = field(default_factory=list)

    # Metadata
    timestamp_ms: int = 0
    emotion: str = ""
    user_tokens: int = 0
    response_tokens: int = 0

    # Archive tracking
    archived_to_local_cold: bool = False
    archive_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "turn_id": self.turn_id,
            "turn_number": self.turn_number,
            "entities": self.entities,
            "intents": self.intents,
            "key_phrases": self.key_phrases,
            "timestamp_ms": self.timestamp_ms,
            "emotion": self.emotion,
            "user_tokens": self.user_tokens,
            "response_tokens": self.response_tokens,
            "archived_to_local_cold": self.archived_to_local_cold,
            "archive_id": self.archive_id,
        }

    @classmethod
    def from_full_turn(
        cls,
        turn_id: str,
        turn_number: int,
        entities: List[str],
        intents: List[str],
        key_phrases: List[str],
        timestamp_ms: int = 0,
        emotion: str = "",
        user_tokens: int = 0,
        response_tokens: int = 0,
    ) -> "CompressedTurn":
        """Create compressed turn from full turn data."""
        return cls(
            turn_id=turn_id,
            turn_number=turn_number,
            entities=entities,
            intents=intents,
            key_phrases=key_phrases,
            timestamp_ms=timestamp_ms,
            emotion=emotion,
            user_tokens=user_tokens,
            response_tokens=response_tokens,
        )


@dataclass
class SummarizedTurn:
    """
    Summarized turn - LLM-generated single sentence.

    Used for turns 31-40 (most compressed, near eviction).
    Maps to SummarizedTurn table in history_recent_section.fbs.
    """

    turn_id: str
    turn_number: int

    # Single-sentence summary (~100 chars max)
    summary: str

    # Minimal metadata
    timestamp_ms: int = 0
    primary_intent: str = ""
    primary_entity: str = ""

    # Archive tracking
    archived_to_local_cold: bool = False
    archive_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "turn_id": self.turn_id,
            "turn_number": self.turn_number,
            "summary": self.summary,
            "timestamp_ms": self.timestamp_ms,
            "primary_intent": self.primary_intent,
            "primary_entity": self.primary_entity,
            "archived_to_local_cold": self.archived_to_local_cold,
            "archive_id": self.archive_id,
        }

    @classmethod
    def from_compressed(
        cls,
        compressed: CompressedTurn,
        summary: str,
    ) -> "SummarizedTurn":
        """Create summarized turn from compressed turn."""
        return cls(
            turn_id=compressed.turn_id,
            turn_number=compressed.turn_number,
            summary=summary,
            timestamp_ms=compressed.timestamp_ms,
            primary_intent=compressed.intents[0] if compressed.intents else "",
            primary_entity=compressed.entities[0] if compressed.entities else "",
        )


@dataclass
class EvictedData:
    """Data evicted from WARM tier for archival to LOCAL COLD."""

    compressed_turns: List[CompressedTurn] = field(default_factory=list)
    summarized_turns: List[SummarizedTurn] = field(default_factory=list)
    bytes_freed: int = 0
    eviction_reason: str = "pressure"


# =============================================================================
# HistoryRecentSection - Main Implementation
# =============================================================================


class HistoryRecentSection:
    """
    Recent history section - turns 11-40 (WARM tier).

    Implements ISection and IEvictable protocols.

    Budget: 20KB (20480 bytes)
    Eviction Priority: 3 (third to evict)

    Two-stage compression:
    - Compressed turns (11-30): entities + intents + key phrases only
    - Summarized turns (31-40): single sentence each

    Attributes:
        _compressed_turns: List[CompressedTurn] - Turns 11-30
        _summarized_turns: List[SummarizedTurn] - Turns 31-40
        _session_summary: str - Overall session summary
        _archived_turn_ids: List[str] - Turn IDs in K0

    Example:
        section = HistoryRecentSection()

        # Accept compressed turn from HOT
        section.add_compressed_turn(compressed)

        # Compress oldest to summarized
        section.compress_to_summarized(count=5)

        # Evict to LOCAL COLD
        evicted = section.evict_partial(target_kb=4)
    """

    # Section constants
    BUDGET_BYTES = 20480  # 20KB
    TIER = "warm"
    SECTION_NAME = "history_recent"
    CAN_EVICT = True
    EVICTION_PRIORITY = 3  # Third to evict

    # Capacity limits
    MAX_COMPRESSED_TURNS = 20  # Turns 11-30
    MAX_SUMMARIZED_TURNS = 10  # Turns 31-40
    MAX_SESSION_SUMMARY_CHARS = 200

    # Turn number ranges
    COMPRESSED_START = 11
    COMPRESSED_END = 30
    SUMMARIZED_START = 31
    SUMMARIZED_END = 40

    def __init__(self) -> None:
        """Initialize empty HistoryRecentSection."""
        self._compressed_turns: List[CompressedTurn] = []
        self._summarized_turns: List[SummarizedTurn] = []
        self._session_summary: str = ""
        self._archived_turn_ids: List[str] = []
        self._total_turns_archived: int = 0
        self._last_eviction_ms: int = 0
        self._bytes_evicted_total: int = 0
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

        CompressedTurn: ~700 bytes each
        SummarizedTurn: ~200 bytes each
        Session summary + metadata: ~500 bytes
        """
        base_size = 500
        compressed_size = len(self._compressed_turns) * 700
        summarized_size = len(self._summarized_turns) * 200
        summary_size = len(self._session_summary)
        archive_size = len(self._archived_turn_ids) * 40
        return base_size + compressed_size + summarized_size + summary_size + archive_size

    def clear(self) -> None:
        """Clear all data."""
        self._compressed_turns.clear()
        self._summarized_turns.clear()
        self._session_summary = ""
        self._archived_turn_ids.clear()
        self._total_turns_archived = 0
        self._last_eviction_ms = 0
        self._bytes_evicted_total = 0
        self._integrity_hash = ""
        self._invalidate_cache()

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to dictionary representation."""
        return {
            "name": self.name,
            "tier": self.tier,
            "size_bytes": self.get_size_bytes(),
            "budget_bytes": self.budget_bytes,
            "compressed_turns": [t.to_dict() for t in self._compressed_turns],
            "summarized_turns": [t.to_dict() for t in self._summarized_turns],
            "session_summary": self._session_summary,
            "archived_turn_ids": self._archived_turn_ids,
            "total_turns_archived": self._total_turns_archived,
            "oldest_compressed_turn": self.get_oldest_compressed_turn(),
            "newest_compressed_turn": self.get_newest_compressed_turn(),
            "oldest_summarized_turn": self.get_oldest_summarized_turn(),
            "newest_summarized_turn": self.get_newest_summarized_turn(),
        }

    # =========================================================================
    # IEvictable Protocol
    # =========================================================================

    def get_eviction_priority(self) -> int:
        """
        Get eviction priority (lower = evict first).

        Returns:
            int: Priority 3
        """
        return self.EVICTION_PRIORITY

    def can_evict(self) -> bool:
        """
        Check if this section can be evicted.

        Returns:
            bool: True if there are turns to evict
        """
        return len(self._compressed_turns) > 0 or len(self._summarized_turns) > 0

    def evict_partial(self, target_kb: float) -> EvictedData:
        """
        Evict turns to free up space.

        Eviction order:
        1. Summarized turns (oldest first) - they're most compressed already
        2. Compressed turns (oldest first)

        Args:
            target_kb: Target kilobytes to free

        Returns:
            EvictedData: Turns evicted and bytes freed
        """
        target_bytes = int(target_kb * 1024)
        bytes_freed = 0
        now_ms = int(time.time() * 1000)

        evicted_compressed: List[CompressedTurn] = []
        evicted_summarized: List[SummarizedTurn] = []

        # First evict summarized turns (oldest first)
        while self._summarized_turns and bytes_freed < target_bytes:
            turn = self._summarized_turns.pop(0)
            self._archived_turn_ids.append(turn.turn_id)
            evicted_summarized.append(turn)
            bytes_freed += 200

        # Then evict compressed turns if needed
        while self._compressed_turns and bytes_freed < target_bytes:
            turn = self._compressed_turns.pop(0)
            self._archived_turn_ids.append(turn.turn_id)
            evicted_compressed.append(turn)
            bytes_freed += 700

        self._total_turns_archived += len(evicted_compressed) + len(evicted_summarized)
        self._bytes_evicted_total += bytes_freed
        self._last_eviction_ms = now_ms
        self._invalidate_cache()

        return EvictedData(
            compressed_turns=evicted_compressed,
            summarized_turns=evicted_summarized,
            bytes_freed=bytes_freed,
            eviction_reason="pressure",
        )

    # =========================================================================
    # Compressed Turns API
    # =========================================================================

    def add_compressed_turn(self, turn: CompressedTurn) -> bool:
        """
        Add a compressed turn.

        Args:
            turn: Compressed turn to add

        Returns:
            bool: True if added, False if at capacity
        """
        # If at capacity, compress oldest to summarized first
        if len(self._compressed_turns) >= self.MAX_COMPRESSED_TURNS:
            self.compress_to_summarized(count=1)

        # Insert in turn_number order
        self._insert_compressed_ordered(turn)
        self._invalidate_cache()
        return True

    def add_compressed_turns(self, turns: List[CompressedTurn]) -> int:
        """
        Add multiple compressed turns.

        Args:
            turns: Compressed turns to add

        Returns:
            int: Number added
        """
        count = 0
        for turn in turns:
            if self.add_compressed_turn(turn):
                count += 1
        return count

    def _insert_compressed_ordered(self, turn: CompressedTurn) -> None:
        """Insert compressed turn in turn_number order."""
        for i, existing in enumerate(self._compressed_turns):
            if turn.turn_number < existing.turn_number:
                self._compressed_turns.insert(i, turn)
                return
        self._compressed_turns.append(turn)

    def get_compressed_turn(self, turn_id: str) -> Optional[CompressedTurn]:
        """Get compressed turn by ID."""
        for turn in self._compressed_turns:
            if turn.turn_id == turn_id:
                return turn
        return None

    def get_compressed_by_number(self, turn_number: int) -> Optional[CompressedTurn]:
        """Get compressed turn by number."""
        for turn in self._compressed_turns:
            if turn.turn_number == turn_number:
                return turn
        return None

    def list_compressed_turns(self) -> List[CompressedTurn]:
        """List all compressed turns."""
        return list(self._compressed_turns)

    def compressed_count(self) -> int:
        """Get count of compressed turns."""
        return len(self._compressed_turns)

    def get_oldest_compressed_turn(self) -> int:
        """Get oldest compressed turn number."""
        if not self._compressed_turns:
            return 0
        return self._compressed_turns[0].turn_number

    def get_newest_compressed_turn(self) -> int:
        """Get newest compressed turn number."""
        if not self._compressed_turns:
            return 0
        return self._compressed_turns[-1].turn_number

    # =========================================================================
    # Summarized Turns API
    # =========================================================================

    def add_summarized_turn(self, turn: SummarizedTurn) -> bool:
        """
        Add a summarized turn.

        Args:
            turn: Summarized turn to add

        Returns:
            bool: True if added, False if at capacity
        """
        # If at capacity, evict oldest
        if len(self._summarized_turns) >= self.MAX_SUMMARIZED_TURNS:
            evicted = self._summarized_turns.pop(0)
            self._archived_turn_ids.append(evicted.turn_id)
            self._total_turns_archived += 1

        # Insert in turn_number order
        self._insert_summarized_ordered(turn)
        self._invalidate_cache()
        return True

    def _insert_summarized_ordered(self, turn: SummarizedTurn) -> None:
        """Insert summarized turn in turn_number order."""
        for i, existing in enumerate(self._summarized_turns):
            if turn.turn_number < existing.turn_number:
                self._summarized_turns.insert(i, turn)
                return
        self._summarized_turns.append(turn)

    def get_summarized_turn(self, turn_id: str) -> Optional[SummarizedTurn]:
        """Get summarized turn by ID."""
        for turn in self._summarized_turns:
            if turn.turn_id == turn_id:
                return turn
        return None

    def get_summarized_by_number(self, turn_number: int) -> Optional[SummarizedTurn]:
        """Get summarized turn by number."""
        for turn in self._summarized_turns:
            if turn.turn_number == turn_number:
                return turn
        return None

    def list_summarized_turns(self) -> List[SummarizedTurn]:
        """List all summarized turns."""
        return list(self._summarized_turns)

    def summarized_count(self) -> int:
        """Get count of summarized turns."""
        return len(self._summarized_turns)

    def get_oldest_summarized_turn(self) -> int:
        """Get oldest summarized turn number."""
        if not self._summarized_turns:
            return 0
        return self._summarized_turns[0].turn_number

    def get_newest_summarized_turn(self) -> int:
        """Get newest summarized turn number."""
        if not self._summarized_turns:
            return 0
        return self._summarized_turns[-1].turn_number

    # =========================================================================
    # Compression API
    # =========================================================================

    def compress_to_summarized(
        self,
        count: int = 1,
        summary_generator: Optional[Callable[[CompressedTurn], str]] = None,
    ) -> List[SummarizedTurn]:
        """
        Compress oldest compressed turns to summarized.

        Args:
            count: Number to compress
            summary_generator: Optional callable(CompressedTurn) -> str
                              If not provided, uses default summary

        Returns:
            List[SummarizedTurn]: Newly summarized turns
        """
        summarized = []

        for _ in range(min(count, len(self._compressed_turns))):
            compressed = self._compressed_turns.pop(0)

            # Generate summary
            if summary_generator:
                summary = summary_generator(compressed)
            else:
                summary = self._default_summary(compressed)

            summarized_turn = SummarizedTurn.from_compressed(compressed, summary)
            self.add_summarized_turn(summarized_turn)
            summarized.append(summarized_turn)

        self._invalidate_cache()
        return summarized

    def _default_summary(self, compressed: CompressedTurn) -> str:
        """Generate default summary from compressed turn."""
        parts = []

        if compressed.intents:
            parts.append(f"Intent: {compressed.intents[0]}")

        if compressed.entities:
            entity_str = ", ".join(compressed.entities[:3])
            parts.append(f"about {entity_str}")

        if compressed.emotion:
            parts.append(f"({compressed.emotion})")

        if parts:
            return " ".join(parts)[:100]
        return f"Turn {compressed.turn_number}"

    # =========================================================================
    # Session Summary API
    # =========================================================================

    def set_session_summary(self, summary: str) -> None:
        """
        Set session summary.

        Args:
            summary: Session summary (max 200 chars)
        """
        self._session_summary = summary[: self.MAX_SESSION_SUMMARY_CHARS]
        self._invalidate_cache()

    def get_session_summary(self) -> str:
        """Get session summary."""
        return self._session_summary

    def update_session_summary(self, new_context: str) -> str:
        """
        Update session summary with new context.

        Appends to existing summary, truncating if needed.

        Args:
            new_context: New context to add

        Returns:
            str: Updated summary
        """
        if self._session_summary:
            combined = f"{self._session_summary}. {new_context}"
        else:
            combined = new_context

        self._session_summary = combined[: self.MAX_SESSION_SUMMARY_CHARS]
        self._invalidate_cache()
        return self._session_summary

    # =========================================================================
    # Query API
    # =========================================================================

    def get_turn(self, turn_id: str) -> Optional[CompressedTurn | SummarizedTurn]:
        """Get any turn by ID."""
        compressed = self.get_compressed_turn(turn_id)
        if compressed:
            return compressed
        return self.get_summarized_turn(turn_id)

    def get_by_number(self, turn_number: int) -> Optional[CompressedTurn | SummarizedTurn]:
        """Get any turn by number."""
        compressed = self.get_compressed_by_number(turn_number)
        if compressed:
            return compressed
        return self.get_summarized_by_number(turn_number)

    def get_turns_by_entity(self, entity: str) -> List[CompressedTurn]:
        """Get compressed turns mentioning an entity."""
        return [t for t in self._compressed_turns if entity in t.entities]

    def get_turns_by_intent(self, intent: str) -> List[CompressedTurn]:
        """Get compressed turns with a specific intent."""
        return [t for t in self._compressed_turns if intent in t.intents]

    def search_key_phrases(self, phrase: str) -> List[CompressedTurn]:
        """Search for turns containing a key phrase."""
        phrase_lower = phrase.lower()
        return [
            t
            for t in self._compressed_turns
            if any(phrase_lower in kp.lower() for kp in t.key_phrases)
        ]

    def total_count(self) -> int:
        """Get total turn count."""
        return len(self._compressed_turns) + len(self._summarized_turns)

    def is_archived(self, turn_id: str) -> bool:
        """Check if turn has been archived."""
        return turn_id in self._archived_turn_ids

    # =========================================================================
    # Archive Management
    # =========================================================================

    def get_archived_turn_ids(self) -> List[str]:
        """Get list of archived turn IDs."""
        return list(self._archived_turn_ids)

    def get_total_turns_archived(self) -> int:
        """Get total count of archived turns."""
        return self._total_turns_archived

    def get_bytes_evicted_total(self) -> int:
        """Get total bytes evicted."""
        return self._bytes_evicted_total

    def get_last_eviction_ms(self) -> int:
        """Get timestamp of last eviction."""
        return self._last_eviction_ms

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get section statistics."""
        return {
            "compressed_count": len(self._compressed_turns),
            "summarized_count": len(self._summarized_turns),
            "total_count": self.total_count(),
            "max_compressed": self.MAX_COMPRESSED_TURNS,
            "max_summarized": self.MAX_SUMMARIZED_TURNS,
            "oldest_compressed": self.get_oldest_compressed_turn(),
            "newest_compressed": self.get_newest_compressed_turn(),
            "oldest_summarized": self.get_oldest_summarized_turn(),
            "newest_summarized": self.get_newest_summarized_turn(),
            "total_archived": self._total_turns_archived,
            "bytes_evicted": self._bytes_evicted_total,
            "session_summary_length": len(self._session_summary),
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

        # Hash compressed turns
        for turn in self._compressed_turns:
            hasher.update(turn.turn_id.encode("utf-8"))
            hasher.update(str(turn.turn_number).encode("utf-8"))
            for entity in turn.entities:
                hasher.update(entity.encode("utf-8"))
            for intent in turn.intents:
                hasher.update(intent.encode("utf-8"))

        # Hash summarized turns
        for turn in self._summarized_turns:
            hasher.update(turn.turn_id.encode("utf-8"))
            hasher.update(turn.summary.encode("utf-8"))

        # Hash session summary
        hasher.update(self._session_summary.encode("utf-8"))

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

        builder = flatbuffers.Builder(8192)

        # Build section name
        name_offset = builder.CreateString(self.SECTION_NAME)

        # Build session summary
        summary_offset = None
        if self._session_summary:
            summary_offset = builder.CreateString(self._session_summary)

        # Build compressed turns
        compressed_offsets = []
        for turn in reversed(self._compressed_turns):
            # Build string arrays
            entity_offsets = [builder.CreateString(e) for e in turn.entities]
            CompressedTurnStartEntitiesVector(builder, len(entity_offsets))
            for off in reversed(entity_offsets):
                builder.PrependUOffsetTRelative(off)
            entities_vec = builder.EndVector()

            intent_offsets = [builder.CreateString(i) for i in turn.intents]
            CompressedTurnStartIntentsVector(builder, len(intent_offsets))
            for off in reversed(intent_offsets):
                builder.PrependUOffsetTRelative(off)
            intents_vec = builder.EndVector()

            phrase_offsets = [builder.CreateString(p) for p in turn.key_phrases]
            CompressedTurnStartKeyPhrasesVector(builder, len(phrase_offsets))
            for off in reversed(phrase_offsets):
                builder.PrependUOffsetTRelative(off)
            phrases_vec = builder.EndVector()

            turn_id_off = builder.CreateString(turn.turn_id)
            emotion_off = builder.CreateString(turn.emotion) if turn.emotion else None
            archive_id_off = builder.CreateString(turn.archive_id) if turn.archive_id else None

            CompressedTurnStart(builder)
            CompressedTurnAddTurnId(builder, turn_id_off)
            CompressedTurnAddTurnNumber(builder, turn.turn_number)
            CompressedTurnAddEntities(builder, entities_vec)
            CompressedTurnAddIntents(builder, intents_vec)
            CompressedTurnAddKeyPhrases(builder, phrases_vec)
            CompressedTurnAddTimestampMs(builder, turn.timestamp_ms)
            if emotion_off:
                CompressedTurnAddEmotion(builder, emotion_off)
            CompressedTurnAddUserTokens(builder, turn.user_tokens)
            CompressedTurnAddResponseTokens(builder, turn.response_tokens)
            CompressedTurnAddArchivedToLocalCold(builder, turn.archived_to_local_cold)
            if archive_id_off:
                CompressedTurnAddArchiveId(builder, archive_id_off)
            compressed_offsets.append(CompressedTurnEnd(builder))

        compressed_offsets.reverse()
        HistoryRecentSectionStartCompressedTurnsVector(builder, len(compressed_offsets))
        for off in reversed(compressed_offsets):
            builder.PrependUOffsetTRelative(off)
        compressed_vec = builder.EndVector()

        # Build summarized turns
        summarized_offsets = []
        for turn in reversed(self._summarized_turns):
            turn_id_off = builder.CreateString(turn.turn_id)
            summary_off = builder.CreateString(turn.summary)
            intent_off = builder.CreateString(turn.primary_intent) if turn.primary_intent else None
            entity_off = builder.CreateString(turn.primary_entity) if turn.primary_entity else None
            archive_id_off = builder.CreateString(turn.archive_id) if turn.archive_id else None

            SummarizedTurnStart(builder)
            SummarizedTurnAddTurnId(builder, turn_id_off)
            SummarizedTurnAddTurnNumber(builder, turn.turn_number)
            SummarizedTurnAddSummary(builder, summary_off)
            SummarizedTurnAddTimestampMs(builder, turn.timestamp_ms)
            if intent_off:
                SummarizedTurnAddPrimaryIntent(builder, intent_off)
            if entity_off:
                SummarizedTurnAddPrimaryEntity(builder, entity_off)
            SummarizedTurnAddArchivedToLocalCold(builder, turn.archived_to_local_cold)
            if archive_id_off:
                SummarizedTurnAddArchiveId(builder, archive_id_off)
            summarized_offsets.append(SummarizedTurnEnd(builder))

        summarized_offsets.reverse()
        HistoryRecentSectionStartSummarizedTurnsVector(builder, len(summarized_offsets))
        for off in reversed(summarized_offsets):
            builder.PrependUOffsetTRelative(off)
        summarized_vec = builder.EndVector()

        # Build archived turn IDs
        archive_id_offsets = [builder.CreateString(tid) for tid in self._archived_turn_ids]
        HistoryRecentSectionStartArchivedTurnIdsVector(builder, len(archive_id_offsets))
        for off in reversed(archive_id_offsets):
            builder.PrependUOffsetTRelative(off)
        archived_vec = builder.EndVector()

        # Build header
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, int(time.time() * 1000))
        header_offset = SectionHeaderEnd(builder)

        # Build root
        HistoryRecentSectionStart(builder)
        HistoryRecentSectionAddHeader(builder, header_offset)
        HistoryRecentSectionAddCompressedTurns(builder, compressed_vec)
        HistoryRecentSectionAddSummarizedTurns(builder, summarized_vec)
        if summary_offset:
            HistoryRecentSectionAddSessionSummary(builder, summary_offset)
        HistoryRecentSectionAddArchivedTurnIds(builder, archived_vec)
        HistoryRecentSectionAddTotalTurnsArchived(builder, self._total_turns_archived)
        HistoryRecentSectionAddOldestCompressedTurn(builder, self.get_oldest_compressed_turn())
        HistoryRecentSectionAddNewestCompressedTurn(builder, self.get_newest_compressed_turn())
        HistoryRecentSectionAddOldestSummarizedTurn(builder, self.get_oldest_summarized_turn())
        HistoryRecentSectionAddNewestSummarizedTurn(builder, self.get_newest_summarized_turn())
        HistoryRecentSectionAddEvictionPriority(builder, self.EVICTION_PRIORITY)
        HistoryRecentSectionAddLastEvictionMs(builder, self._last_eviction_ms)
        HistoryRecentSectionAddBytesEvictedTotal(builder, self._bytes_evicted_total)
        root = HistoryRecentSectionEnd(builder)

        builder.Finish(root)
        self._fb_cache = bytes(builder.Output())
        return self._fb_cache

    @classmethod
    def from_flatbuffer(cls, data: bytes) -> "HistoryRecentSection":
        """
        Deserialize from FlatBuffer bytes.

        Args:
            data: FlatBuffer bytes

        Returns:
            HistoryRecentSection: Restored section
        """
        fb = FBHistoryRecentSection.GetRootAsHistoryRecentSection(data, 0)

        section = cls()

        # Restore session summary
        summary = fb.SessionSummary()
        if summary:
            section._session_summary = (
                summary.decode("utf-8") if isinstance(summary, bytes) else summary
            )

        # Restore metadata
        section._total_turns_archived = fb.TotalTurnsArchived()
        section._last_eviction_ms = fb.LastEvictionMs()
        section._bytes_evicted_total = fb.BytesEvictedTotal()

        # Restore compressed turns
        for i in range(fb.CompressedTurnsLength()):
            ct = fb.CompressedTurns(i)
            if ct is None:
                continue

            entities = []
            for j in range(ct.EntitiesLength()):
                e = ct.Entities(j)
                if e:
                    entities.append(e.decode("utf-8") if isinstance(e, bytes) else str(e))

            intents = []
            for j in range(ct.IntentsLength()):
                n = ct.Intents(j)
                if n:
                    intents.append(n.decode("utf-8") if isinstance(n, bytes) else str(n))

            key_phrases = []
            for j in range(ct.KeyPhrasesLength()):
                p = ct.KeyPhrases(j)
                if p:
                    key_phrases.append(p.decode("utf-8") if isinstance(p, bytes) else str(p))

            turn_id_raw = ct.TurnId()
            turn_id = (
                turn_id_raw.decode("utf-8")
                if isinstance(turn_id_raw, bytes)
                else (str(turn_id_raw) if turn_id_raw else "")
            )

            emotion_raw = ct.Emotion()
            emotion = (
                emotion_raw.decode("utf-8")
                if isinstance(emotion_raw, bytes)
                else (str(emotion_raw) if emotion_raw else "")
            )

            archive_id_raw = ct.ArchiveId()
            archive_id = (
                archive_id_raw.decode("utf-8")
                if isinstance(archive_id_raw, bytes)
                else (str(archive_id_raw) if archive_id_raw else "")
            )

            turn = CompressedTurn(
                turn_id=turn_id,
                turn_number=ct.TurnNumber(),
                entities=entities,
                intents=intents,
                key_phrases=key_phrases,
                timestamp_ms=ct.TimestampMs(),
                emotion=emotion,
                user_tokens=ct.UserTokens(),
                response_tokens=ct.ResponseTokens(),
                archived_to_local_cold=ct.ArchivedToLocalCold(),
                archive_id=archive_id,
            )
            section._compressed_turns.append(turn)

        # Restore summarized turns
        for i in range(fb.SummarizedTurnsLength()):
            st = fb.SummarizedTurns(i)
            if st is None:
                continue

            turn_id_raw = st.TurnId()
            turn_id = (
                turn_id_raw.decode("utf-8")
                if isinstance(turn_id_raw, bytes)
                else (str(turn_id_raw) if turn_id_raw else "")
            )

            summary_raw = st.Summary()
            summary = (
                summary_raw.decode("utf-8")
                if isinstance(summary_raw, bytes)
                else (str(summary_raw) if summary_raw else "")
            )

            intent_raw = st.PrimaryIntent()
            primary_intent = (
                intent_raw.decode("utf-8")
                if isinstance(intent_raw, bytes)
                else (str(intent_raw) if intent_raw else "")
            )

            entity_raw = st.PrimaryEntity()
            primary_entity = (
                entity_raw.decode("utf-8")
                if isinstance(entity_raw, bytes)
                else (str(entity_raw) if entity_raw else "")
            )

            archive_id_raw = st.ArchiveId()
            archive_id = (
                archive_id_raw.decode("utf-8")
                if isinstance(archive_id_raw, bytes)
                else (str(archive_id_raw) if archive_id_raw else "")
            )

            turn = SummarizedTurn(
                turn_id=turn_id,
                turn_number=st.TurnNumber(),
                summary=summary,
                timestamp_ms=st.TimestampMs(),
                primary_intent=primary_intent,
                primary_entity=primary_entity,
                archived_to_local_cold=st.ArchivedToLocalCold(),
                archive_id=archive_id,
            )
            section._summarized_turns.append(turn)

        # Restore archived turn IDs
        for i in range(fb.ArchivedTurnIdsLength()):
            tid = fb.ArchivedTurnIds(i)
            if tid:
                decoded = tid.decode("utf-8") if isinstance(tid, bytes) else str(tid)
                section._archived_turn_ids.append(decoded)

        return section

    # =========================================================================
    # Apply Operations (MutationGuard Pattern)
    # =========================================================================

    def apply(self, operation: str, data: Dict[str, Any]) -> Any:
        """
        Apply a mutation operation.

        Supported operations:
        - add_compressed: Add compressed turn
        - add_summarized: Add summarized turn
        - compress_to_summarized: Compress oldest to summarized
        - set_session_summary: Set session summary
        - evict_partial: Evict to free space
        - clear: Clear all data

        Args:
            operation: Operation name
            data: Operation parameters

        Returns:
            Any: Operation result
        """
        self._invalidate_cache()

        if operation == "add_compressed":
            turn = CompressedTurn(**data["turn"])
            return self.add_compressed_turn(turn)

        elif operation == "add_summarized":
            turn = SummarizedTurn(**data["turn"])
            return self.add_summarized_turn(turn)

        elif operation == "compress_to_summarized":
            return self.compress_to_summarized(count=data.get("count", 1))

        elif operation == "set_session_summary":
            return self.set_session_summary(data["summary"])

        elif operation == "evict_partial":
            return self.evict_partial(data["target_kb"])

        elif operation == "clear":
            return self.clear()

        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Utility
    # =========================================================================

    def __repr__(self) -> str:
        return (
            f"HistoryRecentSection("
            f"compressed={len(self._compressed_turns)}/{self.MAX_COMPRESSED_TURNS}, "
            f"summarized={len(self._summarized_turns)}/{self.MAX_SUMMARIZED_TURNS}, "
            f"archived={self._total_turns_archived})"
        )

    def __len__(self) -> int:
        return self.total_count()


# =============================================================================
# Factory Function
# =============================================================================


def create_history_recent_section() -> HistoryRecentSection:
    """
    Factory function to create HistoryRecentSection.

    Returns:
        HistoryRecentSection: New section instance
    """
    return HistoryRecentSection()
