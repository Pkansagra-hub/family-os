"""
P03 Consolidation Pipeline - Envelope Models

This module contains the internal state envelope for the P03 consolidation pipeline.
P03BatchEnvelope is INTERNAL to P03 and distinct from the kernel FeedbackEnvelope.

Module Layout:
    context.py       - P03CycleContext (frozen, set in R0)
    event_state.py   - P03EventState + ReconciliationAction enum
    phase_outputs.py - P03PhaseOutputs + all RxOutput types
    staged_writes.py - P03StagedWrites + WriteOperation enum
    observability.py - P03ObservabilityContext + P03Error
    serializer.py    - P03EnvelopeSerializer for checkpoints/DLQ
    envelope.py      - P03BatchEnvelope (top-level container)

Design Decisions (from M1 Issue 1.1.1):
    - Uses dataclasses (not Pydantic) for performance
    - P03CycleContext is frozen (immutable after R0)
    - Event states are mutable (enriched R1-R6)
    - JSON serialization via explicit P03EnvelopeSerializer

References:
    - Discovery: docs/pipelines/P03_envelope_fields_discovery.md
    - Dossier: docs/pipelines/P03_consolidation_dossier_v2.md
    - ADR: docs/architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md
"""

from k0.pipelines.p03.checkpoint import (  # Issue 1.2.5 - Checkpoint contract
    P03_CHECKPOINT_TOPIC,
    P03_SOURCE_TOPIC,
    P03_SUBSCRIBER_ID,
    CheckpointError,
    CheckpointLoadError,
    CheckpointNotFoundError,
    CheckpointSaveError,
    CheckpointStoreBase,
    CheckpointStoreProtocol,
    InMemoryCheckpointStore,
    P03Checkpoint,
    P03Offset,
    create_checkpoint_from_envelope,
)
from k0.pipelines.p03.context import P03CycleContext, generate_ulid
from k0.pipelines.p03.deterministic import (  # Issue 1.2.7 - Deterministic seeding + skip rules
    DEFAULT_MINIMAL_WORK_THRESHOLD,
    DEFAULT_R5_BACKLOG_THRESHOLD,
    MINIMAL_WORK_SKIP_PHASES,
    R5_SKIP_PHASES,
    DeterministicError,
    P03DeterministicContext,
    P03SeededRNG,
    P03SkipPolicy,
    SeedDerivationError,
    SkipDecision,
    SkipPolicyConfig,
    SkipPolicyError,
    SkipPolicyProtocol,
    SkipReason,
    derive_cycle_seed,
    derive_phase_seed,
    evaluate_minimal_work_skip,
    evaluate_r5_skip,
    get_phases_to_skip_for_fast_path,
    record_skip_in_envelope,
    validate_skip_transition,
)
from k0.pipelines.p03.envelope import P03BatchEnvelope
from k0.pipelines.p03.event_state import P03EventState, PruneDecision, ReconciliationAction
from k0.pipelines.p03.gap_emitter import (  # Issue 3.2.3 - Gap emitter
    GAP_PRIORITY_MAP,
    GapEmitResult,
    GapType,
    P03GapEmitter,
    P03GapEmitterConfig,
)
from k0.pipelines.p03.observability import (  # Dataclasses; Constants; Phase transition logging (Issue 1.2.4); R1 metrics (Issue 4.1.7)
    DURATION_MS_BUCKETS,
    EDGE_WEIGHT_BUCKETS,
    IMPORTANCE_SCORE_BUCKETS,
    PIPELINE_ID,
    R1_ERROR_THRESHOLD_MS,
    R1_WARNING_THRESHOLD_MS,
    VALID_PHASES,
    P03Error,
    P03ObservabilityContext,
    PhaseEventType,
    PhaseTransitionEvent,
    PhaseTransitionLogger,
    PhaseTransitionLoggerProtocol,
    R1PhaseMetrics,
)
from k0.pipelines.p03.offset_manager import (  # Issue 1.2.6 - Offset/watermark integration
    InMemoryOffset,
    InMemoryOffsetStore,
    OffsetAction,
    OffsetDecision,
    OffsetIdempotencyError,
    OffsetManagerError,
    OffsetStoreProtocol,
    OffsetWriteError,
    P03OffsetManager,
    create_offset_from_checkpoint,
    should_advance_offset,
)
from k0.pipelines.p03.outbox_publisher import (  # Issue 3.1.3 - Outbox publisher
    OutboxPublisherConfig,
    P03OutboxPublisher,
    PublishResult,
)
from k0.pipelines.p03.phase_interface import (  # Issue 1.2.2 - Phase interface
    P03CycleResult,
    P03PhaseBase,
    P03PhaseProtocol,
    P03PhaseResult,
    P03RunnerContext,
)
from k0.pipelines.p03.phase_outputs import (  # Main container; R1 types; R2 types; R3 types; R4 types; R5 types; R6 types; R7 types; R8 types
    CausalEdge,
    CounterfactualScenario,
    CycleSummary,
    DecayUpdate,
    DedupMerge,
    EmittedEvent,
    EpisodeCluster,
    EventStatusUpdate,
    GapCandidate,
    HebbianEdgeUpdate,
    Insight,
    KGEdge,
    KGEdgeUpdate,
    KGEntity,
    KGEntityUpdate,
    P03PhaseOutputs,
    ProspectiveMemory,
    ReconciliationSummary,
    RoutineOptimization,
    ScoredEvent,
    TruthWrite,
    WriteManifest,
    WriteResult,
)
from k0.pipelines.p03.qos import (  # Issue 6.4.1 + 6.4.2 - QoS integration
    P03_QOS_DEFAULTS,
    P03_SCHEDULER_PROFILES,
    P03QoSContext,
    P03SchedulerIntegration,
    P03SchedulerProfile,
    create_p03_qos_context,
)
from k0.pipelines.p03.runner_contract import (  # Issue 1.2.1 - Runner contract
    ERROR_RECOVERY_MATRIX,
    NORMAL_TRANSITIONS,
    PHASE_CONTRACTS,
    REQUIRED_PHASES,
    RESUME_MATRIX,
    SKIP_TRANSITIONS,
    SKIPPABLE_PHASES,
    ErrorRecovery,
    P03PhaseId,
    P03PhaseStatus,
    PhaseContract,
    ResumePolicy,
    is_valid_transition,
)
from k0.pipelines.p03.sequential_runner import (  # Issue 1.2.3 - Sequential runner
    InvalidPhaseTransitionError,
    P03RunnerError,
    P03SequentialRunner,
    PhaseNotRegisteredError,
    PhaseTimelineEntry,
    ResumeNotAllowedError,
    create_runner,
)
from k0.pipelines.p03.serializer import (  # Exception; Dataclasses; Serializer class; Helper function
    InvalidPhaseTransition,
    P03EnvelopeSerializer,
    PhaseCheckpoint,
    generate_phase_summary,
)
from k0.pipelines.p03.staged_writes import (  # Enum; Dataclasses; Layer constants
    LAYER_ST_EPI,
    LAYER_ST_HIPP_EVENTS,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_LEARNING_QUEUE,
    LAYER_ST_PROCEDURAL,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    LAYER_ST_SOCIAL,
    LAYER_ST_VEC,
    VALID_LAYERS,
    P03StagedWrites,
    StagedOutboxEvent,
    StagedWrite,
    WriteOperation,
)

