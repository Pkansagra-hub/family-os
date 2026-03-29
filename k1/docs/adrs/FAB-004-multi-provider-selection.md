---
adr_id: FAB-004
title: "Multi-Provider Selection"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-001"
  - "FAB-002"
  - "FAB-005"
related_events:
  - "k1.fabric.provider.ranked.v1"
  - "k1.fabric.provider.selected.v1"
related_contracts: []
related_ports:
  - "IProviderSelector"
  - "ISoftRanker"
implements_issue: "1.1.10"
superseded_by: ""
tags:
  - provider-selection
  - ranking
  - resolution
  - retrieval
---

# FAB-004: Multi-Provider Selection

## Context

### Problem Statement

When multiple providers can handle the same capability, the system needs a deterministic selection mechanism. The architecture mentions both a Retrieval Soft Ranker and a Provider Selector but does not clarify whether these are the same component or distinct, and what scoring algorithm is used.

### Current Situation

- fabric_discussion.md defines ProviderSelector in Resolution subsystem (Role 2)
- Retrieval subsystem (Role 1) has SemanticIndex + SoftRanker for semantic scoring
- FAB-002 decided UltraBERT v4.0.0 with S5 text format, top-10 results sent to Resolution
- Open Question #8 asks: "Is Retrieval Soft Ranker the same as Provider Selector?"
- No ranking algorithm is specified beyond cosine similarity

### Constraints

- Must be deterministic for same inputs
- Must support policy-based filtering AFTER ranking (PolicyGuard)
- Must handle provider priority levels (preferred, fallback)
- Must degrade gracefully when preferred provider unavailable
- Retrieval returns top-10 candidates to Resolution (FAB-002 decision)

### Requirements

- Score and rank up to 10 candidates (top-K from Retrieval)
- Primary scoring factor: semantic similarity from FAISS (already computed)
- Secondary factors: historical success rate, provider latency, provider type priority
- Policy veto after ranking (security, privacy constraints via PolicyGuard)
- Fallback chain when top-ranked provider fails at execution

---

## Decision

### Chosen Approach: Two-Stage Pipeline — Retrieval SoftRanker + Resolution ProviderSelector

Retrieval and Resolution are distinct components with distinct responsibilities:

### Stage 1: Retrieval SoftRanker (Role 1)

```
SemanticIndex.search(intent)
  -> FAISS top-10 by cosine similarity
  -> SoftRanker re-scores with lightweight heuristics
  -> Returns ranked RetrievalResult (top-10 candidates)
```

**SoftRanker responsibilities:**



- Re-rank FAISS results using capability match score (exact match boost)
- Apply name similarity bonus (fuzzy match on capability name)
- Filter out below-threshold candidates (cosine similarity < 0.3)
- Output: `RetrievalResult` with `similarity_score` per candidate

### Stage 2: Resolution ProviderSelector (Role 2)

```
ProviderSelector.resolve(retrieval_result, request)
  -> Apply operational scoring (success rate, latency, type priority)
  -> Combine with semantic score from Stage 1
  -> PolicyGuard.check(top_candidate, request)
  -> Returns selected provider (or fallback chain)
```



**ProviderSelector responsibilities:**

- Combine semantic score with operational scores
- Apply provider type priority weights
- Build fallback chain (top-3 ranked providers)
- Delegate policy check to PolicyGuard

### Scoring Formula

```python
def score_provider(candidate: RetrievalCandidate, stats: ProviderStats) -> float:
    """
    Weighted composite score for provider selection.

    All factors normalized to [0.0, 1.0] before weighting.
    """
    semantic_score = candidate.similarity_score        # From FAISS (0.0 to 1.0)
    success_rate = stats.success_rate_7d               # Last 7 days (0.0 to 1.0)
    latency_score = 1.0 - min(stats.p95_latency_ms / 1000.0, 1.0)  # Lower is better
    type_priority = TYPE_PRIORITY_MAP[candidate.provider_type]       # See below

    return (
        0.50 * semantic_score +    # Dominant factor: semantic relevance
        0.20 * success_rate +      # Reliability matters
        0.15 * latency_score +     # Speed matters
        0.15 * type_priority       # Prefer tools over agents (cheaper)
    )

TYPE_PRIORITY_MAP = {
    "tool":      1.0,   # Direct MCP tool — fast, deterministic, cheap
    "composite": 0.7,   # Multi-step capability — medium cost
    "agent":     0.5,   # LLM-backed agent — slow, non-deterministic, expensive
}
```

### Why This Separation

| Concern | Retrieval SoftRanker | Resolution ProviderSelector |
|---|---|---|
| **Input** | Raw FAISS cosine scores | Ranked candidates + operational stats |
| **Scoring basis** | Semantic similarity only | Composite (semantic + operational) |
| **Performance data** | None (no access to stats) | Success rates, latencies, error rates |
| **Policy** | None | PolicyGuard check after ranking |
| **Output** | RetrievalResult (top-10) | Selected provider + fallback chain |
| **Stateless?** | Yes | Reads ProviderStats (read-only) |

**Answer to Open Question #8:** Retrieval SoftRanker and ProviderSelector are DISTINCT. SoftRanker handles semantic refinement. ProviderSelector handles operational scoring and policy.

### Fallback Chain

