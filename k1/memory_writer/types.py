"""
Memory Writer v2 Domain Types -- All dataclasses and enums for MW v2.

Pure frozen dataclasses with NO business logic, NO I/O, NO port references.
Maps 1:1 to the JSON schema at:
  k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json

Source of truth:
  docs/pipelines/p03/stage5_proposal_corrections.md LAYER 2 Field Reference

Design decisions:
  - All dataclasses are frozen (immutable after creation)
  - All enums inherit from (str, Enum) for JSON serialization
  - Single types.py module -- do NOT split into per-service files
  - MemoryAtom has exactly 34 fields matching the JSON schema
  - ExtractionContext assembled from 15 SessionState sections

Anti-hallucination rules:
  - Do NOT add async methods to dataclasses
  - Do NOT import from k1.memory_writer.pipeline/* or service modules
  - Do NOT import from k1.memory_writer.ports/* (no circular deps)
  - No business logic -- types are data containers only

Import graph:
  - k1.memory_writer.types -> stdlib only (dataclasses, enum, typing)
  - NEVER import from service, port, or adapter modules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ===========================================================================
# Enums (12 enums -- all str-based for JSON serialization)
# ===========================================================================


class SentimentLabel(str, Enum):
    """Sentiment classification from affective_now."""

    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


class NoveltyLevel(str, Enum):
    """Novelty classification. MW compares extraction against beliefs + scoreboard."""

    ROUTINE = "ROUTINE"
    EXPECTED = "EXPECTED"
    NOVEL = "NOVEL"
    SURPRISING = "SURPRISING"


class ElaborationDepth(str, Enum):
    """How deeply a topic was discussed across conversation turns.

    MENTION          -- 1 turn on topic
    DISCUSSED        -- 2-3 turns
    ELABORATED       -- 4-6 turns
    DEEPLY_PROCESSED -- 7+ turns
    """

    MENTION = "MENTION"
    DISCUSSED = "DISCUSSED"
    ELABORATED = "ELABORATED"
    DEEPLY_PROCESSED = "DEEPLY_PROCESSED"


class TemporalOrientation(str, Enum):
    """Temporal orientation derived from resolved_epoch_ms vs now."""

    PAST = "PAST"
    ONGOING = "ONGOING"
    FUTURE_COMMITMENT = "FUTURE_COMMITMENT"


class SourceType(str, Enum):
    """Memory provenance. MW cross-references history_active vs extraction origin."""

    USER_STATED = "user_stated"
    USER_IMPLIED = "user_implied"
    DEVICE_OBSERVED = "device_observed"
    SYSTEM_INFERRED = "system_inferred"


class ArcPosition(str, Enum):
    """Story arc position from narrative_active.arc.position."""

    EXPOSITION = "EXPOSITION"
    RISING_ACTION = "RISING_ACTION"
    CLIMAX = "CLIMAX"
    RESOLUTION = "RESOLUTION"


class SocialIntimacy(str, Enum):
    """Social intimacy level. family=HIGH, friends=MEDIUM, unknown=LOW."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ActivityType(str, Enum):
    """Activity classification. 20-value enum merged from K1 12-type + legacy 12-type."""

    MEAL = "MEAL"
    TASK = "TASK"
    TRAVEL = "TRAVEL"
    HEALTH = "HEALTH"
    SOCIAL = "SOCIAL"
    WORK = "WORK"
    EDUCATION = "EDUCATION"
    EXERCISE = "EXERCISE"
    SHOPPING = "SHOPPING"
    ENTERTAINMENT = "ENTERTAINMENT"
    CELEBRATION = "CELEBRATION"
    APPOINTMENT = "APPOINTMENT"
    DIARY = "DIARY"
    FINANCE = "FINANCE"
    RELATIONSHIP = "RELATIONSHIP"
    PLANNING = "PLANNING"
    CONCERN = "CONCERN"
    GRATITUDE = "GRATITUDE"
    META = "META"
    MEMORY = "MEMORY"


class RelationshipType(str, Enum):
    """Relationship type between participant and target."""

    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    SPOUSE_OF = "SPOUSE_OF"
    SIBLING_OF = "SIBLING_OF"
    FRIEND_OF = "FRIEND_OF"
    COLLEAGUE_OF = "COLLEAGUE_OF"
    CARETAKER_OF = "CARETAKER_OF"
    OTHER = "OTHER"


class LocationType(str, Enum):
    """Location category. 12 values."""

    HOME = "home"
    RESTAURANT = "restaurant"
    HOSPITAL = "hospital"
    SCHOOL = "school"
    OFFICE = "office"
    GYM = "gym"
    STORE = "store"
    PARK = "park"
    CHURCH = "church"
    AIRPORT = "airport"
    HOTEL = "hotel"
    OTHER = "other"


