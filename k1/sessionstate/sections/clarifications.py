"""
ClarificationsSection - Pending Clarification Requests (HOT CORE)
===================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.5 (clarifications)

This section tracks pending clarification requests from agents that need
user input before proceeding. It prevents duplicate questions and manages
question lifecycle (open, answered, expired, cancelled).

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/clarifications_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- pending: [Clarification] - Max ~20 clarifications
- recently_resolved: [Clarification] - Last 5 resolved
- total_pending: uint16
- total_resolved_session: uint32
- avg_resolution_time_ms: uint32
- is_blocked: bool
- blocking_clarification_id: string
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

import flatbuffers

# Generated FlatBuffer types
from k1.sessionstate.generated.flatbuffers.K1.SessionState import (
    ClarificationsSection as FBClarificationsSection,
)

# Import builder functions from individual files
from k1.sessionstate.generated.flatbuffers.K1.SessionState.Clarification import (
    ClarificationAddAgentId,
    ClarificationAddAnswer,
    ClarificationAddAnsweredAtMs,
    ClarificationAddCreatedAtMs,
    ClarificationAddId,
    ClarificationAddOptions,
    ClarificationAddPriority,
    ClarificationAddQuestion,
    ClarificationAddRelatedEntity,
    ClarificationAddRelatedIntent,
    ClarificationAddSelectedOptionId,
    ClarificationAddStatus,
    ClarificationAddTimeoutMs,
    ClarificationEnd,
    ClarificationStart,
    ClarificationStartOptionsVector,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.ClarificationOption import (
    ClarificationOptionAddAction,
    ClarificationOptionAddConfidence,
    ClarificationOptionAddId,
    ClarificationOptionAddText,
    ClarificationOptionEnd,
    ClarificationOptionStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.ClarificationsSection import (
    ClarificationsSectionAddAvgResolutionTimeMs,
    ClarificationsSectionAddBlockingClarificationId,
    ClarificationsSectionAddHeader,
    ClarificationsSectionAddIsBlocked,
    ClarificationsSectionAddPending,
    ClarificationsSectionAddRecentlyResolved,
    ClarificationsSectionAddTotalPending,
    ClarificationsSectionAddTotalResolvedSession,
    ClarificationsSectionEnd,
    ClarificationsSectionStart,
    ClarificationsSectionStartPendingVector,
    ClarificationsSectionStartRecentlyResolvedVector,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)

# =============================================================================
# Enums matching FlatBuffer schema (common.fbs)
# =============================================================================


class QuestionStatus(IntEnum):
    """Question/clarification status per common.fbs."""

    OPEN = 0  # Awaiting answer
    ANSWERED = 1  # User responded
    EXPIRED = 2  # Timed out
    CANCELLED = 3  # Agent cancelled


class ClarificationPriority(IntEnum):
    """Clarification priority levels per schema."""

    NORMAL = 0
    HIGH = 1
    URGENT = 2


# =============================================================================
# Data Classes matching FlatBuffer schema
# =============================================================================


@dataclass
class ClarificationOption:
    """
    Single option for a clarification question.

    Maps to ClarificationOption table in clarifications_section.fbs:
    - id: string (required)
    - text: string (required)
    - action: string
    - confidence: float = 0.5
    """

    id: str
    text: str
    action: str = ""
    confidence: float = 0.5


@dataclass
class Clarification:
    """
    Clarification request from an agent.

    Maps to Clarification table in clarifications_section.fbs:
    - id: string (required)
    - agent_id: string (required)
    - question: string (required)
    - options: [ClarificationOption]
    - created_at_ms: int64
    - priority: uint8 = 0
    - status: QuestionStatus = OPEN
    - related_entity: string
    - related_intent: string
    - timeout_ms: int64
    - answered_at_ms: int64
    - answer: string
    - selected_option_id: string
    """

    id: str
    agent_id: str
    question: str
    options: List[ClarificationOption] = field(default_factory=list)
    created_at_ms: int = 0
    priority: ClarificationPriority = ClarificationPriority.NORMAL
    status: QuestionStatus = QuestionStatus.OPEN
    related_entity: str = ""
    related_intent: str = ""
    timeout_ms: int = 0
    answered_at_ms: int = 0
    answer: str = ""
    selected_option_id: str = ""

    # Runtime-only fields (not serialized)
    is_blocking: bool = False


# =============================================================================
# ClarificationsSection Implementation
# =============================================================================


class ClarificationsSection:
    """
    Clarifications Section - pending questions requiring user input.

    This section tracks clarification requests from agents. It maintains
    pending requests, recently resolved requests for context, and statistics
    about resolution times.

    Budget: 4KB (4096 bytes)
    Tier: HOT CORE
    Eviction: Cannot evict section

    FlatBuffer Schema: clarifications_section.fbs
    Serialization Target: <100 microseconds

    Contents per schema:
    - pending: [Clarification] - Max ~20 clarifications
    - recently_resolved: [Clarification] - Last 5 resolved
    - total_pending: uint16
    - total_resolved_session: uint32
    - avg_resolution_time_ms: uint32
    - is_blocked: bool
    - blocking_clarification_id: string

    Example:
        section = ClarificationsSection(session_id="sess-123")

        # Request clarification with options
        clarification = section.request(
            agent_id="planner",
            question="Do you want the short or detailed version?",
            options=[
                ClarificationOption(id="1", text="Short"),
                ClarificationOption(id="2", text="Detailed"),
            ],
        )

        # Answer the clarification
        section.answer(clarification.id, "Short", selected_option_id="1")

        # Check if blocked
        if section.is_blocked:
            print(f"Blocked by: {section.blocking_clarification_id}")
    """

    BUDGET_BYTES = 4096  # 4KB
    TIER = "hot"
    CAN_EVICT = False
    SECTION_NAME = "clarifications"
    SCHEMA_VERSION = "1.0.0"
    MAX_PENDING = 20  # Per schema budget notes
    MAX_RECENTLY_RESOLVED = 5  # Last 5 resolved
    DEFAULT_TIMEOUT_MS = 5 * 60 * 1000  # 5 minutes

    def __init__(
        self,
        session_id: str = "",
        schema_version: str = "",
    ) -> None:
        """
        Initialize ClarificationsSection.

        Args:
            session_id: Session UUID (generated if empty)
            schema_version: Schema version (uses default if empty)
        """
        now_ms = int(time.time() * 1000)

        self._session_id = session_id or str(uuid.uuid4())
        self._schema_version = schema_version or self.SCHEMA_VERSION
        self._last_updated_ms = now_ms

        # Core state per schema
        self._pending: Dict[str, Clarification] = {}
        self._recently_resolved: List[Clarification] = []

        # Statistics per schema
        self._total_resolved_session: int = 0
        self._total_resolution_time_ms: int = 0  # For computing average

        # Blocking state per schema
        self._is_blocked: bool = False
        self._blocking_clarification_id: str = ""

        # Indexes for fast lookup (runtime optimization)
        self._by_agent: Dict[str, List[str]] = {}
        self._by_entity: Dict[str, List[str]] = {}
        self._by_intent: Dict[str, List[str]] = {}

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
    def is_blocked(self) -> bool:
        """Whether conversation is blocked waiting for clarification."""
        return self._is_blocked

    @property
    def blocking_clarification_id(self) -> str:
        """ID of the blocking clarification if is_blocked is True."""
        return self._blocking_clarification_id

    @property
    def total_pending(self) -> int:
        """Count of pending clarifications."""
        return len(self._pending)

    @property
    def total_resolved_session(self) -> int:
        """Total clarifications resolved in this session."""
        return self._total_resolved_session

    @property
    def avg_resolution_time_ms(self) -> int:
        """Average resolution time in milliseconds."""
        if self._total_resolved_session == 0:
            return 0
        return self._total_resolution_time_ms // self._total_resolved_session

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

        Uses cached value if available, otherwise computes estimate.
        Size budget breakdown per schema:
        - Header: ~100 bytes
        - Clarification: ~150 bytes each x 20 = 3KB
        - Recently resolved: ~150 bytes x 5 = 750 bytes
        - Stats + blocking: ~50 bytes
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 100  # Header overhead
        size += len(self._pending) * 150  # ~150 bytes per clarification
        size += len(self._recently_resolved) * 150  # ~150 bytes per resolved
        size += 50  # stats + blocking fields
        size += len(self._blocking_clarification_id) if self._blocking_clarification_id else 0

        return min(size, self.BUDGET_BYTES)

    def clear(self) -> None:
        """Clear all section data."""
        self._pending.clear()
        self._recently_resolved.clear()
        self._by_agent.clear()
        self._by_entity.clear()
        self._by_intent.clear()
        self._total_resolved_session = 0
        self._total_resolution_time_ms = 0
        self._is_blocked = False
        self._blocking_clarification_id = ""
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
            "pending_count": len(self._pending),
            "recently_resolved_count": len(self._recently_resolved),
            "total_resolved_session": self._total_resolved_session,
            "avg_resolution_time_ms": self.avg_resolution_time_ms,
            "is_blocked": self._is_blocked,
            "blocking_clarification_id": self._blocking_clarification_id,
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Clarification Request Operations
    # =========================================================================

    def request(
        self,
        agent_id: str,
        question: str,
        options: Optional[List[ClarificationOption]] = None,
        priority: ClarificationPriority = ClarificationPriority.NORMAL,
        related_entity: str = "",
        related_intent: str = "",
        timeout_ms: int = 0,
        blocking: bool = False,
        clarification_id: str = "",
    ) -> Clarification:
        """
        Request a clarification from the user.

        Args:
            agent_id: Agent requesting clarification
            question: Question text for user
            options: Optional list of predefined options
            priority: Priority level (NORMAL, HIGH, URGENT)
            related_entity: Entity this question is about
            related_intent: Intent that triggered this question
            timeout_ms: Custom timeout (default 5min)
            blocking: Whether this blocks conversation
            clarification_id: Optional custom ID (generated if empty)

        Returns:
            Created Clarification object

        Raises:
            ValueError: If max pending clarifications reached
        """
        if len(self._pending) >= self.MAX_PENDING:
            raise ValueError(f"Maximum pending clarifications ({self.MAX_PENDING}) reached")

        now_ms = int(time.time() * 1000)
        cid = clarification_id or str(uuid.uuid4())
        timeout = timeout_ms or self.DEFAULT_TIMEOUT_MS

        clarification = Clarification(
            id=cid,
            agent_id=agent_id,
            question=question,
            options=options or [],
            created_at_ms=now_ms,
            priority=priority,
            status=QuestionStatus.OPEN,
            related_entity=related_entity,
            related_intent=related_intent,
            timeout_ms=timeout,
            is_blocking=blocking,
        )

        self._pending[cid] = clarification

        # Update indexes
        self._by_agent.setdefault(agent_id, []).append(cid)
        if related_entity:
            self._by_entity.setdefault(related_entity, []).append(cid)
        if related_intent:
            self._by_intent.setdefault(related_intent, []).append(cid)

        # Update blocking state
        if blocking:
            self._is_blocked = True
            self._blocking_clarification_id = cid

        self._invalidate_cache()
        self._touch()
        return clarification

    def get(self, clarification_id: str) -> Optional[Clarification]:
        """
        Get clarification by ID.

        Args:
            clarification_id: Clarification UUID

        Returns:
            Clarification or None
        """
        return self._pending.get(clarification_id)

    def answer(
        self,
        clarification_id: str,
        answer: str,
        selected_option_id: str = "",
    ) -> bool:
        """
        Answer a pending clarification.

        Args:
            clarification_id: Clarification to answer
            answer: User's answer text
            selected_option_id: ID of selected option (if applicable)

        Returns:
            bool: True if found and answered
        """
        if clarification_id not in self._pending:
            return False

        now_ms = int(time.time() * 1000)
        clarification = self._pending[clarification_id]

        # Update clarification
        clarification.status = QuestionStatus.ANSWERED
        clarification.answer = answer
        clarification.selected_option_id = selected_option_id
        clarification.answered_at_ms = now_ms

        # Calculate resolution time
        resolution_time_ms = now_ms - clarification.created_at_ms
        self._total_resolution_time_ms += resolution_time_ms
        self._total_resolved_session += 1

        # Move to recently resolved
        self._move_to_resolved(clarification_id)

        # Update blocking state
        if self._blocking_clarification_id == clarification_id:
            self._is_blocked = False
            self._blocking_clarification_id = ""

        self._invalidate_cache()
        self._touch()
        return True

    def cancel(self, clarification_id: str) -> bool:
        """
        Cancel a pending clarification.

        Args:
            clarification_id: Clarification to cancel

        Returns:
            bool: True if found and cancelled
        """
        if clarification_id not in self._pending:
            return False

        clarification = self._pending[clarification_id]
        clarification.status = QuestionStatus.CANCELLED

        # Move to recently resolved
        self._move_to_resolved(clarification_id)

        # Update blocking state
        if self._blocking_clarification_id == clarification_id:
            self._is_blocked = False
            self._blocking_clarification_id = ""

        self._invalidate_cache()
        self._touch()
        return True

    def expire(self, clarification_id: str) -> bool:
        """
        Mark a clarification as expired.

        Args:
            clarification_id: Clarification to expire

        Returns:
            bool: True if found and expired
        """
        if clarification_id not in self._pending:
            return False

        clarification = self._pending[clarification_id]
        clarification.status = QuestionStatus.EXPIRED

        # Move to recently resolved
        self._move_to_resolved(clarification_id)

        # Update blocking state
        if self._blocking_clarification_id == clarification_id:
            self._is_blocked = False
            self._blocking_clarification_id = ""

        self._invalidate_cache()
        self._touch()
        return True

    def expire_old(self) -> int:
        """
        Expire all clarifications that have exceeded their timeout.

        Returns:
            int: Number of clarifications expired
        """
        now_ms = int(time.time() * 1000)
        expired_ids = []

        for cid, clarification in self._pending.items():
            if clarification.timeout_ms > 0:
                expiry_time = clarification.created_at_ms + clarification.timeout_ms
                if now_ms > expiry_time:
                    expired_ids.append(cid)

        for cid in expired_ids:
            self.expire(cid)

        return len(expired_ids)

    # =========================================================================
    # Query Operations
    # =========================================================================

    def list_pending(self) -> List[Clarification]:
        """
        Get all pending clarifications ordered by priority and creation time.

        Returns:
            List[Clarification]: Pending clarifications
        """
        pending = list(self._pending.values())
        # Sort by priority (descending) then by creation time (ascending)
        pending.sort(key=lambda c: (-c.priority, c.created_at_ms))
        return pending

    def list_recently_resolved(self) -> List[Clarification]:
        """
        Get recently resolved clarifications.

        Returns:
            List[Clarification]: Recently resolved (up to 5)
        """
        return list(self._recently_resolved)

    def find_by_agent(self, agent_id: str) -> List[Clarification]:
        """
        Find pending clarifications by agent.

        Args:
            agent_id: Agent identifier

        Returns:
            List[Clarification]: Matching clarifications
        """
        cids = self._by_agent.get(agent_id, [])
        return [self._pending[cid] for cid in cids if cid in self._pending]

    def find_by_entity(self, entity: str) -> List[Clarification]:
        """
        Find pending clarifications by related entity.

        Args:
            entity: Entity identifier

        Returns:
            List[Clarification]: Matching clarifications
        """
        cids = self._by_entity.get(entity, [])
        return [self._pending[cid] for cid in cids if cid in self._pending]

    def find_by_intent(self, intent: str) -> List[Clarification]:
        """
        Find pending clarifications by related intent.

        Args:
            intent: Intent identifier

        Returns:
            List[Clarification]: Matching clarifications
        """
        cids = self._by_intent.get(intent, [])
        return [self._pending[cid] for cid in cids if cid in self._pending]

    def is_already_asked(
        self,
        question: str,
        agent_id: str = "",
        threshold: float = 0.9,
    ) -> bool:
        """
        Check if a similar question is already pending.

        Uses simple string matching. For production, consider fuzzy matching.

        Args:
            question: Question to check
            agent_id: Optional agent filter
            threshold: Similarity threshold (not yet implemented)

        Returns:
            bool: True if similar question exists
        """
        question_lower = question.lower().strip()

        for clarification in self._pending.values():
            if agent_id and clarification.agent_id != agent_id:
                continue
            if clarification.question.lower().strip() == question_lower:
                return True

        return False

    def has_pending(self) -> bool:
        """Check if there are any pending clarifications."""
        return len(self._pending) > 0

    def get_blocking(self) -> Optional[Clarification]:
        """
        Get the blocking clarification if any.

        Returns:
            Clarification or None
        """
        if self._is_blocked and self._blocking_clarification_id:
            return self._pending.get(self._blocking_clarification_id)
        return None

    def set_blocking(self, clarification_id: str) -> bool:
        """
        Set a clarification as blocking.

        Args:
            clarification_id: Clarification to set as blocking

        Returns:
            bool: True if found and set
        """
        if clarification_id not in self._pending:
            return False

        self._is_blocked = True
        self._blocking_clarification_id = clarification_id
        self._pending[clarification_id].is_blocking = True

        self._invalidate_cache()
        self._touch()
        return True

    def clear_blocking(self) -> None:
        """Clear the blocking state."""
        if self._blocking_clarification_id and self._blocking_clarification_id in self._pending:
            self._pending[self._blocking_clarification_id].is_blocking = False
        self._is_blocked = False
        self._blocking_clarification_id = ""
        self._invalidate_cache()
        self._touch()

    # =========================================================================
    # Option Management
    # =========================================================================

    def add_option(
        self,
        clarification_id: str,
        option_id: str,
        text: str,
        action: str = "",
        confidence: float = 0.5,
    ) -> bool:
        """
        Add an option to an existing clarification.

        Args:
            clarification_id: Clarification to add option to
            option_id: Unique option ID
            text: Option text
            action: Action to take if selected
            confidence: System confidence this is correct

        Returns:
            bool: True if option added
        """
        if clarification_id not in self._pending:
            return False

        clarification = self._pending[clarification_id]
        option = ClarificationOption(
            id=option_id,
            text=text,
            action=action,
            confidence=confidence,
        )
        clarification.options.append(option)

        self._invalidate_cache()
        self._touch()
        return True

    def get_options(self, clarification_id: str) -> List[ClarificationOption]:
        """
        Get options for a clarification.

        Args:
            clarification_id: Clarification ID

        Returns:
            List of options or empty list
        """
        clarification = self._pending.get(clarification_id)
        if clarification:
            return list(clarification.options)
        return []

    # =========================================================================
    # Priority Management
    # =========================================================================

    def update_priority(
        self,
        clarification_id: str,
        priority: ClarificationPriority,
    ) -> bool:
        """
        Update clarification priority.

        Args:
            clarification_id: Clarification to update
            priority: New priority level

        Returns:
            bool: True if updated
        """
        if clarification_id not in self._pending:
            return False

        self._pending[clarification_id].priority = priority
        self._invalidate_cache()
        self._touch()
        return True

    def get_urgent(self) -> List[Clarification]:
        """
        Get urgent (priority=2) clarifications.

        Returns:
            List of urgent clarifications
        """
        return [c for c in self._pending.values() if c.priority == ClarificationPriority.URGENT]

    def get_high_priority(self) -> List[Clarification]:
        """
        Get high priority (priority>=1) clarifications.

        Returns:
            List of high priority clarifications
        """
        return [c for c in self._pending.values() if c.priority >= ClarificationPriority.HIGH]

    # =========================================================================
    # FlatBuffer Serialization
    # =========================================================================

    def to_flatbuffer(self) -> bytes:
        """
        Serialize section to FlatBuffer bytes.

        Returns:
            bytes: FlatBuffer-encoded data per clarifications_section.fbs

        Performance Target: <100 microseconds
        """
        if self._cache_valid and self._cached_bytes:
            return self._cached_bytes

        builder = flatbuffers.Builder(self.BUDGET_BYTES)

        # Build section name for header
        section_name_offset = builder.CreateString(self.SECTION_NAME)

        # Build blocking_clarification_id string
        blocking_id_offset = 0
        if self._blocking_clarification_id:
            blocking_id_offset = builder.CreateString(self._blocking_clarification_id)

        # Helper function to build clarification
        def build_clarification(clarification: Clarification) -> int:
            # Build strings first
            id_off = builder.CreateString(clarification.id)
            agent_id_off = builder.CreateString(clarification.agent_id)
            question_off = builder.CreateString(clarification.question)
            related_entity_off = builder.CreateString(clarification.related_entity)
            related_intent_off = builder.CreateString(clarification.related_intent)
            answer_off = builder.CreateString(clarification.answer)
            selected_option_id_off = builder.CreateString(clarification.selected_option_id)

            # Build options vector
            option_offsets = []
            for opt in clarification.options:
                opt_id_off = builder.CreateString(opt.id)
                opt_text_off = builder.CreateString(opt.text)
                opt_action_off = builder.CreateString(opt.action)

                ClarificationOptionStart(builder)
                ClarificationOptionAddId(builder, opt_id_off)
                ClarificationOptionAddText(builder, opt_text_off)
                ClarificationOptionAddAction(builder, opt_action_off)
                ClarificationOptionAddConfidence(builder, opt.confidence)
                option_offsets.append(ClarificationOptionEnd(builder))

            options_vector = 0
            if option_offsets:
                ClarificationStartOptionsVector(builder, len(option_offsets))
                for offset in reversed(option_offsets):
                    builder.PrependUOffsetTRelative(offset)
                options_vector = builder.EndVector()

            # Build clarification
            ClarificationStart(builder)
            ClarificationAddId(builder, id_off)
            ClarificationAddAgentId(builder, agent_id_off)
            ClarificationAddQuestion(builder, question_off)
            if options_vector:
                ClarificationAddOptions(builder, options_vector)
            ClarificationAddCreatedAtMs(builder, clarification.created_at_ms)
            ClarificationAddPriority(builder, int(clarification.priority))
            ClarificationAddStatus(builder, int(clarification.status))
            ClarificationAddRelatedEntity(builder, related_entity_off)
            ClarificationAddRelatedIntent(builder, related_intent_off)
            ClarificationAddTimeoutMs(builder, clarification.timeout_ms)
            ClarificationAddAnsweredAtMs(builder, clarification.answered_at_ms)
            ClarificationAddAnswer(builder, answer_off)
            ClarificationAddSelectedOptionId(builder, selected_option_id_off)
            return ClarificationEnd(builder)

        # Build pending vector (ordered by priority, then creation)
        pending_list = self.list_pending()
        pending_offsets = [build_clarification(c) for c in pending_list]

        pending_vector = 0
        if pending_offsets:
            ClarificationsSectionStartPendingVector(builder, len(pending_offsets))
            for offset in reversed(pending_offsets):
                builder.PrependUOffsetTRelative(offset)
            pending_vector = builder.EndVector()

        # Build recently_resolved vector
        resolved_offsets = [build_clarification(c) for c in self._recently_resolved]

        resolved_vector = 0
        if resolved_offsets:
            ClarificationsSectionStartRecentlyResolvedVector(builder, len(resolved_offsets))
            for offset in reversed(resolved_offsets):
                builder.PrependUOffsetTRelative(offset)
            resolved_vector = builder.EndVector()

        # Build header
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # Build ClarificationsSection root
        ClarificationsSectionStart(builder)
        ClarificationsSectionAddHeader(builder, header_offset)
        if pending_vector:
            ClarificationsSectionAddPending(builder, pending_vector)
        if resolved_vector:
            ClarificationsSectionAddRecentlyResolved(builder, resolved_vector)
        ClarificationsSectionAddTotalPending(builder, len(self._pending))
        ClarificationsSectionAddTotalResolvedSession(builder, self._total_resolved_session)
        ClarificationsSectionAddAvgResolutionTimeMs(builder, self.avg_resolution_time_ms)
        ClarificationsSectionAddIsBlocked(builder, self._is_blocked)
        if blocking_id_offset:
            ClarificationsSectionAddBlockingClarificationId(builder, blocking_id_offset)
        section_offset = ClarificationsSectionEnd(builder)

        builder.Finish(section_offset)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize section from FlatBuffer bytes.

        Args:
            data: FlatBuffer-encoded data per clarifications_section.fbs
        """
        fb = FBClarificationsSection.GetRootAsClarificationsSection(data, 0)

        # Clear current state
        self._pending.clear()
        self._recently_resolved.clear()
        self._by_agent.clear()
        self._by_entity.clear()
        self._by_intent.clear()

        # Helper to load clarification
        def load_clarification(fb_clarification) -> Clarification:
            # Load options
            options = []
            for j in range(fb_clarification.OptionsLength()):
                opt_fb = fb_clarification.Options(j)
                if opt_fb:
                    options.append(
                        ClarificationOption(
                            id=self._decode_string(opt_fb.Id()) or str(uuid.uuid4()),
                            text=self._decode_string(opt_fb.Text()) or "",
                            action=self._decode_string(opt_fb.Action()) or "",
                            confidence=opt_fb.Confidence(),
                        )
                    )

            return Clarification(
                id=self._decode_string(fb_clarification.Id()) or str(uuid.uuid4()),
                agent_id=self._decode_string(fb_clarification.AgentId()) or "",
                question=self._decode_string(fb_clarification.Question()) or "",
                options=options,
                created_at_ms=fb_clarification.CreatedAtMs(),
                priority=ClarificationPriority(fb_clarification.Priority()),
                status=QuestionStatus(fb_clarification.Status()),
                related_entity=self._decode_string(fb_clarification.RelatedEntity()) or "",
                related_intent=self._decode_string(fb_clarification.RelatedIntent()) or "",
                timeout_ms=fb_clarification.TimeoutMs(),
                answered_at_ms=fb_clarification.AnsweredAtMs(),
                answer=self._decode_string(fb_clarification.Answer()) or "",
                selected_option_id=self._decode_string(fb_clarification.SelectedOptionId()) or "",
            )

        # Load pending clarifications
        for i in range(fb.PendingLength()):
            fb_clarification = fb.Pending(i)
            if fb_clarification:
                clarification = load_clarification(fb_clarification)
                self._pending[clarification.id] = clarification

                # Rebuild indexes
                self._by_agent.setdefault(clarification.agent_id, []).append(clarification.id)
                if clarification.related_entity:
                    self._by_entity.setdefault(clarification.related_entity, []).append(
                        clarification.id
                    )
                if clarification.related_intent:
                    self._by_intent.setdefault(clarification.related_intent, []).append(
                        clarification.id
                    )

        # Load recently resolved
        for i in range(fb.RecentlyResolvedLength()):
            fb_clarification = fb.RecentlyResolved(i)
            if fb_clarification:
                clarification = load_clarification(fb_clarification)
                self._recently_resolved.append(clarification)

        # Load statistics
        self._total_resolved_session = fb.TotalResolvedSession()
        # Reconstruct total_resolution_time_ms from average
        avg_ms = fb.AvgResolutionTimeMs()
        self._total_resolution_time_ms = avg_ms * self._total_resolved_session

        # Load blocking state
        self._is_blocked = fb.IsBlocked()
        self._blocking_clarification_id = self._decode_string(fb.BlockingClarificationId()) or ""

        # Mark blocking clarification
        if self._blocking_clarification_id and self._blocking_clarification_id in self._pending:
            self._pending[self._blocking_clarification_id].is_blocking = True

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

    def get_pending(self) -> List[Clarification]:
        """Legacy alias for list_pending."""
        return self.list_pending()

    def get_answered(self) -> List[Clarification]:
        """Get answered clarifications from recently_resolved."""
        return [c for c in self._recently_resolved if c.status == QuestionStatus.ANSWERED]

    def apply(self, operation: str, data: dict) -> Any:
        """
        Apply mutation operation.

        Args:
            operation: Operation name (request, answer, cancel, expire)
            data: Operation data

        Returns:
            Operation result
        """
        if operation == "request":
            options = None
            if "options" in data:
                options = [
                    ClarificationOption(
                        id=opt.get("id", str(uuid.uuid4())),
                        text=opt.get("text", ""),
                        action=opt.get("action", ""),
                        confidence=opt.get("confidence", 0.5),
                    )
                    for opt in data.get("options", [])
                ]
            return self.request(
                agent_id=data.get("agent_id", ""),
                question=data.get("question", ""),
                options=options,
                priority=ClarificationPriority(data.get("priority", 0)),
                related_entity=data.get("related_entity", ""),
                related_intent=data.get("related_intent", ""),
                timeout_ms=data.get("timeout_ms", 0),
                blocking=data.get("blocking", False),
            )
        elif operation == "answer":
            return self.answer(
                clarification_id=data.get("clarification_id", ""),
                answer=data.get("answer", ""),
                selected_option_id=data.get("selected_option_id", ""),
            )
        elif operation == "cancel":
            return self.cancel(data.get("clarification_id", ""))
        elif operation == "expire":
            return self.expire(data.get("clarification_id", ""))
        elif operation == "expire_old":
            return self.expire_old()
        elif operation == "set_blocking":
            return self.set_blocking(data.get("clarification_id", ""))
        elif operation == "clear_blocking":
            self.clear_blocking()
            return True
        elif operation == "update_priority":
            return self.update_priority(
                clarification_id=data.get("clarification_id", ""),
                priority=ClarificationPriority(data.get("priority", 0)),
            )
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

    def _move_to_resolved(self, clarification_id: str) -> None:
        """Move clarification from pending to recently_resolved."""
        if clarification_id not in self._pending:
            return

        clarification = self._pending.pop(clarification_id)

        # Update indexes
        if clarification.agent_id in self._by_agent:
            self._by_agent[clarification.agent_id] = [
                cid for cid in self._by_agent[clarification.agent_id] if cid != clarification_id
            ]
        if clarification.related_entity in self._by_entity:
            self._by_entity[clarification.related_entity] = [
                cid
                for cid in self._by_entity[clarification.related_entity]
                if cid != clarification_id
            ]
        if clarification.related_intent in self._by_intent:
            self._by_intent[clarification.related_intent] = [
                cid
                for cid in self._by_intent[clarification.related_intent]
                if cid != clarification_id
            ]

        # Add to recently resolved (keep last 5)
        self._recently_resolved.append(clarification)
        if len(self._recently_resolved) > self.MAX_RECENTLY_RESOLVED:
            self._recently_resolved = self._recently_resolved[-self.MAX_RECENTLY_RESOLVED :]

    @staticmethod
    def _decode_string(value) -> Optional[str]:
        """Decode bytes to string if needed."""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value