```python
@dataclass(frozen=True)
class SelectionResult:
    """Result of provider selection with fallback chain."""
    primary: RetrievalCandidate        # Top-ranked provider
    fallbacks: list[RetrievalCandidate] # Next 2 providers (ordered by score)
    scores: dict[str, float]           # contract_name -> composite_score
    policy_vetoed: list[str]           # contract_names rejected by PolicyGuard

async def execute_with_fallback(
    selection: SelectionResult,
    request: CapabilityRequest,
    factory: AgentFactory,
) -> CapabilityResult:
    """Execute with automatic fallback on failure."""
    providers = [selection.primary] + selection.fallbacks

    for provider in providers:
        result = await factory.execute(provider, request)
        if result.status == RequestStatus.COMPLETED:
            return result
        # Log failure, try next fallback

    return CapabilityResult.failure(
        request_id=request.trace_id,
        error=f"All {len(providers)} providers failed for intent: {request.intent}",
    )
```

### Rationale

1. **Separation of concerns**: Retrieval knows semantics; Resolution knows operations. Merging them would couple FAISS scoring with latency/success tracking.
2. **Top-10 to top-1 reduction**: Retrieval produces a manageable candidate set (10); Resolution picks the best considering real-world performance data.
3. **Semantic score dominant (50%)**: The primary question is "can this provider handle the intent?" — semantic similarity answers this best.
4. **Tool preference**: Tools are deterministic, fast, and cheap. Agents require LLM calls. Preferring tools when semantics are equal reduces cost and latency.
5. **Fallback chain**: Instead of re-running the full pipeline on failure, keep the top-3 and try the next one (<5ms overhead).

---

## Alternatives Considered

### Alternative 1: Single ProviderSelector (no SoftRanker)


**Description:** ProviderSelector handles everything — takes raw FAISS scores + operational stats.



**Pros:**

- Single component, simpler pipeline

- One scoring formula

**Cons:**

- ProviderSelector needs FAISS internals (coupling)
- No separation between "what can handle this?" and "who should handle this?"
- Harder to test semantic scoring independently


**Rejected because:** Tight coupling between semantic retrieval and operational selection makes both harder to evolve independently.

### Alternative 2: LLM-Based Selection



**Description:** Send top-10 candidates + request to LLM, let it pick the best provider.

**Pros:**


- Handles nuanced intent disambiguation
- Can reason about complex multi-step capabilities

**Cons:**


- LLM call adds 200-2000ms to every request
- Non-deterministic (violates constraint)
- Cost per selection ~$0.001 (adds up at scale)
- Fabric invariant: NO LLM in Retrieval or Resolution (FAB-05)


**Rejected because:** Fabric itself never calls LLM (Invariant FAB-05). Also violates determinism requirement and adds unacceptable latency.


### Alternative 3: Pluggable Scoring Strategy (Strategy Pattern)

**Description:** ProviderSelector uses strategy pattern with pluggable scorers.


**Pros:**

- Most extensible
- Easy to add new scoring dimensions

**Cons:**

- Over-engineering for initial implementation
- Strategy selection itself needs configuration
- Harder to reason about composite score behavior

**Rejected because:** Premature abstraction. The fixed 4-factor formula (semantic, success, latency, type) is sufficient for M1-M3. Can refactor to strategy pattern in M4+ if new scoring dimensions emerge.

---

## Consequences

### Positive

- Clean separation: Retrieval handles semantics, Resolution handles operations
- Deterministic ranking (same inputs = same scores)
- Fallback chain eliminates re-running the full pipeline on failure
- Tool preference reduces cost and latency automatically

### Negative

- Two components to maintain (SoftRanker + ProviderSelector)
- Fixed weight formula (0.50/0.20/0.15/0.15) may need tuning
- ProviderStats requires a metrics collection pipeline (dependency on observability)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Weight formula suboptimal | Medium | Medium | A/B test weights; log all scores for analysis |
| ProviderStats unavailable at startup | High | Low | Default to semantic-only scoring (weight = 1.0) when no stats |
| Policy veto rejects all providers | Low | High | Return helpful error with vetoed reasons; surface to Orchestrator |
| Fallback chain always hits provider 3 | Low | Medium | Monitor fallback rate; investigate consistently failing providers |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| SoftRanker | `k1/fabric/retrieval/soft_ranker.py` | New |
| ProviderSelector | `k1/fabric/resolution/selector.py` | New |
| ProviderStats | `k1/fabric/resolution/stats.py` | New |
| SelectionResult | `k1/fabric/types/selection.py` | New |
| ScoreCalculator | `k1/fabric/resolution/scoring.py` | New |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.fabric.provider.ranked.v1` | Emitted | All candidates scored and ranked |
| `k1.fabric.provider.selected.v1` | Emitted | Primary provider selected from ranked list |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IProviderSelector` | `WeightedProviderSelector` | New port |
| `ISoftRanker` | `SemanticSoftRanker` | New port |
| `IProviderStats` | `InMemoryProviderStats` | New port (metrics backend) |

### Testing Strategy

- [ ] Ranking determinism tests (same input = same output, 100 runs)
- [ ] Weight formula tests (verify each factor contributes correctly)
- [ ] Fallback chain tests (primary fails -> secondary succeeds)
- [ ] Policy veto tests (vetoed provider excluded, next best selected)
- [ ] Cold start tests (no ProviderStats -> semantic-only scoring)
- [ ] Type priority tests (tool preferred over agent at equal semantic score)
- [ ] Performance benchmarks (score + rank 10 providers <5ms)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2025-01-01 | - | Initial proposal (seeded from implementation plan 1.1.10) |
| 2026-02-06 | - | Accepted: Two-stage pipeline, weighted composite scoring, fallback chain. |
