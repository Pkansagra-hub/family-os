# GAP-007 Algorithm Math & Threshold Tuning Skeleton

> **Scope**: GAP-007 — R4 Knowledge Graph Edge Enrichment (Math/Thresholds)
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD
>
> **Goal**: Provide a *math + thresholds* specification skeleton for the edge enrichment algorithms
> that will run inside P03 / R4. This document is intended to be filled in during implementation.
>
---

## Document Overview

This document captures the math, scoring functions, thresholds, hyperparameters, and calibration
strategy for GAP-007 edge enrichment algorithms.

**Non-goals (for this skeleton)**:

- Final numeric values for thresholds (leave as TBD)
- Full implementation details (covered by wiring + code)
- Full schema migrations (covered elsewhere)

**Key outputs affected**:

- R4 emits `KGEdge` and `KGEdgeUpdate`
- R6 stages writes
- R7 persists to `st_kg_edges`

---

## Part A: Shared definitions (skeleton)

### A.1 Symbols and conventions

- Time is epoch milliseconds.
- Similarity is cosine similarity unless explicitly stated.

**Notation (TBD)**:

- $e$: entity
- $u, v$: entities/nodes
- $\Delta t$: time delta between observations
- $s(u,v)$: similarity score
- $w(u,v)$: edge weight
- $c(u,v)$: edge confidence

### A.2 Edge identity and directionality

- Define whether edges are treated as directed, undirected, or both depending on `relation_type`.
- Define canonical ordering rule for undirected edges.

### A.3 Weight vs confidence

- Weight ($w$) represents strength/importance for traversal/ranking.
- Confidence ($c$) represents belief/probability that relation is true.

**Open decisions (TBD)**:

- Are $w$ and $c$ always coupled (e.g., $w=c$), or separately derived?
- How do multiple algorithms combine contributions to the same edge?

### A.4 Combining multiple signals (multi-algorithm fusion)

Define the fusion rule when multiple algorithms propose the same edge:

- Max rule: $w = \max(w_i)$
- Sum rule: $w = \sum_i w_i$ (with cap)
- Bayesian update rule (if applicable)
- Confidence routing (existing router integration)

---

## Part B: Algorithm catalog (what we will use)

> This is the authoritative list of algorithms planned for GAP-007 math/threshold tuning.

### B.1 Edge enrichment algorithms (GAP-007)

- **Semantic similarity edges** (`semantic_similarity`)
- **Temporal proximity edges** (`temporal_proximity`)
- **Contextual edges** (`contextual`)
- **Transitive closure inference** (`transitive_closure`)
- **Bayesian causal inference** (`bayesian_causal`)
- **Edge weight normalization** (`weight_normalization`)

### B.2 Existing algorithms that interact with GAP-007 (reference)

- **Co-occurrence / Hebbian reinforcement** (`co_occurrence`)
- **Granger causality inference** (existing causal edges)

---

## Part C: Per-algorithm math & thresholds (skeleton)

### C.1 Semantic similarity edges (`semantic_similarity`)

#### C.1.1 Purpose

- Create edges for semantically similar entities using embedding similarity.

#### C.1.2 Inputs

- Embedding vectors $x_u, x_v \in \mathbb{R}^{768}$
- Candidate neighbor set size $k$

#### C.1.3 Scoring function

- Cosine similarity:

$$
 s(u,v) = \frac{x_u \cdot x_v}{\lVert x_u \rVert \lVert x_v \rVert}
$$

- Weight mapping (TBD):

$$
 w(u,v) = f(s(u,v))
$$

- Confidence mapping (TBD):

$$
 c(u,v) = g(s(u,v), \text{obs}(u,v))
$$

#### C.1.4 Thresholds / hyperparameters (TBD)

- `k`: TBD
- `similarity_threshold`: TBD
- `max_edges_per_entity_per_cycle`: TBD
- `max_edges_per_pair_per_cycle`: TBD

#### C.1.5 Calibration strategy (TBD)

- Offline evaluation on labeled relationships (if available)
- Proxy evaluation:
  - stability over time
  - correlation with co-occurrence

---