__all__ = [
    # Envelope (Issue 1.1.1 - Top-level container)
    "P03BatchEnvelope",
    # Context (Issue 1.1.2)
    "P03CycleContext",
    "generate_ulid",
    # Event State (Issue 1.1.3)
    "P03EventState",
    "ReconciliationAction",
    "PruneDecision",
    # Phase Outputs (Issue 1.1.4)
    "P03PhaseOutputs",
    "ScoredEvent",
    "HebbianEdgeUpdate",
    "EpisodeCluster",
    "DedupMerge",
    "DecayUpdate",
    "KGEntity",
    "KGEntityUpdate",
    "KGEdge",
    "KGEdgeUpdate",
    "CausalEdge",
    "GapCandidate",
    "CounterfactualScenario",
    "Insight",
    "RoutineOptimization",
    "ProspectiveMemory",
    "EventStatusUpdate",
    "TruthWrite",
    "ReconciliationSummary",
    "WriteResult",
    "WriteManifest",
    "EmittedEvent",
    "CycleSummary",
    # Staged Writes (Issue 1.1.5)
    "WriteOperation",
    "StagedWrite",
    "StagedOutboxEvent",
    "P03StagedWrites",
    "LAYER_ST_EPI",
    "LAYER_ST_SEM",
    "LAYER_ST_PROCEDURAL",
    "LAYER_ST_SOCIAL",
    "LAYER_ST_PROSPECTIVE",
    "LAYER_ST_KG_DOM",
    "LAYER_ST_KG_EDGES",
    "LAYER_ST_VEC",
    "LAYER_ST_HIPP_EVENTS",
    "LAYER_ST_LEARNING_QUEUE",
    "VALID_LAYERS",
    # Observability (Issue 1.1.6 + 1.2.4)
    "P03ObservabilityContext",
    "P03Error",
    "PIPELINE_ID",
    "VALID_PHASES",
    # Phase Transition Logging (Issue 1.2.4)
    "PhaseEventType",
    "PhaseTransitionEvent",
    "PhaseTransitionLogger",
    "PhaseTransitionLoggerProtocol",
    # R1 Phase Metrics (Issue 4.1.7)
    "R1PhaseMetrics",
    "R1_WARNING_THRESHOLD_MS",
    "R1_ERROR_THRESHOLD_MS",
    "IMPORTANCE_SCORE_BUCKETS",
    "EDGE_WEIGHT_BUCKETS",
    "DURATION_MS_BUCKETS",
    # Gap Emitter (Issue 3.2.3)
    "GapType",
    "GAP_PRIORITY_MAP",
    "P03GapEmitter",
    "P03GapEmitterConfig",
    "GapEmitResult",
    # Serializer (Issue 1.1.7)
    "InvalidPhaseTransition",
    "PhaseCheckpoint",
    "P03EnvelopeSerializer",
    "generate_phase_summary",
    # Runner Contract (Issue 1.2.1)
    "P03PhaseId",
    "P03PhaseStatus",
    "PhaseContract",
    "ResumePolicy",
    "ErrorRecovery",
    "PHASE_CONTRACTS",
    "NORMAL_TRANSITIONS",
    "SKIP_TRANSITIONS",
    "REQUIRED_PHASES",
    "SKIPPABLE_PHASES",
    "RESUME_MATRIX",
    "ERROR_RECOVERY_MATRIX",
    "is_valid_transition",
    # Phase Interface (Issue 1.2.2)
    "P03PhaseResult",
    "P03RunnerContext",
    "P03PhaseProtocol",
    "P03PhaseBase",
    "P03CycleResult",
    # Sequential Runner (Issue 1.2.3)
    "P03SequentialRunner",
    "P03RunnerError",
    "InvalidPhaseTransitionError",
    "PhaseNotRegisteredError",
    "ResumeNotAllowedError",
    "PhaseTimelineEntry",
    "create_runner",
    # Checkpoint Contract (Issue 1.2.5)
    "P03Checkpoint",
    "P03Offset",
    "CheckpointStoreProtocol",
    "CheckpointStoreBase",
    "InMemoryCheckpointStore",
    "CheckpointError",
    "CheckpointSaveError",
    "CheckpointLoadError",
    "CheckpointNotFoundError",
    "P03_SUBSCRIBER_ID",
    "P03_CHECKPOINT_TOPIC",
    "P03_SOURCE_TOPIC",
    "create_checkpoint_from_envelope",
    # Offset Manager (Issue 1.2.6)
    "P03OffsetManager",
    "OffsetAction",
    "OffsetDecision",
    "OffsetManagerError",
    "OffsetWriteError",
    "OffsetIdempotencyError",
    "OffsetStoreProtocol",
    "InMemoryOffset",
    "InMemoryOffsetStore",
    "create_offset_from_checkpoint",
    "should_advance_offset",
    # Deterministic Seeding + Skip Rules (Issue 1.2.7)
    "derive_cycle_seed",
    "derive_phase_seed",
    "P03SeededRNG",
    "P03SkipPolicy",
    "P03DeterministicContext",
    "SkipDecision",
    "SkipReason",
    "SkipPolicyConfig",
    "SkipPolicyProtocol",
    "evaluate_r5_skip",
    "evaluate_minimal_work_skip",
    "get_phases_to_skip_for_fast_path",
    "validate_skip_transition",
    "record_skip_in_envelope",
    "DEFAULT_R5_BACKLOG_THRESHOLD",
    "DEFAULT_MINIMAL_WORK_THRESHOLD",
    "R5_SKIP_PHASES",
    "MINIMAL_WORK_SKIP_PHASES",
    "DeterministicError",
    "SeedDerivationError",
    "SkipPolicyError",
    # Outbox Publisher (Issue 3.1.3)
    "OutboxPublisherConfig",
    "P03OutboxPublisher",
    "PublishResult",
    # QoS Integration (Issue 6.4.1 + 6.4.2)
    "P03SchedulerIntegration",
    "P03SchedulerProfile",
    "P03_SCHEDULER_PROFILES",
    "P03QoSContext",
    "P03_QOS_DEFAULTS",
    "create_p03_qos_context",
]
