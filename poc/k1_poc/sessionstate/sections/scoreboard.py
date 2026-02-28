"""
ScoreboardSection - Discourse State Tracking (HOT CORE)
=========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.3 (scoreboard)

This section tracks the current discourse state - what's being talked
about and what's important. Implements the linguistic "scoreboard" model.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/scoreboard_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/
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
    QuestionAddAnsweredAtTurn,
    QuestionAddAnswerSummary,
    QuestionAddAskedAtTurn,
    QuestionAddAskedBy,
    QuestionAddId,
    QuestionAddPriority,
    QuestionAddStatus,
    QuestionAddText,
    QuestionEnd,
    QuestionStart,
    ReferentAddEntityId,
    ReferentAddEntityType,
    ReferentAddFirstMentionedTurn,
    ReferentAddId,
    ReferentAddLastMentionedTurn,
    ReferentAddMentionCount,
    ReferentAddSalience,
    ReferentAddText,
    ReferentEnd,
    ReferentStart,
    SalienceEntryAddDecayRate,
    SalienceEntryAddEntityId,
    SalienceEntryAddScore,
    SalienceEntryEnd,
    SalienceEntryStart,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    ScoreboardSection as FBScoreboardSection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    ScoreboardSectionAddCurrentTurn,
    ScoreboardSectionAddHeader,
    ScoreboardSectionAddLastUpdatedMs,
    ScoreboardSectionAddLastUserIntent,
    ScoreboardSectionAddLastUserIntentConfidence,
    ScoreboardSectionAddQudStack,
    ScoreboardSectionAddReferents,
    ScoreboardSectionAddSalienceMap,
    ScoreboardSectionAddTopicStack,
    ScoreboardSectionEnd,
    ScoreboardSectionStart,
    ScoreboardSectionStartQudStackVector,
    ScoreboardSectionStartReferentsVector,
    ScoreboardSectionStartSalienceMapVector,
    ScoreboardSectionStartTopicStackVector,
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
    TopicAddFirstTurn,
    TopicAddId,
    TopicAddIsPrimary,
    TopicAddLastTurn,
    TopicAddName,
    TopicAddSalience,
    TopicEnd,
    TopicStart,
)

# =============================================================================
# Enums matching FlatBuffer schema
# =============================================================================


class QuestionStatus(IntEnum):
    """Question Under Discussion (QUD) status."""

    OPEN = 0  # Question is still active
    ANSWERED = 1  # Question has been answered
    ABANDONED = 2  # Question was dropped
    DEFERRED = 3  # Question pushed back for later


# =============================================================================
# Data Classes for Domain Objects
# =============================================================================


@dataclass
class Referent:
    """
    Discourse referent - entity currently active in conversation.

    Referents are entities that have been introduced into the
    discourse and can be referred to with pronouns, demonstratives,
    or definite descriptions.
    """

    id: str
    text: str  # How it was mentioned
    entity_id: str = ""  # Link to entity if resolved
    entity_type: str = ""  # person, place, thing, etc.
    salience: float = 0.5  # How prominent (0.0-1.0)
    first_mentioned_turn: int = 0
    last_mentioned_turn: int = 0
    mention_count: int = 1


@dataclass
class Question:
    """
    Question Under Discussion (QUD).

    QUDs represent open conversational goals - things being discussed
    or asked that haven't been resolved yet.
    """

    id: str
    text: str
    status: QuestionStatus = QuestionStatus.OPEN
    asked_by: str = ""  # "user" or agent_id
    asked_at_turn: int = 0
    answered_at_turn: int = 0
    answer_summary: str = ""
    priority: int = 0  # Higher = more important


@dataclass
class Topic:
    """
    Conversation topic with salience score.

    Topics represent what the conversation is "about" at various
    levels of granularity.
    """

    id: str
    name: str
    salience: float = 0.5
    first_turn: int = 0
    last_turn: int = 0
    is_primary: bool = False


@dataclass
class SalienceEntry:
    """
    Salience map entry for entity tracking.

    Tracks how salient (prominent/important) each entity is
    in the current discourse context.
    """

    entity_id: str
    score: float = 0.0  # 0.0-1.0
    decay_rate: float = 0.1  # How fast salience decays per turn


# =============================================================================
# ScoreboardSection - Production Implementation
# =============================================================================


class ScoreboardSection:
    """
    Scoreboard Section - current discourse state.

    This section implements the linguistic "scoreboard" model that
    tracks:
    - Referents: What entities are being talked about
    - QUD Stack: What questions are under discussion
    - Salience Map: How prominent each entity is
    - Topic Stack: What topics are being discussed
    - Last User Intent: Most recent classified intent

    Budget: 6KB (6144 bytes)
    Tier: HOT CORE
    Eviction: No

    FlatBuffer Schema: scoreboard_section.fbs
    Serialization Target: <100 microseconds

    Example:
        section = ScoreboardSection()

        # Add a referent
        ref = section.add_referent(
            text="the car",
            entity_id="vehicle-123",
            entity_type="vehicle",
        )

        # Push a question
        q = section.push_question(
            text="What color is it?",
            asked_by="user",
        )

        # Update salience
        section.boost_salience("vehicle-123", 0.3)

        # Apply decay
        section.decay_salience()
    """

    BUDGET_BYTES = 6144  # 6KB
    TIER = "hot"
    CAN_EVICT = False
    SECTION_NAME = "scoreboard"
    SCHEMA_VERSION = "1.0.0"
    DEFAULT_DECAY_RATE = 0.1
    MIN_SALIENCE = 0.01  # Below this, entity is removed from map

    def __init__(self) -> None:
        """Initialize ScoreboardSection."""
        now_ms = int(time.time() * 1000)

        self._last_updated_ms = now_ms
        self._current_turn = 0

        # Core state
        self._referents: Dict[str, Referent] = {}
        self._qud_stack: List[Question] = []  # Stack (last = top)
        self._salience_map: Dict[str, SalienceEntry] = {}
        self._topic_stack: List[Topic] = []  # Stack (last = top)
        self._last_user_intent: str = ""
        self._last_user_intent_confidence: float = 0.0

        # Indexes
        self._referents_by_entity: Dict[str, str] = {}  # entity_id -> referent_id

        # Cached serialization
        self._cached_bytes: Optional[bytes] = None
        self._cache_valid = False

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
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 0

        # Header overhead (~50 bytes)
        size += 50

        # Referents (~80 bytes each average)
        size += len(self._referents) * 80

        # QUD stack (~100 bytes each)
        size += len(self._qud_stack) * 100

        # Salience entries (~50 bytes each)
        size += len(self._salience_map) * 50

        # Topics (~60 bytes each)
        size += len(self._topic_stack) * 60

        # Intent (~100 bytes)
        size += len(self._last_user_intent) + 10

        return size

    def to_flatbuffer(self) -> bytes:
        """
        Serialize section to FlatBuffer bytes.

        Returns:
            bytes: FlatBuffer-encoded data

        Performance Target: <100 microseconds
        """
        if self._cache_valid and self._cached_bytes:
            return self._cached_bytes

        builder = flatbuffers.Builder(self.BUDGET_BYTES)

        # 1. Build referents
        referent_offsets = []
        for ref in self._referents.values():
            id_offset = builder.CreateString(ref.id)
            text_offset = builder.CreateString(ref.text)
            entity_id_offset = builder.CreateString(ref.entity_id)
            entity_type_offset = builder.CreateString(ref.entity_type)

            ReferentStart(builder)
            ReferentAddId(builder, id_offset)
            ReferentAddText(builder, text_offset)
            ReferentAddEntityId(builder, entity_id_offset)
            ReferentAddEntityType(builder, entity_type_offset)
            ReferentAddSalience(builder, ref.salience)
            ReferentAddFirstMentionedTurn(builder, ref.first_mentioned_turn)
            ReferentAddLastMentionedTurn(builder, ref.last_mentioned_turn)
            ReferentAddMentionCount(builder, ref.mention_count)
            referent_offsets.append(ReferentEnd(builder))

        # Build referents vector
        if referent_offsets:
            ScoreboardSectionStartReferentsVector(builder, len(referent_offsets))
            for ro in reversed(referent_offsets):
                builder.PrependUOffsetTRelative(ro)
            referents_vec = builder.EndVector()
        else:
            referents_vec = 0

        # 2. Build QUD stack
        question_offsets = []
        for q in self._qud_stack:
            id_offset = builder.CreateString(q.id)
            text_offset = builder.CreateString(q.text)
            asked_by_offset = builder.CreateString(q.asked_by)
            answer_offset = builder.CreateString(q.answer_summary)

            QuestionStart(builder)
            QuestionAddId(builder, id_offset)
            QuestionAddText(builder, text_offset)
            QuestionAddStatus(builder, int(q.status))
            QuestionAddAskedBy(builder, asked_by_offset)
            QuestionAddAskedAtTurn(builder, q.asked_at_turn)
            QuestionAddAnsweredAtTurn(builder, q.answered_at_turn)
            QuestionAddAnswerSummary(builder, answer_offset)
            QuestionAddPriority(builder, q.priority)
            question_offsets.append(QuestionEnd(builder))

        # Build questions vector
        if question_offsets:
            ScoreboardSectionStartQudStackVector(builder, len(question_offsets))
            for qo in reversed(question_offsets):
                builder.PrependUOffsetTRelative(qo)
            qud_vec = builder.EndVector()
        else:
            qud_vec = 0

        # 3. Build salience map
        salience_offsets = []
        for entry in self._salience_map.values():
            entity_id_offset = builder.CreateString(entry.entity_id)

            SalienceEntryStart(builder)
            SalienceEntryAddEntityId(builder, entity_id_offset)
            SalienceEntryAddScore(builder, entry.score)
            SalienceEntryAddDecayRate(builder, entry.decay_rate)
            salience_offsets.append(SalienceEntryEnd(builder))

        # Build salience vector
        if salience_offsets:
            ScoreboardSectionStartSalienceMapVector(builder, len(salience_offsets))
            for so in reversed(salience_offsets):
                builder.PrependUOffsetTRelative(so)
            salience_vec = builder.EndVector()
        else:
            salience_vec = 0

        # 4. Build topic stack
        topic_offsets = []
        for topic in self._topic_stack:
            id_offset = builder.CreateString(topic.id)
            name_offset = builder.CreateString(topic.name)

            TopicStart(builder)
            TopicAddId(builder, id_offset)
            TopicAddName(builder, name_offset)
            TopicAddSalience(builder, topic.salience)
            TopicAddFirstTurn(builder, topic.first_turn)
            TopicAddLastTurn(builder, topic.last_turn)
            TopicAddIsPrimary(builder, topic.is_primary)
            topic_offsets.append(TopicEnd(builder))

        # Build topics vector
        if topic_offsets:
            ScoreboardSectionStartTopicStackVector(builder, len(topic_offsets))
            for to in reversed(topic_offsets):
                builder.PrependUOffsetTRelative(to)
            topics_vec = builder.EndVector()
        else:
            topics_vec = 0

        # 5. Build last user intent
        intent_offset = builder.CreateString(self._last_user_intent)

        # 6. Build header
        section_name_offset = builder.CreateString(self.SECTION_NAME)

        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # 7. Build ScoreboardSection root
        ScoreboardSectionStart(builder)
        ScoreboardSectionAddHeader(builder, header_offset)
        if referents_vec:
            ScoreboardSectionAddReferents(builder, referents_vec)
        if qud_vec:
            ScoreboardSectionAddQudStack(builder, qud_vec)
        if salience_vec:
            ScoreboardSectionAddSalienceMap(builder, salience_vec)
        if topics_vec:
            ScoreboardSectionAddTopicStack(builder, topics_vec)
        ScoreboardSectionAddLastUserIntent(builder, intent_offset)
        ScoreboardSectionAddLastUserIntentConfidence(builder, self._last_user_intent_confidence)
        ScoreboardSectionAddCurrentTurn(builder, self._current_turn)
        ScoreboardSectionAddLastUpdatedMs(builder, self._last_updated_ms)
        scoreboard_section = ScoreboardSectionEnd(builder)

        builder.Finish(scoreboard_section)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize section from FlatBuffer bytes.

        Args:
            data: FlatBuffer-encoded data
        """
        fb = FBScoreboardSection.GetRootAsScoreboardSection(data, 0)

        # Clear current state
        self._referents.clear()
        self._qud_stack.clear()
        self._salience_map.clear()
        self._topic_stack.clear()
        self._referents_by_entity.clear()

        # Load referents
        for i in range(fb.ReferentsLength()):
            ref_fb = fb.Referents(i)
            if ref_fb:
                ref = Referent(
                    id=self._decode_string(ref_fb.Id()),
                    text=self._decode_string(ref_fb.Text()),
                    entity_id=self._decode_string(ref_fb.EntityId()),
                    entity_type=self._decode_string(ref_fb.EntityType()),
                    salience=ref_fb.Salience(),
                    first_mentioned_turn=ref_fb.FirstMentionedTurn(),
                    last_mentioned_turn=ref_fb.LastMentionedTurn(),
                    mention_count=ref_fb.MentionCount(),
                )
                self._referents[ref.id] = ref
                if ref.entity_id:
                    self._referents_by_entity[ref.entity_id] = ref.id

        # Load QUD stack
        for i in range(fb.QudStackLength()):
            q_fb = fb.QudStack(i)
            if q_fb:
                q = Question(
                    id=self._decode_string(q_fb.Id()),
                    text=self._decode_string(q_fb.Text()),
                    status=QuestionStatus(q_fb.Status()),
                    asked_by=self._decode_string(q_fb.AskedBy()),
                    asked_at_turn=q_fb.AskedAtTurn(),
                    answered_at_turn=q_fb.AnsweredAtTurn(),
                    answer_summary=self._decode_string(q_fb.AnswerSummary()),
                    priority=q_fb.Priority(),
                )
                self._qud_stack.append(q)

        # Load salience map
        for i in range(fb.SalienceMapLength()):
            s_fb = fb.SalienceMap(i)
            if s_fb:
                entry = SalienceEntry(
                    entity_id=self._decode_string(s_fb.EntityId()),
                    score=s_fb.Score(),
                    decay_rate=s_fb.DecayRate(),
                )
                self._salience_map[entry.entity_id] = entry

        # Load topic stack
        for i in range(fb.TopicStackLength()):
            t_fb = fb.TopicStack(i)
            if t_fb:
                topic = Topic(
                    id=self._decode_string(t_fb.Id()),
                    name=self._decode_string(t_fb.Name()),
                    salience=t_fb.Salience(),
                    first_turn=t_fb.FirstTurn(),
                    last_turn=t_fb.LastTurn(),
                    is_primary=t_fb.IsPrimary(),
                )
                self._topic_stack.append(topic)

        # Load intent
        intent = fb.LastUserIntent()
        if intent:
            self._last_user_intent = self._decode_string(intent)
        self._last_user_intent_confidence = fb.LastUserIntentConfidence()

        # Load metadata
        self._current_turn = fb.CurrentTurn()
        self._last_updated_ms = fb.LastUpdatedMs()

        self._invalidate_cache()

    def clear(self) -> None:
        """Clear all section data to initial state."""
        self._referents.clear()
        self._qud_stack.clear()
        self._salience_map.clear()
        self._topic_stack.clear()
        self._referents_by_entity.clear()
        self._last_user_intent = ""
        self._last_user_intent_confidence = 0.0
        self._current_turn = 0
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def get_metadata(self) -> Dict[str, Any]:
        """Get section metadata for telemetry/debugging."""
        return {
            "name": self.name,
            "tier": self.tier,
            "budget_bytes": self.budget_bytes,
            "current_size_bytes": self.get_size_bytes(),
            "utilization_pct": (self.get_size_bytes() / self.budget_bytes) * 100,
            "can_evict": self.can_evict,
            "referent_count": len(self._referents),
            "qud_count": len(self._qud_stack),
            "salience_entry_count": len(self._salience_map),
            "topic_count": len(self._topic_stack),
            "current_turn": self._current_turn,
            "last_user_intent": self._last_user_intent,
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Referent Management
    # =========================================================================

    def add_referent(
        self,
        text: str,
        entity_id: str = "",
        entity_type: str = "",
        salience: float = 0.5,
    ) -> Referent:
        """
        Add or update a discourse referent.

        Args:
            text: How the entity was mentioned
            entity_id: Optional link to entity store
            entity_type: Type of entity (person, place, etc.)
            salience: Initial salience (0.0-1.0)

        Returns:
            Referent: Created or updated referent
        """
        # Check if we already have a referent for this entity
        if entity_id and entity_id in self._referents_by_entity:
            ref_id = self._referents_by_entity[entity_id]
            ref = self._referents[ref_id]
            ref.last_mentioned_turn = self._current_turn
            ref.mention_count += 1
            ref.salience = min(1.0, ref.salience + 0.1)  # Boost on re-mention
            self._touch()
            return ref

        # Create new referent
        ref = Referent(
            id=str(uuid.uuid4()),
            text=text,
            entity_id=entity_id,
            entity_type=entity_type,
            salience=salience,
            first_mentioned_turn=self._current_turn,
            last_mentioned_turn=self._current_turn,
            mention_count=1,
        )

        self._referents[ref.id] = ref
        if entity_id:
            self._referents_by_entity[entity_id] = ref.id

        # Also update salience map
        if entity_id:
            self.set_salience(entity_id, salience)

        self._touch()
        return ref

    def get_referent(self, referent_id: str) -> Optional[Referent]:
        """Get referent by ID."""
        return self._referents.get(referent_id)

    def get_referent_by_entity(self, entity_id: str) -> Optional[Referent]:
        """Get referent by entity ID."""
        ref_id = self._referents_by_entity.get(entity_id)
        if ref_id:
            return self._referents.get(ref_id)
        return None

    def list_referents(self, sort_by_salience: bool = True) -> List[Referent]:
        """List all referents, optionally sorted by salience."""
        refs = list(self._referents.values())
        if sort_by_salience:
            refs.sort(key=lambda r: r.salience, reverse=True)
        return refs

    def remove_referent(self, referent_id: str) -> bool:
        """Remove a referent."""
        ref = self._referents.get(referent_id)
        if not ref:
            return False

        del self._referents[referent_id]
        if ref.entity_id and ref.entity_id in self._referents_by_entity:
            del self._referents_by_entity[ref.entity_id]

        self._touch()
        return True

    def get_most_salient_referent(self) -> Optional[Referent]:
        """Get the most salient referent."""
        if not self._referents:
            return None
        return max(self._referents.values(), key=lambda r: r.salience)

    # =========================================================================
    # QUD (Question Under Discussion) Management
    # =========================================================================

    def push_question(
        self,
        text: str,
        asked_by: str = "user",
        priority: int = 0,
    ) -> Question:
        """
        Push a question onto the QUD stack.

        Args:
            text: Question text
            asked_by: Who asked ("user" or agent_id)
            priority: Priority (higher = more important)

        Returns:
            Question: Created question
        """
        q = Question(
            id=str(uuid.uuid4()),
            text=text,
            status=QuestionStatus.OPEN,
            asked_by=asked_by,
            asked_at_turn=self._current_turn,
            priority=priority,
        )

        self._qud_stack.append(q)
        self._touch()
        return q

    def pop_question(self) -> Optional[Question]:
        """Pop the top question from the stack."""
        if not self._qud_stack:
            return None
        q = self._qud_stack.pop()
        self._touch()
        return q

    def peek_question(self) -> Optional[Question]:
        """Get the top question without removing it."""
        if not self._qud_stack:
            return None
        return self._qud_stack[-1]

    def get_question(self, question_id: str) -> Optional[Question]:
        """Get question by ID."""
        for q in self._qud_stack:
            if q.id == question_id:
                return q
        return None

    def answer_question(
        self,
        question_id: str,
        answer_summary: str = "",
    ) -> bool:
        """
        Mark a question as answered.

        Args:
            question_id: Question UUID
            answer_summary: Brief summary of the answer

        Returns:
            bool: True if found and updated
        """
        for q in self._qud_stack:
            if q.id == question_id:
                q.status = QuestionStatus.ANSWERED
                q.answered_at_turn = self._current_turn
                q.answer_summary = answer_summary
                self._touch()
                return True
        return False

    def abandon_question(self, question_id: str) -> bool:
        """Mark a question as abandoned."""
        for q in self._qud_stack:
            if q.id == question_id:
                q.status = QuestionStatus.ABANDONED
                self._touch()
                return True
        return False

    def defer_question(self, question_id: str) -> bool:
        """Mark a question as deferred."""
        for q in self._qud_stack:
            if q.id == question_id:
                q.status = QuestionStatus.DEFERRED
                self._touch()
                return True
        return False

    def list_questions(
        self,
        status: Optional[QuestionStatus] = None,
    ) -> List[Question]:
        """List questions, optionally filtered by status."""
        if status is None:
            return list(self._qud_stack)
        return [q for q in self._qud_stack if q.status == status]

    def list_open_questions(self) -> List[Question]:
        """List all open questions."""
        return self.list_questions(QuestionStatus.OPEN)

    def clear_answered_questions(self) -> int:
        """Remove answered questions from stack."""
        before = len(self._qud_stack)
        self._qud_stack = [
            q
            for q in self._qud_stack
            if q.status not in (QuestionStatus.ANSWERED, QuestionStatus.ABANDONED)
        ]
        after = len(self._qud_stack)
        if before != after:
            self._touch()
        return before - after

    # =========================================================================
    # Salience Management
    # =========================================================================

    def set_salience(
        self,
        entity_id: str,
        score: float,
        decay_rate: Optional[float] = None,
    ) -> SalienceEntry:
        """
        Set salience for an entity.

        Args:
            entity_id: Entity identifier
            score: Salience score (0.0-1.0)
            decay_rate: How fast salience decays per turn

        Returns:
            SalienceEntry: Created or updated entry
        """
        entry = self._salience_map.get(entity_id)
        if entry:
            entry.score = max(0.0, min(1.0, score))
            if decay_rate is not None:
                entry.decay_rate = decay_rate
        else:
            entry = SalienceEntry(
                entity_id=entity_id,
                score=max(0.0, min(1.0, score)),
                decay_rate=decay_rate or self.DEFAULT_DECAY_RATE,
            )
            self._salience_map[entity_id] = entry

        self._touch()
        return entry

    def get_salience(self, entity_id: str) -> float:
        """Get salience for an entity."""
        entry = self._salience_map.get(entity_id)
        return entry.score if entry else 0.0

    def boost_salience(self, entity_id: str, boost: float) -> float:
        """
        Boost salience for an entity.

        Args:
            entity_id: Entity identifier
            boost: Amount to add (capped at 1.0)

        Returns:
            New salience score
        """
        entry = self._salience_map.get(entity_id)
        if entry:
            entry.score = min(1.0, entry.score + boost)
            self._touch()
            return entry.score
        else:
            # Create new entry
            new_entry = self.set_salience(entity_id, boost)
            return new_entry.score

    def decay_salience(self) -> int:
        """
        Apply decay to all salience entries.

        Should be called at turn transitions.

        Returns:
            Number of entries removed due to low salience
        """
        removed = 0
        to_remove = []

        for entity_id, entry in self._salience_map.items():
            entry.score = entry.score * (1.0 - entry.decay_rate)
            if entry.score < self.MIN_SALIENCE:
                to_remove.append(entity_id)

        for entity_id in to_remove:
            del self._salience_map[entity_id]
            removed += 1

        if to_remove:
            self._touch()

        return removed

    def list_salient_entities(
        self,
        min_score: float = 0.0,
    ) -> List[SalienceEntry]:
        """List entities sorted by salience."""
        entries = [e for e in self._salience_map.values() if e.score >= min_score]
        entries.sort(key=lambda e: e.score, reverse=True)
        return entries

    def get_most_salient_entity(self) -> Optional[str]:
        """Get the most salient entity ID."""
        if not self._salience_map:
            return None
        entry = max(self._salience_map.values(), key=lambda e: e.score)
        return entry.entity_id

    # =========================================================================
    # Topic Management
    # =========================================================================

    def push_topic(
        self,
        name: str,
        salience: float = 0.5,
        is_primary: bool = False,
    ) -> Topic:
        """
        Push a topic onto the topic stack.

        Args:
            name: Topic name
            salience: Topic salience
            is_primary: Whether this is the primary topic

        Returns:
            Topic: Created topic
        """
        # If is_primary, demote existing primary
        if is_primary:
            for t in self._topic_stack:
                t.is_primary = False

        topic = Topic(
            id=str(uuid.uuid4()),
            name=name,
            salience=salience,
            first_turn=self._current_turn,
            last_turn=self._current_turn,
            is_primary=is_primary,
        )

        self._topic_stack.append(topic)
        self._touch()
        return topic

    def pop_topic(self) -> Optional[Topic]:
        """Pop the top topic from the stack."""
        if not self._topic_stack:
            return None
        topic = self._topic_stack.pop()
        self._touch()
        return topic

    def peek_topic(self) -> Optional[Topic]:
        """Get the top topic without removing it."""
        if not self._topic_stack:
            return None
        return self._topic_stack[-1]

    def get_primary_topic(self) -> Optional[Topic]:
        """Get the primary topic."""
        for t in reversed(self._topic_stack):
            if t.is_primary:
                return t
        # Fall back to top of stack
        return self.peek_topic()

    def list_topics(self) -> List[Topic]:
        """List all topics (most recent first)."""
        return list(reversed(self._topic_stack))

    def set_primary_topic(self, topic_id: str) -> bool:
        """Set a topic as primary."""
        found = False
        for t in self._topic_stack:
            if t.id == topic_id:
                t.is_primary = True
                t.last_turn = self._current_turn
                found = True
            else:
                t.is_primary = False

        if found:
            self._touch()
        return found

    # =========================================================================
    # Intent Management
    # =========================================================================

    def set_user_intent(
        self,
        intent: str,
        confidence: float = 1.0,
    ) -> None:
        """Set the last user intent."""
        self._last_user_intent = intent
        self._last_user_intent_confidence = confidence
        self._touch()

    def get_user_intent(self) -> tuple[str, float]:
        """Get the last user intent and confidence."""
        return self._last_user_intent, self._last_user_intent_confidence

    # =========================================================================
    # Turn Management
    # =========================================================================

    @property
    def current_turn(self) -> int:
        """Current turn number."""
        return self._current_turn

    def advance_turn(self) -> int:
        """
        Advance to the next turn.

        This should be called at turn boundaries. It:
        - Increments turn counter
        - Applies salience decay
        - Updates topic timestamps

        Returns:
            New turn number
        """
        self._current_turn += 1

        # Apply salience decay
        self.decay_salience()

        # Update topic last_turn for active topics
        if self._topic_stack:
            self._topic_stack[-1].last_turn = self._current_turn

        self._touch()
        return self._current_turn

    @property
    def last_updated_ms(self) -> int:
        """Last update timestamp."""
        return self._last_updated_ms

    # =========================================================================
    # Legacy API (backward compatibility)
    # =========================================================================

    def create_task(
        self,
        name: str,
        owner: str = "",
        parent_id: str = "",
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Question:
        """Create task as QUD (legacy API)."""
        return self.push_question(
            text=name,
            asked_by=owner or "system",
            priority=priority,
        )

    def get(self, task_id: str) -> Optional[Question]:
        """Get task/question by ID (legacy API)."""
        return self.get_question(task_id)

    def list(self) -> List[Question]:
        """List all questions (legacy API)."""
        return list(self._qud_stack)

    def update_status(
        self,
        task_id: str,
        status: Any,
    ) -> bool:
        """Update question status (legacy API)."""
        # Map TaskStatus to QuestionStatus
        if hasattr(status, "value"):
            status_str = status.value
        else:
            status_str = str(status)

        status_map = {
            "pending": QuestionStatus.OPEN,
            "in_progress": QuestionStatus.OPEN,
            "blocked": QuestionStatus.DEFERRED,
            "complete": QuestionStatus.ANSWERED,
            "failed": QuestionStatus.ABANDONED,
        }

        q = self.get_question(task_id)
        if q:
            q.status = status_map.get(status_str, QuestionStatus.OPEN)
            self._touch()
            return True
        return False

    def update_progress(
        self,
        task_id: str,
        progress: float,
    ) -> bool:
        """Update progress (legacy API - no-op for QUD)."""
        # QUDs don't have progress, but we acknowledge the call
        return task_id in [q.id for q in self._qud_stack]

    def complete_task(self, task_id: str) -> bool:
        """Complete task (legacy API)."""
        return self.answer_question(task_id, "Completed")

    def fail_task(self, task_id: str, reason: str = "") -> bool:
        """Fail task (legacy API)."""
        return self.abandon_question(task_id)

    def block_task(self, task_id: str, reason: str = "") -> bool:
        """Block task (legacy API)."""
        return self.defer_question(task_id)

    def get_active(self) -> List[Question]:
        """Get active questions (legacy API)."""
        return self.list_open_questions()

    def get_pending(self) -> List[Question]:
        """Get pending questions (legacy API)."""
        return self.list_open_questions()

    def get_by_owner(self, owner: str) -> List[Question]:
        """Get questions by asker (legacy API)."""
        return [q for q in self._qud_stack if q.asked_by == owner]

    def get_subtasks(self, parent_id: str) -> List[Question]:
        """Get subtasks (legacy API - returns empty)."""
        return []

    def remove_completed(self) -> int:
        """Remove completed questions (legacy API)."""
        return self.clear_answered_questions()

    def serialize(self) -> bytes:
        """Serialize to FlatBuffer bytes (legacy API)."""
        return self.to_flatbuffer()

    def deserialize(self, data: bytes) -> None:
        """Deserialize from FlatBuffer bytes (legacy API)."""
        self.from_flatbuffer(data)

    def apply(self, operation: str, data: Dict[str, Any]) -> Any:
        """Apply mutation operation (legacy API)."""
        if operation == "push_question":
            return self.push_question(
                data["text"],
                data.get("asked_by", "user"),
            )
        elif operation == "pop_question":
            return self.pop_question()
        elif operation == "answer_question":
            return self.answer_question(
                data["question_id"],
                data.get("answer_summary", ""),
            )
        elif operation == "add_referent":
            return self.add_referent(
                data["text"],
                data.get("entity_id", ""),
                data.get("entity_type", ""),
                data.get("salience", 0.5),
            )
        elif operation == "set_salience":
            return self.set_salience(
                data["entity_id"],
                data["score"],
            )
        elif operation == "push_topic":
            return self.push_topic(
                data["name"],
                data.get("salience", 0.5),
                data.get("is_primary", False),
            )
        elif operation == "set_user_intent":
            self.set_user_intent(
                data["intent"],
                data.get("confidence", 1.0),
            )
        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _touch(self) -> None:
        """Update timestamp and invalidate cache."""
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate serialization cache."""
        self._cache_valid = False
        self._cached_bytes = None

    def _decode_string(self, value: Any) -> str:
        """Decode string from FlatBuffer."""
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)


# =============================================================================
# Legacy TaskStatus for backward compatibility
# =============================================================================


class TaskStatus(IntEnum):
    """Task status values (legacy, maps to QuestionStatus)."""

    PENDING = 0
    IN_PROGRESS = 1
    BLOCKED = 2
    COMPLETE = 3
    FAILED = 4


@dataclass
class Task:
    """Legacy Task class - maps to Question."""

    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    owner: str = ""
    parent_id: str = ""
    priority: int = 5
    created_at_ms: int = 0
    updated_at_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    failure_reason: str = ""


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "ScoreboardSection",
    "Referent",
    "Question",
    "Topic",
    "SalienceEntry",
    "QuestionStatus",
    # Legacy exports
    "Task",
    "TaskStatus",
]
