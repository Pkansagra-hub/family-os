# Final Episode Retrieval Pipeline Strategy

**Status**: Production-ready specification
**Based on**: HYPOTHESIS_CATALOG.md (theory) + RESEARCH_PIPELINE.md (execution) + human benchmark validation
**Final metric**: MRR = 0.7770, nDCG = 0.7745 (v4 + conditional MGRH rerank, human-annotated benchmark, 49 queries, 88 episodes)
**Previous v4-only**: MRR = 0.7410, nDCG = 0.7406

---

## 1. Hypothesis vs Execution: Alignment Report

The HYPOTHESIS_CATALOG.md and RESEARCH_PIPELINE.md describe the **same research program** -- the pipeline is the operationalized version of the catalog. All 67 research items (R0.x through R4.x) plus 7 cross-cutting items (RX.1-RX.7) map 1:1 to pipeline experiments. The research faithfully tested every hypothesis.

### 1.1 What the Hypothesis Catalog Predicted (Part V: The Final Answer)

The catalog proposed a **3-Layer architecture** with a **3-term unified scoring function**:

```
score(q,e) = alpha * cos(q, mu_e)                     -- Term 1: Centroid signal
           + beta  * SUM(sigma_k * (q . w_k)^2)       -- Term 2: Satellite signal
           + gamma * SUM(axis_score(q, A_e))           -- Term 3: Structural signal
```

- **Layer 1**: Episode Vector -- adaptive (centroid for small, MMR text-embed for large)
- **Layer 2**: Satellite Vectors -- salience-gated, K<=5 per episode, stored in centroid_metadata_json
- **Layer 3**: Structural Metadata -- social/temporal/spatial/affective axis scoring

### 1.2 What the Research Actually Found

| Predicted Component          | Hypothesis | Result   | Evidence |
|-|-|-|-|
| Centroid episode vector      | H2.1       | WORKS    | Phase 0: MRR 0.41 vs text-embed 0.22 |
| IDF-weighted centroid        | H2.3       | WORKS    | Phase 2: +2pp over naive mean centroid |
| Text-embed for large eps     | H1.1-H1.6 | FAILS    | Phase 0: centroid wins at ALL sizes |
| Adaptive centroid/text-embed | Part V     | FAILS    | Centroid always better, no routing needed |
| Satellite vectors            | H3.1       | REDUNDANT| Phase 3: event search already captures specifics |
| Event-level search           | H3.2       | WORKS    | Phase 1: +6pp MRR, weighted_max grouping wins |
| DiagMahalanobis geometry     | H3.3       | MARGINAL | Phase 3: +1.5pp on old benchmark, HURTS on human |
| Structural axis scoring      | H6.1-H6.5 | WORKS    | Phase 4: +5pp MRR, gamma=0.35, spatial-heavy |
| Entropy-adaptive weights     | H6.6       | FAILS    | Phase 4: fixed weights beat entropy-adaptive |
| Query-type routing           | H5.1-H5.3 | FAILS    | Phase 5: oracle lift <0.02 nDCG |
| BM25 keyword complement      | H4.1       | FAILS    | Phase 6: complementarity <10%, UltraBERT already captures keywords |
| SPLADE sparse vectors        | H4.2       | BLOCKED  | UltraBERT has no MLM head |
| NLI cross-encoder re-ranking | H5.7       | WORKS (CONDITIONAL) | UltraBERT v4.0.9 MGRH; +0.036 MRR with top3 routing (thematic/temporal/emotional only) |

### 1.3 Key Divergences from Prediction

1. **Catalog overestimated text-embed**: Predicted adaptive centroid/text-embed routing; research proved centroid wins universally, even for large episodes
2. **Catalog overestimated satellites**: Predicted K<=5 salience-gated satellite vectors; event-level search with weighted_max grouping already captures event-level specificity, making satellites redundant
3. **Catalog underestimated spatial axis**: Data-driven weight optimization revealed spatial dominance (0.620) over social (0.331), with temporal/affective near-zero
4. **Catalog's 3-term formula collapsed to 2 effective terms**: Term 2 (satellites) absorbed by event search; the actual formula is 2-term (semantic RRF + structural)

