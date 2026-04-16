"""K1 Memory Writer v2 — Episodic Memory Formation.

Exports all public symbols as declared in module.contract.yaml.
"""

# --- Adapters (5) ---
from k1.memory_writer.adapters import (
    BridgeCommandAdapter,
    EventSubscriptionAdapter,
    HealthAdapter,
    ModelHubAdapter,
    SessionReadAdapter,
)
from k1.memory_writer.batch import BatchEmitter, DeltaAggregator

# --- Config (1) ---
from k1.memory_writer.config import MWConfig

# --- Phase 1: Filter + Context Assembly ---
from k1.memory_writer.context import ContextBuilder, MWSessionReader, PersonResolver

# --- Phase 3: Envelope + Batch + Bridge ---
from k1.memory_writer.envelope import EnvelopeBuilder, FieldMapper, PrivacyEnforcer

# --- Events (6 topics + 6 payloads + 2 convenience tuples) ---
from k1.memory_writer.events import (
    ALL_CONSUMED_TOPICS,
    ALL_PRODUCED_TOPICS,
    TOPIC_BATCH_SUBMITTED,
    TOPIC_CIRCUIT_OPEN,
    TOPIC_EXTRACTION_COMPLETE,
    TOPIC_FILTER_DECISION,
    TOPIC_PIPELINE_ERROR,
    TOPIC_TURN_COMPLETE,
    BatchSubmittedEvent,
    CircuitOpenEvent,
    ExtractionCompleteEvent,
    FilterDecisionEvent,
    PipelineErrorEvent,
    TurnCompletePayload,
)

# --- Phase 2: LLM Extraction ---
from k1.memory_writer.extraction import (
    ExtractionValidator,
    MemoryWriterAgent,
    PromptLoader,
    RawExtraction,
)

# --- Phase 5: Fabric Integration ---
from k1.memory_writer.fabric_registration import MemoryWriterFabricRegistration

# --- Phase 4: Factory + Service ---
from k1.memory_writer.factory import MemoryWriterFactory
from k1.memory_writer.filter import RelevanceFilter
from k1.memory_writer.health import CircuitBreaker, CircuitBreakerState

# --- Invariants (1) ---
from k1.memory_writer.invariants import InvariantViolation

# --- Phase 4: Pipeline Orchestration ---
from k1.memory_writer.pipeline import MemoryWriterPipeline, PipelineResult, TurnDispatcher

# --- Context helpers (2) ---
from k1.memory_writer.place_resolver import PlaceResolver, ResolvedPlace

# --- Ports (5) ---
from k1.memory_writer.ports import (
    IBridgeCommandPort,
    IEventSubscriptionPort,
    IHealthPort,
    IModelHubPort,
    ISessionReadPort,
)
from k1.memory_writer.service import MemoryWriterService

# --- Enums (15) ---
# --- Nested value objects (5) ---
# --- Core types (9) ---
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ArcPosition,
    ChatResponse,
    CompressedTurn,
    ElaborationDepth,
    ExtractionContext,
    FilterDecision,
    HealthStatus,
    IdentityDomain,
    IntentType,
    LocationType,
    MemoryAtom,
    MWEnvelope,
    Narrative,
    NoveltyLevel,
    ParticipantRelationship,
    PersonResolution,
    RelationshipType,
    SentimentLabel,
    SkipReason,
    SocialContext,
    SocialIntimacy,
    SourceType,
    Subscription,
    Temporal,
    TemporalLink,
    TemporalLinkType,
    TemporalOrientation,
)

# Phase 1: RelevanceFilter, ContextBuilder, PersonResolver
# Phase 2: MemoryWriterAgent, ExtractionValidator, PromptLoader, RawExtraction
# Phase 3: EnvelopeBuilder, FieldMapper, PrivacyEnforcer, DeltaAggregator, BatchEmitter
# Phase 4: MemoryWriterPipeline, PipelineResult, TurnDispatcher, MemoryWriterFactory, MemoryWriterService
# Phase 4 (dep): CircuitBreaker, CircuitBreakerState

__all__ = [
    # Ports
    "IBridgeCommandPort",
    "IEventSubscriptionPort",
    "IHealthPort",
    "IModelHubPort",
    "ISessionReadPort",
    # Core types
    "ChatResponse",
    "CompressedTurn",
    "ExtractionContext",
    "FilterDecision",
    "HealthStatus",
    "MemoryAtom",
    "MWEnvelope",
    "PersonResolution",
    "Subscription",
    # Nested VOs
    "Affect",
    "Narrative",
    "ParticipantRelationship",
    "Temporal",
    "TemporalLink",
    # Enums
    "ActivityType",
    "ArcPosition",
    "ElaborationDepth",
    "IdentityDomain",
    "IntentType",
    "LocationType",
    "NoveltyLevel",
    "RelationshipType",
    "SentimentLabel",
    "SkipReason",
    "SocialContext",
    "SocialIntimacy",
    "SourceType",
    "TemporalLinkType",
    "TemporalOrientation",
    # Config
    "MWConfig",
    # Events (topics)
    "TOPIC_TURN_COMPLETE",
    "TOPIC_FILTER_DECISION",
    "TOPIC_EXTRACTION_COMPLETE",
    "TOPIC_BATCH_SUBMITTED",
    "TOPIC_PIPELINE_ERROR",
    "TOPIC_CIRCUIT_OPEN",
    "ALL_CONSUMED_TOPICS",
    "ALL_PRODUCED_TOPICS",
    # Events (payloads)
    "TurnCompletePayload",
    "FilterDecisionEvent",
    "ExtractionCompleteEvent",
    "BatchSubmittedEvent",
    "PipelineErrorEvent",
    "CircuitOpenEvent",
    # Invariants
    "InvariantViolation",
    # Context
    "PlaceResolver",
    "ResolvedPlace",
    # Phase 1: Filter + Context Assembly
    "RelevanceFilter",
    "ContextBuilder",
    "MWSessionReader",
    "PersonResolver",
    # Phase 2: LLM Extraction
    "ExtractionValidator",
    "MemoryWriterAgent",
    "PromptLoader",
    "RawExtraction",
    # Phase 3: Envelope
    "EnvelopeBuilder",
    "FieldMapper",
    "PrivacyEnforcer",
    "BatchEmitter",
    "DeltaAggregator",
    # Adapters
    "BridgeCommandAdapter",
    "EventSubscriptionAdapter",
    "HealthAdapter",
    "SessionReadAdapter",
    "ModelHubAdapter",
    # Phase 4: Pipeline Orchestration
    "MemoryWriterPipeline",
    "PipelineResult",
    "TurnDispatcher",
    # Phase 4: Factory + Service
    "MemoryWriterFactory",
    "MemoryWriterService",
    "CircuitBreaker",
    "CircuitBreakerState",
    # Phase 5: Fabric Integration
    "MemoryWriterFabricRegistration",
]
