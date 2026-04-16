"""
MigrationEngine - HOT <-> WARM Demote/Promote
=============================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.4

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0017g: Single-Writer Concurrency Pattern
- ADR-0018 series: 3-Tier Eviction Strategy

DEPENDENCIES:
- SizeTracker (for capacity checks)
- MutationGuard (for section locking during migration)

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Migrate data between HOT and WARM tiers.
    - Demote: HOT -> WARM (when HOT pressure high or turn completes)
    - Promote: WARM -> HOT (when section needed for active context)

MIGRATION PAIRS:
    HOT                 -> WARM
    beliefs_active      -> beliefs_history
    history_active      -> history_recent
    narrative_active    -> narrative_active (WARM has history)

TRIGGER CONDITIONS:
    Demote triggers:
    - HOT pressure > 90% (ELEVATED)
    - Turn completion (beliefs_active -> beliefs_history)
    - history_active full (10 turns max -> compress to history_recent)

    Promote triggers:
    - Context switch needs old beliefs
    - Narrative thread resumption

NEVER MIGRATE:
    - control section (NEVER EVICT, stays in HOT)
    - meta section (NEVER EVICT, stays in HOT)

==============================================================================
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol

from .config import SessionStateConfig
from .sizetracker import (
    ALL_SECTIONS,
    HOT_SECTIONS,
    HOT_SIZE_LIMIT_BYTES,
    NEVER_EVICT_SECTIONS,
    WARM_SECTIONS,
    PressureLevel,
    SizeTracker,
)

if TYPE_CHECKING:
    from .guard import MutationGuard

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS (config-backed: sessionstate.migration.*)
# =============================================================================

# Maximum turns in history_active before demotion
MAX_HISTORY_ACTIVE_TURNS: int = 10  # config: sessionstate.migration.max_history_active_turns

# Compression threshold (turns 11-30 are compressed)
COMPRESSION_TURN_THRESHOLD: int = 30  # config: sessionstate.migration.compression_turn_threshold

# Target HOT utilization after pressure demotion
TARGET_HOT_UTILIZATION: float = 0.70  # config: sessionstate.migration.target_hot_utilization

# Minimum bytes to demote per pass
MIN_DEMOTE_BYTES: int = 1024  # config: sessionstate.migration.min_demote_bytes

# Maximum demote iterations
MAX_DEMOTE_ITERATIONS: int = 10  # config: sessionstate.migration.max_demote_iterations


class MigrationDirection(str, Enum):
    """Direction of migration."""

    DEMOTE = "demote"  # HOT -> WARM
    PROMOTE = "promote"  # WARM -> HOT


class MigrationTrigger(str, Enum):
    """What triggered the migration."""

    PRESSURE = "pressure"  # HOT pressure > 90%
    TURN_COMPLETE = "turn_complete"  # End of turn
    HISTORY_OVERFLOW = "history_overflow"  # history_active > 10 turns
    CONTEXT_SWITCH = "context_switch"  # Need old beliefs
    THREAD_RESUME = "thread_resume"  # Narrative thread resumption
    MANUAL = "manual"  # Explicit call


# Migration pairs: HOT section -> WARM section
MIGRATION_PAIRS: Dict[str, str] = {
    "beliefs_active": "beliefs_history",
    "history_active": "history_recent",
    # narrative_active: No direct pair, stays in HOT or manual archive
}

# Reverse pairs: WARM section -> HOT section (for promote)
REVERSE_MIGRATION_PAIRS: Dict[str, str] = {v: k for k, v in MIGRATION_PAIRS.items()}

# Demotion priority (lower = demote first)
DEMOTE_PRIORITY: Dict[str, int] = {
    "history_active": 1,  # Oldest turns first
    "beliefs_active": 2,  # Previous turn facts
    "narrative_active": 3,  # Paused threads
}


@dataclass
class MigrationItem:
    """
    An item being migrated.

    Attributes:
        section: Source section name
        key: Item identifier within section (turn_id, fact_id, etc.)
        data: The data being migrated
        size_bytes: Size in bytes
        metadata: Additional item metadata
    """

    section: str
    key: str
    data: Any
    size_bytes: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"MigrationItem(section='{self.section}', key='{self.key}', "
            f"size={self.size_bytes}B)"
        )


@dataclass
class CompressedTurn:
    """
    A compressed turn for history_recent (turns 11-30).

    Compression extracts:
    - Entity references
    - Intent classifications
    - Key phrases

    Full text is dropped.
    """

    turn_id: str
    timestamp_ms: int
    entities: List[str]
    intents: List[str]
    key_phrases: List[str]
    user_summary: str  # First 100 chars of user message
    assistant_summary: str  # First 100 chars of assistant response

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "turn_id": self.turn_id,
            "timestamp_ms": self.timestamp_ms,
            "entities": self.entities,
            "intents": self.intents,
            "key_phrases": self.key_phrases,
            "user_summary": self.user_summary,
            "assistant_summary": self.assistant_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompressedTurn":
        """Create from dictionary."""
        return cls(
            turn_id=data.get("turn_id", ""),
            timestamp_ms=data.get("timestamp_ms", 0),
            entities=data.get("entities", []),
            intents=data.get("intents", []),
            key_phrases=data.get("key_phrases", []),
            user_summary=data.get("user_summary", ""),
            assistant_summary=data.get("assistant_summary", ""),
        )


@dataclass
class SummarizedTurn:
    """
    A summarized turn for history_recent (turns 31-40).

    Minimal representation: just ID, timestamp, and single-sentence summary.
    """

    turn_id: str
    timestamp_ms: int
    summary: str  # Single sentence summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "turn_id": self.turn_id,
            "timestamp_ms": self.timestamp_ms,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummarizedTurn":
        """Create from dictionary."""
        return cls(
            turn_id=data.get("turn_id", ""),
            timestamp_ms=data.get("timestamp_ms", 0),
            summary=data.get("summary", ""),
        )


@dataclass
class MigrationResult:
    """
    Result of a migration operation.

    Attributes:
        success: Whether migration completed successfully
        direction: Demote or promote
        source_section: Source section
        target_section: Target section
        items_migrated: Number of items migrated
        bytes_migrated: Total bytes migrated
        bytes_freed: Bytes freed from source tier
        bytes_added: Bytes added to target tier (may differ due to compression)
        duration_ms: Time taken in milliseconds
        trigger: What triggered this migration
        new_hot_pressure: HOT pressure after migration
        new_warm_pressure: WARM pressure after migration
        error: Error message if failed
    """

    success: bool
    direction: MigrationDirection
    source_section: str
    target_section: str
    items_migrated: int
    bytes_migrated: int
    bytes_freed: int
    bytes_added: int
    duration_ms: float
    trigger: MigrationTrigger = MigrationTrigger.MANUAL
    new_hot_pressure: PressureLevel = PressureLevel.NORMAL
    new_warm_pressure: PressureLevel = PressureLevel.NORMAL
    error: Optional[str] = None

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"MigrationResult({status}: {self.direction.value} "
            f"'{self.source_section}' -> '{self.target_section}', "
            f"items={self.items_migrated}, freed={self.bytes_freed}B, "
            f"added={self.bytes_added}B, took={self.duration_ms:.2f}ms)"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "direction": self.direction.value,
            "source_section": self.source_section,
            "target_section": self.target_section,
            "items_migrated": self.items_migrated,
            "bytes_migrated": self.bytes_migrated,
            "bytes_freed": self.bytes_freed,
            "bytes_added": self.bytes_added,
            "duration_ms": round(self.duration_ms, 3),
            "trigger": self.trigger.value,
            "new_hot_pressure": self.new_hot_pressure.value,
            "new_warm_pressure": self.new_warm_pressure.value,
            "error": self.error,
        }

    @staticmethod
    def failure(
        direction: MigrationDirection,
        source_section: str,
        target_section: str,
        error: str,
        duration_ms: float = 0.0,
        trigger: MigrationTrigger = MigrationTrigger.MANUAL,
    ) -> "MigrationResult":
        """Create a failure result."""
        return MigrationResult(
            success=False,
            direction=direction,
            source_section=source_section,
            target_section=target_section,
            items_migrated=0,
            bytes_migrated=0,
            bytes_freed=0,
            bytes_added=0,
            duration_ms=duration_ms,
            trigger=trigger,
            error=error,
        )


# =============================================================================
# SECTION DATA PROVIDER PROTOCOL
# =============================================================================


class ISectionDataProvider(Protocol):
    """
    Protocol for accessing section data for migration.

    The MigrationEngine needs to read/write section data during migration.
    This protocol abstracts the section access pattern.
    """

    def get_items(self, section: str) -> List[MigrationItem]:
        """Get all items from a section."""
        ...

    def add_items(self, section: str, items: List[MigrationItem]) -> int:
        """Add items to a section, return bytes added."""
        ...

    def remove_items(self, section: str, keys: List[str]) -> int:
        """Remove items by keys, return bytes freed."""
        ...

    def clear_section(self, section: str) -> int:
        """Clear all items from section, return bytes freed."""
        ...

    def get_turn_count(self, section: str) -> int:
        """Get number of turns in history section."""
        ...

    def get_oldest_turns(self, section: str, count: int) -> List[MigrationItem]:
        """Get oldest N turns from history section."""
        ...


# =============================================================================
# MIGRATION ENGINE
# =============================================================================


class MigrationEngine:
    """
    Manages data migration between HOT and WARM tiers.

    Demote: Move data from HOT to WARM when:
    - HOT pressure exceeds ELEVATED threshold (>80%)
    - Turn completes (automatic beliefs migration)
    - history_active exceeds 10 turns

    Promote: Move data from WARM to HOT when:
    - Section needed for active context
    - Narrative thread resumption

    NEVER MIGRATE:
    - control section (NEVER EVICT, stays in HOT)
    - meta section (NEVER EVICT, stays in HOT)

    Thread Safety:
        - Uses MutationGuard.lock_section() during migration
        - Migration is NOT concurrent (single migration at a time)
        - Multiple readers can read during migration

    Performance:
        - demote(): O(n) where n = items to demote
        - promote(): O(n) where n = items to promote
        - Compression adds ~1ms per turn

    Invariants:
        - NEVER demote control or meta sections
        - Data is preserved (demote = move, not delete)
        - Compression reduces fidelity but preserves essentials
        - Promote expands data (may fail if HOT full)

    Example:
        engine = MigrationEngine(size_tracker)

        # Demote beliefs after turn completion
        result = engine.demote(
            section="beliefs_active",
            items=current_turn_facts,
        )

        # Promote old beliefs for context
        result = engine.promote(
            section="beliefs_history",
            items=relevant_facts,
        )

        # Auto-demote on pressure
        result = engine.demote_on_pressure()

    Attributes:
        _size_tracker: SizeTracker for capacity checks
        _mutation_guard: MutationGuard for section locking
        _section_provider: Optional provider for section data access
        _migration_in_progress: Flag to prevent concurrent migrations
        _session_id: Session identifier
    """

    __slots__ = (
        "_ss_cfg",
        "_size_tracker",
        "_mutation_guard",
        "_section_provider",
        "_migration_in_progress",
        "_session_id",
        "_compress_fn",
        "_summarize_fn",
    )

    def __init__(
        self,
        size_tracker: SizeTracker,
        mutation_guard: Optional["MutationGuard"] = None,
        section_provider: Optional[ISectionDataProvider] = None,
        session_id: str = "",
        compress_fn: Optional[Callable[[Any], CompressedTurn]] = None,
        summarize_fn: Optional[Callable[[Any], SummarizedTurn]] = None,
        config: Optional[SessionStateConfig] = None,
    ) -> None:
        """
        Initialize MigrationEngine.

        Args:
            size_tracker: SizeTracker for capacity checks
            mutation_guard: MutationGuard for section locking (optional for testing)
            section_provider: Provider for section data access (optional)
            session_id: Session ID for migration metadata
            compress_fn: Custom compression function (optional)
            summarize_fn: Custom summarization function (optional)
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        self._size_tracker = size_tracker
        self._mutation_guard = mutation_guard
        self._section_provider = section_provider
        self._migration_in_progress = False
        self._session_id = session_id or str(uuid.uuid4())
        self._compress_fn = compress_fn
        self._summarize_fn = summarize_fn

        logger.info(
            "MigrationEngine initialized (session=%s, pairs=%s)",
            self._session_id[:8],
            ", ".join(f"{k}->{v}" for k, v in MIGRATION_PAIRS.items()),
        )

    # =========================================================================
    # VALIDATION HELPERS
    # =========================================================================

    def can_demote(self, section: str) -> bool:
        """
        Check if a section can be demoted.

        Args:
            section: Section name to check

        Returns:
            bool: True if section can be demoted

        A section can be demoted if:
        - It exists and is in HOT tier
        - It is NOT in NEVER_EVICT_SECTIONS
        - It has a WARM pair in MIGRATION_PAIRS
        """
        if section not in ALL_SECTIONS:
            return False

        if section not in HOT_SECTIONS:
            return False

        if section in NEVER_EVICT_SECTIONS:
            return False

        # Must have a migration pair
        return section in MIGRATION_PAIRS

    def can_promote(self, section: str) -> bool:
        """
        Check if a section can be promoted.

        Args:
            section: Section name to check

        Returns:
            bool: True if section can be promoted

        A section can be promoted if:
        - It exists and is in WARM tier
        - It has a HOT counterpart in REVERSE_MIGRATION_PAIRS
        """
        if section not in ALL_SECTIONS:
            return False

        if section not in WARM_SECTIONS:
            return False

        # Must have a reverse migration pair
        return section in REVERSE_MIGRATION_PAIRS

    def get_target_section(self, section: str, direction: MigrationDirection) -> Optional[str]:
        """
        Get the target section for migration.

        Args:
            section: Source section name
            direction: Migration direction

        Returns:
            Target section name, or None if no valid pair
        """
        if direction == MigrationDirection.DEMOTE:
            return MIGRATION_PAIRS.get(section)
        else:
            return REVERSE_MIGRATION_PAIRS.get(section)

    # =========================================================================
    # DEMOTE OPERATIONS
    # =========================================================================

    def demote(
        self,
        section: str,
        items: List[MigrationItem],
        trigger: MigrationTrigger = MigrationTrigger.MANUAL,
    ) -> MigrationResult:
        """
        Demote items from HOT to WARM.

        DEMOTE FLOW:
        1. Validate section can be demoted
        2. Get target WARM section
        3. Check WARM has capacity (or trigger eviction)
        4. Lock both sections
        5. Transform items if needed (e.g., compress history)
        6. Add to WARM section
        7. Remove from HOT section
        8. Update SizeTracker for both sections
        9. Unlock sections

        Args:
            section: Source HOT section name
            items: Items to demote
            trigger: What triggered this migration

        Returns:
            MigrationResult: Success/failure with details

        Section-specific behavior:
        - beliefs_active -> beliefs_history:
          Move facts directly, maintain LRU order

        - history_active -> history_recent:
          Compress turns (extract entities, intents, key phrases)
          If turn 31+, summarize instead of compress
        """
        start_time = time.perf_counter()

        # Prevent concurrent migrations
        if self._migration_in_progress:
            logger.warning("Migration already in progress, skipping demote")
            return MigrationResult.failure(
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section=MIGRATION_PAIRS.get(section, "unknown"),
                error="Migration already in progress",
                trigger=trigger,
            )

        # Validate section can be demoted
        if not self.can_demote(section):
            error = f"Section '{section}' cannot be demoted"
            if section in NEVER_EVICT_SECTIONS:
                error = f"Section '{section}' is NEVER_EVICT and cannot be demoted"
            elif section not in HOT_SECTIONS:
                error = f"Section '{section}' is not in HOT tier"
            elif section not in MIGRATION_PAIRS:
                error = f"Section '{section}' has no WARM migration pair"
            logger.warning("Demote rejected: %s", error)
            return MigrationResult.failure(
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section=MIGRATION_PAIRS.get(section, "unknown"),
                error=error,
                trigger=trigger,
            )

        target_section = MIGRATION_PAIRS[section]

        # Check for empty items
        if not items:
            logger.debug("Demote called with empty items list for section '%s'", section)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                success=True,
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section=target_section,
                items_migrated=0,
                bytes_migrated=0,
                bytes_freed=0,
                bytes_added=0,
                duration_ms=duration_ms,
                trigger=trigger,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

        try:
            self._migration_in_progress = True

            # Calculate source bytes
            source_bytes = sum(item.size_bytes for item in items)

            # Check WARM capacity
            warm_available = self._size_tracker.get_tier_available_bytes("warm")

            # Transform items based on section type
            transformed_items: List[MigrationItem] = []
            target_bytes = 0

            for item in items:
                if section == "history_active":
                    # Compress or summarize history turns
                    transformed = self._transform_history_item(item)
                else:
                    # Direct migration for other sections
                    transformed = item

                transformed_items.append(transformed)
                target_bytes += transformed.size_bytes

            # Check if WARM has space after transformation
            if target_bytes > warm_available:
                logger.warning(
                    "WARM tier has insufficient capacity: need %d, available %d",
                    target_bytes,
                    warm_available,
                )
                duration_ms = (time.perf_counter() - start_time) * 1000
                return MigrationResult.failure(
                    direction=MigrationDirection.DEMOTE,
                    source_section=section,
                    target_section=target_section,
                    error=f"WARM capacity insufficient: need {target_bytes}B, available {warm_available}B",
                    duration_ms=duration_ms,
                    trigger=trigger,
                )

            # Lock sections if MutationGuard available
            if self._mutation_guard is not None:
                self._mutation_guard.lock_section(section)
                self._mutation_guard.lock_section(target_section)

            try:
                # Add to WARM section
                if self._section_provider is not None:
                    bytes_added = self._section_provider.add_items(
                        target_section, transformed_items
                    )
                else:
                    bytes_added = target_bytes

                # Remove from HOT section
                if self._section_provider is not None:
                    keys = [item.key for item in items]
                    bytes_freed = self._section_provider.remove_items(section, keys)
                else:
                    bytes_freed = source_bytes

                # Update SizeTracker
                self._size_tracker.update(section, -bytes_freed)
                self._size_tracker.update(target_section, bytes_added)

            finally:
                # Unlock sections
                if self._mutation_guard is not None:
                    self._mutation_guard.unlock_section(target_section)
                    self._mutation_guard.unlock_section(section)

            duration_ms = (time.perf_counter() - start_time) * 1000

            result = MigrationResult(
                success=True,
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section=target_section,
                items_migrated=len(items),
                bytes_migrated=source_bytes,
                bytes_freed=bytes_freed,
                bytes_added=bytes_added,
                duration_ms=duration_ms,
                trigger=trigger,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

            logger.info(
                "Demoted %d items from '%s' to '%s': freed %dB, added %dB (%.2fms)",
                len(items),
                section,
                target_section,
                bytes_freed,
                bytes_added,
                duration_ms,
            )

            return result

        except Exception as e:
            logger.exception("Demote failed: %s", e)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult.failure(
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section=target_section,
                error=str(e),
                duration_ms=duration_ms,
                trigger=trigger,
            )
        finally:
            self._migration_in_progress = False

    def _transform_history_item(self, item: MigrationItem) -> MigrationItem:
        """
        Transform a history item for WARM storage.

        Turns 11-30: Compress (extract entities, intents, key phrases)
        Turns 31+: Summarize (single sentence)

        Args:
            item: Original history item

        Returns:
            Transformed MigrationItem with compressed/summarized data
        """
        # Get turn number from metadata or key
        turn_number = item.metadata.get("turn_number", 0)

        if turn_number > self._ss_cfg.migration.compression_turn_threshold:
            # Summarize for turns 31+
            summarized = self._summarize_turn(item.data)
            summarized_bytes = len(json.dumps(summarized.to_dict()).encode("utf-8"))
            return MigrationItem(
                section=item.section,
                key=item.key,
                data=summarized,
                size_bytes=summarized_bytes,
                metadata={**item.metadata, "compression_level": "summarized"},
            )
        else:
            # Compress for turns 11-30
            compressed = self._compress_turn(item.data)
            compressed_bytes = len(json.dumps(compressed.to_dict()).encode("utf-8"))
            return MigrationItem(
                section=item.section,
                key=item.key,
                data=compressed,
                size_bytes=compressed_bytes,
                metadata={**item.metadata, "compression_level": "compressed"},
            )

    def _compress_turn(self, turn: Any) -> CompressedTurn:
        """
        Compress a turn for history_recent storage.

        Compression (turns 11-30):
        - Extract entities
        - Extract intents
        - Extract key phrases
        - Drop full message text

        Args:
            turn: Full turn data (dict or object)

        Returns:
            CompressedTurn with extracted information
        """
        # Use custom compression function if provided
        if self._compress_fn is not None:
            return self._compress_fn(turn)

        # Default compression logic
        if isinstance(turn, dict):
            turn_id = turn.get("turn_id", str(uuid.uuid4()))
            timestamp_ms = turn.get("timestamp_ms", int(time.time() * 1000))
            user_message = turn.get("user_message", "")
            assistant_response = turn.get("assistant_response", "")
            entities = turn.get("entities", [])
            intents = turn.get("intents", [])
            key_phrases = turn.get("key_phrases", [])
        else:
            # Assume object with attributes
            turn_id = getattr(turn, "turn_id", str(uuid.uuid4()))
            timestamp_ms = getattr(turn, "timestamp_ms", int(time.time() * 1000))
            user_message = getattr(turn, "user_message", "")
            assistant_response = getattr(turn, "assistant_response", "")
            entities = getattr(turn, "entities", [])
            intents = getattr(turn, "intents", [])
            key_phrases = getattr(turn, "key_phrases", [])

        # Extract summaries (first 100 chars)
        user_summary = (user_message[:100] + "...") if len(user_message) > 100 else user_message
        assistant_summary = (
            (assistant_response[:100] + "...")
            if len(assistant_response) > 100
            else assistant_response
        )

        return CompressedTurn(
            turn_id=turn_id,
            timestamp_ms=timestamp_ms,
            entities=entities if isinstance(entities, list) else [],
            intents=intents if isinstance(intents, list) else [],
            key_phrases=key_phrases if isinstance(key_phrases, list) else [],
            user_summary=user_summary,
            assistant_summary=assistant_summary,
        )

    def _summarize_turn(self, turn: Any) -> SummarizedTurn:
        """
        Summarize a turn for history_recent storage.

        Summarization (turns 31-40):
        - Generate single-sentence summary
        - Keep only turn_id, summary, timestamp

        Args:
            turn: Full or compressed turn

        Returns:
            SummarizedTurn with minimal information

        Note:
            May use LLM for quality summarization in production.
            Fallback: Extract first sentence + key entities.
        """
        # Use custom summarization function if provided
        if self._summarize_fn is not None:
            return self._summarize_fn(turn)

        # Default summarization logic
        if isinstance(turn, CompressedTurn):
            turn_id = turn.turn_id
            timestamp_ms = turn.timestamp_ms
            summary = f"{turn.user_summary} - {turn.assistant_summary}"
        elif isinstance(turn, dict):
            turn_id = turn.get("turn_id", str(uuid.uuid4()))
            timestamp_ms = turn.get("timestamp_ms", int(time.time() * 1000))
            user_msg = turn.get("user_message", turn.get("user_summary", ""))
            assistant_msg = turn.get("assistant_response", turn.get("assistant_summary", ""))
            # Create simple summary
            summary = f"User: {user_msg[:50]}... Assistant: {assistant_msg[:50]}..."
        else:
            turn_id = getattr(turn, "turn_id", str(uuid.uuid4()))
            timestamp_ms = getattr(turn, "timestamp_ms", int(time.time() * 1000))
            user_msg = getattr(turn, "user_message", getattr(turn, "user_summary", ""))
            assistant_msg = getattr(
                turn, "assistant_response", getattr(turn, "assistant_summary", "")
            )
            summary = f"User: {user_msg[:50]}... Assistant: {assistant_msg[:50]}..."

        return SummarizedTurn(
            turn_id=turn_id,
            timestamp_ms=timestamp_ms,
            summary=summary[:200],  # Cap at 200 chars
        )

    # =========================================================================
    # PROMOTE OPERATIONS
    # =========================================================================

    def promote(
        self,
        section: str,
        items: List[MigrationItem],
        trigger: MigrationTrigger = MigrationTrigger.MANUAL,
    ) -> MigrationResult:
        """
        Promote items from WARM to HOT.

        PROMOTE FLOW:
        1. Validate section is in WARM and has HOT pair
        2. Get target HOT section
        3. Check HOT has capacity
        4. If not enough capacity, fail (caller should demote first)
        5. Lock both sections
        6. Expand items if needed (decompress - not implemented yet)
        7. Add to HOT section
        8. Optionally remove from WARM (default: keep copy)
        9. Update SizeTracker
        10. Unlock sections

        Args:
            section: Source WARM section name
            items: Items to promote
            trigger: What triggered this migration

        Returns:
            MigrationResult: Success/failure with details

        Note:
            Promotion is less common than demotion.
            Used for context switches and narrative resumption.
            WARM copy is kept by default for safety.
        """
        start_time = time.perf_counter()

        # Prevent concurrent migrations
        if self._migration_in_progress:
            logger.warning("Migration already in progress, skipping promote")
            return MigrationResult.failure(
                direction=MigrationDirection.PROMOTE,
                source_section=section,
                target_section=REVERSE_MIGRATION_PAIRS.get(section, "unknown"),
                error="Migration already in progress",
                trigger=trigger,
            )

        # Validate section can be promoted
        if not self.can_promote(section):
            error = f"Section '{section}' cannot be promoted"
            if section not in WARM_SECTIONS:
                error = f"Section '{section}' is not in WARM tier"
            elif section not in REVERSE_MIGRATION_PAIRS:
                error = f"Section '{section}' has no HOT migration pair"
            logger.warning("Promote rejected: %s", error)
            return MigrationResult.failure(
                direction=MigrationDirection.PROMOTE,
                source_section=section,
                target_section=REVERSE_MIGRATION_PAIRS.get(section, "unknown"),
                error=error,
                trigger=trigger,
            )

        target_section = REVERSE_MIGRATION_PAIRS[section]

        # Check for empty items
        if not items:
            logger.debug("Promote called with empty items list for section '%s'", section)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                success=True,
                direction=MigrationDirection.PROMOTE,
                source_section=section,
                target_section=target_section,
                items_migrated=0,
                bytes_migrated=0,
                bytes_freed=0,
                bytes_added=0,
                duration_ms=duration_ms,
                trigger=trigger,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

        try:
            self._migration_in_progress = True

            # Calculate bytes needed in HOT
            # Note: Promotion may need to expand compressed data
            target_bytes = sum(item.size_bytes for item in items)

            # Check HOT capacity
            hot_available = self._size_tracker.get_tier_available_bytes("hot")

            if target_bytes > hot_available:
                logger.warning(
                    "HOT tier has insufficient capacity: need %d, available %d",
                    target_bytes,
                    hot_available,
                )
                duration_ms = (time.perf_counter() - start_time) * 1000
                return MigrationResult.failure(
                    direction=MigrationDirection.PROMOTE,
                    source_section=section,
                    target_section=target_section,
                    error=f"HOT capacity insufficient: need {target_bytes}B, available {hot_available}B. Demote first.",
                    duration_ms=duration_ms,
                    trigger=trigger,
                )

            # Lock sections if MutationGuard available
            if self._mutation_guard is not None:
                self._mutation_guard.lock_section(section)
                self._mutation_guard.lock_section(target_section)

            try:
                # Add to HOT section
                if self._section_provider is not None:
                    bytes_added = self._section_provider.add_items(target_section, items)
                else:
                    bytes_added = target_bytes

                # Update SizeTracker (WARM keeps copy, HOT gains)
                self._size_tracker.update(target_section, bytes_added)
                # Note: We don't remove from WARM by default (keep copy)

            finally:
                # Unlock sections
                if self._mutation_guard is not None:
                    self._mutation_guard.unlock_section(target_section)
                    self._mutation_guard.unlock_section(section)

            duration_ms = (time.perf_counter() - start_time) * 1000

            result = MigrationResult(
                success=True,
                direction=MigrationDirection.PROMOTE,
                source_section=section,
                target_section=target_section,
                items_migrated=len(items),
                bytes_migrated=target_bytes,
                bytes_freed=0,  # WARM keeps copy
                bytes_added=bytes_added,
                duration_ms=duration_ms,
                trigger=trigger,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

            logger.info(
                "Promoted %d items from '%s' to '%s': added %dB (%.2fms)",
                len(items),
                section,
                target_section,
                bytes_added,
                duration_ms,
            )

            return result

        except Exception as e:
            logger.exception("Promote failed: %s", e)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult.failure(
                direction=MigrationDirection.PROMOTE,
                source_section=section,
                target_section=target_section,
                error=str(e),
                duration_ms=duration_ms,
                trigger=trigger,
            )
        finally:
            self._migration_in_progress = False

    # =========================================================================
    # AUTOMATIC DEMOTION HELPERS
    # =========================================================================

    def demote_on_pressure(self) -> MigrationResult:
        """
        Automatically demote when HOT pressure exceeds threshold.

        Called when HOT pressure > ELEVATED (80%).

        Strategy:
        1. Calculate bytes to free to reach 70% utilization
        2. Select sections to demote (by DEMOTE_PRIORITY)
        3. Get items from section_provider
        4. Demote items iteratively until target reached
        5. Return aggregated result

        Returns:
            MigrationResult: Aggregated result of all demotions

        Note:
            Requires section_provider to be set for full functionality.
            Without section_provider, creates placeholder items.
        """
        start_time = time.perf_counter()

        # Check current HOT pressure
        hot_pressure = self._size_tracker.get_pressure("hot")

        if hot_pressure == PressureLevel.NORMAL:
            logger.debug("HOT pressure is NORMAL, no demotion needed")
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                success=True,
                direction=MigrationDirection.DEMOTE,
                source_section="hot",
                target_section="warm",
                items_migrated=0,
                bytes_migrated=0,
                bytes_freed=0,
                bytes_added=0,
                duration_ms=duration_ms,
                trigger=MigrationTrigger.PRESSURE,
                new_hot_pressure=hot_pressure,
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

        # Calculate bytes to free
        current_hot = self._size_tracker.get_tier_size("hot")
        _cfg_mig = self._ss_cfg.migration
        target_hot = int(HOT_SIZE_LIMIT_BYTES * _cfg_mig.target_hot_utilization)
        bytes_to_free = current_hot - target_hot

        if bytes_to_free <= 0:
            logger.debug("HOT within target, no demotion needed")
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                success=True,
                direction=MigrationDirection.DEMOTE,
                source_section="hot",
                target_section="warm",
                items_migrated=0,
                bytes_migrated=0,
                bytes_freed=0,
                bytes_added=0,
                duration_ms=duration_ms,
                trigger=MigrationTrigger.PRESSURE,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

        logger.info(
            "Pressure demotion: HOT is %s, need to free %dB",
            hot_pressure.value,
            bytes_to_free,
        )

        # Get candidates sorted by demote priority
        candidates = self._get_demote_candidates()

        total_freed = 0
        total_added = 0
        total_items = 0
        sections_demoted = []
        iterations = 0

        for section in candidates:
            if total_freed >= bytes_to_free:
                break

            if iterations >= self._ss_cfg.migration.max_demote_iterations:
                logger.warning("Max demote iterations reached")
                break

            iterations += 1

            # Get items to demote
            section_size = self._size_tracker.get_section_size(section)
            if section_size == 0:
                continue

            # Calculate how much to demote from this section
            needed = bytes_to_free - total_freed
            to_demote = min(section_size, needed)

            # Create placeholder items or get from provider
            if self._section_provider is not None:
                # Get actual items from provider
                items = self._section_provider.get_items(section)
                # Select items up to to_demote bytes
                selected_items = []
                selected_bytes = 0
                for item in items:
                    if selected_bytes >= to_demote:
                        break
                    selected_items.append(item)
                    selected_bytes += item.size_bytes
                items = selected_items
            else:
                # Create placeholder items
                items = [
                    MigrationItem(
                        section=section,
                        key=f"pressure_demote_{iterations}",
                        data=None,
                        size_bytes=to_demote,
                        metadata={"placeholder": True},
                    )
                ]

            if not items:
                continue

            # Demote items
            result = self.demote(section, items, trigger=MigrationTrigger.PRESSURE)

            if result.success:
                total_freed += result.bytes_freed
                total_added += result.bytes_added
                total_items += result.items_migrated
                sections_demoted.append(section)
            else:
                logger.warning("Demote failed for section '%s': %s", section, result.error)

        duration_ms = (time.perf_counter() - start_time) * 1000

        return MigrationResult(
            success=total_freed > 0,
            direction=MigrationDirection.DEMOTE,
            source_section=",".join(sections_demoted) if sections_demoted else "none",
            target_section="warm",
            items_migrated=total_items,
            bytes_migrated=total_freed,
            bytes_freed=total_freed,
            bytes_added=total_added,
            duration_ms=duration_ms,
            trigger=MigrationTrigger.PRESSURE,
            new_hot_pressure=self._size_tracker.get_pressure("hot"),
            new_warm_pressure=self._size_tracker.get_pressure("warm"),
            error=None if total_freed > 0 else "No sections could be demoted",
        )

    def demote_turn_beliefs(self, turn_id: str) -> MigrationResult:
        """
        Demote current turn beliefs after turn completion.

        Called at end of each turn to move beliefs_active to beliefs_history.

        Args:
            turn_id: Completed turn identifier

        Returns:
            MigrationResult: Result of demotion

        Flow:
        1. Get all facts from beliefs_active via section_provider
        2. Add turn_id and timestamp metadata
        3. Demote to beliefs_history
        4. Clear beliefs_active via section_provider (or let demote handle removal)
        """
        start_time = time.perf_counter()
        section = "beliefs_active"

        # Get current size
        current_size = self._size_tracker.get_section_size(section)

        if current_size == 0:
            logger.debug("beliefs_active is empty, nothing to demote")
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                success=True,
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section="beliefs_history",
                items_migrated=0,
                bytes_migrated=0,
                bytes_freed=0,
                bytes_added=0,
                duration_ms=duration_ms,
                trigger=MigrationTrigger.TURN_COMPLETE,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

        # Get items from provider or create placeholder
        if self._section_provider is not None:
            items = self._section_provider.get_items(section)
        else:
            # Create placeholder with all beliefs
            items = [
                MigrationItem(
                    section=section,
                    key=f"turn_{turn_id}",
                    data={"turn_id": turn_id, "timestamp_ms": int(time.time() * 1000)},
                    size_bytes=current_size,
                    metadata={"turn_id": turn_id},
                )
            ]

        # Add turn metadata to all items
        for item in items:
            item.metadata["turn_id"] = turn_id
            item.metadata["demoted_at_ms"] = int(time.time() * 1000)

        return self.demote(section, items, trigger=MigrationTrigger.TURN_COMPLETE)

    def demote_history_overflow(self) -> MigrationResult:
        """
        Demote oldest history when history_active exceeds 10 turns.

        Called when history_active has > 10 turns.

        Strategy:
        1. Get turn count from section_provider
        2. If <= 10 turns, return success (no-op)
        3. Get oldest turns beyond 10
        4. Compress turns 11-30, summarize 31+
        5. Demote to history_recent

        Returns:
            MigrationResult: Result of demotion
        """
        start_time = time.perf_counter()
        section = "history_active"

        # Get turn count
        if self._section_provider is not None:
            turn_count = self._section_provider.get_turn_count(section)
        else:
            # Estimate based on size (assume ~1KB per turn average)
            current_size = self._size_tracker.get_section_size(section)
            turn_count = current_size // 1024 + (1 if current_size % 1024 > 0 else 0)

        _max_turns = self._ss_cfg.migration.max_history_active_turns
        if turn_count <= _max_turns:
            logger.debug(
                "history_active has %d turns (<= %d), no demotion needed",
                turn_count,
                _max_turns,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MigrationResult(
                success=True,
                direction=MigrationDirection.DEMOTE,
                source_section=section,
                target_section="history_recent",
                items_migrated=0,
                bytes_migrated=0,
                bytes_freed=0,
                bytes_added=0,
                duration_ms=duration_ms,
                trigger=MigrationTrigger.HISTORY_OVERFLOW,
                new_hot_pressure=self._size_tracker.get_pressure("hot"),
                new_warm_pressure=self._size_tracker.get_pressure("warm"),
            )

        # Calculate how many turns to demote
        turns_to_demote = turn_count - _max_turns

        logger.info(
            "history_active has %d turns, demoting oldest %d",
            turn_count,
            turns_to_demote,
        )

        # Get oldest turns
        if self._section_provider is not None:
            items = self._section_provider.get_oldest_turns(section, turns_to_demote)
        else:
            # Create placeholder items
            current_size = self._size_tracker.get_section_size(section)
            bytes_per_turn = current_size // turn_count if turn_count > 0 else 1024
            items = [
                MigrationItem(
                    section=section,
                    key=f"turn_{i}",
                    data={
                        "turn_id": f"turn_{i}",
                        "timestamp_ms": int(time.time() * 1000) - (turns_to_demote - i) * 60000,
                        "user_message": f"User message for turn {i}",
                        "assistant_response": f"Assistant response for turn {i}",
                    },
                    size_bytes=bytes_per_turn,
                    metadata={"turn_number": 11 + i},  # These are turns 11+
                )
                for i in range(turns_to_demote)
            ]

        return self.demote(section, items, trigger=MigrationTrigger.HISTORY_OVERFLOW)

    def _get_demote_candidates(self) -> List[str]:
        """
        Get sections that can be demoted, sorted by priority.

        Returns:
            List of section names in demote priority order
        """
        candidates = []

        for section, priority in sorted(DEMOTE_PRIORITY.items(), key=lambda x: x[1]):
            if self.can_demote(section):
                size = self._size_tracker.get_section_size(section)
                if size > 0:
                    candidates.append(section)

        return candidates

    # =========================================================================
    # STATUS AND DIAGNOSTICS
    # =========================================================================

    def get_demote_candidates(self) -> List[MigrationItem]:
        """
        Get items that can be demoted from HOT.

        Returns:
            List of demotable items, sorted by priority

        Priority (demote first):
        1. history_active turns beyond 10
        2. beliefs_active from previous turns
        3. narrative threads that are paused

        Note:
            Requires section_provider for actual items.
            Returns placeholders otherwise.
        """
        result: List[MigrationItem] = []

        for section in self._get_demote_candidates():
            if self._section_provider is not None:
                items = self._section_provider.get_items(section)
                result.extend(items)
            else:
                # Create placeholder
                size = self._size_tracker.get_section_size(section)
                if size > 0:
                    result.append(
                        MigrationItem(
                            section=section,
                            key=f"{section}_all",
                            data=None,
                            size_bytes=size,
                            metadata={"placeholder": True},
                        )
                    )

        return result

    def get_status(self) -> Dict[str, Any]:
        """
        Get current migration engine status.

        Returns:
            Dict with status information
        """
        hot_pressure = self._size_tracker.get_pressure("hot")
        warm_pressure = self._size_tracker.get_pressure("warm")

        demotable_sections = []
        for section in MIGRATION_PAIRS:
            if self.can_demote(section):
                size = self._size_tracker.get_section_size(section)
                demotable_sections.append({"section": section, "size_bytes": size})

        promotable_sections = []
        for section in REVERSE_MIGRATION_PAIRS:
            if self.can_promote(section):
                size = self._size_tracker.get_section_size(section)
                promotable_sections.append({"section": section, "size_bytes": size})

        return {
            "session_id": self._session_id[:8],
            "migration_in_progress": self._migration_in_progress,
            "hot_pressure": hot_pressure.value,
            "warm_pressure": warm_pressure.value,
            "hot_size_bytes": self._size_tracker.get_tier_size("hot"),
            "warm_size_bytes": self._size_tracker.get_tier_size("warm"),
            "demotable_sections": demotable_sections,
            "promotable_sections": promotable_sections,
            "demote_needed": hot_pressure != PressureLevel.NORMAL,
            "migration_pairs": MIGRATION_PAIRS,
        }

    def estimate_demote_needed(self) -> int:
        """
        Estimate bytes that should be demoted to reach normal pressure.

        Returns:
            int: Bytes to demote (0 if pressure is normal)
        """
        current_hot = self._size_tracker.get_tier_size("hot")
        target_hot = int(HOT_SIZE_LIMIT_BYTES * self._ss_cfg.migration.target_hot_utilization)

        if current_hot <= target_hot:
            return 0

        return current_hot - target_hot

    @property
    def migration_in_progress(self) -> bool:
        """Check if migration is currently in progress."""
        return self._migration_in_progress
        return self._migration_in_progress
