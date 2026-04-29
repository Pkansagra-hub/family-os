"""
HistoryActiveSection - Last 10 Conversation Turns (HOT CORE)
=============================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.4 (history_active)

This section contains the last 10 conversation turns with full fidelity.
Used for prompt construction, continuity, and immediate context.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/history_active_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- turns: [TurnFull] - Max 10 full fidelity turns
- current_turn_number: uint16
- oldest_turn_number: uint16
- session_start_ms: int64
- last_activity_ms: int64
- total_user_tokens: uint32
- total_response_tokens: uint32
- avg_turn_duration_ms: uint32

Lifecycle: When turns exceed 10, oldest demotes to history_recent (WARM)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

import flatbuffers

# Generated FlatBuffer types
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    HistoryActiveSection as FBHistoryActiveSection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.HistoryActiveSection import (
    HistoryActiveSectionAddAvgTurnDurationMs,
    HistoryActiveSectionAddCurrentTurnNumber,
    HistoryActiveSectionAddHeader,
    HistoryActiveSectionAddLastActivityMs,
    HistoryActiveSectionAddOldestTurnNumber,
    HistoryActiveSectionAddSessionStartMs,
    HistoryActiveSectionAddTotalResponseTokens,
    HistoryActiveSectionAddTotalUserTokens,
    HistoryActiveSectionAddTurns,
    HistoryActiveSectionEnd,
    HistoryActiveSectionStart,
    HistoryActiveSectionStartTurnsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.TurnFull import (
    TurnFullAddAssistantResponse,
    TurnFullAddDurationMs,
    TurnFullAddEmotion,
    TurnFullAddEntities,
    TurnFullAddIntents,
    TurnFullAddMetadata,
    TurnFullAddResponseBytes,
    TurnFullAddTimestampMs,
    TurnFullAddTurnId,
    TurnFullAddTurnNumber,
    TurnFullAddUserMessage,
    TurnFullAddUserMessageBytes,
    TurnFullEnd,
    TurnFullStart,
    TurnFullStartEntitiesVector,
    TurnFullStartIntentsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.TurnMetadata import (
    TurnMetadataAddConfidence,
    TurnMetadataAddEmotion,
    TurnMetadataAddEntities,
    TurnMetadataAddIntent,
    TurnMetadataAddProcessingTimeMs,
    TurnMetadataEnd,
    TurnMetadataStart,
    TurnMetadataStartEntitiesVector,
)

# =============================================================================
# Data Classes matching FlatBuffer schema
# =============================================================================


@dataclass
class TurnMetadata:
    """
    Metadata for a conversation turn.

    Maps to TurnMetadata table in common.fbs:
    - intent: string
    - entities: [string]
    - emotion: string
    - confidence: float = 1.0
    - processing_time_ms: uint32
    """

    intent: str = ""
    entities: List[str] = field(default_factory=list)
    emotion: str = ""
    confidence: float = 1.0
    processing_time_ms: int = 0


@dataclass
class TypedHistoryEntry:
    """Extended history entry for dual-LLM architecture.

    Wraps the existing Turn schema with additional type discrimination.

    Entry types and their sources:
      user           -- User's raw input. Source: "user".
      ack            -- Front's acknowledgment (Phase A). Source: "front".
      final          -- Front's final response. Source: "front".
      weave          -- Front's async result presentation. Source: "front".
      clarification  -- Front asking user to clarify. Source: "front".
      hitl_request   -- Front presenting HITL question. Source: "front".
      hitl_response  -- User's answer to HITL question. Source: "user".
      error          -- Front's error explanation. Source: "front".
      proactive      -- ProactiveAgent fill message during wait. Source: "system".
    """

    turn_number: int
    entry_type: Literal[
        "user",
        "ack",
        "final",
        "weave",
        "clarification",
        "hitl_request",
        "hitl_response",
        "error",
        "proactive",
    ]
    text: str
    timestamp_ms: int
    source: Literal["user", "front", "back", "system"]
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Valid (entry_type, source) combinations enforced at construction
_VALID_TYPE_SOURCE = frozenset(
    {
        ("user", "user"),
        ("ack", "front"),
        ("final", "front"),
        ("weave", "front"),
        ("clarification", "front"),
        ("hitl_request", "front"),
        ("hitl_response", "user"),
        ("error", "front"),
        ("proactive", "system"),
    }
)


@dataclass
class Turn:
    """
    Full fidelity conversation turn.

    Maps to TurnFull table in history_active_section.fbs:
    - turn_id: string (required)
    - turn_number: uint16
    - user_message: string (required)
    - assistant_response: string (required)
    - timestamp_ms: int64
    - duration_ms: uint32
    - metadata: TurnMetadata
    - entities: [string]
    - intents: [string]
    - emotion: string
    - user_message_bytes: uint32
    - response_bytes: uint32
    """

    turn_id: str
    turn_number: int
    user_message: str
    assistant_response: str
    timestamp_ms: int = 0
    duration_ms: int = 0
    metadata: Optional[TurnMetadata] = None
    entities: List[str] = field(default_factory=list)
    intents: List[str] = field(default_factory=list)
    emotion: str = ""

    # Sub-entries for dual-LLM decomposition (POC extension)
    # Stores intermediate entries: ack, weave, hitl_request, hitl_response, error, proactive
    # If empty, get_typed_entries() creates a single "final" entry from assistant_response
    sub_entries: List[TypedHistoryEntry] = field(default_factory=list)

    # Computed fields
    user_message_bytes: int = 0
    response_bytes: int = 0

    def __post_init__(self):
        """Compute byte sizes if not provided."""
        if self.user_message_bytes == 0 and self.user_message:
            self.user_message_bytes = len(self.user_message.encode("utf-8"))
        if self.response_bytes == 0 and self.assistant_response:
            self.response_bytes = len(self.assistant_response.encode("utf-8"))

    @property
    def user_tokens(self) -> int:
        """Approximate user message token count (chars / 4)."""
        return max(1, len(self.user_message) // 4) if self.user_message else 0

    @property
    def response_tokens(self) -> int:
        """Approximate assistant response token count (chars / 4)."""
        return max(1, len(self.assistant_response) // 4) if self.assistant_response else 0


# =============================================================================
# HistoryActiveSection Implementation
# =============================================================================


class HistoryActiveSection:
    """
    History Active Section - last 10 turns with full fidelity.

    This section contains the most recent conversation turns with complete
    user messages and assistant responses preserved (no compression).

    Budget: 8KB (8192 bytes)
    Tier: HOT CORE
    Max Turns: 10
    Eviction: Section stays, items demote to history_recent

    FlatBuffer Schema: history_active_section.fbs
    Serialization Target: <100 microseconds

    Contents per schema:
    - turns: [TurnFull] - Max 10 full fidelity turns
    - current_turn_number: uint16 - Latest turn number
    - oldest_turn_number: uint16 - Oldest turn in section
    - session_start_ms: int64 - Session start time
    - last_activity_ms: int64 - Last activity time
    - total_user_tokens: uint32 - Cumulative user tokens
    - total_response_tokens: uint32 - Cumulative response tokens
    - avg_turn_duration_ms: uint32 - Average turn processing time

    Example:
        section = HistoryActiveSection(session_id="sess-123")

        # Add a complete turn
        turn = section.add_turn(
            user_message="What's the weather?",
            assistant_response="Let me check the weather for you...",
        )

        # Get recent turns for prompt
        recent = section.get_recent(5)

        # Serialize for persistence
        data = section.to_flatbuffer()
    """

    BUDGET_BYTES = 16384  # 16KB (increased for longer context)
    TIER = "hot"
    CAN_EVICT = False  # Section stays, items demote
    SECTION_NAME = "history_active"
    SCHEMA_VERSION = "1.0.0"
    MAX_TURNS = 25  # Increased from 10 to support longer conversations

    def __init__(
        self,
        session_id: str = "",
        schema_version: str = "",
    ) -> None:
        """
        Initialize HistoryActiveSection.

        Args:
            session_id: Session UUID (generated if empty)
            schema_version: Schema version (uses default if empty)
        """
        now_ms = int(time.time() * 1000)

        self._session_id = session_id or str(uuid.uuid4())
        self._schema_version = schema_version or self.SCHEMA_VERSION
        self._session_start_ms = now_ms
        self._last_activity_ms = now_ms
        self._last_updated_ms = now_ms

        # Core state per schema
        self._turns: List[Turn] = []
        self._next_turn_number = 1

        # Aggregates per schema
        self._total_user_tokens = 0
        self._total_response_tokens = 0
        self._total_duration_ms = 0

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
    def session_start_ms(self) -> int:
        """Session start timestamp in milliseconds."""
        return self._session_start_ms

    @property
    def last_activity_ms(self) -> int:
        """Last activity timestamp in milliseconds."""
        return self._last_activity_ms

    @property
    def last_updated_ms(self) -> int:
        """Last update timestamp in milliseconds."""
        return self._last_updated_ms

    @property
    def schema_version(self) -> str:
        """Schema version string."""
        return self._schema_version

    @property
    def current_turn_number(self) -> int:
        """Current (latest) turn number."""
        if self._turns:
            return self._turns[-1].turn_number
        return 0

    @property
    def oldest_turn_number(self) -> int:
        """Oldest turn number in section."""
        if self._turns:
            return self._turns[0].turn_number
        return 0

    @property
    def total_user_tokens(self) -> int:
        """Total user tokens across all turns."""
        return self._total_user_tokens

    @property
    def total_response_tokens(self) -> int:
        """Total response tokens across all turns."""
        return self._total_response_tokens

    @property
    def avg_turn_duration_ms(self) -> int:
        """Average turn duration in milliseconds."""
        if not self._turns:
            return 0
        return self._total_duration_ms // len(self._turns)

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
        - Turn: ~800 bytes each x 10 turns = 8KB max
        - Aggregates: ~50 bytes
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 100  # Header overhead
        for turn in self._turns:
            size += 50  # turn_id, turn_number overhead
            size += turn.user_message_bytes
            size += turn.response_bytes
            size += 50  # metadata, timestamps
            size += len(turn.entities) * 30  # entities
            size += len(turn.intents) * 20  # intents
        size += 50  # Aggregates (tokens, duration, etc.)

        return min(size, self.BUDGET_BYTES)

    def clear(self) -> None:
        """Clear all section data."""
        self._turns.clear()
        self._next_turn_number = 1
        self._total_user_tokens = 0
        self._total_response_tokens = 0
        self._total_duration_ms = 0
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
            "schema_version": self._schema_version,
            "turn_count": len(self._turns),
            "max_turns": self.MAX_TURNS,
            "current_turn_number": self.current_turn_number,
            "oldest_turn_number": self.oldest_turn_number,
            "total_user_tokens": self._total_user_tokens,
            "total_response_tokens": self._total_response_tokens,
            "avg_turn_duration_ms": self.avg_turn_duration_ms,
            "session_start_ms": self._session_start_ms,
            "last_activity_ms": self._last_activity_ms,
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Turn Management
    # =========================================================================

    def add_turn(
        self,
        user_message: str,
        assistant_response: str,
        turn_id: str = "",
        timestamp_ms: int = 0,
        duration_ms: int = 0,
        metadata: Optional[TurnMetadata] = None,
        entities: Optional[List[str]] = None,
        intents: Optional[List[str]] = None,
        emotion: str = "",
    ) -> Turn:
        """
        Add a new complete turn.

        Args:
            user_message: Full user message text (required)
            assistant_response: Full assistant response text (required)
            turn_id: Optional turn UUID (generated if empty)
            timestamp_ms: Turn timestamp (uses current time if 0)
            duration_ms: Turn processing duration
            metadata: Optional turn metadata
            entities: Extracted entities
            intents: Classified intents
            emotion: Detected emotion

        Returns:
            Created Turn object

        Note:
            If MAX_TURNS is exceeded, oldest turn is automatically demoted.
            Use get_overflow() to retrieve demoted turns.
        """
        now_ms = int(time.time() * 1000)

        turn = Turn(
            turn_id=turn_id or str(uuid.uuid4()),
            turn_number=self._next_turn_number,
            user_message=user_message,
            assistant_response=assistant_response,
            timestamp_ms=timestamp_ms or now_ms,
            duration_ms=duration_ms,
            metadata=metadata,
            entities=entities or [],
            intents=intents or [],
            emotion=emotion,
        )

        self._turns.append(turn)
        self._next_turn_number += 1

        # Update aggregates
        self._total_user_tokens += turn.user_tokens
        self._total_response_tokens += turn.response_tokens
        self._total_duration_ms += duration_ms

        self._last_activity_ms = now_ms
        self._invalidate_cache()
        self._touch()

        return turn

    # =========================================================================
    # TypedHistoryEntry API (Epic 2.4)
    # =========================================================================

    def get_typed_entries(self, count: int = 20) -> List[TypedHistoryEntry]:
        """Return last N typed entries, decomposed from Turn objects.

        Each Turn object is decomposed into multiple TypedHistoryEntry objects:
        1. Always: a "user" entry from turn.user_message
        2. If turn has sub_entries: include them (ack, weave, hitl_*, etc.)
        3. Otherwise: a "final" entry from turn.assistant_response

        Args:
            count: Maximum number of entries to return (default 20 for Front,
                   use 5 for Back via history_to_back_context).

        Returns:
            List of TypedHistoryEntry ordered by timestamp_ms, last N entries.

        Note:
            Internal storage still uses Turn objects (for FlatBuffer compat).
            This API provides the TypedHistoryEntry view for LLM context builders.
        """
        entries: List[TypedHistoryEntry] = []
        for turn in self._turns:
            # User input entry
            meta: Dict[str, Any] = {}
            if turn.intents:
                meta["intent"] = turn.intents
            if turn.emotion:
                meta["emotion"] = turn.emotion
            entries.append(
                TypedHistoryEntry(
                    turn_number=turn.turn_number,
                    entry_type="user",
                    text=turn.user_message,
                    timestamp_ms=turn.timestamp_ms,
                    source="user",
                    metadata=meta,
                )
            )
            # Sub-entries if present (POC dual-LLM extension)
            if turn.sub_entries:
                entries.extend(turn.sub_entries)
            else:
                # Default: assistant_response = "final" entry
                entries.append(
                    TypedHistoryEntry(
                        turn_number=turn.turn_number,
                        entry_type="final",
                        text=turn.assistant_response,
                        timestamp_ms=turn.timestamp_ms + turn.duration_ms,
                        source="front",
                    )
                )
        return entries[-count:]

    def get_turn(self, turn_id: str) -> Optional[Turn]:
        """
        Get turn by ID.

        Args:
            turn_id: Turn UUID

        Returns:
            Turn or None
        """
        for turn in self._turns:
            if turn.turn_id == turn_id:
                return turn
        return None

    def get_by_number(self, turn_number: int) -> Optional[Turn]:
        """
        Get turn by number.

        Args:
            turn_number: Sequential turn number

        Returns:
            Turn or None
        """
        for turn in self._turns:
            if turn.turn_number == turn_number:
                return turn
        return None

    def get_recent(self, n: int) -> List[Turn]:
        """
        Get last N turns.

        Args:
            n: Number of turns to retrieve

        Returns:
            List[Turn]: Last N turns, oldest first
        """
        return self._turns[-n:] if n > 0 else []

    def get_all(self) -> List[Turn]:
        """
        Get all turns.

        Returns:
            List[Turn]: All turns, oldest first
        """
        return list(self._turns)

    def count(self) -> int:
        """
        Get turn count.

        Returns:
            int: Number of turns
        """
        return len(self._turns)

    def is_full(self) -> bool:
        """
        Check if section is at max capacity.

        Returns:
            bool: True if MAX_TURNS reached
        """
        return len(self._turns) >= self.MAX_TURNS

    def has_overflow(self) -> bool:
        """
        Check if there are turns that need demotion.

        Returns:
            bool: True if turn count exceeds MAX_TURNS
        """
        return len(self._turns) > self.MAX_TURNS

    def get_overflow(self) -> List[Turn]:
        """
        Get and remove overflow turns for demotion to WARM.

        Returns:
            List[Turn]: Turns exceeding MAX_TURNS limit
        """
        if len(self._turns) <= self.MAX_TURNS:
            return []

        overflow_count = len(self._turns) - self.MAX_TURNS
        overflow = self._turns[:overflow_count]
        self._turns = self._turns[overflow_count:]

        # Update aggregates (subtract demoted turns)
        for turn in overflow:
            self._total_user_tokens -= turn.user_tokens
            self._total_response_tokens -= turn.response_tokens
            self._total_duration_ms -= turn.duration_ms

        self._invalidate_cache()
        self._touch()
        return overflow

    def demote_oldest(self, count: int = 1) -> List[Turn]:
        """
        Remove and return oldest turns for demotion to WARM.

        Args:
            count: Number of turns to demote

        Returns:
            List[Turn]: Demoted turns
        """
        count = min(count, len(self._turns))
        if count <= 0:
            return []

        demoted = self._turns[:count]
        self._turns = self._turns[count:]

        # Update aggregates
        for turn in demoted:
            self._total_user_tokens -= turn.user_tokens
            self._total_response_tokens -= turn.response_tokens
            self._total_duration_ms -= turn.duration_ms

        self._invalidate_cache()
        self._touch()
        return demoted

    def remove_turn(self, turn_id: str) -> bool:
        """
        Remove a turn by ID.

        Args:
            turn_id: Turn UUID

        Returns:
            bool: True if removed
        """
        for i, turn in enumerate(self._turns):
            if turn.turn_id == turn_id:
                removed = self._turns.pop(i)
                # Update aggregates
                self._total_user_tokens -= removed.user_tokens
                self._total_response_tokens -= removed.response_tokens
                self._total_duration_ms -= removed.duration_ms
                self._invalidate_cache()
                self._touch()
                return True
        return False

    # =========================================================================
    # Capacity Management
    # =========================================================================

    def should_demote(self) -> bool:
        """
        Check if section needs demotion.

        Returns:
            bool: True if at or over 90% of budget or MAX_TURNS
        """
        size_pressure = self.get_size_bytes() >= self.BUDGET_BYTES * 0.9
        count_pressure = len(self._turns) >= self.MAX_TURNS
        return size_pressure or count_pressure

    def get_available_capacity(self) -> int:
        """
        Get available capacity in turns.

        Returns:
            int: Number of turns that can be added
        """
        return max(0, self.MAX_TURNS - len(self._turns))

    def get_pressure(self) -> float:
        """
        Get memory pressure as percentage.

        Returns:
            float: Pressure 0.0-1.0
        """
        size_pressure = self.get_size_bytes() / self.BUDGET_BYTES
        count_pressure = len(self._turns) / self.MAX_TURNS
        return max(size_pressure, count_pressure)

    # =========================================================================
    # Dict Serialization (for SessionReadAdapter / Memory Writer)
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Return section as a plain dict for snapshot reads.

        Consumed by ``SessionReadAdapter._section_to_dict``. Without this,
        ``history_active`` is silently dropped from MW snapshots and
        ``recent_turns`` is always empty.

        Returns full Turn fidelity including ``assistant_response``, intents,
        entities, and emotion. Tool call metadata (when present on a Turn)
        is preserved under each turn's ``metadata`` key so the existing
        ``ContextBuilder._extract_tool_calls_from_turn`` keeps working.
        """

        def _turn_to_dict(t: Turn) -> Dict[str, Any]:
            d: Dict[str, Any] = {
                "turn_id": t.turn_id,
                "turn_number": t.turn_number,
                "user_message": t.user_message,
                "assistant_response": t.assistant_response,
                "timestamp_ms": t.timestamp_ms,
                "duration_ms": t.duration_ms,
                "entities": list(t.entities),
                "intents": list(t.intents),
                "emotion": t.emotion,
            }
            if t.metadata is not None:
                meta = t.metadata
                d["metadata"] = {
                    "intent": getattr(meta, "intent", ""),
                    "entities": list(getattr(meta, "entities", [])),
                    "emotion": getattr(meta, "emotion", ""),
                    "confidence": float(getattr(meta, "confidence", 0.0)),
                    "processing_time_ms": int(getattr(meta, "processing_time_ms", 0)),
                }
            return d

        return {
            "turns": [_turn_to_dict(t) for t in self._turns],
            "current_turn_number": self.current_turn_number,
            "oldest_turn_number": self.oldest_turn_number,
            "session_start_ms": self._session_start_ms,
            "last_activity_ms": self._last_activity_ms,
            "total_user_tokens": self._total_user_tokens,
            "total_response_tokens": self._total_response_tokens,
            "turn_count": len(self._turns),
            "max_turns": self.MAX_TURNS,
        }

    # =========================================================================
    # FlatBuffer Serialization
    # =========================================================================

    def to_flatbuffer(self) -> bytes:
        """
        Serialize section to FlatBuffer bytes.

        Returns:
            bytes: FlatBuffer-encoded data per history_active_section.fbs

        Performance Target: <100 microseconds
        """
        if self._cache_valid and self._cached_bytes:
            return self._cached_bytes

        builder = flatbuffers.Builder(self.BUDGET_BYTES)

        # Build nested objects first (FlatBuffers requirement)

        # 1. Build section name for header
        section_name_offset = builder.CreateString(self.SECTION_NAME)

        # 2. Build turns vector
        turn_offsets = []
        for turn in self._turns:
            # Build turn strings
            turn_id_off = builder.CreateString(turn.turn_id)
            user_msg_off = builder.CreateString(turn.user_message)
            response_off = builder.CreateString(turn.assistant_response)
            emotion_off = builder.CreateString(turn.emotion) if turn.emotion else 0

            # Build entities vector
            if turn.entities:
                entity_offsets = [builder.CreateString(e) for e in turn.entities]
                TurnFullStartEntitiesVector(builder, len(entity_offsets))
                for off in reversed(entity_offsets):
                    builder.PrependUOffsetTRelative(off)
                entities_vector = builder.EndVector()
            else:
                entities_vector = 0

            # Build intents vector
            if turn.intents:
                intent_offsets = [builder.CreateString(i) for i in turn.intents]
                TurnFullStartIntentsVector(builder, len(intent_offsets))
                for off in reversed(intent_offsets):
                    builder.PrependUOffsetTRelative(off)
                intents_vector = builder.EndVector()
            else:
                intents_vector = 0

            # Build metadata if present
            metadata_offset = 0
            if turn.metadata:
                intent_off = (
                    builder.CreateString(turn.metadata.intent) if turn.metadata.intent else 0
                )
                emotion_meta_off = (
                    builder.CreateString(turn.metadata.emotion) if turn.metadata.emotion else 0
                )

                if turn.metadata.entities:
                    meta_entity_offsets = [builder.CreateString(e) for e in turn.metadata.entities]
                    TurnMetadataStartEntitiesVector(builder, len(meta_entity_offsets))
                    for off in reversed(meta_entity_offsets):
                        builder.PrependUOffsetTRelative(off)
                    meta_entities_vector = builder.EndVector()
                else:
                    meta_entities_vector = 0

                TurnMetadataStart(builder)
                if intent_off:
                    TurnMetadataAddIntent(builder, intent_off)
                if meta_entities_vector:
                    TurnMetadataAddEntities(builder, meta_entities_vector)
                if emotion_meta_off:
                    TurnMetadataAddEmotion(builder, emotion_meta_off)
                TurnMetadataAddConfidence(builder, turn.metadata.confidence)
                TurnMetadataAddProcessingTimeMs(builder, turn.metadata.processing_time_ms)
                metadata_offset = TurnMetadataEnd(builder)

            # Build TurnFull
            TurnFullStart(builder)
            TurnFullAddTurnId(builder, turn_id_off)
            TurnFullAddTurnNumber(builder, turn.turn_number)
            TurnFullAddUserMessage(builder, user_msg_off)
            TurnFullAddAssistantResponse(builder, response_off)
            TurnFullAddTimestampMs(builder, turn.timestamp_ms)
            TurnFullAddDurationMs(builder, turn.duration_ms)
            if metadata_offset:
                TurnFullAddMetadata(builder, metadata_offset)
            if entities_vector:
                TurnFullAddEntities(builder, entities_vector)
            if intents_vector:
                TurnFullAddIntents(builder, intents_vector)
            if emotion_off:
                TurnFullAddEmotion(builder, emotion_off)
            TurnFullAddUserMessageBytes(builder, turn.user_message_bytes)
            TurnFullAddResponseBytes(builder, turn.response_bytes)
            turn_offsets.append(TurnFullEnd(builder))

        # Build turns vector
        if turn_offsets:
            HistoryActiveSectionStartTurnsVector(builder, len(turn_offsets))
            for offset in reversed(turn_offsets):
                builder.PrependUOffsetTRelative(offset)
            turns_vector = builder.EndVector()
        else:
            turns_vector = 0

        # 3. Build header
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # 4. Build HistoryActiveSection root
        HistoryActiveSectionStart(builder)
        HistoryActiveSectionAddHeader(builder, header_offset)
        if turns_vector:
            HistoryActiveSectionAddTurns(builder, turns_vector)
        HistoryActiveSectionAddCurrentTurnNumber(builder, self.current_turn_number)
        HistoryActiveSectionAddOldestTurnNumber(builder, self.oldest_turn_number)
        HistoryActiveSectionAddSessionStartMs(builder, self._session_start_ms)
        HistoryActiveSectionAddLastActivityMs(builder, self._last_activity_ms)
        HistoryActiveSectionAddTotalUserTokens(builder, self._total_user_tokens)
        HistoryActiveSectionAddTotalResponseTokens(builder, self._total_response_tokens)
        HistoryActiveSectionAddAvgTurnDurationMs(builder, self.avg_turn_duration_ms)
        section_offset = HistoryActiveSectionEnd(builder)

        builder.Finish(section_offset)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize section from FlatBuffer bytes.

        Args:
            data: FlatBuffer-encoded data per history_active_section.fbs
        """
        fb = FBHistoryActiveSection.GetRootAsHistoryActiveSection(data, 0)

        # Clear current state
        self._turns.clear()
        self._total_user_tokens = 0
        self._total_response_tokens = 0
        self._total_duration_ms = 0

        # Load session timing
        self._session_start_ms = fb.SessionStartMs()
        self._last_activity_ms = fb.LastActivityMs()

        # Load turns
        max_turn_number = 0
        for i in range(fb.TurnsLength()):
            turn_fb = fb.Turns(i)
            if turn_fb:
                turn_id = self._decode_string(turn_fb.TurnId())
                turn_number = turn_fb.TurnNumber()
                max_turn_number = max(max_turn_number, turn_number)

                # Load metadata
                metadata = None
                meta_fb = turn_fb.Metadata()
                if meta_fb:
                    meta_entities = []
                    for j in range(meta_fb.EntitiesLength()):
                        ent = self._decode_string(meta_fb.Entities(j))
                        if ent:
                            meta_entities.append(ent)
                    metadata = TurnMetadata(
                        intent=self._decode_string(meta_fb.Intent()) or "",
                        entities=meta_entities,
                        emotion=self._decode_string(meta_fb.Emotion()) or "",
                        confidence=meta_fb.Confidence(),
                        processing_time_ms=meta_fb.ProcessingTimeMs(),
                    )

                # Load entities
                entities = []
                for j in range(turn_fb.EntitiesLength()):
                    ent = self._decode_string(turn_fb.Entities(j))
                    if ent:
                        entities.append(ent)

                # Load intents
                intents = []
                for j in range(turn_fb.IntentsLength()):
                    intent = self._decode_string(turn_fb.Intents(j))
                    if intent:
                        intents.append(intent)

                turn = Turn(
                    turn_id=turn_id or str(uuid.uuid4()),
                    turn_number=turn_number,
                    user_message=self._decode_string(turn_fb.UserMessage()) or "",
                    assistant_response=self._decode_string(turn_fb.AssistantResponse()) or "",
                    timestamp_ms=turn_fb.TimestampMs(),
                    duration_ms=turn_fb.DurationMs(),
                    metadata=metadata,
                    entities=entities,
                    intents=intents,
                    emotion=self._decode_string(turn_fb.Emotion()) or "",
                    user_message_bytes=turn_fb.UserMessageBytes(),
                    response_bytes=turn_fb.ResponseBytes(),
                )
                self._turns.append(turn)

                # Update aggregates
                self._total_user_tokens += turn.user_tokens
                self._total_response_tokens += turn.response_tokens
                self._total_duration_ms += turn.duration_ms

        # Set next turn number
        self._next_turn_number = max_turn_number + 1 if max_turn_number > 0 else 1

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

    def get(self, turn_id: str) -> Optional[Turn]:
        """Legacy alias for get_turn."""
        return self.get_turn(turn_id)

    def append(
        self,
        user_message: str,
        assistant_response: str,
        **kwargs,
    ) -> Turn:
        """Legacy alias for add_turn."""
        return self.add_turn(user_message, assistant_response, **kwargs)

    def touch(self) -> None:
        """Update last_updated_ms timestamp (legacy API)."""
        self._touch()

    # =========================================================================
    # Search & Query
    # =========================================================================

    def find_turns_by_entity(self, entity_id: str) -> List[Turn]:
        """
        Find turns mentioning a specific entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List[Turn]: Turns mentioning the entity
        """
        return [turn for turn in self._turns if entity_id in turn.entities]

    def find_turns_by_intent(self, intent: str) -> List[Turn]:
        """
        Find turns with a specific intent.

        Args:
            intent: Intent identifier

        Returns:
            List[Turn]: Turns with the intent
        """
        return [turn for turn in self._turns if intent in turn.intents]

    def find_turns_by_emotion(self, emotion: str) -> List[Turn]:
        """
        Find turns with a specific emotion.

        Args:
            emotion: Emotion identifier

        Returns:
            List[Turn]: Turns with the emotion
        """
        return [turn for turn in self._turns if turn.emotion == emotion]

    def search_messages(
        self,
        query: str,
        include_user: bool = True,
        include_assistant: bool = True,
    ) -> List[Turn]:
        """
        Search turns for text content.

        Args:
            query: Search string (case-insensitive)
            include_user: Search user messages
            include_assistant: Search assistant responses

        Returns:
            List[Turn]: Matching turns
        """
        query_lower = query.lower()
        results = []
        for turn in self._turns:
            if include_user and query_lower in turn.user_message.lower():
                results.append(turn)
            elif include_assistant and query_lower in turn.assistant_response.lower():
                results.append(turn)
        return results

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive section statistics.

        Returns:
            Dict with stats about turns, tokens, timing, etc.
        """
        if not self._turns:
            return {
                "turn_count": 0,
                "total_user_tokens": 0,
                "total_response_tokens": 0,
                "avg_user_tokens": 0,
                "avg_response_tokens": 0,
                "avg_turn_duration_ms": 0,
                "size_bytes": self.get_size_bytes(),
                "pressure": 0.0,
            }

        return {
            "turn_count": len(self._turns),
            "total_user_tokens": self._total_user_tokens,
            "total_response_tokens": self._total_response_tokens,
            "avg_user_tokens": self._total_user_tokens // len(self._turns),
            "avg_response_tokens": self._total_response_tokens // len(self._turns),
            "avg_turn_duration_ms": self.avg_turn_duration_ms,
            "oldest_turn": self.oldest_turn_number,
            "newest_turn": self.current_turn_number,
            "size_bytes": self.get_size_bytes(),
            "pressure": self.get_pressure(),
            "unique_entities": len(set(e for t in self._turns for e in t.entities)),
            "unique_intents": len(set(i for t in self._turns for i in t.intents)),
            "emotions": list(set(t.emotion for t in self._turns if t.emotion)),
        }

    def format_for_prompt(
        self,
        n: int = 5,
        include_metadata: bool = False,
    ) -> str:
        """
        Format recent turns for LLM prompt injection.

        Args:
            n: Number of recent turns
            include_metadata: Include entities/intents/emotion

        Returns:
            Formatted string for prompt
        """
        turns = self.get_recent(n)
        lines = []
        for turn in turns:
            lines.append(f"User: {turn.user_message}")
            lines.append(f"Assistant: {turn.assistant_response}")
            if include_metadata:
                if turn.entities:
                    lines.append(f"  [Entities: {', '.join(turn.entities)}]")
                if turn.intents:
                    lines.append(f"  [Intents: {', '.join(turn.intents)}]")
                if turn.emotion:
                    lines.append(f"  [Emotion: {turn.emotion}]")
            lines.append("")
        return "\n".join(lines)

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