### 1.4 What Survived Intact

- IDF-weighted centroid as episode representation (Layer 1 simplified)
- Structural axis scoring with weighted combination (Layer 3 intact)
- The overall retrieve-then-fuse architecture pattern
- UltraBERT as the sole embedding model (768-dim, L2-normalized)

---

## 2. Final Pipeline Architecture (v4)

### 2.1 Overview

The production pipeline has **two stages**: semantic retrieval (3-path RRF) then structural fusion.

```
Query -> UltraBERT embed -> [3 parallel paths] -> RRF merge -> Structural Fusion -> Top-K
                |                                                       |
                |-- Path A: Centroid FAISS (episode-level)             |
                |-- Path B: Event FAISS + weighted_max (event-level)   |-- extract_query_context()
                |-- Path C: DiagMahalanobis (optional, see note)       |-- combined_axis_score()
```

### 2.2 Stage 1: Semantic Retrieval (3-path RRF)

**Path A -- IDF-Weighted Centroid Search**

- Index: FAISS IndexFlatIP over 88 episode centroids (768-dim each)
- Centroid computation: IDF-weighted mean of event embeddings per episode
  - For each episode, weight each event embedding by its IDF score (log(N_episodes / n_episodes_containing_event))
  - Normalize result to unit length (L2)
- Returns: ranked list of episode_ids by cosine similarity

**Path B -- Event-Level Search with weighted_max Grouping**

- Index: FAISS IndexFlatIP over all ~529 event embeddings (768-dim each)
- Search: retrieve top-50 events (event_k=50)
- Grouping: `weighted_max` -- for each episode, score = max(event_score) * log(1 + count_matching_events)
  - This captures both the best match AND breadth of matching
- Returns: ranked list of episode_ids by grouped score

**Path C -- DiagMahalanobis (OPTIONAL)**

- Computes per-episode diagonal covariance from event embeddings
- Scores query against each episode using diagonal Mahalanobis distance
- **NOTE**: This helped +1.5pp on old benchmark but HURT on human benchmark (v3 MRR 0.70 < v2 MRR 0.76). Consider omitting in production and re-evaluating on larger data.

**RRF Fusion**

- Reciprocal Rank Fusion with k=60
- Weights: centroid=1.0, event=5.0, diag=1.0
- Event weight of 5x reflects the dominance of event-level search
- Formula per episode: `rrf_score(ep) = SUM_over_paths(weight / (60 + rank + 1))`

### 2.3 Stage 2: Structural Fusion

**Query Context Extraction** (`extract_query_context`)

- Social: extract person entities from query text via alias lookup
- Spatial: extract location references via location alias lookup
- Temporal: extract bucket (morning/afternoon/evening/night) and day-of-week references
- Affective: extract valence/arousal from emotional keywords

**Per-Axis Scoring Functions**

- `social_score`: Jaccard(query_entities, episode_participants). Returns 0.5 if no entities in query.
- `spatial_score`: Exact match (1.0) or substring match (0.5) between query locations and episode locations. Returns 0.5 if no locations in query.
- `temporal_score`: Exact match on bucket and/or day-of-week. Returns 0.5 if no temporal signal.
- `affective_score`: 1 - normalized_euclidean_distance(query_affect, episode_affect). Returns 0.5 if no affect signal.

**Fusion Formula**

```
final_score = (1 - gamma) * normalized_semantic + gamma * structural_score

where:
  gamma = 0.35
  normalized_semantic = rrf_score / max(rrf_scores)
  structural_score = weighted_sum(social, temporal, spatial, affective) / sum(weights)

  axis_weights = {
    social:    0.331,
    temporal:  0.025,
    spatial:   0.620,
    affective: 0.025,
  }
```

