---
adr_number: 'K003'
affected_layers: ['k0/modules/hippocampus']
affected_modules: ['M01', 'M02', 'M03']
authors:
- K0 Architecture Team
concerns:
- memory-formation
- pattern-separation
- semantic-extraction
date_created: '2025-11-16'
date_updated: '2025-11-16'
implementation_date: null
implementation_phase: 'P02-EPISODIC-WRITE'
implementation_status: PLANNING
propagation:
  affected_adrs: ['K003.1', 'K003.2', 'K003.3']
  affected_contracts: ['k0/contracts/modules/hippocampus_protocol.yml']
  affected_tests: ['tests/k0/modules/hippocampus/']
  triggers:
  - Any pipeline requiring episodic memory formation
  - Pattern separation for deduplication
  - Semantic extraction for knowledge graphs
related_adrs: []
related_contracts: ['PipelineProtocol', 'SyscallProtocol']
related_diagrams: ['architecture_diagrams/k0/k0_source_of_truth.mmd']
research_citations:
- 'Treves & Rolls (1994) - Computational analysis of hippocampal function'
- 'O''Reilly & McClelland (1994) - Hippocampal conjunctive encoding'
status: PROPOSED
superseded_by: []
supersedes: []
title: Hippocampus Module Architecture
---

# K003: Hippocampus Module Architecture

**Status**: PROPOSED

**Date**: 2025-11-16

**Authors**: K0 Architecture Team

## Context

The hippocampus subsystem is responsible for **episodic memory formation** in the intelligence kernel. It implements three core functions inspired by biological hippocampal structure:

1. **DG (Dentate Gyrus)**: Pattern separation via SimHash/MinHash fingerprinting
2. **CA1**: Semantic projection via entity extraction and knowledge graph construction
3. **CA3**: Episode clustering and deduplication via similarity queries

### Current Pain Points

- No unified hippocampus abstraction
- Fingerprinting logic scattered across codebase
- Entity extraction tightly coupled to specific pipelines
- Deduplication happens ad-hoc without systematic clustering

### Business Drivers

- **P02** needs fast pattern separation (<15ms) for write-path enrichment
- **P03** needs clustering to consolidate similar memories
- **P04** needs semantic indexing for working memory queries
- **P06** needs episode similarity for learning loops

### Constraints

- DG must be <15ms P95 (inline in P02)
- CA1 can be external service (40ms acceptable)
- CA3 operates in background (no latency constraint)
- Must support 10K events/day throughput per tenant

## Decision

Create three independent modules under `k0/modules/hippocampus/`:

### 1. DGService (M01) - Pattern Separation

**Location**: `k0/modules/hippocampus/dg_service.py`

**Responsibility**: Generate perceptual fingerprints for deduplication

**Interface**:
```python
@dataclass
class DGFingerprint:
    simhash_hex: str  # 64-bit SimHash
    minhash32: list[int]  # 32 permutations
    input_features: dict  # text, participants, place, time
    computation_ms: float

class DGService:
    def compute_fingerprint(self, envelope: Envelope) -> DGFingerprint:
        """Generate DG fingerprint from envelope content."""
        pass
```

**Current Capabilities**:
- SimHash computation from text + metadata
- MinHash signature generation (32 permutations)
- Fast <15ms P95 performance

**Future Capabilities** (see K003.1):
- Adaptive MinHash permutations (16-128 based on content)
- Locality-sensitive hashing (LSH) for neighbor queries
- Multi-modal fingerprinting (images, audio)

### 2. CA1Bridge (M02) - Semantic Extraction

**Location**: `k0/modules/hippocampus/ca1_bridge.py`

**Responsibility**: Extract entities and knowledge graph triples

**Interface**:
```python
@dataclass
class CA1Projection:
    entities: list[Entity]  # Extracted entities
    kg_triples: list[KGTriple]  # Subject-predicate-object
    embedding_id: str  # UUID for P08
    confidence: float

class CA1Bridge:
    async def project_semantic(self, text: str, context: dict) -> CA1Projection:
        """Extract semantic structure from text."""
        pass
```

**Current Capabilities**:
- Entity extraction (people, places, activities)
- Knowledge graph triple generation
- Embedding ID allocation for P08

**Future Capabilities** (see K003.2):
- Multi-hop reasoning over knowledge graph
- Temporal entity resolution (person_dad vs person_son1)
- Cross-document entity linking

### 3. CA3Service (M03) - Clustering

**Location**: `k0/modules/hippocampus/ca3_service.py`

**Responsibility**: Find near-duplicates and cluster episodes