# =============================================================================
# TypedHistoryEntry Converters (Epic 2.4.3, 2.4.4)
# =============================================================================


def history_to_front_messages(entries: List[TypedHistoryEntry]) -> List[Dict[str, str]]:
    """Convert typed history to LLM message format for Front.

    Front sees a continuous conversation. The type discrimination is invisible
    to the LLM -- it just sees alternating user/assistant messages.

    Mapping:
        entry_type "user" or "hitl_response"  -> {"role": "user", "content": text}
        entry_type in ("ack", "final", "weave", "clarification",
                       "hitl_request", "error", "proactive")  -> {"role": "assistant", "content": text}

    Args:
        entries: List of TypedHistoryEntry (typically from get_typed_entries(20))

    Returns:
        List of {"role": "user"|"assistant", "content": str} dicts.
        Last 20 entries used. Ready for LLM messages array.
    """
    messages: List[Dict[str, str]] = []
    for entry in entries[-20:]:
        if entry.entry_type in ("user", "hitl_response"):
            messages.append({"role": "user", "content": entry.text})
        elif entry.entry_type in (
            "ack",
            "final",
            "weave",
            "clarification",
            "hitl_request",
            "error",
            "proactive",
        ):
            messages.append({"role": "assistant", "content": entry.text})
    return messages


def history_to_back_context(entries: List[TypedHistoryEntry]) -> List[Dict[str, Any]]:
    """Convert typed history to context for Back. Filtered and condensed.

    Back only needs decision-relevant messages:
    - "user": what the user said
    - "final": what was concluded
    - "hitl_response": what the user chose

    Back does NOT need: ack text, weave bridges, proactive fills, error explanations.

    Args:
        entries: List of TypedHistoryEntry (typically from get_typed_entries(20))

    Returns:
        List of {"turn": int, "type": str, "text": str} dicts.
        Last 5 relevant entries. Text truncated to 500 chars.
    """
    relevant_types = {"user", "final", "hitl_response"}
    filtered = [e for e in entries if e.entry_type in relevant_types]
    return [
        {"turn": e.turn_number, "type": e.entry_type, "text": e.text[:500]} for e in filtered[-5:]
    ]