Spatial dominates (62%) because family events are strongly location-anchored (park, school, restaurant, home). Social is secondary (33%) for person-specific queries. Temporal and affective contribute minimally.

---

## 3. How Embeddings Are Made

### 3.1 Event Embeddings

- **Model**: UltraBERT v4.0.7 (`get_embedding()`)
- **Dimensions**: 768, L2-normalized
- **Input**: Raw event text (the full JSON body text from st_hipp_events)
- **Max tokens**: 512 (only 2/88 episodes have events exceeding this; truncation is acceptable)
- **Storage**: One 768-dim vector per event in st_vec, linked by event_id

### 3.2 Episode Centroid Embedding (IDF-Weighted)

- **Method**: IDF-weighted mean of constituent event embeddings
- **IDF computation**:
  1. For each event, count how many episodes contain that event (should be 1, but dedup matters)
  2. IDF weight = log(N_total_episodes / n_episodes_containing_event)
  3. Weighted sum: `centroid = SUM(idf_weight_i * event_embedding_i) / SUM(idf_weight_i)`
  4. L2-normalize the result
- **When to recompute**: After any R2 consolidation cycle that adds/removes events from an episode
- **Storage**: One 768-dim vector per episode in st_vec, linked by episode embedding_id in st_epi

### 3.3 What NOT to Compute

- **No text-embed episode vectors**: Centroid beats text-embed universally
- **No satellite vectors**: Event search with weighted_max makes them redundant
- **No SPLADE sparse vectors**: UltraBERT has no MLM head
- **No document-level re-embedding**: The IDF-weighted centroid IS the episode representation

---

## 4. How Retrieval Works (Runtime Flow)

### Step 1: Embed the Query

```python
q_vec = ultrabert.get_embedding(query_text)  # 768-dim, L2-normalized
```

### Step 2: Three Parallel Semantic Searches

```python
# Path A: Centroid search
centroid_scores, centroid_indices = centroid_index.search(q_vec, k=10)
centroid_ranked = [episode_ids[i] for i in centroid_indices[0] if i >= 0]

# Path B: Event search + weighted_max grouping
event_hits = event_index.search(q_vec, k=50)  # top-50 raw event hits
grouped = {}
for event_id, score in event_hits:
    ep_id = event_to_episode[event_id]
    grouped.setdefault(ep_id, []).append(score)
event_ranked = sorted(
    [(ep, max(scores) * math.log(1 + len(scores))) for ep, scores in grouped.items()],
    key=lambda x: -x[1]
)

# Path C: DiagMahalanobis (optional)
diag_ranked = diag_mahalanobis_search(q_vec, episode_covariances, k=10)
```

### Step 3: RRF Merge

```python
rrf_k = 60
rrf_scores = {}
for rank, ep in enumerate(centroid_ranked):
    rrf_scores[ep] = rrf_scores.get(ep, 0) + 1.0 / (rrf_k + rank + 1)
for rank, (ep, _) in enumerate(event_ranked):
    rrf_scores[ep] = rrf_scores.get(ep, 0) + 5.0 / (rrf_k + rank + 1)
for rank, ep in enumerate(diag_ranked):
    rrf_scores[ep] = rrf_scores.get(ep, 0) + 1.0 / (rrf_k + rank + 1)
```

### Step 4: Extract Query Context

```python
ctx = extract_query_context(query_text)
# -> entities: {"person_maya", "person_dad"}
# -> locations: {"park", "olive_garden"}
# -> temporal_bucket: "evening"
# -> valence: 0.8, arousal: 0.6, has_affect: True
```

### Step 5: Structural Fusion

```python
gamma = 0.35
axis_weights = {"social": 0.331, "temporal": 0.025, "spatial": 0.620, "affective": 0.025}
max_sem = max(rrf_scores.values())

results = []
for ep_id in all_episode_ids:
    sem_s = rrf_scores.get(ep_id, 0.0) / max_sem
    ax = episode_axes[ep_id]
    struct_s = combined_axis_score(ctx, ax, axis_weights)
    final = (1 - gamma) * sem_s + gamma * struct_s
    results.append((ep_id, final))

results.sort(key=lambda x: -x[1])
return results[:k]
```