class IdentityDomain(str, Enum):
    """Identity categories activated by a memory. 9 values."""

    PARENT = "parent"
    CHILD = "child"
    SPOUSE = "spouse"
    PROFESSIONAL = "professional"
    HEALTH_SELF = "health_self"
    FINANCIAL_SELF = "financial_self"
    SOCIAL_SELF = "social_self"
    ACADEMIC_SELF = "academic_self"
    SPIRITUAL_SELF = "spiritual_self"


class SkipReason(str, Enum):
    """Reason why RelevanceFilter skipped a turn.

    R1 DUPLICATE     -- Turn ID seen within dedup window
    R2 TRIVIAL       -- Turn text < trivial_word_threshold words
    R3 SYSTEM_TURN   -- Turn role is system/tool (not user or assistant)
    R4 STALE         -- Turn timestamp older than dedup window
    R5 EMPTY         -- Turn content is None/empty/whitespace
    """

    DUPLICATE = "DUPLICATE"
    TRIVIAL = "TRIVIAL"
    SYSTEM_TURN = "SYSTEM_TURN"
    STALE = "STALE"
    EMPTY = "EMPTY"


class IntentType(str, Enum):
    """Primary intent classification from control.intents[0]."""

    LOG_MEMORY = "log_memory"
    QUERY_MEMORY = "query_memory"
    SET_REMINDER = "set_reminder"
    EXPRESS_FEELING = "express_feeling"
    SEEK_ADVICE = "seek_advice"
    SHARE_NEWS = "share_news"
    REFLECT = "reflect"
    OTHER = "other"


class SocialContext(str, Enum):
    """Social context derived from participant_relationships."""

    SOLO = "solo"
    FRIENDS = "friends"
    COLLEAGUES = "colleagues"
    NUCLEAR_FAMILY = "nuclear_family"
    EXTENDED_FAMILY = "extended_family"
    COMMUNITY = "community"


# ===========================================================================
# Nested value objects (frozen dataclasses)
# ===========================================================================


@dataclass(frozen=True)
class Affect:
    """Valence-Arousal-Dominance triple from affective_now.dimensions.

    Valence:   -1.0 (negative) to +1.0 (positive)
    Arousal:    0.0 (calm) to 1.0 (excited)
    Dominance:  0.0 (submissive) to 1.0 (dominant)
    """

    valence: float
    arousal: float
    dominance: float


@dataclass(frozen=True)
class ParticipantRelationship:
    """Typed relationship between two persons with confidence score.

    Pattern: person_id must match ^person_[a-z0-9_]+$
    """

    type: RelationshipType
    target: str
    confidence: float


@dataclass(frozen=True)
class Narrative:
    """Narrative thread context from narrative_active."""

    thread_id: str
    arc_position: ArcPosition
    is_goal_event: bool


@dataclass(frozen=True)
class Temporal:
    """Temporal context from beliefs_active.MentionedTime.

    mentioned_time:     Raw text like "yesterday evening"
    resolved_epoch_ms:  Unix ms (resolved absolute time)
    is_backdated:       True if mentioned_time != now
    """

    mentioned_time: str
    resolved_epoch_ms: int
    is_backdated: bool


# ===========================================================================
# Core domain types
# ===========================================================================


@dataclass(frozen=True)
class MemoryAtom:
    """The 34-field output per LLM extraction. Maps 1:1 to memory_atom.v2.schema.json.

    All 34 fields are the canonical schema. No v1/v2 distinction.
    Required fields (14): schema_version, operation, text, topics,
      sentiment_label, affect, source_type, novelty, elaboration_depth,
      temporal_orientation, confidence, session_id, conversation_turn, language
    """

    # --- Constants ---
    schema_version: str = "2.0"
    operation: str = "UPSERT"

    # --- Core content (WHAT) ---
    text: str = ""
    topics: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    activity_type: Optional[ActivityType] = None

    # --- Participants (WHO) ---
    participants: List[str] = field(default_factory=list)
    participant_relationships: Dict[str, ParticipantRelationship] = field(default_factory=dict)
    social_context: Optional[SocialContext] = None
    social_intimacy: Optional[SocialIntimacy] = None

    # --- Location (WHERE) ---
    location_name: Optional[str] = None
    location_type: Optional[LocationType] = None

    # --- Emotion (EMOTION) ---
    sentiment_label: SentimentLabel = SentimentLabel.NEUTRAL
    emotion_tags: List[str] = field(default_factory=list)
    affect: Affect = field(default_factory=lambda: Affect(0.0, 0.0, 0.5))

    # --- Salience (SALIENCE) ---
    entity_salience: Dict[str, float] = field(default_factory=dict)

    # --- Narrative (NARRATIVE) ---
    narrative: Optional[Narrative] = None

    # --- Temporal (WHEN) ---
    temporal: Optional[Temporal] = None

    # --- Intent (WHY) ---
    intent_type: Optional[IntentType] = None
    goal_context: Optional[str] = None
    task_context: Optional[str] = None

    # --- Cognitive dimensions ---
    source_type: SourceType = SourceType.USER_STATED
    novelty: NoveltyLevel = NoveltyLevel.EXPECTED
    elaboration_depth: ElaborationDepth = ElaborationDepth.MENTION
    identity_domains: List[str] = field(default_factory=list)
    temporal_orientation: TemporalOrientation = TemporalOrientation.PAST

    # --- Meta ---
    confidence: float = 0.0
    session_id: str = ""
    conversation_turn: int = 0
    language: str = "en"


