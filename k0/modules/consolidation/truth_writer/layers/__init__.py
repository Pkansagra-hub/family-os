"""
R7 Layer Writers — Issue 5.0.1

Per-layer write implementations for R7 TruthWriter.

Each layer writer knows how to:
    - Map StagedWrite data to table columns
    - Apply layer-specific validation
    - Handle INSERT/UPDATE/ARCHIVE/TOMBSTONE operations
    - Report WriteResult with success/failure details

Spec Reference:
    - Dossier §4.8.2-4.8.8 (Per-Layer Write Specs)
    - M5_EXECUTION.md (Epic 5.2)

Layer Writers (populated as issues complete):
    - EpisodicLayerWriter: st_epi — Episode clusters (Issue 5.2.W1.1)
    - SemanticLayerWriter: st_sem — Semantic patterns (Issue 5.2.W1.2)
    - ProceduralLayerWriter: st_procedural — Procedural habits (Issue 5.2.W1.3)
    - SocialLayerWriter: st_social — Social relationships (Issue 5.2.W1.4)
    - ProspectiveLayerWriter: st_prospective — Prospective intentions (Issue 5.2.W1.5)
    - KGLayerWriter: st_kg_dom + st_kg_edges — KG entities/edges (Issue 5.2.W1.6)
    - VectorLayerWriter: st_vec — Embeddings with P08 coord (Issue 5.2.W1.7)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

# Episodic layer (st_epi) - Issue 5.2.3
from k0.modules.consolidation.truth_writer.layers.episodic import (
    EpisodeWriteData,
    EpisodicLayerWriter,
    create_episodic_writer,
)

# KG layer (st_kg_dom, st_kg_edges) - Issue 5.2.8
from k0.modules.consolidation.truth_writer.layers.kg import (
    EdgeWriteData,
    EntityAction,
    EntityWriteData,
    KGLayerWriter,
    create_kg_writer,
)

# Procedural layer (st_procedural) - Issue 5.2.5
from k0.modules.consolidation.truth_writer.layers.procedural import (
    ProceduralLayerWriter,
    RoutineAction,
    RoutineWriteData,
    create_procedural_writer,
)

# Prospective layer (st_prospective) - Issue 5.2.7
from k0.modules.consolidation.truth_writer.layers.prospective import (
    IntentionAction,
    IntentionWriteData,
    ProspectiveLayerWriter,
    create_prospective_writer,
)

# Semantic layer (st_sem) - Issue 5.2.4
from k0.modules.consolidation.truth_writer.layers.semantic import (
    PatternAction,
    PatternWriteData,
    SemanticLayerWriter,
    create_semantic_writer,
)

# Social layer (st_social) - Issue 5.2.6
from k0.modules.consolidation.truth_writer.layers.social import (
    RelationshipAction,
    RelationshipWriteData,
    SocialLayerWriter,
    create_social_writer,
)

# Vector layer (st_vec) - Issue 5.2.9
from k0.modules.consolidation.truth_writer.layers.vector import (
    P08_EMBEDDING_CREATED,
    P08_EMBEDDING_UPDATED,
    EmbeddingWriteData,
    P08CircuitBreakerConfig,
    VectorLayerWriter,
    create_vector_writer,
)

__all__: list[str] = [
    # Episodic layer (st_epi) - Issue 5.2.3
    "EpisodicLayerWriter",
    "EpisodeWriteData",
    "create_episodic_writer",
    # Semantic layer (st_sem) - Issue 5.2.4
    "SemanticLayerWriter",
    "PatternWriteData",
    "PatternAction",
    "create_semantic_writer",
    # Procedural layer (st_procedural) - Issue 5.2.5
    "ProceduralLayerWriter",
    "RoutineWriteData",
    "RoutineAction",
    "create_procedural_writer",
    # Social layer (st_social) - Issue 5.2.6
    "SocialLayerWriter",
    "RelationshipWriteData",
    "RelationshipAction",
    "create_social_writer",
    # Prospective layer (st_prospective) - Issue 5.2.7
    "ProspectiveLayerWriter",
    "IntentionWriteData",
    "IntentionAction",
    "create_prospective_writer",
    # KG layer (st_kg_dom, st_kg_edges) - Issue 5.2.8
    "KGLayerWriter",
    "EntityWriteData",
    "EdgeWriteData",
    "EntityAction",
    "create_kg_writer",
    # Vector layer (st_vec) - Issue 5.2.9
    "VectorLayerWriter",
    "EmbeddingWriteData",
    "P08CircuitBreakerConfig",
    "P08_EMBEDDING_CREATED",
    "P08_EMBEDDING_UPDATED",
    "create_vector_writer",
]
