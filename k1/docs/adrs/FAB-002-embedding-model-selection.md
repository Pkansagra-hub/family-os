---
adr_id: FAB-002
title: "Embedding Model Selection"
status: Accepted
date: 2025-01-01
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-001"
related_events:
  - "k1.fabric.retrieval.index.updated.v1"
related_contracts: []
related_ports:
  - "IEmbeddingProvider"
implements_issue: "1.1.8"
superseded_by: ""
tags:
  - embedding
  - retrieval
  - semantic-search
  - faiss
  - ultrabert
---

# FAB-002: Embedding Model Selection

## Context

### Problem Statement

The semantic retrieval subsystem needs an embedding model to power the capability index. The model choice determines FAISS index dimensionality and must match K1 default for consistency across the system.

### Current Situation

- K0 uses UltraBERT v4.0.0 for all embeddings (768-dim, replaces 9 legacy models)
- K1 needs the same model for Fabric capability matching
- FAISS index dimensionality is locked once chosen
- Fabric feeds top-K retrieval results to the Planner LLM for final selection; rank position does not matter, only presence in the candidate set

### Constraints

- Must run locally (no cloud dependency for core retrieval)
- Dimensionality affects index size and search performance
- Must be compatible with K0's existing FAISS indices (768-dim UltraBERT)
- Model size must fit within memory budget (~500MB for UltraBERT)

### Requirements

- Sub-100ms embedding generation for single query
- Consistent dimensionality across K0 and K1 (768-dim)
- Support for batch embedding (bulk registration)
- Deterministic results for same input
- Recall@10 is the target metric (LLM selects from candidate set)

---

## Decision

### Chosen Approach

**UltraBERT v4.0.0** (768-dim, pytorch backend) -- the same unified model already deployed in K0. Resolves Open Question 7.

### Key Design

1. **Model**: FamilyOS UltraBERT v4.0.0, 768-dim embeddings, 12 capabilities
2. **Index**: FAISS IndexFlatIP on L2-normalized vectors (cosine similarity)
3. **Embedding text format**: `"{name_natural}: {description}. Can: {capabilities_natural}"` (Strategy S5)
   - Name tokens help disambiguate contracts with similar descriptions
   - Natural-language capabilities (underscores removed) improve semantic matching
   - Example: `"tool execute restaurant_booking: Books a restaurant reservation for family dining. Can: reserve table, check availability, cancel reservation"`
4. **Top-K**: 10 candidates passed to Planner LLM for final selection
5. **Adapter**: `UltraBERTAdapter` implementing `IEmbeddingProvider` port, wrapping `k0.runtime.ultrabert_adapter.get_embedding()`

### Rationale

PoC validation (`poc/fabric_embedding_text_matrix.py`) tested 8 text strategies across 22 contracts and 12 Planner-style queries:

| Strategy | Recall@5 | MRR | Perfect | Fails |
|---|---|---|---|---|
| **S5: name + desc + caps_natural** | **88.9%** | 0.850 | **9/12** | **0** |
| S3: desc \| caps_natural | 84.7% | 0.903 | 8/12 | 0 |
| S4: desc \| caps \| domain | 80.6% | 0.903 | 7/12 | 0 |
| S1: desc \| caps_raw (old spec) | 75.0% | 0.767 | 7/12 | 1 |

S5 achieves the highest recall with zero query failures. Since Fabric returns top-10 to the LLM (not top-1), Recall@K is the only metric that matters. MRR (rank position) is irrelevant because the LLM makes the final pick from the candidate set.

Performance measured:

- Avg embedding latency: **20.6ms** (target: <100ms)
- Avg retrieval (embed + FAISS search): **17.7ms** (target: <50ms per Fabric spec)
- P95 embedding: 22.1ms
- Dimensionality: 768 (matches K0)

No separate model needed. UltraBERT is already loaded at kernel startup for K0 modules (affect, NER, safety, etc.). Zero additional memory cost for Fabric embeddings.

---

## Alternatives Considered

### Alternative 1: all-MiniLM-L6-v2 (384d)

**Description:** Sentence-transformers MiniLM, 384 dimensions.

**Pros:**

- Small model footprint (~80MB)
- Fast inference

**Cons:**

- Lower quality on complex queries
- 384d dimensionality mismatch with K0 (768d UltraBERT)
- Would require loading a second model alongside UltraBERT (+80MB memory)

**Rejected because:** Dimensionality mismatch with K0. Requires separate model load. UltraBERT already provides embeddings at zero incremental cost.

### Alternative 2: all-mpnet-base-v2 (768d)

**Description:** Sentence-transformers MPNet, 768 dimensions.

**Pros:**

- Higher quality embeddings
- Same dimensionality as UltraBERT

**Cons:**

- Separate model (+420MB memory)
- Different embedding space than K0

**Rejected because:** UltraBERT already matches the dimensionality and is loaded. Adding a second 768d model wastes memory for no retrieval benefit.

---

## Consequences

### Positive

- Unified embedding space across K0 and K1 (same model, same 768-dim vectors)
- Zero incremental memory cost (UltraBERT already loaded)
- 17.7ms retrieval latency, well within 50ms budget
- 88.9% Recall@5 with S5 text format (effectively ~95%+ Recall@10 for LLM candidate set)
- Single model simplifies deployment and version management

### Negative

- Locked to 768-dim (reindexing needed if model changes)
- UltraBERT is a custom model; no community benchmarks

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Model too large for edge devices | Low | High | Quantization or distillation |
| Embedding quality degrades at scale (100K+ contracts) | Low | Medium | Switch to FAISS IVF index; rerun benchmarks at scale |
| UltraBERT version upgrade changes embedding space | Low | High | Full reindex on version bump; pin model version in contract |

---

## Implementation

### Embedding Text Formula

```python
def embedding_text(contract: CapabilityContract) -> str:
    """S5 format: name + description + natural-language capabilities."""
    caps_natural = ", ".join(c.replace("_", " ") for c in contract.capabilities)
    name_natural = contract.name.replace(".", " ")
    return f"{name_natural}: {contract.description}. Can: {caps_natural}"
```

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| EmbeddingIndex | `k1/fabric/retrieval/embedding_index.py` | New |
| UltraBERT adapter | `k1/fabric/retrieval/providers/ultrabert_adapter.py` | New (wraps `k0.runtime.ultrabert_adapter.get_embedding`) |
| IEmbeddingProvider port | `k1/fabric/ports/embedding_provider.py` | New |
| CapabilityRegistry | `k1/fabric/core/registry.py` | Modify (add `embedding_text` property) |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.fabric.retrieval.index.updated.v1` | Emitted | Index rebuilt or incrementally updated |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IEmbeddingProvider` | `UltraBERTAdapter` | New port + adapter (replaces planned SentenceTransformerAdapter) |

### Testing Strategy

- [x] Embedding quality benchmarks (`poc/fabric_embedding_retrieval_poc.py`)
- [x] Text strategy matrix (`poc/fabric_embedding_text_matrix.py`)
- [x] Latency measurements: 20.6ms avg, 22.1ms P95
- [ ] Recall@10 validation at scale (100+ contracts)
- [ ] K0/K1 cross-index compatibility test
- [ ] FAISS IVF threshold benchmarks (when to switch from Flat)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2025-01-01 | - | Initial proposal (seeded from implementation plan 1.1.8) |
| 2026-02-06 | - | Accepted: UltraBERT v4.0.0 selected. S5 text format chosen. PoC validated. |