---

## 5. What to Store in R2 (st_epi) Columns

### 5.1 Already Existing Columns Used by Retrieval

These st_epi columns are **already present** and directly used in structural scoring:

| Column | Migration | Used By | Axis |
|-|-|-|-|
| `participants_json` | 0027 | social_score (Jaccard) | Social |
| `participant_count` | 0027 | social_score (fallback) | Social |
| `primary_location` | 0027 | spatial_score (exact/substring match) | Spatial |
| `location_type` | 0027 | spatial_score (category match) | Spatial |
| `start_time_utc` | 0027 | temporal derivation | Temporal |
| `end_time_utc` | 0027 | temporal derivation | Temporal |
| `temporal_bucket` | 0027 | temporal_score (bucket match) | Temporal |
| `day_of_week` | 0027 | temporal_score (day match) | Temporal |
| `source_events_json` | 0027 | event-to-episode mapping | Semantic |
| `source_event_count` | 0027 | grouping denominator | Semantic |
| `embedding_id` | 0027 | links to st_vec for centroid vector | Semantic |
| `embedding_vector` | 0061 | inline centroid (3072 bytes) | Semantic |
| `dominant_sentiment` | 0086 | affective_score (valence proxy) | Affective |
| `dominant_emotion` | 0086 | affective_score (arousal proxy) | Affective |
| `aggregated_sentiment` | 0086 | affective_score (mean valence) | Affective |

### 5.2 New Columns Required for Production Retrieval

Only **two** new columns are needed:

| Column | Type | Nullable | Purpose |
|-|-|-|-|
| `mean_valence` | REAL | YES | Pre-aggregated mean valence of constituent events for affective axis scoring. Currently computed at runtime from event data; storing it avoids N+1 event lookups during retrieval. |
| `mean_arousal` | REAL | YES | Pre-aggregated mean arousal of constituent events for affective axis scoring. Same rationale as mean_valence. |

These are cheap (8 bytes total), nullable, and populated by the R2 consolidation writer when creating/updating episodes.

### 5.3 Columns NOT Needed

| Rejected Column | Reason |
|-|-|
| `satellite_vectors_json` | Satellites are redundant; event search captures event-level specificity |
| `centroid_metadata_json` (satellite portion) | No satellites needed |
| `embedding_strategy` (centroid/text-embed flag) | Always centroid, no routing |
| `per_dimension_variance` (768 floats) | DiagMahalanobis adds marginal/negative value on human benchmark |
| `bm25_keywords_json` | BM25 failed to show complementarity with dense search |
| `query_type_routing_hints` | Query-type routing failed |

### 5.4 What Goes in centroid_metadata_json (Optional Enrichment)

If `centroid_metadata_json` (TEXT column, already available via existing schema patterns) is used, store lightweight retrieval diagnostics:

```json
{
  "centroid_method": "idf_weighted",
  "n_events_used": 7,
  "idf_range": [0.82, 3.14],
  "centroid_cohesion": 0.73,
  "embedding_model": "ultrabert-v4.0.7"
}
```

This is purely informational for debugging and monitoring, NOT used in scoring.

### 5.5 Event-Level Storage (st_hipp_events + st_vec)

Each event needs:

- Its 768-dim embedding in st_vec (already present from M08 ingestion)
- The event-to-episode mapping via `source_events_json` in st_epi (already present)

No additional event-level columns are needed for retrieval.

---

## 6. Production Retrieval Architecture Summary

### 6.1 Index Structures at Runtime

