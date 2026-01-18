"""
R7 TruthWriter Module — Issue 5.0.1

Provides components for R7 phase: commit staged writes atomically
to truth layer tables via UnitOfWork.

Spec Reference:
    - Dossier §4.8 (R7 — Memory Layer Writes / Truth Update)
    - M5_EXECUTION.md (Epic 5.2)

Components (populated as issues complete):
    - DecisionRouter: Route decisions to layer writers (5.2.1)
    - WriteResult, LayerWriteResult: Per-write success/failure tracking (5.2.1)
    - OutboxWriter: Outbox staging within transaction (5.2.2)
    - TransactionCoordinator: Atomic commit orchestration (5.2.10)

Layer Writers (in layers/ subpackage):
    - EpisodicLayerWriter: st_epi inserts/updates
    - SemanticLayerWriter: st_sem inserts/updates
    - ProceduralLayerWriter: st_procedural inserts/updates
    - SocialLayerWriter: st_social inserts/updates
    - ProspectiveLayerWriter: st_prospective inserts/updates
    - KGLayerWriter: st_kg_dom and st_kg_edges writes
    - VectorLayerWriter: st_vec writes with P08 coordination

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

# Layer writers (Issue 5.2.3, 5.2.4, 5.2.5, 5.2.6, 5.2.7, 5.2.8, 5.2.9)
from k0.modules.consolidation.truth_writer.layers import (
    P08_EMBEDDING_CREATED,
    P08_EMBEDDING_UPDATED,
    EdgeWriteData,
    EmbeddingWriteData,
    EntityAction,
    EntityWriteData,
    EpisodeWriteData,
    EpisodicLayerWriter,
    IntentionAction,
    IntentionWriteData,
    KGLayerWriter,
    P08CircuitBreakerConfig,
    PatternAction,
    PatternWriteData,
    ProceduralLayerWriter,
    ProspectiveLayerWriter,
    RelationshipAction,
    RelationshipWriteData,
    RoutineAction,
    RoutineWriteData,
    SemanticLayerWriter,
    SocialLayerWriter,
    VectorLayerWriter,
    create_episodic_writer,
    create_kg_writer,
    create_procedural_writer,
    create_prospective_writer,
    create_semantic_writer,
    create_social_writer,
    create_vector_writer,
)

# Observation recorder (Issue 7.4)
from k0.modules.consolidation.truth_writer.observation_recorder import (
    ObservationRecorder,
    get_observation_recorder,
)
from k0.modules.consolidation.truth_writer.outbox import (
    OutboxStagingResult,
    OutboxWriteConfig,
    OutboxWriter,
    create_outbox_writer,
)
from k0.modules.consolidation.truth_writer.result import LayerWriteResult, WriteResult
from k0.modules.consolidation.truth_writer.router import (
    DecisionRouter,
    DecisionRouterError,
    LayerWriterProtocol,
    WriteMode,
    create_decision_router,
)

# Transaction coordinator (Issue 5.2.10)
from k0.modules.consolidation.truth_writer.transaction import (
    LAYER_PK_MAP,
    OptimisticLockError,
    TransactionConfig,
    TransactionCoordinator,
    TransactionResult,
    create_transaction_coordinator,
)

__all__: list[str] = [
    # Issue 5.2.1 — Result dataclasses
    "LayerWriteResult",
    "WriteResult",
    # Issue 5.2.1 — Decision router
    "DecisionRouter",
    "DecisionRouterError",
    "LayerWriterProtocol",
    "WriteMode",
    "create_decision_router",
    # Issue 5.2.2 — Outbox writer
    "OutboxWriter",
    "OutboxWriteConfig",
    "OutboxStagingResult",
    "create_outbox_writer",
    # Issue 5.2.3 — Episodic layer writer
    "EpisodicLayerWriter",
    "EpisodeWriteData",
    "create_episodic_writer",
    # Issue 5.2.4 — Semantic layer writer
    "SemanticLayerWriter",
    "PatternWriteData",
    "PatternAction",
    "create_semantic_writer",
    # Issue 5.2.5 — Procedural layer writer
    "ProceduralLayerWriter",
    "RoutineWriteData",
    "RoutineAction",
    "create_procedural_writer",
    # Issue 5.2.6 — Social layer writer
    "SocialLayerWriter",
    "RelationshipWriteData",
    "RelationshipAction",
    "create_social_writer",
    # Issue 5.2.7 — Prospective layer writer
    "ProspectiveLayerWriter",
    "IntentionWriteData",
    "IntentionAction",
    "create_prospective_writer",
    # Issue 5.2.8 — KG layer writer
    "KGLayerWriter",
    "EntityWriteData",
    "EdgeWriteData",
    "EntityAction",
    "create_kg_writer",
    # Issue 5.2.9 — Vector layer writer
    "VectorLayerWriter",
    "EmbeddingWriteData",
    "P08CircuitBreakerConfig",
    "P08_EMBEDDING_CREATED",
    "P08_EMBEDDING_UPDATED",
    "create_vector_writer",
    # Issue 5.2.10 — Transaction coordinator
    "TransactionCoordinator",
    "TransactionConfig",
    "TransactionResult",
    "OptimisticLockError",
    "LAYER_PK_MAP",
    "create_transaction_coordinator",
    # Issue 7.4 — Observation recorder
    "ObservationRecorder",
    "get_observation_recorder",
]
