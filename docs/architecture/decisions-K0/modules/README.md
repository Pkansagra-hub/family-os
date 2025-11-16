# Module Architecture Decisions (K0)

**Purpose**: Architectural decisions for reusable K0 service modules. Modules are pipeline-agnostic and can be used by ANY pipeline.

**Principle**: Modules are NOT owned by pipelines. They are shared infrastructure components.

---

## Module ADR Index

### Hippocampus Modules (Memory Formation)

- **[K003: Hippocampus Architecture](k003-hippocampus-architecture.md)** - Overall hippocampus subsystem design
  - [K003.1: DG Pattern Separation](k003.1-dg-pattern-separation.md) - SimHash/MinHash fingerprinting (M01)
  - [K003.2: CA1 Semantic Bridge](k003.2-ca1-semantic-bridge.md) - Entity extraction & knowledge graph (M02)
  - [K003.3: CA3 Clustering Service](k003.3-ca3-clustering-service.md) - Episode deduplication & clustering (M03)

### Affect Module (Emotional Classification)

- **[K004: Affect Service Architecture](k004-affect-service.md)** - Emotional classification system (M04)
  - [K004.1: Tier-0 Fast Affect](k004.1-tier0-fast-affect.md) - <70ms affect classification
  - [K004.2: Multi-Modal Affect](k004.2-multimodal-affect.md) - Future: images, audio, video
  - [K004.3: Affect Learning Loop](k004.3-affect-learning-loop.md) - Future: personalized affect models

### Space Module (Visibility & Ownership)

- **[K005: Space Resolver Architecture](k005-space-resolver.md)** - ACL & ownership resolution (M05)
  - [K005.1: ACL Resolution](k005.1-acl-resolution.md) - visible_to computation
  - [K005.2: Ownership Derivation](k005.2-ownership-derivation.md) - owner_id, co_owners, author_role
  - [K005.3: Spatial Indexing](k005.3-spatial-indexing.md) - Future: space hierarchy & inheritance

### Salience Module (Attention & Priority)

- **[K006: Salience Scoring Architecture](k006-salience-scoring.md)** - Attention prioritization (M06)
  - [K006.1: Write-Path Salience](k006.1-write-path-salience.md) - Social + affect + recency scoring
  - [K006.2: Read-Path Salience](k006.2-read-path-salience.md) - Future: query-time reranking
  - [K006.3: Attention Networks](k006.3-attention-networks.md) - Future: learned attention

### Context Modules (Metadata Enrichment)

- **[K007: Context Enrichment Architecture](k007-context-enrichment.md)** - Context profiling subsystem (M08-M12)
  - [K007.1: Temporal Profiler](k007.1-temporal-profiler.md) - Time-of-day, circadian, backdating (M08)
  - [K007.2: Device Profiler](k007.2-device-profiler.md) - Device context & primary device detection (M09)
  - [K007.3: Ingress Classifier](k007.3-ingress-classifier.md) - Channel & source classification (M10)
  - [K007.4: Retention Lookup](k007.4-retention-lookup.md) - Lifecycle policy resolution (M11)
  - [K007.5: Geo Metadata Lookup](k007.5-geo-metadata.md) - Location metadata & masking (M12)
  - [K007.6: Multi-Modal Context](k007.6-multimodal-context.md) - Future: image/audio/video context

### Social Module (Relationship Graph)

- **[K008: Social Graph Architecture](k008-social-graph.md)** - Family & social network (M07)
  - [K008.1: Family Graph Resolver](k008.1-family-graph-resolver.md) - Relationship lookup & roles
  - [K008.2: Social Network Analysis](k008.2-social-network-analysis.md) - Future: extended social graphs
  - [K008.3: Interaction Patterns](k008.3-interaction-patterns.md) - Future: communication analysis

### Builder Modules (Pipeline Assembly)

- **[K009: Pipeline Builders Architecture](k009-pipeline-builders.md)** - Row assembly & queue management (M13-M14)
  - [K009.1: HippEvents Row Builder](k009.1-hipp-events-builder.md) - st_hipp_events row assembly (M13)
  - [K009.2: Embedding Queue Writer](k009.2-embedding-queue-writer.md) - st_embedding_queue management (M14)
  - [K009.3: Batch Optimization](k009.3-batch-optimization.md) - Future: vectorized operations

---

## ADR Naming Convention

**Format**: `kNNN-module-name.md` (top-level), `kNNN.N-sub-decision.md` (sub-ADRs)

**Numbering**:

- K000-K002: Infrastructure/process decisions
- K003-K009: Module architecture decisions
- K010+: Pipeline-specific decisions (reference modules by ID)

**Status Values**:

- `PROPOSED` - Under review
- `ACCEPTED` - Approved and active
- `DEPRECATED` - Superseded but still documented
- `SUPERSEDED` - Replaced by newer ADR

---

## Module Usage Pattern

Modules are imported by pipelines via dependency injection:

```python
# Pipeline imports modules (NOT the other way around)
from k0.modules.hippocampus import DGService, CA1Bridge
from k0.modules.affect import AffectService
from k0.modules.space import SpaceResolver

class P02EpisodicWrite(PipelineProtocol):
    def __init__(
        self,
        dg_service: DGService,
        affect_service: AffectService,
        space_resolver: SpaceResolver,
        # ... other modules
    ):
        self.dg = dg_service
        self.affect = affect_service
        self.space = space_resolver
```

**Key Principle**: Modules have NO knowledge of pipelines. Pipelines orchestrate modules.

---

## Cross-Cutting Concerns

### Performance Budget (Per Module)

| Module | P95 Latency | P99 Latency | Memory | Notes |
|--------|-------------|-------------|--------|-------|
| DGService | ≤15ms | ≤25ms | <10MB | Pattern separation |
| CA1Bridge | ≤40ms | ≤60ms | <50MB | External service |
| AffectService | ≤70ms | ≤100ms | <20MB | Tier-0 classification |
| SpaceResolver | ≤3ms | ≤5ms | <5MB | ACL lookup |
| SalienceScorer | ≤5ms | ≤10ms | <10MB | Write-path only |
| FamilyGraphResolver | ≤10ms | ≤20ms | <15MB | st_relationships query |
| TemporalProfiler | ≤2ms | ≤5ms | <2MB | Pure computation |
| DeviceProfiler | ≤3ms | ≤5ms | <5MB | st_devices lookup |
| IngressClassifier | ≤1ms | ≤2ms | <1MB | Pure logic |
| RetentionLookup | ≤3ms | ≤5ms | <5MB | Policy table lookup |
| GeoMetadataLookup | ≤5ms | ≤10ms | <10MB | Metadata only |

### Observability Requirements (All Modules)

- Structured logging with module name + operation
- Trace IDs propagated through all calls
- Error boundary handling (fail gracefully)
- Metrics: operation count, latency histograms, error rates

### Testing Requirements (All Modules)

- Unit tests: ≥80% coverage
- Integration tests: Real database/service interactions
- Contract tests: Interface compliance
- Performance tests: Validate latency budgets

---

## Future Module Candidates

These may warrant their own ADRs:

- **K010: Connector Ingestion** - P09 geo enrichment, place chains
- **K011: PII Detection** - P10 privacy classification
- **K012: Query Rewriter** - P04/P05 query optimization
- **K013: Consolidation Service** - P03 memory consolidation
- **K014: Learning Service** - P06 adaptation & feedback loops
- **K015: Embedding Service** - P08 vector generation

---

**Last Updated**: 2025-11-16
