# st_observations: P01 Retrieval Integration Guide

**Purpose**: How st_observations feeds into the P01 Recall pipeline's episode retrieval.
**Audience**: Developers building P01 phases.
**Prerequisite**: Read FINAL_PIPELINE_STRATEGY.md first for the retrieval architecture.

---

## 1. What st_observations Is

An append-only observation log (migration 0067, extended in 0068) written by P03 R7 TruthWriter.
Every time a truth layer record is created (FIRST_SEEN) or reinforced (REINFORCEMENT),
R7 writes one row capturing the **situational context** at observation time.

```
st_observations links to ALL truth layers via (layer, record_id):
  layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_kg_edges', 'st_social', 'st_prospective')
```

**Key design properties:**
- Does NOT depend on st_hipp_events (which has 20-day tombstone TTL)
- source_event_id is a SOFT reference (degrades gracefully after st_hipp_events cleanup)
- Append-only: observations accumulate, never deleted (1-5 year TTL matches truth layers)
- observation_type distinguishes FIRST_SEEN (INSERT) from REINFORCEMENT (MERGE)

---

## 2. Schema (32 columns)

### Core Identity (5 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| observation_id | TEXT PK | NO | ULID (ms-level ordering) |
| tenant_id | TEXT | NO | Tenant partition key |
| layer | TEXT | NO | Truth layer name |
| record_id | TEXT | NO | PK of the truth layer record |
| observed_at | BIGINT | NO | Unix ms timestamp |

### Observation Metadata (3 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| observation_type | TEXT | NO | FIRST_SEEN or REINFORCEMENT |
| source_event_id | TEXT | YES | Soft reference to st_hipp_events (degrades after 20 days) |
| observation_weight | FLOAT | NO | Weight [0-1], default 1.0 |

### Emotional Context (5 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| sentiment_score | FLOAT | YES | Sentiment [0-1] |
| sentiment_label | TEXT | YES | positive / negative / neutral |
| affect_valence | FLOAT | YES | Valence [-1 to +1] |
| affect_arousal | FLOAT | YES | Arousal [0-1] |
| dominant_emotion | TEXT | YES | Primary emotion |

### Salience Context (3 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| salience_score | FLOAT | YES | Salience [0-1] |
| novelty_score | FLOAT | YES | Novelty [0-1] from pattern separation |
| salience_band | TEXT | YES | HIGH / MED / LOW |

### Modality Context (3 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| ingress_channel | TEXT | YES | voice / chat / api |
| ingress_source | TEXT | YES | Source app or integration |
| device_kind | TEXT | YES | mobile / desktop / tablet |

### Physical Context (3 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| location_name | TEXT | YES | Human-readable location |
| location_type | TEXT | YES | home / work / transit / etc. |
| geohash_6 | TEXT | YES | 6-char geohash for proximity clustering |

### Social Context (4 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| social_context | TEXT | YES | family / friends / work / solo |
| social_intimacy | TEXT | YES | Intimacy level |
| is_solo_event | BOOLEAN | YES | TRUE if user was alone |
| num_participants | INTEGER | YES | Participant count |

### Temporal Context (4 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| time_of_day_bucket | TEXT | YES | morning / afternoon / evening / night |
| circadian_slot | TEXT | YES | Circadian rhythm slot |
| is_weekend | BOOLEAN | YES | Weekend flag |
| day_of_week | TEXT | YES | Monday through Sunday |

### Prospective Context (2 columns)
| Column | Type | Null | Purpose |
|---|---|---|---|
| anchor_time_utc | BIGINT | YES | When temporal expression was spoken |
| original_temporal_expr | TEXT | YES | Raw expression ("next week", "tomorrow") |

---

## 3. Indexes Available for P01