@dataclass(frozen=True)
class CompressedTurn:
    """Minimal turn representation for history context in LLM prompt.

    Keeps only the fields needed by the WriterAgent to understand
    conversation flow without the full SessionState turn payload.
    """

    turn_id: str
    role: str
    text: str
    timestamp_ms: int
    turn_number: int


@dataclass(frozen=True)
class ExtractionContext:
    """Assembled from 15 SessionState sections for LLM prompt.

    Built by ContextBuilder (Epic 1.12). Consumed by WriterAgent (Epic 1.14).
    Total token budget: 2000 tokens (input + output combined).

    Contains all context the LLM needs to extract MemoryAtom objects:
      - Current turn being processed
      - Recent conversation history (compressed)
      - Active persons and their relationships
      - Emotional baseline and current affect
      - Active goals and narrative threads
      - Device context
      - Topic history
    """

    # Current turn
    current_turn: CompressedTurn = field(default_factory=lambda: CompressedTurn("", "", "", 0, 0))

    # Recent history (compressed turns)
    recent_turns: List[CompressedTurn] = field(default_factory=list)

    # Active persons from SessionState beliefs_active
    active_persons: Dict[str, Any] = field(default_factory=dict)

    # Emotional context from affective_now + affective_baseline
    current_affect: Optional[Affect] = None
    baseline_affect: Optional[Affect] = None

    # Narrative context from narrative_active
    active_narrative: Optional[Dict[str, Any]] = None

    # Topic / scoreboard context
    active_topics: List[str] = field(default_factory=list)
    topic_salience: Dict[str, float] = field(default_factory=dict)

    # Goals from planner / task_state
    active_goals: List[str] = field(default_factory=list)

    # Control context (intents, domains, safety band)
    control_context: Dict[str, Any] = field(default_factory=dict)

    # Device context from ifl section
    device_context: Dict[str, Any] = field(default_factory=dict)

    # Persona context
    persona_context: Dict[str, Any] = field(default_factory=dict)

    # Session identity
    session_id: str = ""
    conversation_turn: int = 0


@dataclass(frozen=True)
class FilterDecision:
    """Result of RelevanceFilter evaluation. PASS or SKIP with reason.

    Every incoming turn gets a FilterDecision before any LLM work.
    MW-07: Filter is rule-based only (no LLM).
    """

    passed: bool
    skip_reason: Optional[SkipReason] = None
    turn_id: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True)
class PersonResolution:
    """Name-to-person_id resolution result.

    natural_name:  The name as mentioned in conversation ("Mom", "Dr. Smith")
    person_id:     Resolved ID matching ^person_[a-z0-9_]+$ pattern
    confidence:    Resolution confidence (0-1)
    is_provisional: True if person_id is a provisional person_unknown_{hash} ID
    """

    natural_name: str
    person_id: str
    confidence: float = 1.0
    is_provisional: bool = False


@dataclass(frozen=True)
class MWEnvelope:
    """Wraps a MemoryAtom with routing headers for Bridge submission.

    topic:          Routing topic (e.g. "memory.write")
    schema_uri:     Schema reference for K0 validation
    trace_id:       cognitive_trace_id -- MW-10 requires this on every envelope
    atom:           The extracted MemoryAtom
    """

    topic: str
    schema_uri: str
    trace_id: str
    atom: MemoryAtom = field(default_factory=MemoryAtom)


@dataclass(frozen=True)
class HealthStatus:
    """Health check result for IHealthPort.

    Used by Fabric agent lifecycle to determine MW readiness.
    """

    is_healthy: bool
    llm_circuit_open: bool = False
    pending_batch_count: int = 0
    last_extraction_ms: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class ChatResponse:
    """Response from IModelHubPort.chat() call.

    Used by WriterAgent to receive LLM extraction output.
    """

    content: str = ""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True)
class Subscription:
    """Event bus subscription handle returned by IEventSubscriptionPort.subscribe()."""

    subscription_id: str
    topic: str