**Interface**:
```python
@dataclass
class CA3Cluster:
    episode_cluster_id: str
    member_event_ids: list[str]
    cluster_confidence: float
    representative_event_id: str  # Canonical event

class CA3Service:
    def find_near_duplicates(self, simhash: str, minhash: list[int]) -> list[str]:
        """Query st_hipp_events for similar fingerprints."""
        pass

    def cluster_episodes(self, event_ids: list[str]) -> list[CA3Cluster]:
        """Group similar episodes into clusters."""
        pass
```

**Current Capabilities**:
- Hamming distance queries on SimHash
- Jaccard similarity on MinHash
- Cluster assignment and confidence scoring

**Future Capabilities** (see K003.3):
- Incremental clustering (update clusters on new events)
- Hierarchical clustering (sub-episode detection)
- Novelty scoring (deviation from known patterns)

## Architecture Diagram References

- `architecture_diagrams/k0/k0_source_of_truth.mmd` (Hippocampus subsystem)
- `architecture_diagrams/k0/p02_write_driver_architecture.mmd` (DG usage in P02)

## Consequences

### Positive

- **Reusability**: Any pipeline can use hippocampus modules (P02, P03, P04, P06)
- **Performance isolation**: DG optimized for speed, CA3 for accuracy
- **Clear brain analog**: Maps directly to neuroscience literature
- **Testability**: Each module independently testable

### Negative

- **Three separate modules**: More code to maintain vs monolithic service
- **Coordination complexity**: P02 calls DG inline, P03 calls CA3 async
- **Data dependency**: CA3 requires DG outputs in st_hipp_events

### Risks

- **DG performance**: If >15ms, blocks P02 write path
  - *Mitigation*: Performance tests in CI, fallback to async if needed
- **CA1 availability**: External service downtime impacts P02
  - *Mitigation*: Circuit breaker, graceful degradation (skip entities)
- **CA3 scale**: Clustering cost grows O(n²) with episode count
  - *Mitigation*: Batch processing, LSH indexing, periodic re-clustering

## Alternatives Considered

### Alternative 1: Monolithic HippocampusService

**Description**: Single service with `pattern_separate()`, `extract_semantic()`, `cluster()` methods

**Rejected because**:
- Performance requirements differ (DG <15ms, CA3 no limit)
- Deployment differs (DG inline, CA1 external, CA3 background)
- Testing harder (can't test pattern separation without semantic extraction)

### Alternative 2: External Hippocampus API

**Description**: All three functions behind REST/gRPC API

**Rejected because**:
- DG latency budget too tight for network calls
- Increases operational complexity (another service to deploy)
- Loses type safety (serialization overhead)

### Alternative 3: Pipeline-Specific Implementations

**Description**: P02 implements DG, P03 implements CA3, etc.

**Rejected because**:
- Code duplication across pipelines
- No shared fingerprinting logic
- Can't reuse DG fingerprints from P02 in P03

## Implementation Notes

### Phase 1: DG Pattern Separation (P02)

1. Create `k0/modules/hippocampus/dg_service.py`
2. Implement SimHash + MinHash algorithms
3. Add performance tests (<15ms P95)
4. Integrate into P02EpisodicWrite

### Phase 2: CA1 Semantic Bridge (P02)

1. Create `k0/modules/hippocampus/ca1_bridge.py`
2. Implement HTTP client to external CA1 service
3. Add circuit breaker and fallback logic
4. Integrate into P02EpisodicWrite

### Phase 3: CA3 Clustering (P03)

1. Create `k0/modules/hippocampus/ca3_service.py`
2. Implement similarity queries on st_hipp_events
3. Implement clustering algorithm (DBSCAN or hierarchical)
4. Create P03 pipeline using CA3Service

### Testing Requirements

- **DGService**: Unit tests (100% coverage), perf tests (<15ms)
- **CA1Bridge**: Integration tests (mock external service), contract tests
- **CA3Service**: Integration tests (real st_hipp_events), clustering accuracy tests

### Migration Path

- No breaking changes (new modules)
- Existing code can gradually adopt hippocampus modules
- st_hipp_events schema already supports DG/CA3 columns

## Sub-ADRs

- **[K003.1: DG Pattern Separation](k003.1-dg-pattern-separation.md)** - SimHash/MinHash implementation
- **[K003.2: CA1 Semantic Bridge](k003.2-ca1-semantic-bridge.md)** - Entity extraction & KG
- **[K003.3: CA3 Clustering Service](k003.3-ca3-clustering-service.md)** - Deduplication & clustering

## References

- **Module Registry**: `k0/pipelines/k0_architecture_master.md` (M01, M02, M03)
- **P02 Dossier**: `docs/pipelines/P02_write_dossier.md`
- **Research**: Treves & Rolls (1994), O'Reilly & McClelland (1994)

## Revision History

- 2025-11-16: Initial draft (K0 Architecture Team)