| Index | Columns | Filter | P01 Use Case |
|---|---|---|---|
| idx_obs_record_time | layer, record_id, observed_at DESC | -- | Fetch observations for top-K episode candidates |
| idx_obs_tenant_time | tenant_id, observed_at DESC | -- | Temporal range queries |
| idx_obs_sentiment | tenant_id, sentiment_label, observed_at DESC | sentiment_label IS NOT NULL | Emotion-filtered retrieval |
| idx_obs_salience_high | tenant_id, observed_at DESC | salience_band = 'HIGH' | High-salience episode boosting |
| idx_obs_social | tenant_id, social_context, observed_at DESC | social_context IS NOT NULL | Social context filtering |
| idx_obs_location | tenant_id, location_type, observed_at DESC | location_type IS NOT NULL | Location-based retrieval |
| idx_obs_circadian | tenant_id, time_of_day_bucket, circadian_slot | time_of_day_bucket IS NOT NULL | Circadian pattern queries |
| idx_obs_high_novelty | tenant_id, observed_at DESC | novelty_score > 0.8 | Novel memory boosting |

---

## 4. How st_observations Feeds Into P01 Retrieval Phases

### Current P01 Phase Architecture (from FINAL_PIPELINE_STRATEGY.md)

```
Phase 1: Query Understanding
  UltraBERT embed + extract_query_context + classify_query_type

Phase 2: Semantic Retrieval (v4)
  Centroid FAISS + Event FAISS + RRF merge

Phase 2.5: Structural Fusion (gamma=0.35)        <-- st_observations enriches HERE
  Per-axis scoring: social, spatial, temporal, affective

Phase 3: Conditional MGRH Reranking
  Cross-encoder rerank for {thematic, temporal, emotional} queries

Phase 4: Context Expansion
  Entity graph expansion + related context fetch
```

### Where st_observations Plugs In

**Phase 2.5 (Structural Fusion) -- Primary integration point:**

After RRF produces top-20 candidates, fetch their observations in a single batch:

```sql
SELECT record_id,
       -- Affective (replaces need for mean_valence/mean_arousal on st_epi)
       AVG(affect_valence)    AS mean_valence,
       AVG(affect_arousal)    AS mean_arousal,
       -- Temporal (richer than st_epi columns)
       array_agg(DISTINCT time_of_day_bucket) FILTER (WHERE time_of_day_bucket IS NOT NULL) AS time_buckets,
       array_agg(DISTINCT circadian_slot)     FILTER (WHERE circadian_slot IS NOT NULL)     AS circadian_slots,
       bool_or(is_weekend)                                                                   AS has_weekend,
       array_agg(DISTINCT day_of_week)        FILTER (WHERE day_of_week IS NOT NULL)        AS days_of_week,
       -- Spatial (multi-location, adds geohash proximity)
       array_agg(DISTINCT location_name)      FILTER (WHERE location_name IS NOT NULL)      AS locations,
       array_agg(DISTINCT location_type)      FILTER (WHERE location_type IS NOT NULL)      AS location_types,
       array_agg(DISTINCT geohash_6)          FILTER (WHERE geohash_6 IS NOT NULL)          AS geohashes,
       -- Social (richer than participants_json alone)
       array_agg(DISTINCT social_context)     FILTER (WHERE social_context IS NOT NULL)     AS social_contexts,
       bool_or(is_solo_event)                                                                AS has_solo,
       AVG(num_participants)                                                                 AS avg_participants,
       -- Salience (for candidate boosting)
       MAX(salience_score)                                                                   AS max_salience,
       MAX(novelty_score)                                                                    AS max_novelty,
       COUNT(*) FILTER (WHERE observation_type = 'REINFORCEMENT')                            AS reinforcement_count
FROM st_observations
WHERE layer = 'st_epi'
  AND record_id = ANY(:episode_ids)   -- top-20 candidate IDs
GROUP BY record_id
```

**Cost**: Single query, ~20-50 rows returned, <5ms. Uses idx_obs_record_time.

### How Each Axis Benefits

#### Affective Axis (weight: 0.025)