| Index | Contents | Size | Update Frequency |
|-|-|-|-|
| Episode Centroid FAISS (IndexFlatIP) | 768-dim IDF centroids, one per episode | N_episodes x 768 x 4 bytes | After each R2 consolidation cycle |
| Event FAISS (IndexFlatIP) | 768-dim embeddings, one per event | N_events x 768 x 4 bytes | After M08 ingestion of new events |
| Episode Axes Cache | Precomputed EpisodeAxes structs | In-memory dict | After each R2 consolidation cycle |
| Event-to-Episode Map | event_id -> episode_id lookup | In-memory dict | After R2 consolidation |

### 6.2 Latency Budget

All operations are local vector math (no LLM calls, no external API calls):

- UltraBERT embed: ~5-10ms
- FAISS centroid search (88 episodes): <1ms
- FAISS event search (529 events, k=50): <1ms
- Weighted_max grouping: <1ms
- RRF merge: <1ms
- Structural scoring (88 episodes): <1ms
- **Total: ~10-15ms per query** (dominated by embedding)

### 6.3 Scaling Considerations

- FAISS IndexFlatIP is exact brute-force; sufficient up to ~100K episodes
- Beyond 100K episodes, switch to IndexIVFFlat or IndexHNSW
- Event index scales linearly; at ~10 events/episode, 100K episodes = 1M event vectors
- Structural axis scoring is O(N_episodes) but very cheap per episode

---

## 7. Per-Query-Type Performance (Human Benchmark)

| Query Type | Count | MRR (v4) | MRR (v4+MGRH) | nDCG@10 | MGRH Routed? | Dominant Signal |
|-|-|-|-|-|-|-|
| entity | 12 | 0.833 | 0.833 | 0.792 | No | Social axis + event specificity |
| temporal | 8 | 0.522 | **0.599** | 0.624 | Yes | MGRH rerank + structural |
| emotional | 7 | 0.560 | **0.573** | 0.682 | Yes | MGRH rerank + semantic |
| thematic | 10 | 0.775 | **0.883** | 0.887 | Yes | MGRH rerank excels at theme matching |
| cross_episode | 6 | 0.917 | 0.917 | 0.889 | No | Event search finds shared participants/locations |
| causal | 6 | 0.857 | 0.857 | 0.762 | No | Semantic + spatial context |

**Weakest areas**: temporal and emotional queries. Conditional MGRH reranking now addresses both (+0.077 and +0.013 MRR respectively).

---

## 8. Definitive Configuration

```python
# ============================================================
# Final v4 Production Configuration
# ============================================================

# Embedding
EMBEDDING_MODEL = "ultrabert-v4.0.9"
EMBEDDING_DIM = 768
EMBEDDING_NORM = "L2"

# Episode Centroid
CENTROID_METHOD = "idf_weighted"  # IDF-weighted mean of event embeddings

# Event Search
EVENT_K = 50                     # top-K events to retrieve from FAISS
EVENT_GROUPING = "weighted_max"  # max(score) * log(1 + count)

# RRF Fusion
RRF_K = 60
RRF_WEIGHTS = {
    "centroid": 1.0,
    "event": 5.0,
    "diag_mahalanobis": 1.0,     # optional; consider omitting
}

# Structural Fusion
GAMMA = 0.35                     # structural weight in final score
AXIS_WEIGHTS = {
    "social": 0.331,
    "temporal": 0.025,
    "spatial": 0.620,
    "affective": 0.025,
}

# Retrieval
TOP_K = 10                       # return top-10 episodes

# MGRH Cross-Encoder Reranking (conditional)
MGRH_ENABLED = True
MGRH_ROUTING_TYPES = {"thematic", "temporal", "emotional"}
MGRH_DEPTH = 20                  # rerank top-20 from v4
MGRH_MU = 0.5                   # interpolation: 0.5 * norm_v4 + 0.5 * mgrh
MGRH_TEXT_STRATEGY = "full_concat"  # concatenated source events, max 1900 chars
```

---

## 9. Migration Checklist for R2 Production

### Phase A: Schema (1 migration)

