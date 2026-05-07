"""
NarrativeActiveSection - Active Conversation Threads (HOT CORE)
================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.7 (narrative_active)

This section tracks the active conversation thread and narrative arc position.
Enables multi-topic conversations with context switching and thread resumption.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/narrative_active_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- primary_thread: ConversationThread - currently active thread
- paused_threads: [ConversationThread] - max 5, beyond → archive
- total_threads_session: uint16
- active_thread_count: uint8
- paused_thread_count: uint8
- arc: NarrativeArc - session-level narrative position
- current_thread_id: string
- resumption_hint: string
- archived_thread_ids: [string]
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    NarrativeActiveSection as FBNarrativeActiveSection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.ConversationThread import (
    ConversationThreadAddContextSummary,
    ConversationThreadAddGoal,
    ConversationThreadAddId,
    ConversationThreadAddIsGoalMet,
    ConversationThreadAddLastActiveTurn,
    ConversationThreadAddRelatedEntities,
    ConversationThreadAddRelatedIntents,
    ConversationThreadAddResolvedTurn,
    ConversationThreadAddResumptionHint,
    ConversationThreadAddStartedTurn,
    ConversationThreadAddState,
    ConversationThreadAddTitle,
    ConversationThreadEnd,
    ConversationThreadStart,
    ConversationThreadStartRelatedEntitiesVector,
    ConversationThreadStartRelatedIntentsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.NarrativeActiveSection import (
    NarrativeActiveSectionAddActiveThreadCount,
    NarrativeActiveSectionAddArc,
    NarrativeActiveSectionAddArchivedThreadIds,
    NarrativeActiveSectionAddCurrentThreadId,
    NarrativeActiveSectionAddHeader,
    NarrativeActiveSectionAddPausedThreadCount,
    NarrativeActiveSectionAddPausedThreads,
    NarrativeActiveSectionAddPrimaryThread,
    NarrativeActiveSectionAddResumptionHint,
    NarrativeActiveSectionAddTotalThreadsSession,
    NarrativeActiveSectionEnd,
    NarrativeActiveSectionStart,
    NarrativeActiveSectionStartArchivedThreadIdsVector,
    NarrativeActiveSectionStartPausedThreadsVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState.NarrativeArc import (
    NarrativeArcAddClimaxEnd,
    NarrativeArcAddClimaxTurn,
    NarrativeArcAddExpositionEnd,
    NarrativeArcAddIncitingIncidentTurn,
    NarrativeArcAddPosition,
    NarrativeArcAddProgress,
    NarrativeArcAddRisingEnd,
    NarrativeArcEnd,
    NarrativeArcStart,
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


class ThreadState(IntEnum):
    """Thread state enumeration (matches ThreadState in narrative_active_section.fbs)."""

    ACTIVE = 0  # Currently being discussed
    PAUSED = 1  # User switched topics, may resume
    RESOLVED = 2  # Goal completed
    ARCHIVED = 3  # Moved to COLD storage


class ArcPosition(IntEnum):
    """Narrative arc position (matches ArcPosition in common.fbs)."""

    EXPOSITION = 0  # Turns 1-10: User intro, goals set
    RISING_ACTION = 1  # Turns 11-40: Working on tasks
    CLIMAX = 2  # Turns 41-60: Key decision moment
    RESOLUTION = 3  # Ongoing: Wrapping up


# =============================================================================
# Data Classes matching FlatBuffer schema
# =============================================================================


@dataclass
class ConversationThread:
    """
    Conversation thread - a coherent topic of discussion.

    Maps to ConversationThread table in narrative_active_section.fbs.
    """

    id: str
    title: str = ""
    state: ThreadState = ThreadState.ACTIVE

    # Thread lifecycle
    started_turn: int = 0
    last_active_turn: int = 0
    resolved_turn: int = 0

    # Goal tracking
    goal: str = ""
    is_goal_met: bool = False

    # Related context
    related_entities: List[str] = field(default_factory=list)
    related_intents: List[str] = field(default_factory=list)

    # Resumption support
    resumption_hint: str = ""
    context_summary: str = ""

    def __post_init__(self):
        """Ensure state is proper enum type."""
        if isinstance(self.state, int):
            self.state = ThreadState(self.state)

    def is_active(self) -> bool:
        """Check if thread is currently active."""
        return self.state == ThreadState.ACTIVE

    def is_paused(self) -> bool:
        """Check if thread is paused."""
        return self.state == ThreadState.PAUSED

    def is_resolved(self) -> bool:
        """Check if thread goal is completed."""
        return self.state == ThreadState.RESOLVED

    def is_archived(self) -> bool:
        """Check if thread has been archived."""
        return self.state == ThreadState.ARCHIVED

    def can_resume(self) -> bool:
        """Check if thread can be resumed."""
        return self.state in (ThreadState.PAUSED, ThreadState.ACTIVE)

    def turns_active(self) -> int:
        """Get number of turns this thread has been active."""
        if self.last_active_turn >= self.started_turn:
            return self.last_active_turn - self.started_turn + 1
        return 0


@dataclass
class NarrativeArc:
    """
    Session-level narrative arc tracking.

    Maps to NarrativeArc table in narrative_active_section.fbs.
    """

    position: ArcPosition = ArcPosition.EXPOSITION

    # Phase boundaries (turn numbers)
    exposition_end: int = 10  # Turns 1-10
    rising_end: int = 40  # Turns 11-40
    climax_end: int = 60  # Turns 41-60

    # Key moments
    inciting_incident_turn: int = 0  # When main goal was established
    climax_turn: int = 0  # Key decision moment (if reached)

    # Progress indicator (0.0 to 1.0)
    progress: float = 0.0

    def __post_init__(self):
        """Ensure position is proper enum type and clamp progress."""
        if isinstance(self.position, int):
            self.position = ArcPosition(self.position)
        self.progress = max(0.0, min(1.0, self.progress))

    def update_for_turn(self, turn_number: int) -> None:
        """
        Update arc position based on current turn.

        Args:
            turn_number: Current turn number
        """
        if turn_number <= self.exposition_end:
            self.position = ArcPosition.EXPOSITION
            self.progress = turn_number / self.exposition_end if self.exposition_end > 0 else 0.0
        elif turn_number <= self.rising_end:
            self.position = ArcPosition.RISING_ACTION
            self.progress = (
                (turn_number - self.exposition_end) / (self.rising_end - self.exposition_end)
                if self.rising_end > self.exposition_end
                else 0.0
            )
        elif turn_number <= self.climax_end:
            self.position = ArcPosition.CLIMAX
            self.progress = (
                (turn_number - self.rising_end) / (self.climax_end - self.rising_end)
                if self.climax_end > self.rising_end
                else 0.0
            )
        else:
            self.position = ArcPosition.RESOLUTION
            self.progress = 1.0

    def set_inciting_incident(self, turn_number: int) -> None:
        """Mark turn as the inciting incident."""
        self.inciting_incident_turn = turn_number

    def set_climax(self, turn_number: int) -> None:
        """Mark turn as the climax."""
        self.climax_turn = turn_number
        self.position = ArcPosition.CLIMAX


# =============================================================================
# Constants
# =============================================================================

MAX_PAUSED_THREADS = 5  # Beyond this, archive oldest
DEFAULT_RESUMPTION_TEMPLATE = "Earlier, you were discussing {title}."


# =============================================================================
# NarrativeActiveSection Implementation
# =============================================================================


class NarrativeActiveSection:
    """
    Narrative Active Section - current thread and arc.

    This section tracks the active conversation thread and narrative arc
    position. Enables multi-topic conversations with context switching
    and thread resumption.

    Budget: 4KB (4096 bytes)
    Tier: HOT CORE
    Eviction: Never (section stays, resets on session end)

    FlatBuffer Schema: narrative_active_section.fbs
    Serialization Target: <100 microseconds

    Contents per schema:
    - primary_thread: ConversationThread - currently active thread
    - paused_threads: [ConversationThread] - max 5
    - arc: NarrativeArc - session-level narrative position
    - current_thread_id: string - quick access to active thread
    - resumption_hint: string - from primary thread
    - archived_thread_ids: [string] - threads moved to COLD

    Example:
        section = NarrativeActiveSection(session_id="sess-123")

        # Start a new thread
        thread = section.create_thread(
            title="Weather discussion",
            goal="Get weather forecast for weekend trip",
            turn_number=1,
        )

        # User switches topic
        new_thread = section.create_thread(
            title="Meeting scheduling",
            goal="Schedule team meeting",
            turn_number=5,
        )

        # User wants to go back to weather
        section.switch_to(thread.id)
        hint = section.resumption_hint  # "Earlier, you were discussing Weather discussion."
    """

    BUDGET_BYTES = 4096  # 4KB
    TIER = "hot"
    CAN_EVICT = False  # Section stays, resets on session end
    SECTION_NAME = "narrative_active"
    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        session_id: str = "",
        schema_version: str = "",
    ) -> None:
        """
        Initialize NarrativeActiveSection.

        Args:
            session_id: Session UUID (generated if empty)
            schema_version: Schema version (uses default if empty)
        """
        now_ms = int(time.time() * 1000)

        self._session_id = session_id or str(uuid.uuid4())
        self._schema_version = schema_version or self.SCHEMA_VERSION
        self._last_updated_ms = now_ms

        # Thread tracking
        self._primary_thread: Optional[ConversationThread] = None
        self._paused_threads: List[ConversationThread] = []
        self._archived_thread_ids: List[str] = []
        self._thread_index: Dict[str, ConversationThread] = {}
        self._total_threads_session = 0

        # Narrative arc
        self._arc = NarrativeArc()
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
    def schema_version(self) -> str:
        """Schema version string."""
        return self._schema_version

    @property
    def primary_thread(self) -> Optional[ConversationThread]:
        """Currently active thread."""
        return self._primary_thread

    @property
    def paused_threads(self) -> List[ConversationThread]:
        """List of paused threads (max 5)."""
        return list(self._paused_threads)

    @property
    def archived_thread_ids(self) -> List[str]:
        """List of archived thread IDs."""
        return list(self._archived_thread_ids)

    @property
    def current_thread_id(self) -> Optional[str]:
        """ID of the currently active thread."""
        return self._primary_thread.id if self._primary_thread else None

    @property
    def resumption_hint(self) -> str:
        """Resumption hint from primary thread."""
        if self._primary_thread and self._primary_thread.resumption_hint:
            return self._primary_thread.resumption_hint
        return ""

    @property
    def arc(self) -> NarrativeArc:
        """Session-level narrative arc."""
        return self._arc

    @property
    def arc_position(self) -> ArcPosition:
        """Current arc position."""
        return self._arc.position

    @property
    def arc_progress(self) -> float:
        """Arc progress (0.0 to 1.0)."""
        return self._arc.progress

    @property
    def total_threads_session(self) -> int:
        """Total threads created this session."""
        return self._total_threads_session

    @property
    def active_thread_count(self) -> int:
        """Number of active threads (should be 1 or 0)."""
        return 1 if self._primary_thread else 0

    @property
    def paused_thread_count(self) -> int:
        """Number of paused threads."""
        return len(self._paused_threads)

    @property
    def current_turn(self) -> int:
        """Current turn number."""
        return self._current_turn

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
        - Primary thread: ~300 bytes
        - Paused threads: ~300 bytes x 5 = 1.5KB
        - NarrativeArc: ~50 bytes
        - Archive pointers: ~500 bytes
        - Total: ~2.5KB typical, 4KB max
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 100  # Header overhead
        if self._primary_thread:
            size += self._estimate_thread_size(self._primary_thread)
        for thread in self._paused_threads:
            size += self._estimate_thread_size(thread)
        size += 50  # Arc
        size += sum(len(tid.encode("utf-8")) + 4 for tid in self._archived_thread_ids)

        return min(size, self.BUDGET_BYTES)

    def _estimate_thread_size(self, thread: ConversationThread) -> int:
        """Estimate size of a thread in bytes."""
        size = 50  # Base overhead
        size += len(thread.id.encode("utf-8"))
        size += len(thread.title.encode("utf-8"))
        size += len(thread.goal.encode("utf-8"))
        size += len(thread.resumption_hint.encode("utf-8"))
        size += len(thread.context_summary.encode("utf-8"))
        size += sum(len(e.encode("utf-8")) + 4 for e in thread.related_entities)
        size += sum(len(i.encode("utf-8")) + 4 for i in thread.related_intents)
        return size

    def clear(self) -> None:
        """Clear all section data, reset to initial state."""
        now_ms = int(time.time() * 1000)

        self._primary_thread = None
        self._paused_threads.clear()
        self._archived_thread_ids.clear()
        self._thread_index.clear()
        self._total_threads_session = 0
        self._arc = NarrativeArc()
        self._current_turn = 0
        self._last_updated_ms = now_ms
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
            "current_thread_id": self.current_thread_id,
            "primary_thread_title": self._primary_thread.title if self._primary_thread else None,
            "paused_thread_count": self.paused_thread_count,
            "archived_thread_count": len(self._archived_thread_ids),
            "total_threads_session": self._total_threads_session,
            "arc_position": self._arc.position.name,
            "arc_progress": self._arc.progress,
            "current_turn": self._current_turn,
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Thread Management Operations
    # =========================================================================

    def create_thread(
        self,
        title: str,
        goal: str = "",
        turn_number: Optional[int] = None,
        related_entities: Optional[List[str]] = None,
        related_intents: Optional[List[str]] = None,
        auto_switch: bool = True,
    ) -> ConversationThread:
        """
        Create a new conversation thread.

        Args:
            title: Brief thread description
            goal: What user wants to achieve
            turn_number: Starting turn (auto-increments if None)
            related_entities: Associated entity IDs
            related_intents: Associated intent types
            auto_switch: Whether to switch to this thread

        Returns:
            Created ConversationThread
        """
        now_ms = int(time.time() * 1000)

        if turn_number is not None:
            self._current_turn = turn_number
        else:
            self._current_turn += 1

        thread = ConversationThread(
            id=str(uuid.uuid4()),
            title=title,
            state=ThreadState.ACTIVE if auto_switch else ThreadState.PAUSED,
            started_turn=self._current_turn,
            last_active_turn=self._current_turn,
            goal=goal,
            related_entities=related_entities or [],
            related_intents=related_intents or [],
        )

        # Add to index
        self._thread_index[thread.id] = thread
        self._total_threads_session += 1

        if auto_switch:
            # Pause current primary thread
            if self._primary_thread:
                self._pause_thread_internal(self._primary_thread)
            self._primary_thread = thread
        else:
            self._paused_threads.append(thread)
            self._enforce_paused_limit()

        # Update arc
        self._arc.update_for_turn(self._current_turn)
        if self._total_threads_session == 1 and goal:
            self._arc.set_inciting_incident(self._current_turn)

        self._last_updated_ms = now_ms
        self._invalidate_cache()

        return thread

    def get_thread(self, thread_id: str) -> Optional[ConversationThread]:
        """
        Get thread by ID.

        Args:
            thread_id: Thread UUID

        Returns:
            ConversationThread or None
        """
        return self._thread_index.get(thread_id)

    def switch_to(self, thread_id: str, turn_number: Optional[int] = None) -> bool:
        """
        Switch to a different thread.

        Args:
            thread_id: Thread to switch to
            turn_number: Current turn (auto-increments if None)

        Returns:
            True if switch succeeded
        """
        thread = self._thread_index.get(thread_id)
        if not thread or not thread.can_resume():
            return False

        now_ms = int(time.time() * 1000)

        if turn_number is not None:
            self._current_turn = turn_number
        else:
            self._current_turn += 1

        # Pause current primary
        if self._primary_thread and self._primary_thread.id != thread_id:
            self._pause_thread_internal(self._primary_thread)

        # Remove from paused list if there
        self._paused_threads = [t for t in self._paused_threads if t.id != thread_id]

        # Activate thread
        thread.state = ThreadState.ACTIVE
        thread.last_active_turn = self._current_turn
        self._primary_thread = thread

        # Generate resumption hint
        thread.resumption_hint = self._generate_resumption_hint(thread)

        # Update arc
        self._arc.update_for_turn(self._current_turn)

        self._last_updated_ms = now_ms
        self._invalidate_cache()

        return True

    def pause_thread(self, thread_id: str) -> bool:
        """
        Pause a thread (switch away).

        Args:
            thread_id: Thread to pause

        Returns:
            True if paused
        """
        thread = self._thread_index.get(thread_id)
        if not thread or thread.state != ThreadState.ACTIVE:
            return False

        self._pause_thread_internal(thread)

        if self._primary_thread and self._primary_thread.id == thread_id:
            self._primary_thread = None

        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

        return True

    def resolve_thread(
        self,
        thread_id: str,
        turn_number: Optional[int] = None,
    ) -> bool:
        """
        Mark thread goal as completed.

        Args:
            thread_id: Thread to resolve
            turn_number: Resolution turn

        Returns:
            True if resolved
        """
        thread = self._thread_index.get(thread_id)
        if not thread:
            return False

        now_ms = int(time.time() * 1000)

        if turn_number is not None:
            self._current_turn = turn_number

        thread.state = ThreadState.RESOLVED
        thread.is_goal_met = True
        thread.resolved_turn = self._current_turn

        # Remove from active/paused
        if self._primary_thread and self._primary_thread.id == thread_id:
            self._primary_thread = None
        self._paused_threads = [t for t in self._paused_threads if t.id != thread_id]

        self._last_updated_ms = now_ms
        self._invalidate_cache()

        return True

    def archive_thread(self, thread_id: str) -> bool:
        """
        Archive a thread to COLD storage pointer.

        Args:
            thread_id: Thread to archive

        Returns:
            True if archived
        """
        thread = self._thread_index.get(thread_id)
        if not thread:
            return False

        now_ms = int(time.time() * 1000)

        thread.state = ThreadState.ARCHIVED
        self._archived_thread_ids.append(thread_id)

        # Remove from active/paused
        if self._primary_thread and self._primary_thread.id == thread_id:
            self._primary_thread = None
        self._paused_threads = [t for t in self._paused_threads if t.id != thread_id]

        # Remove from index
        del self._thread_index[thread_id]

        self._last_updated_ms = now_ms
        self._invalidate_cache()

        return True

    def update_thread(
        self,
        thread_id: str,
        title: Optional[str] = None,
        goal: Optional[str] = None,
        context_summary: Optional[str] = None,
        turn_number: Optional[int] = None,
    ) -> bool:
        """
        Update thread metadata.

        Args:
            thread_id: Thread to update
            title: New title (if provided)
            goal: New goal (if provided)
            context_summary: Updated context summary
            turn_number: Current turn

        Returns:
            True if updated
        """
        thread = self._thread_index.get(thread_id)
        if not thread:
            return False

        now_ms = int(time.time() * 1000)

        if turn_number is not None:
            self._current_turn = turn_number
            thread.last_active_turn = self._current_turn

        if title is not None:
            thread.title = title
        if goal is not None:
            thread.goal = goal
        if context_summary is not None:
            thread.context_summary = context_summary

        self._last_updated_ms = now_ms
        self._invalidate_cache()

        return True

    def add_related_entity(self, thread_id: str, entity_id: str) -> bool:
        """Add a related entity to a thread."""
        thread = self._thread_index.get(thread_id)
        if not thread:
            return False

        if entity_id not in thread.related_entities:
            thread.related_entities.append(entity_id)
            self._last_updated_ms = int(time.time() * 1000)
            self._invalidate_cache()

        return True

    def add_related_intent(self, thread_id: str, intent: str) -> bool:
        """Add a related intent to a thread."""
        thread = self._thread_index.get(thread_id)
        if not thread:
            return False

        if intent not in thread.related_intents:
            thread.related_intents.append(intent)
            self._last_updated_ms = int(time.time() * 1000)
            self._invalidate_cache()

        return True

    def record_turn(self, turn_number: int) -> None:
        """
        Record a turn without changing threads.

        Args:
            turn_number: Current turn number
        """
        self._current_turn = turn_number

        if self._primary_thread:
            self._primary_thread.last_active_turn = turn_number

        self._arc.update_for_turn(turn_number)
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_all_threads(self) -> List[ConversationThread]:
        """Get all threads in memory (primary + paused)."""
        threads = []
        if self._primary_thread:
            threads.append(self._primary_thread)
        threads.extend(self._paused_threads)
        return threads

    def get_active_threads(self) -> List[ConversationThread]:
        """Get active and paused threads (resumable)."""
        return [t for t in self.get_all_threads() if t.can_resume()]

    def get_active_thread_name(self) -> str:
        """Return the title of the currently active primary thread.

        Used by Front handler (WEAVE mode scenario_data) and FSM for
        injecting narrative context into Back dispatch payloads.
        Returns empty string if no primary thread exists.
        """
        if self._primary_thread:
            return self._primary_thread.title
        return ""

    def get_threads_by_entity(self, entity_id: str) -> List[ConversationThread]:
        """Get threads related to an entity."""
        return [t for t in self.get_all_threads() if entity_id in t.related_entities]

    def get_threads_by_intent(self, intent: str) -> List[ConversationThread]:
        """Get threads related to an intent."""
        return [t for t in self.get_all_threads() if intent in t.related_intents]

    def has_active_thread(self) -> bool:
        """Check if there is an active thread."""
        return self._primary_thread is not None

    def has_paused_threads(self) -> bool:
        """Check if there are paused threads."""
        return len(self._paused_threads) > 0

    def get_suggested_resumptions(self, max_count: int = 3) -> List[Dict[str, Any]]:
        """
        Get suggested thread resumptions for user.

        Args:
            max_count: Maximum suggestions to return

        Returns:
            List of resumption suggestions with thread info and hints
        """
        suggestions = []
        for thread in self._paused_threads[:max_count]:
            hint = self._generate_resumption_hint(thread)
            suggestions.append(
                {
                    "thread_id": thread.id,
                    "title": thread.title,
                    "goal": thread.goal,
                    "hint": hint,
                    "paused_since_turn": thread.last_active_turn,
                    "turns_active": thread.turns_active(),
                }
            )
        return suggestions

    # =========================================================================
    # Arc Operations
    # =========================================================================

    def set_inciting_incident(self, turn_number: int) -> None:
        """Mark turn as the inciting incident (main goal established)."""
        self._arc.set_inciting_incident(turn_number)
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def set_climax(self, turn_number: int) -> None:
        """Mark turn as the climax (key decision moment)."""
        self._arc.set_climax(turn_number)
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def update_arc_boundaries(
        self,
        exposition_end: Optional[int] = None,
        rising_end: Optional[int] = None,
        climax_end: Optional[int] = None,
    ) -> None:
        """Update arc phase boundaries."""
        if exposition_end is not None:
            self._arc.exposition_end = exposition_end
        if rising_end is not None:
            self._arc.rising_end = rising_end
        if climax_end is not None:
            self._arc.climax_end = climax_end

        self._arc.update_for_turn(self._current_turn)
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def is_exposition(self) -> bool:
        """Check if in exposition phase."""
        return self._arc.position == ArcPosition.EXPOSITION

    def is_rising_action(self) -> bool:
        """Check if in rising action phase."""
        return self._arc.position == ArcPosition.RISING_ACTION

    def is_climax(self) -> bool:
        """Check if in climax phase."""
        return self._arc.position == ArcPosition.CLIMAX

    def is_resolution(self) -> bool:
        """Check if in resolution phase."""
        return self._arc.position == ArcPosition.RESOLUTION

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

        builder = flatbuffers.Builder(4096)

        # Build archived thread IDs vector
        archived_offsets = [
            builder.CreateString(tid) for tid in reversed(self._archived_thread_ids)
        ]
        NarrativeActiveSectionStartArchivedThreadIdsVector(builder, len(archived_offsets))
        for offset in archived_offsets:
            builder.PrependUOffsetTRelative(offset)
        archived_vector = builder.EndVector()

        # Build paused threads
        paused_offsets = []
        for thread in reversed(self._paused_threads):
            offset = self._build_thread(builder, thread)
            paused_offsets.append(offset)

        NarrativeActiveSectionStartPausedThreadsVector(builder, len(paused_offsets))
        for offset in paused_offsets:
            builder.PrependUOffsetTRelative(offset)
        paused_vector = builder.EndVector()

        # Build primary thread
        primary_offset = None
        if self._primary_thread:
            primary_offset = self._build_thread(builder, self._primary_thread)

        # Build arc
        NarrativeArcStart(builder)
        NarrativeArcAddPosition(builder, int(self._arc.position))
        NarrativeArcAddExpositionEnd(builder, self._arc.exposition_end)
        NarrativeArcAddRisingEnd(builder, self._arc.rising_end)
        NarrativeArcAddClimaxEnd(builder, self._arc.climax_end)
        NarrativeArcAddIncitingIncidentTurn(builder, self._arc.inciting_incident_turn)
        NarrativeArcAddClimaxTurn(builder, self._arc.climax_turn)
        NarrativeArcAddProgress(builder, self._arc.progress)
        arc_offset = NarrativeArcEnd(builder)

        # Build header
        name_offset = builder.CreateString(self.SECTION_NAME)
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # Build strings
        current_thread_id_offset = None
        if self.current_thread_id:
            current_thread_id_offset = builder.CreateString(self.current_thread_id)
        resumption_hint_offset = None
        if self.resumption_hint:
            resumption_hint_offset = builder.CreateString(self.resumption_hint)

        # Build NarrativeActiveSection
        NarrativeActiveSectionStart(builder)
        NarrativeActiveSectionAddHeader(builder, header_offset)
        if primary_offset:
            NarrativeActiveSectionAddPrimaryThread(builder, primary_offset)
        NarrativeActiveSectionAddPausedThreads(builder, paused_vector)
        NarrativeActiveSectionAddTotalThreadsSession(builder, self._total_threads_session)
        NarrativeActiveSectionAddActiveThreadCount(builder, self.active_thread_count)
        NarrativeActiveSectionAddPausedThreadCount(builder, self.paused_thread_count)
        NarrativeActiveSectionAddArc(builder, arc_offset)
        if current_thread_id_offset:
            NarrativeActiveSectionAddCurrentThreadId(builder, current_thread_id_offset)
        if resumption_hint_offset:
            NarrativeActiveSectionAddResumptionHint(builder, resumption_hint_offset)
        NarrativeActiveSectionAddArchivedThreadIds(builder, archived_vector)
        section_offset = NarrativeActiveSectionEnd(builder)

        builder.Finish(section_offset)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def _build_thread(self, builder: flatbuffers.Builder, thread: ConversationThread) -> int:
        """Build a ConversationThread in the FlatBuffer builder."""
        # Build strings first
        id_offset = builder.CreateString(thread.id)
        title_offset = builder.CreateString(thread.title) if thread.title else None
        goal_offset = builder.CreateString(thread.goal) if thread.goal else None
        hint_offset = (
            builder.CreateString(thread.resumption_hint) if thread.resumption_hint else None
        )
        summary_offset = (
            builder.CreateString(thread.context_summary) if thread.context_summary else None
        )

        # Build entity vector
        entity_offsets = [builder.CreateString(e) for e in reversed(thread.related_entities)]
        ConversationThreadStartRelatedEntitiesVector(builder, len(entity_offsets))
        for offset in entity_offsets:
            builder.PrependUOffsetTRelative(offset)
        entities_vector = builder.EndVector()

        # Build intent vector
        intent_offsets = [builder.CreateString(i) for i in reversed(thread.related_intents)]
        ConversationThreadStartRelatedIntentsVector(builder, len(intent_offsets))
        for offset in intent_offsets:
            builder.PrependUOffsetTRelative(offset)
        intents_vector = builder.EndVector()

        # Build thread
        ConversationThreadStart(builder)
        ConversationThreadAddId(builder, id_offset)
        if title_offset:
            ConversationThreadAddTitle(builder, title_offset)
        ConversationThreadAddState(builder, int(thread.state))
        ConversationThreadAddStartedTurn(builder, thread.started_turn)
        ConversationThreadAddLastActiveTurn(builder, thread.last_active_turn)
        ConversationThreadAddResolvedTurn(builder, thread.resolved_turn)
        if goal_offset:
            ConversationThreadAddGoal(builder, goal_offset)
        ConversationThreadAddIsGoalMet(builder, thread.is_goal_met)
        ConversationThreadAddRelatedEntities(builder, entities_vector)
        ConversationThreadAddRelatedIntents(builder, intents_vector)
        if hint_offset:
            ConversationThreadAddResumptionHint(builder, hint_offset)
        if summary_offset:
            ConversationThreadAddContextSummary(builder, summary_offset)

        return ConversationThreadEnd(builder)

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize from FlatBuffer bytes.

        Args:
            data: FlatBuffer binary data
        """
        fb = FBNarrativeActiveSection.GetRootAsNarrativeActiveSection(data, 0)

        self._thread_index.clear()
        self._paused_threads.clear()
        self._archived_thread_ids.clear()

        # Restore primary thread
        primary_fb = fb.PrimaryThread()
        if primary_fb:
            self._primary_thread = self._parse_thread(primary_fb)
            self._thread_index[self._primary_thread.id] = self._primary_thread
        else:
            self._primary_thread = None

        # Restore paused threads
        for i in range(fb.PausedThreadsLength()):
            thread_fb = fb.PausedThreads(i)
            if thread_fb:
                thread = self._parse_thread(thread_fb)
                self._paused_threads.append(thread)
                self._thread_index[thread.id] = thread

        # Restore archived IDs
        for i in range(fb.ArchivedThreadIdsLength()):
            tid = fb.ArchivedThreadIds(i)
            if tid:
                self._archived_thread_ids.append(
                    tid.decode("utf-8") if isinstance(tid, bytes) else tid
                )

        # Restore counts
        self._total_threads_session = fb.TotalThreadsSession()

        # Restore arc
        arc_fb = fb.Arc()
        if arc_fb:
            self._arc = NarrativeArc(
                position=ArcPosition(arc_fb.Position()),
                exposition_end=arc_fb.ExpositionEnd(),
                rising_end=arc_fb.RisingEnd(),
                climax_end=arc_fb.ClimaxEnd(),
                inciting_incident_turn=arc_fb.IncitingIncidentTurn(),
                climax_turn=arc_fb.ClimaxTurn(),
                progress=arc_fb.Progress(),
            )
        else:
            self._arc = NarrativeArc()

        # Update current turn from threads
        if self._primary_thread:
            self._current_turn = self._primary_thread.last_active_turn
        elif self._paused_threads:
            self._current_turn = max(t.last_active_turn for t in self._paused_threads)

        self._last_updated_ms = (
            fb.Header().LastUpdatedMs() if fb.Header() else int(time.time() * 1000)
        )

        self._cached_bytes = data
        self._cache_valid = True

    def _parse_thread(self, fb) -> ConversationThread:
        """Parse a ConversationThread from FlatBuffer."""
        id_bytes = fb.Id()
        title_bytes = fb.Title()
        goal_bytes = fb.Goal()
        hint_bytes = fb.ResumptionHint()
        summary_bytes = fb.ContextSummary()

        entities = []
        for i in range(fb.RelatedEntitiesLength()):
            e = fb.RelatedEntities(i)
            if e:
                entities.append(e.decode("utf-8") if isinstance(e, bytes) else e)

        intents = []
        for i in range(fb.RelatedIntentsLength()):
            intent = fb.RelatedIntents(i)
            if intent:
                intents.append(intent.decode("utf-8") if isinstance(intent, bytes) else intent)

        return ConversationThread(
            id=id_bytes.decode("utf-8") if isinstance(id_bytes, bytes) else (id_bytes or ""),
            title=(
                title_bytes.decode("utf-8")
                if isinstance(title_bytes, bytes)
                else (title_bytes or "")
            ),
            state=ThreadState(fb.State()),
            started_turn=fb.StartedTurn(),
            last_active_turn=fb.LastActiveTurn(),
            resolved_turn=fb.ResolvedTurn(),
            goal=(
                goal_bytes.decode("utf-8") if isinstance(goal_bytes, bytes) else (goal_bytes or "")
            ),
            is_goal_met=fb.IsGoalMet(),
            related_entities=entities,
            related_intents=intents,
            resumption_hint=(
                hint_bytes.decode("utf-8") if isinstance(hint_bytes, bytes) else (hint_bytes or "")
            ),
            context_summary=(
                summary_bytes.decode("utf-8")
                if isinstance(summary_bytes, bytes)
                else (summary_bytes or "")
            ),
        )

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
        - create_thread: Create new thread
        - switch_to: Switch to thread
        - pause_thread: Pause thread
        - resolve_thread: Mark thread resolved
        - archive_thread: Archive thread
        - update_thread: Update thread metadata
        - record_turn: Record a turn
        - clear: Reset to initial state
        """
        if operation == "create_thread":
            thread = self.create_thread(
                title=data.get("title", ""),
                goal=data.get("goal", ""),
                turn_number=data.get("turn_number"),
                related_entities=data.get("related_entities"),
                related_intents=data.get("related_intents"),
                auto_switch=data.get("auto_switch", True),
            )
            return thread.id

        elif operation == "switch_to":
            return self.switch_to(
                thread_id=data.get("thread_id", ""),
                turn_number=data.get("turn_number"),
            )

        elif operation == "pause_thread":
            return self.pause_thread(thread_id=data.get("thread_id", ""))

        elif operation == "resolve_thread":
            return self.resolve_thread(
                thread_id=data.get("thread_id", ""),
                turn_number=data.get("turn_number"),
            )

        elif operation == "archive_thread":
            return self.archive_thread(thread_id=data.get("thread_id", ""))

        elif operation == "update_thread":
            return self.update_thread(
                thread_id=data.get("thread_id", ""),
                title=data.get("title"),
                goal=data.get("goal"),
                context_summary=data.get("context_summary"),
                turn_number=data.get("turn_number"),
            )

        elif operation == "record_turn":
            self.record_turn(turn_number=data.get("turn_number", self._current_turn + 1))
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

    def _pause_thread_internal(self, thread: ConversationThread) -> None:
        """Internal pause without updating timestamps."""
        thread.state = ThreadState.PAUSED
        thread.resumption_hint = self._generate_resumption_hint(thread)
        if thread not in self._paused_threads:
            self._paused_threads.append(thread)
            self._enforce_paused_limit()

    def _enforce_paused_limit(self) -> None:
        """Archive oldest paused threads if over limit."""
        while len(self._paused_threads) > MAX_PAUSED_THREADS:
            oldest = self._paused_threads.pop(0)
            oldest.state = ThreadState.ARCHIVED
            self._archived_thread_ids.append(oldest.id)
            if oldest.id in self._thread_index:
                del self._thread_index[oldest.id]

    def _generate_resumption_hint(self, thread: ConversationThread) -> str:
        """Generate a resumption hint for a thread."""
        if thread.context_summary:
            return f"Earlier, {thread.context_summary}"
        elif thread.goal:
            return f"Earlier, you were working on: {thread.goal}"
        elif thread.title:
            return DEFAULT_RESUMPTION_TEMPLATE.format(title=thread.title)
        return ""


# =============================================================================
# Factory function
# =============================================================================


def create_narrative_active_section(
    session_id: str = "",
    initial_thread_title: Optional[str] = None,
    initial_thread_goal: Optional[str] = None,
) -> NarrativeActiveSection:
    """
    Factory function to create NarrativeActiveSection with initial state.

    Args:
        session_id: Session UUID (generated if empty)
        initial_thread_title: Title for initial thread (creates thread if provided)
        initial_thread_goal: Goal for initial thread

    Returns:
        Configured NarrativeActiveSection
    """
    section = NarrativeActiveSection(session_id=session_id)

    if initial_thread_title:
        section.create_thread(
            title=initial_thread_title,
            goal=initial_thread_goal or "",
            turn_number=1,
        )

    return section