**Before** (st_epi only): Needed 2 new columns (mean_valence, mean_arousal).
**With st_observations**: Read directly. No schema change needed on st_epi.

```python
def affective_score(query_ctx, obs_ctx):
    if not query_ctx.has_affect:
        return 0.0
    q_val, q_aro = query_ctx.valence, query_ctx.arousal
    e_val = obs_ctx.mean_valence or 0.0
    e_aro = obs_ctx.mean_arousal or 0.0
    return 1.0 - math.sqrt((q_val - e_val)**2 + (q_aro - e_aro)**2) / 2.0
```

#### Spatial Axis (weight: 0.620 -- DOMINANT)

**Before** (st_epi only): Single primary_location.
**With st_observations**: Multi-location per episode + geohash proximity.

```python
def spatial_score(query_ctx, epi_row, obs_ctx):
    # Primary match from st_epi (fast path)
    if epi_row.primary_location and query_ctx.location:
        if query_ctx.location.lower() in epi_row.primary_location.lower():
            return 1.0
    # Multi-location match from observations (enrichment path)
    if obs_ctx.locations:
        for loc in obs_ctx.locations:
            if query_ctx.location and query_ctx.location.lower() in loc.lower():
                return 0.8   # secondary location match
    # Geohash proximity match (future: nearby queries)
    if obs_ctx.geohashes and query_ctx.geohash:
        for gh in obs_ctx.geohashes:
            prefix_match = len(os.path.commonprefix([gh, query_ctx.geohash]))
            if prefix_match >= 4:  # ~600m radius
                return 0.6
    return 0.0
```

#### Temporal Axis (weight: 0.025)

**Before** (st_epi only): temporal_bucket + day_of_week (single values).
**With st_observations**: Multiple time slots + circadian + weekend flag.

```python
def temporal_score(query_ctx, epi_row, obs_ctx):
    score = 0.0
    # Bucket match (from st_epi or observations)
    buckets = obs_ctx.time_buckets or ([epi_row.temporal_bucket] if epi_row.temporal_bucket else [])
    if query_ctx.temporal_bucket and query_ctx.temporal_bucket in buckets:
        score += 0.5
    # Day of week match
    days = obs_ctx.days_of_week or ([epi_row.day_of_week] if epi_row.day_of_week else [])
    if query_ctx.day_of_week and query_ctx.day_of_week in days:
        score += 0.3
    # Weekend match
    if query_ctx.is_weekend is not None and obs_ctx.has_weekend == query_ctx.is_weekend:
        score += 0.2
    return min(score, 1.0)
```

#### Social Axis (weight: 0.331)

**Before** (st_epi only): participants_json + participant_count.
**With st_observations**: social_context + is_solo_event + num_participants.

```python
def social_score(query_ctx, epi_row, obs_ctx):
    # Participant Jaccard (unchanged, from st_epi)
    jaccard = jaccard_similarity(query_ctx.entities, epi_row.participants)
    # Social context boost from observations
    if obs_ctx.social_contexts and query_ctx.social_context:
        if query_ctx.social_context in obs_ctx.social_contexts:
            jaccard = min(jaccard + 0.2, 1.0)
    # Solo event handling
    if query_ctx.is_solo and obs_ctx.has_solo:
        jaccard = max(jaccard, 0.3)
    return jaccard
```

---

## 5. Schema Impact: st_epi New Columns Revisited

FINAL_PIPELINE_STRATEGY.md Section 5.2 originally required 2 new st_epi columns:

| Column | Type | Still Needed? | Reason |
|---|---|---|---|
| mean_valence | REAL | **NO** -- read from st_observations | `AVG(affect_valence) WHERE layer='st_epi' AND record_id=:id` |
| mean_arousal | REAL | **NO** -- read from st_observations | `AVG(affect_arousal) WHERE layer='st_epi' AND record_id=:id` |