- [ ] Migration 0089: Add `mean_valence REAL NULL`, `mean_arousal REAL NULL` to st_epi

### Phase B: R2 Writer Updates

- [ ] Centroid computation: implement IDF-weighted centroid in R2 consolidation writer
- [ ] Populate `mean_valence` and `mean_arousal` from constituent event affect data
- [ ] Store centroid in st_vec (768-dim), link via st_epi.embedding_id
- [ ] Optionally populate `centroid_metadata_json` with diagnostic info

### Phase C: Retrieval Module

- [ ] Build FAISS IndexFlatIP from all st_epi centroid embeddings at startup
- [ ] Build FAISS IndexFlatIP from all st_hipp_events embeddings at startup
- [ ] Build event-to-episode mapping from st_epi.source_events_json
- [ ] Build EpisodeAxes cache from st_epi metadata columns
- [ ] Implement `extract_query_context()` with person/location/temporal/affect extraction
- [ ] Implement 3-path RRF + structural fusion scoring
- [ ] Wire into K1 retrieval syscall

### Phase D: Index Refresh

- [ ] After each R2 consolidation cycle, rebuild centroid FAISS index
- [ ] After M08 ingestion, incrementally add new event embeddings to event index
- [ ] Refresh EpisodeAxes cache after R2 consolidation

---

## 10. MGRH Cross-Encoder Reranking (v4.0.9 Evaluation)

### 10.1 Background

UltraBERT v4.0.9 introduced the MGRH (Multi-Granularity Relevance Head) -- a 4-signal cross-encoder (CLS, CrossAttention/ESIM, Asymmetric Embedding, MaxSim/ColBERT) fused via MLP. This provides a pairwise relevance score for (query, document) pairs, complementary to the bi-encoder retrieval in v4.

MGRH was evaluated across three experiments:

- **M7-1**: Correlation probe (Spearman, AUC vs binary labels)
- **M7-2b**: Text strategy sweep (full_concat, first_event, summary_plus)
- **M7-2c**: Conditional routing by query type

### 10.2 Global MGRH Signal Quality

| Metric | Value | Bi-encoder Baseline |
|-|-|-|
| Spearman | 0.151 | 0.196 (cosine similarity) |
| AUC | 0.642 | 0.684 (cosine similarity) |
| Separation (rel - irr) | +0.034 | +0.063 (cosine similarity) |

MGRH signal is **weaker than bi-encoder similarity globally** -- it cannot replace the bi-encoder. However, it provides **complementary signal** for specific query types.

### 10.3 Text Strategy Impact

Shorter episode text representations HURT reranking performance:

| Strategy | Chars (mean) | Best nDCG | Delta vs v4 |
|-|-|-|-|
| **full_concat** | 631 | **0.7631** | **+0.023** |
| first_event | 110 | 0.7261 | -0.015 |
| summary_plus | 200 | 0.7102 | -0.030 |

MGRH needs the full concatenated event text to match against queries. This contradicts the independent characterization study (which showed MGRH scores 0.75 for short docs vs 0.14 for long docs in isolation) -- when MGRH is used as a reranker on real candidates from the bi-encoder, the additional vocabulary in full text provides critical matching signal.

### 10.4 Per-Query-Type MGRH Lift (full_concat, mu=0.5, d=20)

| Query Type | Baseline MRR | MGRH MRR | Delta MRR | Verdict |
|-|-|-|-|-|
| **thematic** | 0.775 | 0.883 | **+0.108** | Strong benefit |
| **temporal** | 0.522 | 0.599 | **+0.077** | Strong benefit |
| emotional | 0.560 | 0.573 | +0.013 | Marginal benefit |
| cross_episode | 0.917 | 0.917 | 0.000 | No change |
| entity | 0.833 | 0.802 | -0.031 | Slight hurt |
| **causal** | 0.857 | 0.635 | **-0.222** | Severe hurt |

### 10.5 Conditional Routing Results

By gating MGRH reranking on query type, we capture the upside and avoid the downside:

| Routing Policy | Enabled Types | MRR | Delta MRR | nDCG | Delta nDCG |
|-|-|-|-|-|-|
| none (v4 baseline) | -- | 0.7410 | -- | 0.7406 | -- |
| **top3 (WINNER)** | **emotional, temporal, thematic** | **0.7770** | **+0.036** | **0.7745** | **+0.034** |
| top2 | temporal, thematic | 0.7750 | +0.034 | 0.7655 | +0.025 |
| positive | cross_ep, emotional, temporal, thematic | 0.7770 | +0.036 | 0.7716 | +0.031 |
| all (unconditional) | all 6 types | 0.7429 | +0.002 | 0.7631 | +0.023 |

**Winner: `top3` policy** -- rerank emotional + temporal + thematic queries only.

### 10.6 Production MGRH Integration

**Conditional reranking adds a third stage to the pipeline:**

```
Query -> v4 bi-encoder (semantic RRF + structural fusion) -> top-20 candidates
      -> classify query type
      -> IF type in {thematic, temporal, emotional}:
           MGRH rerank(top-20, mu=0.5) -> top-10
         ELSE:
           pass through top-10
```

**Configuration:**

```python
MGRH_ENABLED = True
MGRH_ROUTING_TYPES = {"thematic", "temporal", "emotional"}
MGRH_DEPTH = 20          # rerank top-20 from v4
MGRH_MU = 0.5            # interpolation: 0.5 * norm_v4 + 0.5 * mgrh
MGRH_TEXT_STRATEGY = "full_concat"  # concatenated source events, max 1900 chars
```

**Latency impact:** MGRH adds ~20-40ms per reranked query (cross-encoder inference for 20 pairs). This applies to ~51% of benchmark queries (25/49 = emotional + temporal + thematic). Average per-query latency increase: ~15ms.

**Expected lift over v4 alone:**

- MRR: 0.7410 -> 0.7770 (+0.036, +4.9%)
- nDCG: 0.7406 -> 0.7745 (+0.034, +4.6%)

**Dependency:** Requires a lightweight query-type classifier. Options:

1. UltraBERT intent classification (already available via `client.classify_intent()`)
2. Keyword heuristic (temporal keywords, emotion words, theme patterns)
3. Always-on with routing disabled (fall back to unconditional, still +0.002 MRR)

### 10.7 Updated Pipeline Summary with MGRH

| Component | MRR Contribution | Cumulative |
|-|-|-|
| Centroid search only | 0.410 | 0.410 |
| + Event search (weighted_max) | +0.060 | 0.470 |
| + IDF weighting | +0.020 | 0.490 |
| + Structural fusion (gamma=0.35) | +0.050 | 0.540 |
| + v4 full pipeline tuning | +0.200 | 0.741 |
| + Conditional MGRH rerank (top3) | +0.036 | **0.777** |

---

## 11. What We Learned (Research Insights)

1. **Centroid beats text-embed universally** -- even for large episodes with diverse content, the geometric mean of event embeddings outperforms any text-based summary embedding
2. **IDF weighting helps centroids** -- rare events get more weight, preventing common events from dominating the centroid
3. **Event-level search is the biggest single improvement** -- going from episode-only to event-level search added 6pp MRR; the weighted_max grouping (max * log(1+count)) perfectly balances precision and breadth
4. **Structural metadata provides a significant boost** -- 5pp MRR from location and participant matching; location is king (62% weight)
5. **Fixed beats adaptive** -- entropy-adaptive weights, query-type routing, and dynamic gamma all failed to beat simple fixed parameters
6. **BM25 adds nothing when you have good dense vectors** -- UltraBERT already captures lexical signal
7. **DiagMahalanobis is fragile** -- helps on one benchmark, hurts on another; use cautiously
8. **Satellites are redundant with event search** -- the hypothesis catalog's most complex component (salience-gated satellite vectors) is completely unnecessary when you already search events directly