### C.2 Temporal proximity edges (`temporal_proximity`)

#### C.2.1 Purpose

- Create/strengthen edges when entities are observed within a short time window.

#### C.2.2 Inputs

- Observations timestamps $t_1, t_2, ...$

#### C.2.3 Scoring function (TBD)

- Exponential decay kernel:

$$
 k(\Delta t) = \exp\left(-\frac{\Delta t}{\tau}\right)
$$

- Weight aggregation rule across multiple observations (TBD):

$$
 w(u,v) = \sum_{(i,j)} k(|t_i - t_j|)
$$

#### C.2.4 Thresholds / hyperparameters (TBD)

- `temporal_window_ms`: TBD
- `tau_ms`: TBD
- `min_temporal_weight`: TBD

---

### C.3 Contextual edges (`contextual`)

#### C.3.1 Purpose

- Create edges based on shared context features (location/social/affect/activity).

#### C.3.2 Inputs (TBD)

- Context feature sets $F_u, F_v$ derived from event metadata

#### C.3.3 Scoring function (TBD)

- Jaccard similarity:

$$
 s(u,v) = \frac{|F_u \cap F_v|}{|F_u \cup F_v|}
$$

- Weighted Jaccard (if feature weights exist): TBD

#### C.3.4 Thresholds / hyperparameters (TBD)

- `context_similarity_threshold`: TBD
- Feature weighting rules: TBD

---

### C.4 Transitive closure inference (`transitive_closure`)

#### C.4.1 Purpose

- Infer edges via short paths in the KG (bounded hop count).

#### C.4.2 Inputs

- Existing edges $(u \rightarrow v)$, $(v \rightarrow w)$ and their weights/confidence

#### C.4.3 Scoring function (TBD)

- Two-hop inferred score:

$$
 s(u,w) = h\big(w(u,v), w(v,w)\big)
$$

Example attenuation (TBD):

$$
 w(u,w) = \alpha \cdot \min\big(w(u,v), w(v,w)\big)
$$

#### C.4.4 Thresholds / hyperparameters (TBD)

- `max_hops`: TBD
- `alpha` (attenuation): TBD
- `min_inferred_confidence`: TBD

---

### C.5 Bayesian causal inference (`bayesian_causal`)

#### C.5.1 Purpose

- Infer causal edges under sparse observations where Granger is insufficient.

#### C.5.2 Inputs (TBD)

- Temporal ordering evidence
- Prior distributions
- Event evidence counts

#### C.5.3 Model sketch (TBD)

- Prior: $P(\text{CAUSES}(u,v))$ from entity types / domain priors
- Likelihood from observed precedences
- Posterior update:

$$
 P(\text{CAUSES}(u,v)\mid D) \propto P(D\mid \text{CAUSES}(u,v)) \cdot P(\text{CAUSES}(u,v))
$$

#### C.5.4 Thresholds / hyperparameters (TBD)

- Prior strength: TBD
- Minimum evidence count: TBD
- Posterior threshold: TBD

---

### C.6 Edge weight normalization (`weight_normalization`)

#### C.6.1 Purpose

- Prevent runaway hubs and keep edge weights in a stable range.

#### C.6.2 Inputs

- Current outgoing/incoming edges for a node

#### C.6.3 Normalization rules (TBD)

- Sum-to-one per node:

$$
 w'(u,v) = \frac{w(u,v)}{\sum_{v'} w(u,v')}
$$

- Alternative: cap total outgoing weight, or apply softmax: TBD

#### C.6.4 Thresholds / hyperparameters (TBD)

- Target normalization strategy: TBD
- Min weight floor: TBD
- Max weight cap: TBD

---

## Part D: Validation & monitoring metrics (skeleton)

- Edge type distribution shift
- Algorithm attribution counts (`source_algorithm`)
- Precision proxies:
  - agreement with co-occurrence
  - stability across cycles
- Performance:
  - runtime per algorithm
  - edges created/updated per cycle

---

## Part E: Open decisions (skeleton)

- Evidence storage model: event IDs vs episode IDs vs both
- Canonical relation types to use for each algorithm
- Fusion rule for multi-algorithm proposals