**Trade-off at scale**: If episode count grows to thousands and the observation JOIN
becomes measurable (>5ms for batch of 20), consider materializing these as st_epi
columns. For current scale (88 episodes, ~25 episode observations), the JOIN is free.

---

## 6. Additional Retrieval Patterns Enabled by st_observations

### Pattern A: Reinforcement-Boosted Ranking

Episodes that have been reinforced (re-observed) multiple times are more memorable.
Use reinforcement_count as a soft boost after structural fusion:

```python
reinforcement_boost = math.log1p(obs_ctx.reinforcement_count) * 0.05
final_score = structural_fused_score + reinforcement_boost
```

### Pattern B: Salience-Gated Pre-Filtering

For queries with explicit salience signals ("important", "memorable", "stood out"):

```sql
SELECT record_id FROM st_observations
WHERE layer = 'st_epi' AND tenant_id = :tid AND salience_band = 'HIGH'
```

Use as a whitelist to constrain FAISS candidate set before RRF.

### Pattern C: Cross-Layer Context Expansion (Phase 4)

After retrieving top-10 episodes, fetch observations across ALL layers for those
episodes' related entities:

```sql
-- Get semantic patterns related to retrieved episodes
SELECT o.*, 'st_sem' as source_layer
FROM st_observations o
WHERE o.layer = 'st_sem'
  AND o.record_id IN (
    SELECT pattern_id FROM st_sem
    WHERE source_episode_id = ANY(:retrieved_episode_ids)
  )
```

This connects episode retrieval to semantic patterns, social relationships,
and knowledge graph entities -- building the rich context that Phase 4
(ContextExpander) needs.

### Pattern D: Emotional Journey Queries

For queries like "when was I happiest with Maya?":

```sql
SELECT o.record_id, o.affect_valence, o.dominant_emotion, o.observed_at
FROM st_observations o
WHERE o.layer = 'st_epi'
  AND o.tenant_id = :tid
  AND o.affect_valence > 0.5
  AND o.record_id IN (
    SELECT episode_id FROM st_epi
    WHERE participants_json ILIKE '%Maya%'
  )
ORDER BY o.affect_valence DESC
```

---

## 7. Module Location

The planned module for reading st_observations in P01:

```
k0/modules/recall/observation_context_fetcher.py   (NOT YET BUILT)
```

Referenced in migration 0067 header comment. Should implement:
- `fetch_episode_observations(conn, episode_ids) -> Dict[str, ObservationContext]`
- `fetch_cross_layer_context(conn, episode_ids) -> Dict[str, List[ObservationContext]]`
- Batch queries only (never N+1)
- Returns typed dataclass with all fields from Section 4 query

---

## 8. Current Data Volume (as of last validation run)

| Layer | Observations | Avg Sentiment |
|---|---|---|
| st_sem | 91 | 0.57 |
| st_epi | 25 | 0.58 |
| st_prospective | 13 | 0.00 |
| st_social | 6 | 0.00 |
| st_kg_dom | 2 | 0.00 |
| st_kg_edges | 1 | 0.50 |
| **Total** | **138** | -- |

---

## 9. Key Constraints for P01 Developers

1. **No FK to st_hipp_events**: source_event_id is a soft reference. After st_hipp_events
   tombstone cleanup (20-day TTL), source_event_id becomes a dangling pointer.
   Always handle NULL gracefully.

2. **Layer constraint**: `layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_kg_edges', 'st_social', 'st_prospective')`
   (extended in migration 0068 to include st_kg_edges).

3. **Observation ordering**: Use `observed_at DESC` for recency. ULID observation_id
   also provides ms-level ordering if needed.

4. **Multi-observation episodes**: An episode can have multiple observations (FIRST_SEEN + N REINFORCEMENT).
   Always aggregate, never assume 1:1.

5. **NULL-heavy columns**: Modality, physical, and social context columns are frequently NULL
   (depends on ingress source). Always use COALESCE or FILTER WHERE IS NOT NULL.
