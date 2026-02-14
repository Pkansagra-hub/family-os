# R5 Redesign Proposal: Memory Strengthening via Observation Evidence

> **Version**: 2.0.0
> **Status**: Proposal
> **Created**: 2026-02-13
> **Revised**: 2026-02-13 (v2 -- st_observations-first approach)
> **Author**: Architecture Team
> **Supersedes**: Dossier v2 Section 4.6 R5 algorithms (CPN, TPN-MCTS)
> **Affects**: `k0/pipelines/p03/phases/r5_dream_explorer.py`, `k0/modules/consolidation/dream/`

---

## 1. Executive Summary

Replace R5's speculative algorithms (CPN counterfactuals, TPN-MCTS forward simulation) with **observation-driven memory strengthening algorithms** that solidify existing truth layers for better K1 recall quality. Keep BGT-SM (insights) and TDL-HCO (routine optimization). Add four new algorithms that fix measured deficiencies in the live memory layers.

**Core principle**: K0 builds the richest possible context. K1's LLM reasons over that context at query time. Counterfactual reasoning is a *reasoning* task, not a *memory consolidation* task. It belongs at query time in K1 (Concierge LLM + recalled context), not in K0's offline batch pipeline.

**v2 key change**: All new algorithms are **st_observations-first**. The `st_observations` table (migration 0067) is an append-only holistic observation log with 32 columns (temporal, emotional, salience, modality, physical, social context). Every truth layer INSERT/MERGE already creates FIRST_SEEN/REINFORCEMENT rows via `ObservationRecorder`. R5 algorithms query this evidence trail as their primary signal rather than re-deriving evidence from episode heuristics. This eliminates duplicated logic with R3 (which already owns decay) and provides direct evidence rather than inferred grounding.

**Coordination principle**: R5 does NOT re-implement decay. R3 owns Ebbinghaus decay with per-layer lambda values (st_epi: 0.005/139d, st_sem: 0.003/231d, etc.) and reconciliation (REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT). R5 strictly adds **reinforcement signals and quality corrections** that R3 does not cover.

---

## 2. Evidence: Why Current R5 Algorithms Fail

### 2.1 CPN (Counterfactual Perturbation Network) Is Dead on Arrival

**Data from live system** (`explore_memory_layers.md` Section 19):

```
COUNTERFACTUAL (ACTIVE) - 70 items
  "If home office had also caused issues during 'Social with Mom, Panda a..."
  "If Dallas's involvement during 'Routine at Home' had been different, t..."
  "If Tokyo had also caused issues during 'Routine with Panda at Flight'..."
```

These are **semantically nonsensical**. Algorithmic perturbation of graph nodes produces mechanistic gibberish, not meaningful life reflection.

**CPN requires CAUSES edges** (dossier 4.6.1). R4 produces zero:

```
"R4: Causal inference complete - 0 causal edges from 37 candidate edges"
```

CPN literally cannot produce anything. The 70 counterfactuals currently in `st_prospective` are noise polluting the recall layer.

### 2.2 TPN-MCTS Adds No Value for Personal Memory

MCTS is designed for decision trees with branching outcomes. Personal memory consolidation has no adversary, no branching game tree, no reward function. The dossier's own MVP analysis (Section 4.6.0) acknowledges:

> "If MCTS matches heuristics >95%, it's not worth the cost."

For personal memory decisions (merge/split entities, decay tuning, novelty adjustment), heuristic scoring is sufficient. MCTS overhead (~300ms for rollouts) produces no measurable improvement.

### 2.3 LLM + Rich Context Is Strictly Superior for "What-If"

When a user asks K1 "What if I hadn't switched docks?", the K1 Concierge LLM receives via Bridge recall:

- 92 monitor/display mentions across episodic memory
- The emotional arc (annoyance -> relief) from `st_observations`
- The causal chain from semantic patterns: "dock -> flicker -> patience lesson"
- Explicit causal statements: "After switching docks, display flicker stopped"

This is infinitely more meaningful than a CPN output of `perturbation_target: "dock", counterfactual_outcome: "[algo text]", plausibility: 0.72`.

### 2.4 Measured Deficiencies in Current Memory Layers

| Layer | Count | Problem |
|-------|-------|---------|
| `st_epi` | 339 episodes | No cross-episode reinforcement signals. Salience scores static after R1. |
| `st_sem` | 545 patterns | All at confidence 0.80 flat. No refinement over time. |
| `st_kg_edges` | 1613 edges | 1330 from `weight_normalization` (avg weight 0.051 -- near noise). 0 temporal proximity. 0 Bayesian causal. |
| `st_social` | 39 relationships | Sentiment 0.00 for many (Panda=0.00 despite 19 interactions tagged as joy). |
| `st_prospective` | 257 items | 70 nonsense counterfactuals. Many stale reminders/decisions. |
| `st_anchors` | 0 rows | Schema exists (migration 0038), never populated. Zero Bayesian beliefs tracked. |
| `st_anchor_observations` | 0 rows | No evidence trail. |

### 2.5 R3 Already Owns Decay -- R5 Must Not Duplicate

R3 wiki (Section 3.4.4) implements Ebbinghaus decay with per-layer lambda values:

| Layer | lambda | Half-Life | Notes |
|-------|--------|-----------|-------|
| `st_hipp_events` | 0.100 | ~7 days | Transient buffer, tombstoned at 20d |
| `st_epi` | 0.005 | ~139 days | Episodes fade over ~5 months |
| `st_sem` | 0.003 | ~231 days | Semantic patterns persist ~8 months |
| `st_social` | 0.002 | ~347 days | Social relationships very stable |
| `st_kg_dom` | 0.001 | ~693 days | Knowledge graph nearly permanent |

R3 also owns reconciliation actions: REINFORCE (>=0.85 cosine), EXTEND (0.60-0.84), CREATE (no match), EVOLVE (0.40-0.59), CONTRADICT (<0.40). R3 owns Bayesian lambda fitting from access intervals (min 5 accesses, 7-day spread). R3 owns prune regret detection (14-day tracking).

**R5 boundary rule**: R5 algorithms MUST NOT apply decay, reconciliation, or prune logic. R5 only adds *reinforcement signals and quality corrections* that R3 does not cover. This prevents double-counting and keeps ownership clear.

### 2.6 R4 Already Has 8 Edge Enrichers -- R5 Must Not Duplicate

R4 wiki (Section 4.4.7) implements 8 edge enrichment algorithms:

1. **Contextual Edge** -- shared event contexts
2. **Semantic Similarity** -- embedding cosine
3. **Temporal Proximity** -- 30min/24h/7d windows, creates SEQUENTIAL/SIMULTANEOUS/PERIODIC/CAUSAL_TEMPORAL
4. **Emotion Similarity** -- VAD model distance
5. **Intent Similarity** -- goal alignment
6. **Transitive Closure** -- max path length 3
7. **Bayesian Causal** -- prior/likelihood/posterior
8. **Weight Normalization** -- min-max scaling (source of the 1330 near-zero edges)

R4 Temporal Proximity produces 0 edges currently -- that is an R4 bug, not an R5 responsibility. R5 should not create temporal proximity edges (R4 owns that enricher). R5's EWR focuses on *refinement of existing edge weights* using observation evidence.

### 2.7 st_observations: R5's Primary Evidence Source

**Migration**: 0067_st_observations.py (32 columns), amended by 0068 (adds kg_edges layer).
**Architecture**: Append-only log. P03 writes (via ObservationRecorder in R7 truth writers), P01 Recall reads (planned ObservationContextFetcher -- not yet implemented).
**Key constraint**: No foreign keys by design (st_hipp_events has 20-day tombstone, record_id references different tables per layer).

#### Schema (32 columns across 8 context categories)

```text
Identity:    observation_id (ULID PK), tenant_id, layer, record_id
Type:        observation_type (FIRST_SEEN | REINFORCEMENT), observation_weight
Temporal:    time_of_day_bucket, circadian_slot, is_weekend, day_of_week
Emotional:   sentiment_score, sentiment_label, affect_valence, affect_arousal, dominant_emotion
Salience:    salience_score, novelty_score, salience_band
Modality:    ingress_channel, ingress_source, device_kind
Physical:    location_name, location_type, geohash_6
Social:      social_context, social_intimacy, is_solo_event, num_participants
Prospective: anchor_time_utc, original_temporal_expr
```

#### Write Path (Existing)

```text
R7 Truth Writer (_insert or _reinforce)
    --> ObservationRecorder.record_for_insert()  --> FIRST_SEEN row
    --> ObservationRecorder.record_for_merge()   --> REINFORCEMENT row
    --> INSERT INTO st_observations (32 columns)
```

#### Observation Context Pipeline

1. **R0**: Event ingested as P03EventState with raw context
2. **R1**: Importance scoring adds salience_score, salience_band, novelty_score
3. **R2**: EpisodeCluster accumulates `member_contexts: List[ObservationContext]`
4. **R7**: Truth writers call `ObservationContext.from_event(event)` or `.from_episode_cluster(cluster)`
5. **R7**: `ObservationRecorder.record()` persists full 32-column context row

#### Why This Matters for R5

Every truth layer record (st_epi, st_sem, st_kg_dom, st_social, st_prospective) accumulates observation rows over time. R5 can query st_observations to compute:

- **Reinforcement frequency**: `COUNT(*) WHERE observation_type = 'REINFORCEMENT'` per record
- **Recency**: `MAX(observed_at)` per record
- **Emotional diversity**: `COUNT(DISTINCT dominant_emotion)` per record
- **Temporal patterns**: `GROUP BY circadian_slot, time_of_day_bucket` per actor
- **Social patterns**: `GROUP BY social_context` per actor
- **Location patterns**: `GROUP BY location_type` per actor

This is **direct evidence** (the system observed it) rather than **inferred evidence** (heuristic matching over episode fields).

#### Indexed Queries Available to R5

The migration defines 12 partial indexes optimized for specific query patterns:

| Index | Query Pattern | R5 Algorithm |
|-------|---------------|--------------|
| `idx_obs_record_time` | Observations for a specific record | EST, SPR, EWR |
| `idx_obs_tenant_time` | All observations in time range | ASU |
| `idx_obs_sentiment` | Filter by sentiment_label | SRE |
| `idx_obs_salience_high` | HIGH salience observations | EST |
| `idx_obs_social` | Filter by social_context | SRE, ASU |
| `idx_obs_location` | Filter by location_type | ASU |
| `idx_obs_circadian` | Circadian pattern analysis | ASU |
| `idx_obs_high_novelty` | Novelty > 0.8 observations | EST |
| `idx_obs_weekend` | Weekend vs weekday analysis | ASU |

---

## 3. Recall Path Analysis: Why Layer Quality Matters

### 3.1 K1 Recall Path (from Bridge Architecture)

```text
K1 Concierge                    Bridge                          K0
    |                              |                              |
    |-- CON_RECALL --------------->|                              |
    |   RecallSelector{            |                              |
    |     type: episodic,          |                              |
    |     type: semantic,          |-- QUERY_PORT --------------->|
    |     type: session            |   QueryEnvelope{             |
    |   }                          |     selectors[],             |-- P01 Query
    |                              |     space_id, tenant_id      |   Execution
    |                              |   }                          |     |
    |                              |                              |     |-- pgvector
    |                              |                              |     |   (st_vec)
    |                              |                              |     |-- tsvector
    |                              |<-- RecallResponse -----------|     |   (FTS)
    |<-- recalled episodes --------|     bundles[]                |     |-- WAL
    |    + semantic patterns       |                              |        position
    |    + KG context              |                              |
    |                              |                              |
    v                              |                              |
  LLM Call (TIER_MEDIUM/HIGH)      |                              |
  with recalled context            |                              |
```

### 3.2 What Drives Recall Ranking

| Recall Type | Ranking Factor | Current State | Impact of Strengthening |
|------------|----------------|---------------|------------------------|
| Episodic | `salience_score` on `st_epi` | Static from R1, never updated | EST uses observation count to boost recurrent episodes |
| Semantic | `confidence` on `st_sem` | Flat 0.80 everywhere | SPR uses observation count + specificity to differentiate |
| Entity-linked | `weight` on `st_kg_edges` | 82% near-zero noise | EWR demotes single-enricher noise, boosts multi-evidence edges |
| Social | `sentiment_score` on `st_social` | 0.00 for many | SRE aggregates per-observation emotional context from st_observations |
| Prospective | Retrieved when intent matches | 70 counterfactual junk items | SPC-UQ cleans via observation-based completion detection |
| Personalization | `confidence` on `st_anchors` | Empty table, 0 rows | ASU derives anchors from st_observations distributions |

**Bottom line**: Every weak point in the recall path maps to a memory layer that R5 can strengthen during consolidation. st_observations provides the evidence trail for every strengthening decision.

---

## 4. Proposed R5 Algorithm Suite (v2 -- Observation-Driven)

### 4.0 Algorithm Inventory

| Slot | Old R5 | New R5 | Category | Primary Evidence Source |
|------|--------|--------|----------|------------------------|
| 1 | CPN (Counterfactuals) | **EST** -- Episodic Strength Tracker | Replace | st_observations (REINFORCEMENT count per st_epi record) |
| 2 | TPN-MCTS (Forward Sim) | **EWR** -- Edge Weight Refinement | Replace | st_observations (entity co-occurrence), R4 enricher metadata |
| 3 | SPC-UQ (Prospective Gen) | **SPC-UQ Refocused** -- Prospective Cleanup | Modify | st_observations (REINFORCEMENT recency for st_prospective) |
| 4 | BGT-SM (Insights) | **BGT-SM** -- kept unchanged | Keep | KG graph structure |
| 5 | TDL-HCO (Routine Opt) | **TDL-HCO** -- kept unchanged | Keep | st_procedural + episodes |
| 6 | -- | **ASU** -- Anchor Seeding & Update | New | st_observations (distribution aggregates) |
| 7 | -- | **SRE** -- Social Relationship Enrichment | New | st_observations (per-observation emotional context) |
| 8 | -- | **SPR** -- Semantic Pattern Reinforcement | New | st_observations (REINFORCEMENT count per st_sem record) |
| 9 | -- | **MTP** -- Memory Tier Promotion | New | st_observations (reinforcement count + record age) |
| 10 | -- | **CLV** -- Cross-Layer Coherence Verification | New | All accumulated truth tables (set intersection) |
| 11 | -- | **CTD** -- Contradiction Detection | New | st_kg_dom attributes + st_observations emotional data |
| 12 | -- | **EPC** -- Episode Compression | New | st_epi clusters + st_observations + st_vec embeddings |
| 13 | -- | **SPG** -- Salience Propagation through Graph | New | st_epi salience + st_kg_edges weights |
| 14 | -- | **NTD** -- Narrative Thread Detection | New | st_epi temporal ordering + entity overlap |

### 4.0.1 R5 Observation Evidence Query (Shared Infrastructure)

All R5 algorithms share a common observation evidence loader. This runs once at R5 start and provides pre-aggregated evidence to all algorithms:

```python
@dataclass(frozen=True)
class ObservationEvidence:
    """Pre-aggregated observation evidence for R5 algorithms."""

    # Per-record aggregates (keyed by (layer, record_id))
    record_stats: Dict[Tuple[str, str], RecordObservationStats]

    # Per-tenant distribution aggregates (for ASU anchor derivation)
    circadian_distribution: Dict[str, int]       # circadian_slot -> count
    location_distribution: Dict[str, int]        # location_type -> count
    social_distribution: Dict[str, int]          # social_context -> count
    emotion_distribution: Dict[str, int]         # dominant_emotion -> count
    weekend_distribution: Dict[bool, int]        # is_weekend -> count
    channel_distribution: Dict[str, int]         # ingress_channel -> count

    # Per-entity emotional context (for SRE)
    entity_observations: Dict[str, List[EntityObservation]]

@dataclass(frozen=True)
class RecordObservationStats:
    """Aggregated observation stats for a single truth layer record."""
    record_id: str
    layer: str
    total_observations: int
    reinforcement_count: int
    first_seen_count: int
    last_observed_at: int                        # Unix ms
    first_observed_at: int                       # Unix ms
    avg_sentiment: Optional[float]
    avg_salience: Optional[float]
    distinct_emotions: int
    distinct_locations: int
    distinct_social_contexts: int

@dataclass(frozen=True)
class EntityObservation:
    """Per-observation emotional context for SRE."""
    observed_at: int
    sentiment_score: Optional[float]
    affect_valence: Optional[float]
    dominant_emotion: Optional[str]
    social_context: Optional[str]

class ObservationEvidenceLoader:
    """
    Load and aggregate st_observations data for R5 algorithms.

    Runs once at R5 phase start. Results are shared across all algorithms.
    Uses the indexed queries defined in migration 0067.
    """

    # Aggregate query for per-record stats
    _RECORD_STATS_SQL = """
        SELECT
            layer,
            record_id,
            COUNT(*) as total_observations,
            COUNT(*) FILTER (WHERE observation_type = 'REINFORCEMENT') as reinforcement_count,
            COUNT(*) FILTER (WHERE observation_type = 'FIRST_SEEN') as first_seen_count,
            MAX(observed_at) as last_observed_at,
            MIN(observed_at) as first_observed_at,
            AVG(sentiment_score) FILTER (WHERE sentiment_score IS NOT NULL) as avg_sentiment,
            AVG(salience_score) FILTER (WHERE salience_score IS NOT NULL) as avg_salience,
            COUNT(DISTINCT dominant_emotion) FILTER (WHERE dominant_emotion IS NOT NULL) as distinct_emotions,
            COUNT(DISTINCT location_type) FILTER (WHERE location_type IS NOT NULL) as distinct_locations,
            COUNT(DISTINCT social_context) FILTER (WHERE social_context IS NOT NULL) as distinct_social_contexts
        FROM st_observations
        WHERE tenant_id = $1
        GROUP BY layer, record_id
    """

    # Distribution query for ASU anchor derivation
    _DISTRIBUTION_SQL = """
        SELECT
            circadian_slot,
            location_type,
            social_context,
            dominant_emotion,
            is_weekend,
            ingress_channel
        FROM st_observations
        WHERE tenant_id = $1 AND observed_at > $2
    """

    # Per-entity emotional observations for SRE
    _ENTITY_OBSERVATIONS_SQL = """
        SELECT
            o.record_id,
            o.observed_at,
            o.sentiment_score,
            o.affect_valence,
            o.dominant_emotion,
            o.social_context
        FROM st_observations o
        WHERE o.tenant_id = $1
          AND o.layer IN ('st_epi', 'st_social')
          AND o.sentiment_score IS NOT NULL
        ORDER BY o.observed_at
    """

    async def load(
        self,
        uow: "UnitOfWork",
        tenant_id: str,
        lookback_ms: int,
    ) -> ObservationEvidence:
        """
        Load all observation evidence needed by R5 algorithms.

        Args:
            uow: Unit of work for queries
            tenant_id: Tenant identifier
            lookback_ms: How far back to look for distribution analysis

        Returns:
            ObservationEvidence with pre-aggregated data
        """
        # Three queries, could be parallelized via asyncio.gather
        record_stats = await self._load_record_stats(uow, tenant_id)
        distributions = await self._load_distributions(uow, tenant_id, lookback_ms)
        entity_obs = await self._load_entity_observations(uow, tenant_id)

        return ObservationEvidence(
            record_stats=record_stats,
            entity_observations=entity_obs,
            **distributions,
        )
```

---

### 4.1 EST -- Episodic Strength Tracker (replaces CPN)

**Purpose**: Compute cross-episode reinforcement signals based on observation evidence. When the same pattern repeats across episodes (gym 3x/week, Panda conversations with positive sentiment), those episodes should reinforce each other. Currently episodes sit isolated -- R2 clusters them but never revisits.

**Coordination with R3**: EST does NOT apply decay. R3 already owns Ebbinghaus decay on st_epi (lambda=0.005, ~139d half-life) and reconciliation (REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT). EST strictly adds positive reinforcement signals that R3 does not compute.

**Primary evidence**: st_observations REINFORCEMENT count per st_epi record. Episodes that have been repeatedly reinforced through multiple consolidation cycles are proven recurrent -- no heuristic matching needed.

**Secondary signal**: Heuristic signature matching (location + activity + participants) for brand-new episodes that lack observation history.

**Inputs**:

- `observation_evidence.record_stats` (pre-aggregated from ObservationEvidenceLoader)
- `merged_episodes` (accumulated from `st_epi` + current R2 batch)
- `event_states` (current cycle events with sentiment/salience)

**Algorithm**:

```python
@dataclass(frozen=True)
class EpisodeStrengthUpdate:
    episode_id: str
    new_salience: float           # Updated salience after reinforcement
    reinforcement_count: int      # Observation-based reinforcement count
    last_reinforced_at: int       # Timestamp ms of last observation
    reinforcement_source: str     # "observation_evidence", "signature_match", "sentiment_boost"

class EpisodicStrengthTracker:
    """
    Compute cross-episode reinforcement signals.

    Two-tier evidence system:
    Tier 1 (primary): st_observations REINFORCEMENT count per episode.
        Episodes with many REINFORCEMENT observations are organically recurrent.
    Tier 2 (secondary): Heuristic signature matching for new episodes
        without observation history (location + activity + participants).

    Scientific basis: Spaced repetition -- memories revisited at intervals
    develop stronger neural traces. st_observations tracks these "visits."

    DOES NOT apply decay. R3 owns all decay via Ebbinghaus lambda per layer.
    """

    def compute_reinforcements(
        self,
        current_episodes: List[EpisodeCluster],
        accumulated_episodes: List[EpisodeCluster],
        observation_evidence: ObservationEvidence,
        config: ESTConfig,
    ) -> List[EpisodeStrengthUpdate]:
        updates = []

        # =====================================================================
        # Tier 1: Observation-based reinforcement (primary)
        # Episodes with high REINFORCEMENT counts in st_observations are
        # proven recurrent. Boost salience proportionally.
        # =====================================================================
        for episode in accumulated_episodes:
            stats = observation_evidence.record_stats.get(("st_epi", episode.cluster_id))
            if stats is None:
                continue  # No observation data yet -- handled by Tier 2

            if stats.reinforcement_count >= config.min_reinforcements_for_boost:
                # Logarithmic scaling: diminishing returns per reinforcement
                boost = config.observation_boost * math.log2(1 + stats.reinforcement_count)
                new_salience = min(1.0, episode.aggregated_salience + boost)

                # Emotional diversity bonus: episodes observed in varied emotional
                # contexts are richer memories (McGaugh, 2004)
                if stats.distinct_emotions >= config.emotional_diversity_threshold:
                    diversity_bonus = config.emotional_diversity_boost
                    new_salience = min(1.0, new_salience + diversity_bonus)

                if new_salience > episode.aggregated_salience + 0.001:
                    updates.append(EpisodeStrengthUpdate(
                        episode_id=episode.cluster_id,
                        new_salience=new_salience,
                        reinforcement_count=stats.reinforcement_count,
                        last_reinforced_at=stats.last_observed_at,
                        reinforcement_source="observation_evidence",
                    ))

        # =====================================================================
        # Tier 2: Heuristic signature matching for NEW episodes
        # Only for current-cycle episodes that may not have observation history.
        # =====================================================================
        observation_boosted_ids = {u.episode_id for u in updates}

        for current in current_episodes:
            matches = self._find_recurring_patterns(current, accumulated_episodes, config)

            for matched_episode in matches:
                if matched_episode.cluster_id in observation_boosted_ids:
                    continue  # Already boosted by Tier 1

                boost = config.signature_match_boost * (1.0 + len(matches) * 0.1)
                new_salience = min(1.0, matched_episode.aggregated_salience + boost)

                if new_salience > matched_episode.aggregated_salience + 0.001:
                    updates.append(EpisodeStrengthUpdate(
                        episode_id=matched_episode.cluster_id,
                        new_salience=new_salience,
                        reinforcement_count=len(matches),
                        last_reinforced_at=current.temporal_end,
                        reinforcement_source="signature_match",
                    ))

        # NO STALENESS DECAY -- R3 owns all decay via Ebbinghaus lambda

        return updates

    def _find_recurring_patterns(
        self,
        current: EpisodeCluster,
        accumulated: List[EpisodeCluster],
        config: ESTConfig,
    ) -> List[EpisodeCluster]:
        """
        Find episodes with matching signature: location + activity + participants.

        Secondary to observation evidence. Used only for brand-new episodes
        without observation history.
        """
        matches = []
        for acc in accumulated:
            if acc.cluster_id == current.cluster_id:
                continue

            score = 0.0

            # Location match
            if current.dominant_location and acc.dominant_location:
                if current.dominant_location.lower() == acc.dominant_location.lower():
                    score += config.location_weight

            # Activity type match
            if current.activity_type and acc.activity_type:
                if current.activity_type == acc.activity_type:
                    score += config.activity_weight

            # Participant overlap (Jaccard)
            if current.entity_ids and acc.entity_ids:
                overlap = len(set(current.entity_ids) & set(acc.entity_ids))
                union = len(set(current.entity_ids) | set(acc.entity_ids))
                if union > 0:
                    score += config.participant_weight * (overlap / union)

            if score >= config.match_threshold:
                matches.append(acc)

        return matches
```

**Configuration**:

```python
@dataclass
class ESTConfig:
    # Tier 1: Observation-based reinforcement
    observation_boost: float = 0.03         # Salience boost per log2(reinforcement_count)
    min_reinforcements_for_boost: int = 2   # Min REINFORCEMENT observations to trigger boost
    emotional_diversity_threshold: int = 3  # Distinct emotions for diversity bonus
    emotional_diversity_boost: float = 0.02 # Extra boost for emotionally diverse episodes

    # Tier 2: Heuristic signature matching (for new episodes)
    signature_match_boost: float = 0.05     # Salience boost per signature match
    location_weight: float = 0.3            # Weight for location match in signature
    activity_weight: float = 0.4            # Weight for activity type match
    participant_weight: float = 0.3         # Weight for participant overlap
    match_threshold: float = 0.5            # Minimum signature match score
```

**Outputs**: `List[EpisodeStrengthUpdate]`
**Target table**: `st_epi.salience_score`, `st_epi.reinforcement_count` updates via R6 -> R7

**No decay parameters** -- R3 owns all decay.

**Why this matters for recall**: When K1 queries `type: episodic`, salience_score drives ranking. Observation evidence directly measures how "revisited" a memory is -- the most natural reinforcement signal. Episodes with 10+ REINFORCEMENT observations represent genuine life patterns (gym routine, daily calls to mom). Episodes with 1 FIRST_SEEN are one-off events. This differentiation is what sleep consolidation does in the brain.

---

### 4.2 ASU -- Anchor Seeding & Update (new -- fills empty `st_anchors`)

**Purpose**: Bootstrap and maintain the Bayesian belief system. The schema exists (migration 0038), the dossier spec exists (Section 5.4), but zero rows. Rather than hard-coded heuristic extractors, ASU derives anchors from **st_observations distribution aggregates** -- the actual patterns in the user's data.

**v2 change**: Replaced 4 hard-coded lambda extractors with data-driven distribution analysis. st_observations already captures circadian_slot, location_type, social_context, dominant_emotion, is_weekend, ingress_channel per observation. ASU queries these distributions and derives Bayesian anchors automatically. This is more robust, scales with new context dimensions, and eliminates brittle pattern matching.

**Inputs**:

- `observation_evidence.circadian_distribution` (circadian_slot counts)
- `observation_evidence.location_distribution` (location_type counts)
- `observation_evidence.social_distribution` (social_context counts)
- `observation_evidence.emotion_distribution` (dominant_emotion counts)
- `observation_evidence.weekend_distribution` (is_weekend counts)
- `observation_evidence.channel_distribution` (ingress_channel counts)
- `existing_anchors` (current st_anchors rows, if any)

**Algorithm**:

```python
@dataclass(frozen=True)
class AnchorUpdate:
    entity_id: str
    attribute: str
    tenant_id: str
    space_id: str
    new_alpha: float
    new_beta: float
    evidence_count: int
    observation_context: str        # Why this was interpreted as support/oppose

@dataclass(frozen=True)
class AnchorSeed:
    """Initial anchor creation for first-time attributes."""
    entity_id: str
    attribute: str
    tenant_id: str
    space_id: str
    initial_alpha: float            # 1.0 + evidence_for
    initial_beta: float             # 1.0 + evidence_against
    evidence_count: int
    observation_context: str

# =========================================================================
# Anchor Extractors: Data-driven from st_observations distributions
# =========================================================================

@dataclass(frozen=True)
class DistributionAnchorSpec:
    """Specification for deriving an anchor from an observation distribution."""
    anchor_name: str
    distribution_key: str           # Which distribution to query
    support_values: FrozenSet[str]  # Values that count as supporting evidence
    oppose_values: FrozenSet[str]   # Values that count as opposing evidence
    min_observations: int = 10      # Minimum total observations to derive anchor

# Pre-defined anchor specifications -- data-driven, not hard-coded lambdas
DISTRIBUTION_ANCHOR_SPECS = [
    # Temporal preferences
    DistributionAnchorSpec(
        anchor_name="is_morning_person",
        distribution_key="circadian",
        support_values=frozenset({"early_morning", "morning"}),
        oppose_values=frozenset({"late_night", "night"}),
    ),
    DistributionAnchorSpec(
        anchor_name="prefers_weekends",
        distribution_key="weekend",
        support_values=frozenset({True}),
        oppose_values=frozenset({False}),
        min_observations=20,
    ),
    # Location preferences
    DistributionAnchorSpec(
        anchor_name="prefers_outdoor",
        distribution_key="location",
        support_values=frozenset({"gym", "park", "trail", "beach", "outdoor"}),
        oppose_values=frozenset({"home", "office"}),
    ),
    DistributionAnchorSpec(
        anchor_name="home_oriented",
        distribution_key="location",
        support_values=frozenset({"home"}),
        oppose_values=frozenset({"gym", "park", "trail", "office", "transit"}),
    ),
    # Social preferences
    DistributionAnchorSpec(
        anchor_name="is_social",
        distribution_key="social",
        support_values=frozenset({"family", "friends", "work"}),
        oppose_values=frozenset({"solo"}),
    ),
    DistributionAnchorSpec(
        anchor_name="family_oriented",
        distribution_key="social",
        support_values=frozenset({"family"}),
        oppose_values=frozenset({"solo", "work"}),
    ),
    # Emotional tendencies
    DistributionAnchorSpec(
        anchor_name="generally_positive",
        distribution_key="emotion",
        support_values=frozenset({"joy", "anticipation", "trust", "gratitude"}),
        oppose_values=frozenset({"anger", "sadness", "fear", "disgust"}),
    ),
    DistributionAnchorSpec(
        anchor_name="stress_reactive",
        distribution_key="emotion",
        support_values=frozenset({"anger", "frustration", "anxiety", "stress"}),
        oppose_values=frozenset({"calm", "contentment", "peace"}),
    ),
    # Modality preferences
    DistributionAnchorSpec(
        anchor_name="prefers_voice",
        distribution_key="channel",
        support_values=frozenset({"voice"}),
        oppose_values=frozenset({"chat", "api"}),
    ),
]

class AnchorSeedingAndUpdate:
    """
    Bootstrap and maintain the Bayesian belief system (st_anchors).

    v2: Data-driven from st_observations distributions rather than
    hard-coded episode lambda extractors.

    Scientific basis: Beta-Bernoulli model for probabilistic user modeling.
    Beta(alpha, beta) where:
      - alpha = evidence FOR (from distribution counts)
      - beta = evidence AGAINST (from distribution counts)
      - Mean = alpha / (alpha + beta) = confidence estimate
      - Uncertainty = 1 / (1 + alpha + beta) = decreases with more data

    Dossier Reference: Section 5.4 Bayesian Anchor Points
    """

    DISTRIBUTION_MAP = {
        "circadian": "circadian_distribution",
        "location": "location_distribution",
        "social": "social_distribution",
        "emotion": "emotion_distribution",
        "weekend": "weekend_distribution",
        "channel": "channel_distribution",
    }

    async def process(
        self,
        observation_evidence: ObservationEvidence,
        existing_anchors: Dict[Tuple[str, str], AnchorRow],
        config: ASUConfig,
    ) -> Tuple[List[AnchorSeed], List[AnchorUpdate]]:
        seeds = []
        updates = []
        actor_id = config.actor_id

        for spec in DISTRIBUTION_ANCHOR_SPECS:
            anchor_key = (actor_id, spec.anchor_name)

            # Get the relevant distribution from pre-aggregated evidence
            dist_attr = self.DISTRIBUTION_MAP[spec.distribution_key]
            distribution = getattr(observation_evidence, dist_attr, {})

            if not distribution:
                continue

            # Count supporting and opposing observations
            total = sum(distribution.values())
            if total < spec.min_observations:
                continue  # Not enough data to derive this anchor

            support_count = sum(
                count for value, count in distribution.items()
                if self._normalize_value(value) in spec.support_values
            )
            oppose_count = sum(
                count for value, count in distribution.items()
                if self._normalize_value(value) in spec.oppose_values
            )

            if support_count == 0 and oppose_count == 0:
                continue  # No relevant observations

            if anchor_key not in existing_anchors:
                # Seed new anchor from distribution evidence
                alpha = 1.0 + support_count
                beta = 1.0 + oppose_count
                seeds.append(AnchorSeed(
                    entity_id=actor_id,
                    attribute=spec.anchor_name,
                    tenant_id=config.tenant_id,
                    space_id=config.space_id,
                    initial_alpha=alpha,
                    initial_beta=beta,
                    evidence_count=support_count + oppose_count,
                    observation_context=(
                        f"Distribution-derived: {support_count} supporting, "
                        f"{oppose_count} opposing out of {total} observations"
                    ),
                ))
            else:
                # Update existing anchor with incremental evidence
                anchor = existing_anchors[anchor_key]

                # Temporal decay before update (dossier 5.4.2)
                decay = self._calculate_decay(anchor.last_updated_at, config.decay_rate)
                decayed_alpha = 1.0 + (anchor.alpha - 1.0) * decay
                decayed_beta = 1.0 + (anchor.beta - 1.0) * decay

                # Add new evidence (scaled to avoid over-updating)
                new_alpha = decayed_alpha + support_count * config.evidence_scale
                new_beta = decayed_beta + oppose_count * config.evidence_scale

                if abs(new_alpha - anchor.alpha) > 0.01 or abs(new_beta - anchor.beta) > 0.01:
                    updates.append(AnchorUpdate(
                        entity_id=actor_id,
                        attribute=spec.anchor_name,
                        tenant_id=config.tenant_id,
                        space_id=config.space_id,
                        new_alpha=new_alpha,
                        new_beta=new_beta,
                        evidence_count=support_count + oppose_count,
                        observation_context=(
                            f"Updated: +{support_count} support, +{oppose_count} oppose, "
                            f"decay={decay:.3f}"
                        ),
                    ))

        # Drift detection (dossier 5.4.4)
        for anchor_key, anchor in existing_anchors.items():
            if anchor_key[0] != actor_id:
                continue
            drift = self._check_drift(anchor, observation_evidence, config)
            if drift:
                updates.append(AnchorUpdate(
                    entity_id=anchor.entity_id,
                    attribute=anchor.attribute,
                    tenant_id=anchor.tenant_id,
                    space_id=anchor.space_id,
                    new_alpha=anchor.alpha,
                    new_beta=anchor.beta,
                    evidence_count=0,
                    observation_context=f"DRIFT DETECTED: magnitude={drift:.3f}",
                ))

        return seeds, updates

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        """Normalize distribution value for comparison with spec values."""
        if isinstance(value, str):
            return value.lower().strip()
        return value
```

**Configuration**:

```python
@dataclass
class ASUConfig:
    actor_id: str                           # Primary user entity ID
    tenant_id: str
    space_id: str
    evidence_scale: float = 0.1             # Scale factor for incremental evidence (avoid over-updating)
    decay_rate: float = 0.001               # ~0.1% per day (dossier 5.4.2)
    drift_threshold: float = 0.20           # 20% shift triggers DRIFTING (dossier 5.4.4)
    drift_min_observations: int = 5         # Min recent observations for drift check
    drift_window_days: int = 30             # Recent window for drift comparison
```

**Outputs**: `List[AnchorSeed]` + `List[AnchorUpdate]`
**Target tables**: `st_anchors` inserts/updates + `st_anchor_observations` inserts via R6 -> R7

**Why this matters for recall**: Anchors enable K1 to personalize responses. Data-driven anchors are self-discovering -- as new context dimensions flow into st_observations (e.g., new location types, new social contexts), new anchor specs can be added without code changes. The distribution evidence is direct and auditable: "is_morning_person: 147 morning observations, 12 night observations, Beta(148, 13) = mean 0.92."

---

### 4.3 EWR -- Edge Weight Refinement (replaces TPN-MCTS)

**Purpose**: Strengthen meaningful KG edges, demote noisy ones. 1613 edges exist but 1330 are from `weight_normalization` enricher (#8 of R4's 8 enrichers) at avg weight 0.051. When K1 does entity-linked recall, these near-zero-weight edges are noise.

**v2 changes**:

1. **No temporal edge creation** -- R4 already has TemporalProximityEnricher (#3). If it produces 0 edges, that's an R4 bug to fix in R4, not an R5 workaround.
2. **Enricher-source analysis** -- Identify edges where the ONLY contributing enricher was WeightNormalization. These are pure noise. Edges with 2+ enrichers have multi-signal evidence.
3. **st_observations co-occurrence** -- Entity pairs that appear in observations of the same record have organic co-occurrence evidence independent of R4 enrichers.

**Inputs**:

- `merged_entities` (accumulated + current R4 entities)
- `merged_edges` (accumulated + current R4 edges, with enricher metadata)
- `observation_evidence.record_stats` (for entity co-occurrence signals)
- `merged_episodes` (for episode-level co-occurrence)

**Algorithm**:

```python
@dataclass(frozen=True)
class EdgeWeightUpdate:
    edge_id: str
    old_weight: float
    new_weight: float
    reinforcement_reason: str       # "multi_enricher_boost", "observation_cooccurrence",
                                    # "episode_cooccurrence", "sentiment_boost",
                                    # "noise_demotion", "staleness_decay"
    evidence_count: int             # Number of evidence sources

class EdgeWeightRefinement:
    """
    Strengthen meaningful KG edges, demote noisy ones.

    v2: Three evidence-based mechanisms (no temporal edge creation):
    1. Multi-enricher boost: edges with 2+ R4 enricher sources get weight increase
    2. Co-occurrence reinforcement: episode co-occurrence evidence
    3. Noise demotion: edges with ONLY WeightNormalization enricher get aggressive decay

    Scientific basis: Hebbian learning -- "neurons that fire together wire together."
    Multiple independent evidence sources (enrichers, episodes, observations) create
    stronger edge confidence than a single source.

    Coordinates with R4: R4 creates edges and assigns initial weights via 8 enrichers.
    EWR refines those weights based on accumulated evidence. EWR does NOT create
    new edge types -- that is R4's responsibility.
    """

    def refine_edges(
        self,
        entities: List[KGEntity],
        edges: List[KGEdge],
        episodes: List[EpisodeCluster],
        observation_evidence: ObservationEvidence,
        config: EWRConfig,
    ) -> List[EdgeWeightUpdate]:
        updates = []

        # =====================================================================
        # 1. Enricher-source analysis
        # Edges with multiple R4 enricher sources are more trustworthy
        # =====================================================================
        for edge in edges:
            enricher_count = self._count_enricher_sources(edge)

            if enricher_count >= config.multi_enricher_threshold:
                boost = config.multi_enricher_boost * (enricher_count - 1)
                new_weight = min(1.0, edge.weight + boost)

                if new_weight > edge.weight + 0.001:
                    updates.append(EdgeWeightUpdate(
                        edge_id=edge.edge_id,
                        old_weight=edge.weight,
                        new_weight=new_weight,
                        reinforcement_reason="multi_enricher_boost",
                        evidence_count=enricher_count,
                    ))

        # =====================================================================
        # 2. Co-occurrence reinforcement from episodes
        # Entity pairs appearing together in episodes get edge boost
        # =====================================================================
        edge_map = {(e.source_entity_id, e.target_entity_id): e for e in edges}
        boosted_edge_ids = {u.edge_id for u in updates}

        for episode in episodes:
            entity_ids = self._entities_in_episode(episode, entities)
            for i, eid_a in enumerate(entity_ids):
                for eid_b in entity_ids[i+1:]:
                    edge_key = (min(eid_a, eid_b), max(eid_a, eid_b))
                    existing = edge_map.get(edge_key) or edge_map.get(edge_key[::-1])

                    if existing and existing.edge_id not in boosted_edge_ids:
                        boost = config.cooccurrence_boost * (episode.aggregated_salience or 0.5)
                        # Emotional episodes reinforce stronger (McGaugh 2004)
                        if abs(episode.dominant_sentiment or 0) > 0.7:
                            boost *= config.sentiment_multiplier
                        new_weight = min(1.0, existing.weight + boost)

                        if new_weight > existing.weight + 0.001:
                            updates.append(EdgeWeightUpdate(
                                edge_id=existing.edge_id,
                                old_weight=existing.weight,
                                new_weight=new_weight,
                                reinforcement_reason="episode_cooccurrence",
                                evidence_count=1,
                            ))
                            boosted_edge_ids.add(existing.edge_id)

        # =====================================================================
        # 3. Noise demotion: WeightNormalization-only edges
        # Edges where the only enricher was WeightNormalization are the 1330
        # near-noise edges at avg 0.051. Decay aggressively.
        # =====================================================================
        reinforced_ids = {u.edge_id for u in updates}
        for edge in edges:
            if edge.edge_id in reinforced_ids:
                continue  # Has positive evidence -- do not demote

            is_normalization_only = self._is_weight_normalization_only(edge)

            if is_normalization_only and edge.weight < config.noise_threshold:
                # Pure noise edge: aggressive decay
                new_weight = max(0.0, edge.weight * config.noise_decay_factor)
                if new_weight < edge.weight - 0.001:
                    updates.append(EdgeWeightUpdate(
                        edge_id=edge.edge_id,
                        old_weight=edge.weight,
                        new_weight=new_weight,
                        reinforcement_reason="noise_demotion",
                        evidence_count=0,
                    ))
            elif self._count_enricher_sources(edge) <= 1 and edge.weight < config.noise_threshold:
                # Single-enricher near-noise: gentle decay
                new_weight = max(0.0, edge.weight * config.staleness_decay_factor)
                if new_weight < edge.weight - 0.001:
                    updates.append(EdgeWeightUpdate(
                        edge_id=edge.edge_id,
                        old_weight=edge.weight,
                        new_weight=new_weight,
                        reinforcement_reason="staleness_decay",
                        evidence_count=0,
                    ))

        return updates

    def _count_enricher_sources(self, edge: KGEdge) -> int:
        """Count how many distinct R4 enrichers contributed to this edge."""
        metadata = getattr(edge, "enricher_metadata", None) or {}
        return len(metadata.get("enricher_sources", []))

    def _is_weight_normalization_only(self, edge: KGEdge) -> bool:
        """Check if WeightNormalization was the only enricher."""
        metadata = getattr(edge, "enricher_metadata", None) or {}
        sources = set(metadata.get("enricher_sources", []))
        return sources == {"weight_normalization"} or sources == {"WeightNormalizationEnricher"}
```

**Configuration**:

```python
@dataclass
class EWRConfig:
    # Multi-enricher boost
    multi_enricher_threshold: int = 2       # Min enrichers for boost
    multi_enricher_boost: float = 0.05      # Weight boost per additional enricher

    # Co-occurrence reinforcement
    cooccurrence_boost: float = 0.02        # Weight boost per co-occurrence
    sentiment_multiplier: float = 1.5       # Extra boost for emotional episodes

    # Noise demotion
    noise_threshold: float = 0.10           # Below this = near noise
    noise_decay_factor: float = 0.80        # Aggressive decay for normalization-only edges
    staleness_decay_factor: float = 0.95    # Gentle decay for single-enricher low-weight edges
```

**Outputs**: `List[EdgeWeightUpdate]` (no NewTemporalEdge -- R4 owns edge creation)
**Target table**: `st_kg_edges.weight` updates via R6 -> R7

**Why this matters for recall**: When K1 queries "tell me about Marcus," edge weights determine which connected entities surface. Multi-enricher edges with co-occurrence evidence bring up Marcus->Amy (birthday party confirmed by 3 enrichers + 5 episode co-occurrences). Normalization-only noise edges get demoted below the recall noise floor.

---

### 4.4 SRE -- Social Relationship Enrichment (new)

**Purpose**: Fix the broken sentiment computation in `st_social`. Live data shows Panda at sentiment 0.00 despite 19 interactions all tagged as joy. The social layer is structurally correct but the numbers are not flowing.

**v2 change**: Uses per-observation emotional context from st_observations rather than episode-level `dominant_sentiment`. This gives the full emotional arc over time at observation granularity -- each event that was consolidated into an episode left an observation record with `sentiment_score`, `affect_valence`, and `dominant_emotion`.

**Inputs**:

- `observation_evidence.entity_observations` (per-entity emotional observations from ObservationEvidenceLoader)
- `existing_relationships` (current `st_social` rows)

**Algorithm**:

```python
@dataclass(frozen=True)
class SocialRelationshipUpdate:
    relationship_id: str
    person_entity_id: str
    new_sentiment: float                # Aggregated sentiment score
    new_interaction_count: int          # Total interactions observed
    sentiment_trajectory: str           # "IMPROVING", "STABLE", "DECLINING"
    emotional_diversity: float          # 0.0 (mono-emotion) to 1.0 (diverse)
    health_score: float                 # Combined relationship health metric
    last_interaction_at: int            # Timestamp of most recent episode together

class SocialRelationshipEnrichment:
    """
    Recompute social relationship metrics from st_observations.

    v2: Uses per-observation sentiment_score, affect_valence, and
    dominant_emotion rather than episode-level aggregates. This provides:
    - Full emotional arc over time (not just episode averages)
    - Accurate sentiment (from original event UltraBERT output)
    - Granular trajectory analysis (observation-level, not episode-level)

    Fixes: st_social sentiment stuck at 0.00 because R4's social extraction
    does not aggregate sentiment from the events/episodes that mention
    each person -- it only extracts the relationship type.
    """

    def enrich(
        self,
        observation_evidence: ObservationEvidence,
        existing_relationships: List[SocialRelationshipRow],
        config: SREConfig,
    ) -> List[SocialRelationshipUpdate]:
        updates = []

        for rel in existing_relationships:
            person_id = rel.person_entity_id
            observations = observation_evidence.entity_observations.get(person_id, [])

            if not observations:
                continue

            # Sort by time for trajectory analysis
            sorted_obs = sorted(observations, key=lambda o: o.observed_at)

            # Sentiment aggregation from observation-level data
            sentiments = [
                o.sentiment_score for o in sorted_obs
                if o.sentiment_score is not None
            ]

            if not sentiments:
                continue

            avg_sentiment = sum(sentiments) / len(sentiments)

            # Sentiment trajectory (observation-level granularity)
            split_point = max(1, len(sentiments) - config.recent_window_size)
            recent = sentiments[split_point:]
            older = sentiments[:split_point]

            if len(older) >= config.min_observations_for_trajectory:
                recent_avg = sum(recent) / len(recent)
                older_avg = sum(older) / len(older)
                diff = recent_avg - older_avg
                if diff > config.trajectory_threshold:
                    trajectory = "IMPROVING"
                elif diff < -config.trajectory_threshold:
                    trajectory = "DECLINING"
                else:
                    trajectory = "STABLE"
            else:
                trajectory = "STABLE"

            # Emotional diversity (Shannon entropy of dominant_emotion)
            emotions = [
                o.dominant_emotion for o in sorted_obs
                if o.dominant_emotion is not None
            ]
            unique_emotions = set(emotions)
            if len(emotions) > 0 and len(unique_emotions) > 1:
                from collections import Counter
                counts = Counter(emotions)
                probs = [c / len(emotions) for c in counts.values()]
                diversity = -sum(
                    p * math.log2(p) for p in probs if p > 0
                ) / math.log2(len(unique_emotions))
            else:
                diversity = 0.0

            # Health score: frequency * sentiment * recency
            last_obs = sorted_obs[-1]
            days_since = max(1, (config.now_ms - last_obs.observed_at) / 86_400_000)
            recency_factor = 1.0 / (1.0 + math.log(days_since))
            health = len(observations) * max(0, avg_sentiment) * recency_factor

            updates.append(SocialRelationshipUpdate(
                relationship_id=rel.relationship_id,
                person_entity_id=person_id,
                new_sentiment=round(avg_sentiment, 4),
                new_interaction_count=len(observations),
                sentiment_trajectory=trajectory,
                emotional_diversity=round(diversity, 4),
                health_score=round(health, 4),
                last_interaction_at=last_obs.observed_at,
            ))

        return updates
```

**Configuration**:

```python
@dataclass
class SREConfig:
    now_ms: int                             # Current timestamp for recency calc
    trajectory_threshold: float = 0.1       # Sentiment diff for IMPROVING/DECLINING
    min_observations_for_trajectory: int = 5 # Min observations before computing trajectory
    recent_window_size: int = 10            # Number of recent observations for trajectory
```

**Outputs**: `List[SocialRelationshipUpdate]`
**Target table**: `st_social` updates via R6 -> R7

**Why this matters for recall**: When K1 asks "who should I call about X?" or "how's my relationship with Panda?", the social layer drives the answer. Observation-level sentiment gives the real picture: Panda with 19 observations averaging sentiment 0.78 (from the actual UltraBERT outputs) instead of 0.00 (from a broken aggregation path).

---

### 4.5 SPC-UQ Refocused -- Prospective Memory Cleanup (modified)

**Purpose**: Shift from "generate new prospective memories from incomplete episodes" to "review and strengthen/expire existing prospective memories." 257 items, 70 are nonsense counterfactuals.

**v2 change**: Completion detection uses st_observations REINFORCEMENT records rather than keyword matching. If a prospective memory's record_id has recent REINFORCEMENT observations, the user has been engaging with that intention. Combined with intent_ultrabert signals from the source events, this is more reliable than keyword matching ("done", "finished").

**Inputs**:

- `observation_evidence.record_stats` (per-record stats for st_prospective layer)
- Existing `st_prospective` items (loaded via syscall)
- `event_states` (current cycle events for new intent detection)

**Algorithm**:

```python
@dataclass(frozen=True)
class ProspectiveUpdate:
    intention_id: str
    new_status: str                 # "ACTIVE", "COMPLETED", "STALE", "ARCHIVED"
    new_confidence: float
    reason: str                     # "stale_no_mention", "completed_by_episode", "counterfactual_cleanup"

@dataclass(frozen=True)
class ProspectiveMerge:
    keep_id: str                    # Surviving intention
    remove_id: str                  # Merged/removed intention
    reason: str

class ProspectiveMemoryCleanup:
    """
    Review and curate prospective memory layer.

    v2: Uses st_observations for evidence-based status detection.

    Focus areas:
    1. Counterfactual cleanup: Purge intention_type='COUNTERFACTUAL' junk
    2. Observation-based completion: Recent REINFORCEMENT = user engaged
    3. Observation-based staleness: No observations for stale_days = stale
    4. Deduplication: Merge similar reminders/decisions
    5. New detection: Only genuinely forward-looking intents from current events
    """

    def cleanup(
        self,
        existing_prospective: List[ProspectiveRow],
        observation_evidence: ObservationEvidence,
        current_events: List[P03EventState],
        config: SPCConfig,
    ) -> Tuple[List[ProspectiveUpdate], List[ProspectiveMerge], List[ProspectiveMemory]]:
        updates = []
        merges = []
        new_items = []

        now_ms = config.now_ms
        stale_cutoff_ms = now_ms - (config.stale_days * 86_400_000)

        # 1. Purge counterfactuals (unconditional)
        for item in existing_prospective:
            if item.intention_type == "COUNTERFACTUAL":
                updates.append(ProspectiveUpdate(
                    intention_id=item.intention_id,
                    new_status="ARCHIVED",
                    new_confidence=0.0,
                    reason="counterfactual_cleanup",
                ))
                continue

            # Get observation stats for this prospective record
            stats = observation_evidence.record_stats.get(
                ("st_prospective", item.intention_id)
            )

            # 2. Observation-based completion detection
            if stats and stats.last_observed_at > stale_cutoff_ms:
                if stats.reinforcement_count >= config.completion_reinforcement_threshold:
                    # Multiple reinforcements = strong engagement = likely completed
                    updates.append(ProspectiveUpdate(
                        intention_id=item.intention_id,
                        new_status="COMPLETED",
                        new_confidence=1.0,
                        reason=f"observation_completed: {stats.reinforcement_count} reinforcements",
                    ))
                    continue
                else:
                    # Recent observations but below threshold = still active
                    new_confidence = min(1.0, item.confidence * 1.1)
                    if new_confidence > item.confidence + 0.01:
                        updates.append(ProspectiveUpdate(
                            intention_id=item.intention_id,
                            new_status="ACTIVE",
                            new_confidence=new_confidence,
                            reason="observation_active",
                        ))
                    continue

            # 3. Staleness detection (no recent observations)
            if stats is None or stats.last_observed_at < stale_cutoff_ms:
                updates.append(ProspectiveUpdate(
                    intention_id=item.intention_id,
                    new_status="STALE",
                    new_confidence=max(0.1, item.confidence * 0.8),
                    reason=f"stale_no_observations_{config.stale_days}d",
                ))

        # 4. Deduplication (text similarity among active items)
        active_items = [
            i for i in existing_prospective
            if i.intention_type != "COUNTERFACTUAL" and i.status == "ACTIVE"
        ]
        merges = self._find_duplicates(active_items, config)

        # 5. New prospective detection from current events
        new_items = self._detect_new_intentions(current_events, existing_prospective, config)

        return updates, merges, new_items
```

**Configuration**:

```python
@dataclass
class SPCConfig:
    now_ms: int                             # Current timestamp
    stale_days: int = 30                    # Days without observations before STALE
    completion_reinforcement_threshold: int = 3  # REINFORCEMENT count for COMPLETED
    dedup_similarity_threshold: float = 0.85  # Text similarity for dedup
    intent_keywords: List[str] = field(default_factory=lambda: [
        "need to", "should", "remind me", "planning to", "want to",
        "have to", "going to", "will", "must",
    ])
```

**Outputs**: `List[ProspectiveUpdate]` + `List[ProspectiveMerge]` + `List[ProspectiveMemory]`
**Target table**: `st_prospective` updates + inserts via R6 -> R7

**Why this matters for recall**: When K1 asks "what decisions do I need to make?", observation-based curation means: items with recent engagement stay active, items nobody mentions fade to STALE, counterfactual junk gets purged. The observation trail is objective evidence of user engagement.

---

### 4.6 SPR -- Semantic Pattern Reinforcement (new)

**Purpose**: Break the flat confidence=0.80 across all 545 patterns. Every semantic pattern currently has identical confidence. Recall treats "When I delegate tasks, I feel less overwhelmed" the same as "annoyance emotional pattern".

**v2 change**: Uses st_observations REINFORCEMENT count as the primary grounding signal rather than scanning episodes for matches. A pattern reinforced 10 times through consolidation cycles is objectively more grounded than a pattern seen once. Specificity scoring (causal/action language analysis) remains as a valuable secondary signal.

**Inputs**:

- `observation_evidence.record_stats` (per-record stats for st_sem layer)
- `accumulated_schemas` (existing patterns from `st_sem`)

**Algorithm**:

```python
@dataclass(frozen=True)
class SemanticPatternUpdate:
    pattern_id: str
    new_confidence: float           # Updated confidence based on observations + specificity
    observation_count: int          # Total observations for this pattern
    reinforcement_count: int        # REINFORCEMENT observations specifically
    last_observed_at: int           # Most recent observation timestamp
    specificity_score: float        # How specific/actionable the pattern is

@dataclass(frozen=True)
class PatternMerge:
    keep_id: str
    remove_id: str
    reason: str                     # "semantic_duplicate"

class SemanticPatternReinforcement:
    """
    Differentiate pattern confidence based on observation evidence
    and specificity.

    v2: Two-signal confidence model:
    Signal 1 (primary): st_observations reinforcement count.
        Patterns reinforced many times through consolidation cycles
        are objectively more grounded than patterns seen once.
    Signal 2 (secondary): Specificity of the pattern text.
        Actionable lessons ("delegation reduces overwhelm") score
        higher than generic tags ("annoyance emotional pattern").

    Problems solved:
    - All 545 patterns at flat confidence 0.80
    - No differentiation between life lessons and generic tags
    - No evidence trail for pattern grounding
    - Duplicate patterns not merged

    DOES NOT apply decay. R3 owns decay for st_sem (lambda=0.003, ~231d half-life).
    """

    def reinforce(
        self,
        patterns: List[SemanticPatternRow],
        observation_evidence: ObservationEvidence,
        config: SPRConfig,
    ) -> Tuple[List[SemanticPatternUpdate], List[PatternMerge]]:
        updates = []

        for pattern in patterns:
            # Signal 1: Observation evidence (primary)
            stats = observation_evidence.record_stats.get(("st_sem", pattern.pattern_id))

            if stats:
                obs_count = stats.total_observations
                reinforcement_count = stats.reinforcement_count
                last_observed = stats.last_observed_at
            else:
                obs_count = 0
                reinforcement_count = 0
                last_observed = 0

            # Observation grounding factor: log-scaled reinforcement count
            if reinforcement_count > 0:
                observation_factor = min(
                    1.0,
                    math.log2(1 + reinforcement_count) / math.log2(1 + config.max_reinforcements_for_full)
                )
            else:
                observation_factor = 0.0

            # Recency factor
            if last_observed > 0:
                days_since = max(1, (config.now_ms - last_observed) / 86_400_000)
                recency_factor = 1.0 / (1.0 + 0.01 * days_since)
            else:
                recency_factor = 0.3  # Never observed = low recency

            # Signal 2: Specificity (secondary)
            specificity = self._compute_specificity(pattern)
            specificity_factor = 0.5 + 0.5 * specificity

            # Combined confidence
            new_confidence = min(0.99, (
                config.base_confidence
                + config.observation_weight * observation_factor
                + config.recency_weight * recency_factor
                + config.specificity_weight * specificity_factor
            ))

            # Only update if meaningfully different
            if abs(new_confidence - pattern.confidence) > 0.01:
                updates.append(SemanticPatternUpdate(
                    pattern_id=pattern.pattern_id,
                    new_confidence=round(new_confidence, 4),
                    observation_count=obs_count,
                    reinforcement_count=reinforcement_count,
                    last_observed_at=last_observed,
                    specificity_score=round(specificity, 4),
                ))

        # Pattern merging (similar descriptions)
        merges = self._find_duplicates(patterns, config)

        return updates, merges

    def _compute_specificity(self, pattern: SemanticPatternRow) -> float:
        """
        Score pattern specificity: 0.0 = generic tag, 1.0 = actionable lesson.

        Heuristics:
        - Token count: longer descriptions are more specific
        - Contains causal language: "because", "caused", "leads to"
        - Contains action language: "should", "need to", "works when"
        - Pattern type: LESSON > EMOTIONAL_TREND > generic
        """
        text = pattern.description or ""
        score = 0.0

        # Token count (normalized)
        tokens = len(text.split())
        score += min(0.3, tokens * 0.02)

        # Causal language
        causal_words = ["because", "caused", "leads to", "results in", "due to", "explained"]
        if any(w in text.lower() for w in causal_words):
            score += 0.3

        # Action language
        action_words = ["should", "need to", "works when", "helps to", "better when"]
        if any(w in text.lower() for w in action_words):
            score += 0.2

        # Pattern type bonus
        if pattern.pattern_type == "LESSON":
            score += 0.2
        elif pattern.pattern_type == "EMOTIONAL_TREND":
            score += 0.0  # Generic, no bonus

        return min(1.0, score)
```

**Configuration**:

```python
@dataclass
class SPRConfig:
    now_ms: int                                 # Current timestamp
    base_confidence: float = 0.30               # Starting point before factors
    observation_weight: float = 0.35            # Weight for observation evidence (primary)
    recency_weight: float = 0.15                # Weight for recency
    specificity_weight: float = 0.20            # Weight for specificity
    max_reinforcements_for_full: int = 10       # Reinforcements for full observation score
    dedup_similarity_threshold: float = 0.90    # Text similarity for merge
```

**Outputs**: `List[SemanticPatternUpdate]` + `List[PatternMerge]`
**Target table**: `st_sem.confidence` updates via R6 -> R7

**Why this matters for recall**: When K1 contexts a response with "things you've learned", confidence differentiates wisdom from noise. A life lesson reinforced 8 times at 0.92 confidence outranks a generic "annoyance emotional pattern" at 0.35. Because confidence is grounded in observation counts, the system can explain *why* a pattern is trusted: "reinforced in 8 consolidation cycles, last observed 3 days ago, contains causal language."

---

### 4.7 BGT-SM -- Bisociative Graph Traversal (kept unchanged)

No changes. BGT-SM discovers non-obvious connections via random-walk-with-restart over the KG. This is genuinely structural work that LLMs cannot efficiently replicate at query time (would require loading the full graph into context).

**Note**: BGT-SM benefits from EWR running first in the same cycle -- refined edge weights improve random walk quality.

---

### 4.8 TDL-HCO -- Temporal Difference Learning (kept unchanged)

No changes. Lightweight (<100ms), optimizes routines detected by RoutineDetector. Already produces valid `st_procedural` updates.

---

### 4.9 MTP -- Memory Tier Promotion (new)

**Purpose**: Prevent decay from eroding important, well-established memories. Currently R3 decays everything uniformly within a layer -- "my daughter's name is Panda" and "had pizza on Tuesday" both decay at the same rate. MTP assigns a tier to each record based on observation evidence, and higher-tier records receive reduced or zero decay in future R3 passes.

**Inputs**:

- `observation_evidence.record_stats` (reinforcement counts and ages across all layers)
- `accumulated_episodes` (for st_epi tier assignment)
- `accumulated_schemas` (for st_sem tier assignment)

**Dataclasses**:

```python
class MemoryTier(str, Enum):
    TRANSIENT = "TRANSIENT"   # reinforcement_count < 3, age < 14 days
    ACTIVE = "ACTIVE"         # reinforcement_count >= 3
    STABLE = "STABLE"         # reinforcement_count >= 10, age >= 30 days
    CORE = "CORE"             # reinforcement_count >= 20, age >= 90 days

    @property
    def decay_multiplier(self) -> float:
        """How much of R3's normal decay to apply."""
        return {
            MemoryTier.TRANSIENT: 1.0,   # Full decay
            MemoryTier.ACTIVE: 0.7,      # 30% decay reduction
            MemoryTier.STABLE: 0.3,      # 70% decay reduction
            MemoryTier.CORE: 0.0,        # No decay -- permanent
        }[self]


@dataclass(frozen=True)
class TierPromotion:
    layer: str                  # st_epi, st_sem, st_social, st_kg_dom, st_procedural
    record_id: str              # Record being promoted
    old_tier: MemoryTier        # Previous tier (or TRANSIENT if unset)
    new_tier: MemoryTier        # Promoted tier
    reinforcement_count: int    # Evidence: how many reinforcements
    record_age_days: int        # Evidence: how old is the record
    last_observed_at: int       # Most recent observation timestamp
```

**Algorithm**:

```python
class MemoryTierPromoter:
    """
    Assign memory tiers based on observation reinforcement counts
    and record age. Higher tiers receive reduced decay from R3.

    Tier thresholds:
    - TRANSIENT: Default. Full R3 decay applies.
    - ACTIVE: 3+ reinforcements. Modest decay reduction (0.7x).
    - STABLE: 10+ reinforcements over 30+ days. Heavy decay reduction (0.3x).
    - CORE: 20+ reinforcements over 90+ days. Zero decay -- permanent memory.

    This creates a natural lifecycle:
    1. New memory enters as TRANSIENT, R3 decays normally
    2. If consolidation keeps reinforcing it, it promotes to ACTIVE
    3. If it persists for months with continued evidence, STABLE
    4. If it survives 3+ months with 20+ reinforcements, CORE

    DOES NOT apply decay itself. Sets a tier marker that R3 reads.
    """

    def promote(
        self,
        observation_evidence: ObservationEvidence,
        config: MTPConfig,
    ) -> List[TierPromotion]:
        promotions = []

        for (layer, record_id), stats in observation_evidence.record_stats.items():
            # Skip layers that don't support tiers
            if layer not in config.tier_eligible_layers:
                continue

            age_days = max(1, (config.now_ms - stats.first_observed_at) / 86_400_000)
            count = stats.reinforcement_count

            # Determine tier
            if count >= config.core_threshold and age_days >= config.core_age_days:
                new_tier = MemoryTier.CORE
            elif count >= config.stable_threshold and age_days >= config.stable_age_days:
                new_tier = MemoryTier.STABLE
            elif count >= config.active_threshold:
                new_tier = MemoryTier.ACTIVE
            else:
                new_tier = MemoryTier.TRANSIENT

            # Only emit promotion if tier actually changed (upward only)
            old_tier = self._get_current_tier(layer, record_id)
            if new_tier.value > old_tier.value:
                promotions.append(TierPromotion(
                    layer=layer,
                    record_id=record_id,
                    old_tier=old_tier,
                    new_tier=new_tier,
                    reinforcement_count=count,
                    record_age_days=int(age_days),
                    last_observed_at=stats.last_observed_at,
                ))

        return promotions

    def _get_current_tier(self, layer: str, record_id: str) -> MemoryTier:
        """
        Read current tier from record metadata.
        Returns TRANSIENT if no tier is set (backward compatible).
        """
        # Implementation reads memory_tier from record's metadata JSONB
        # or a dedicated column, returning TRANSIENT as default.
        ...
```

**Configuration**:

```python
@dataclass
class MTPConfig:
    now_ms: int                                     # Current timestamp
    active_threshold: int = 3                       # Reinforcements for ACTIVE
    stable_threshold: int = 10                      # Reinforcements for STABLE
    stable_age_days: int = 30                       # Minimum age for STABLE
    core_threshold: int = 20                        # Reinforcements for CORE
    core_age_days: int = 90                         # Minimum age for CORE
    tier_eligible_layers: FrozenSet[str] = frozenset({
        "st_epi", "st_sem", "st_social", "st_kg_dom", "st_procedural"
    })
```

**Outputs**: `List[TierPromotion]`
**Target tables**: `memory_tier` metadata on st_epi, st_sem, st_social, st_kg_dom, st_procedural via R6 -> R7

**R3 integration**: R3's decay function becomes:

```python
effective_lambda = base_lambda * record.memory_tier.decay_multiplier
```

A CORE record with `decay_multiplier=0.0` produces `effective_lambda=0.0`, meaning zero decay. A TRANSIENT record is unchanged.

**Why this matters for recall**: "My daughter's name is Panda" at CORE tier never decays. "Had pizza Tuesday" at TRANSIENT tier naturally fades. Recall gets stable, permanent knowledge for core family facts while letting ephemeral details age out naturally. This is how biological memory works -- frequently activated hippocampal memories gradually transfer to neocortical storage where they become resistant to forgetting.

---

### 4.10 CLV -- Cross-Layer Coherence Verification (new)

**Purpose**: Verify referential integrity across truth tables at the semantic level. PostgreSQL enforces row-level FK integrity. CLV enforces memory-level integrity: every entity should have edges, every social entry should have a KG node, every pattern should have supporting evidence.

**Inputs**:

- `accumulated_entities` (st_kg_dom nodes)
- `merged_edges` (st_kg_edges)
- `accumulated_schemas` (st_sem patterns)
- `accumulated_episodes` (st_epi clusters)
- `social_graph` (st_social entries)
- `observation_evidence.record_stats` (observation counts per record)

**Dataclasses**:

```python
class CoherenceIssueType(str, Enum):
    ORPHAN_ENTITY = "ORPHAN_ENTITY"           # Entity with 0 edges
    DANGLING_EDGE = "DANGLING_EDGE"           # Edge referencing archived entity
    UNGROUNDED_SOCIAL = "UNGROUNDED_SOCIAL"   # Social entry with 0 observations
    ORPHAN_PATTERN = "ORPHAN_PATTERN"         # Pattern with 0 supporting episodes
    SOCIAL_WITHOUT_ENTITY = "SOCIAL_WITHOUT_ENTITY"  # Social entry, no KG node
    ENTITY_WITHOUT_SOCIAL = "ENTITY_WITHOUT_SOCIAL"  # Person entity, no social entry


@dataclass(frozen=True)
class CoherenceRepair:
    issue_type: CoherenceIssueType
    layer: str                  # Affected truth table
    record_id: str              # Record with the issue
    action: str                 # DEMOTE, ARCHIVE, SEED, FLAG
    detail: str                 # Human-readable explanation
    related_record_id: str = "" # Related record (e.g., the missing entity)
```

**Algorithm**:

```python
class CrossLayerCoherenceVerifier:
    """
    Verify semantic-level referential integrity across truth tables.

    Checks performed per pass:
    1. Orphan entities: st_kg_dom nodes with 0 edges in st_kg_edges
    2. Dangling edges: st_kg_edges referencing entities not in st_kg_dom
    3. Ungrounded social: st_social entries with 0 st_observations rows
    4. Orphan patterns: st_sem patterns with 0 supporting episodes
    5. Social-entity mismatch: person in st_social but not st_kg_dom (or vice versa)

    All checks are set intersection operations on already-loaded data.
    No additional SQL queries needed.
    """

    def verify(
        self,
        entities: List[EntityRow],
        edges: List[EdgeRow],
        patterns: List[SemanticPatternRow],
        episodes: List[EpisodeCluster],
        social: List[SocialRow],
        observation_evidence: ObservationEvidence,
        config: CLVConfig,
    ) -> List[CoherenceRepair]:
        repairs = []

        entity_ids = {e.entity_id for e in entities}
        edge_source_ids = {e.source_id for e in edges}
        edge_target_ids = {e.target_id for e in edges}
        connected_ids = edge_source_ids | edge_target_ids
        social_entity_ids = {s.entity_id for s in social}

        # 1. Orphan entities: entity exists but has 0 edges
        for entity in entities:
            if entity.entity_id not in connected_ids:
                # Check if it's new (has observations) or truly orphaned
                stats = observation_evidence.record_stats.get(
                    ("st_kg_dom", entity.entity_id)
                )
                if stats and stats.total_observations >= config.min_observations_to_keep:
                    continue  # New entity, edges will come
                repairs.append(CoherenceRepair(
                    issue_type=CoherenceIssueType.ORPHAN_ENTITY,
                    layer="st_kg_dom",
                    record_id=entity.entity_id,
                    action="FLAG",
                    detail=f"Entity '{entity.label}' has 0 edges. "
                           f"Observations: {stats.total_observations if stats else 0}",
                ))

        # 2. Dangling edges: edge references non-existent entity
        for edge in edges:
            if edge.source_id not in entity_ids:
                repairs.append(CoherenceRepair(
                    issue_type=CoherenceIssueType.DANGLING_EDGE,
                    layer="st_kg_edges",
                    record_id=edge.edge_id,
                    action="ARCHIVE",
                    detail=f"Edge source '{edge.source_id}' not in st_kg_dom",
                    related_record_id=edge.source_id,
                ))
            if edge.target_id not in entity_ids:
                repairs.append(CoherenceRepair(
                    issue_type=CoherenceIssueType.DANGLING_EDGE,
                    layer="st_kg_edges",
                    record_id=edge.edge_id,
                    action="ARCHIVE",
                    detail=f"Edge target '{edge.target_id}' not in st_kg_dom",
                    related_record_id=edge.target_id,
                ))

        # 3. Ungrounded social: social entry with 0 observations
        for social_entry in social:
            stats = observation_evidence.record_stats.get(
                ("st_social", social_entry.entity_id)
            )
            if not stats or stats.total_observations == 0:
                repairs.append(CoherenceRepair(
                    issue_type=CoherenceIssueType.UNGROUNDED_SOCIAL,
                    layer="st_social",
                    record_id=social_entry.entity_id,
                    action="FLAG",
                    detail=f"Social entry '{social_entry.name}' has 0 observations",
                ))

        # 4. Orphan patterns: pattern with 0 episodes mentioning it
        episode_pattern_ids = set()
        for ep in episodes:
            episode_pattern_ids.update(ep.semantic_pattern_ids or [])
        for pattern in patterns:
            if pattern.pattern_id not in episode_pattern_ids:
                stats = observation_evidence.record_stats.get(
                    ("st_sem", pattern.pattern_id)
                )
                if stats and stats.reinforcement_count >= config.min_reinforcements_to_keep:
                    continue  # Pattern is reinforced, episodes may have been merged
                repairs.append(CoherenceRepair(
                    issue_type=CoherenceIssueType.ORPHAN_PATTERN,
                    layer="st_sem",
                    record_id=pattern.pattern_id,
                    action="DEMOTE",
                    detail=f"Pattern '{pattern.description[:60]}' has 0 supporting episodes",
                ))

        # 5. Person entity in st_kg_dom without st_social entry
        person_entities = {
            e.entity_id for e in entities
            if e.entity_type in ("PERSON", "FAMILY_MEMBER")
        }
        for eid in person_entities - social_entity_ids:
            repairs.append(CoherenceRepair(
                issue_type=CoherenceIssueType.ENTITY_WITHOUT_SOCIAL,
                layer="st_kg_dom",
                record_id=eid,
                action="SEED",
                detail=f"Person entity has no st_social entry -- seed recommended",
            ))

        # 6. Social entry without st_kg_dom entity
        for sid in social_entity_ids - entity_ids:
            repairs.append(CoherenceRepair(
                issue_type=CoherenceIssueType.SOCIAL_WITHOUT_ENTITY,
                layer="st_social",
                record_id=sid,
                action="FLAG",
                detail=f"Social entry references entity not in st_kg_dom",
            ))

        return repairs
```

**Configuration**:

```python
@dataclass
class CLVConfig:
    min_observations_to_keep: int = 2          # Orphan entities with this many obs are kept
    min_reinforcements_to_keep: int = 3        # Orphan patterns with this many reinforcements kept
```

**Outputs**: `List[CoherenceRepair]`
**Target tables**: Various -- each repair type targets a different table. ARCHIVE repairs go through R6/R7. FLAG repairs go to st_consolidation_audit. SEED repairs generate SocialRelationshipSeed outputs for R7. DEMOTE repairs lower confidence on the affected record.

**Why this matters for recall**: Orphan entities are dead-ends in graph traversal. Dangling edges crash or produce nonsense context. Ungrounded social entries produce 0.00 sentiment results. Every coherence issue is a potential recall failure. CLV ensures the memory graph is internally consistent on every pass.

---

### 4.11 CTD -- Contradiction Detection (new)

**Purpose**: Find and resolve actual contradictions in existing memory. This is the principled replacement for CPN counterfactuals. Instead of inventing imaginary scenarios, CTD finds *real* conflicts in the data and resolves them using observation evidence as the tiebreaker.

**Inputs**:

- `accumulated_entities` (st_kg_dom with attributes)
- `observation_evidence.entity_observations` (per-entity emotional data)
- `observation_evidence.record_stats` (observation counts for tiebreaking)
- `social_graph` (st_social entries for sentiment contradiction check)
- `accumulated_episodes` (for temporal validation)

**Dataclasses**:

```python
class ContradictionType(str, Enum):
    FACT_CONFLICT = "FACT_CONFLICT"             # Same entity, same attribute, different values
    SENTIMENT_MISMATCH = "SENTIMENT_MISMATCH"   # st_social says X, observations say Y
    TEMPORAL_IMPOSSIBLE = "TEMPORAL_IMPOSSIBLE"  # Events can't co-occur in stated timeframe


@dataclass(frozen=True)
class Contradiction:
    contradiction_type: ContradictionType
    layer: str
    record_id_a: str            # First conflicting record
    record_id_b: str            # Second conflicting record (or same for mismatch)
    detail: str                 # Human-readable description
    winner_record_id: str       # Record with more evidence (resolved winner)
    loser_record_id: str        # Record to demote
    winner_evidence: int        # Observation count backing the winner
    loser_evidence: int         # Observation count backing the loser
    resolution: str             # DEMOTE_LOSER, ARCHIVE_LOSER, FORCE_RECALC
```

**Algorithm**:

```python
class ContradictionDetector:
    """
    Detect real contradictions in existing memory and resolve them
    using observation evidence as the tiebreaker.

    This replaces CPN counterfactual generation. Instead of inventing
    "what if Panda didn't go to school?", CTD finds actual conflicts:
    "st_social says sentiment=0.00 for Panda, but 15 observations
    show average sentiment=0.72"

    Contradiction types:
    1. Fact conflicts: Entity has contradictory attribute values
    2. Sentiment mismatch: st_social disagrees with observation trail
    3. Temporal impossibility: Events claim to overlap when they can't

    Resolution strategy: The record with more observation evidence wins.
    The loser is demoted (confidence lowered) or archived.
    """

    def detect(
        self,
        entities: List[EntityRow],
        social: List[SocialRow],
        episodes: List[EpisodeCluster],
        observation_evidence: ObservationEvidence,
        config: CTDConfig,
    ) -> List[Contradiction]:
        contradictions = []

        # 1. Fact conflicts: same entity, same attribute type, different values
        # Build attribute map: entity_id -> {attr_type -> [(value, record_id, obs_count)]}
        attr_map: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
        for entity in entities:
            for attr in (entity.attributes or []):
                stats = observation_evidence.record_stats.get(
                    ("st_kg_dom", entity.entity_id)
                )
                obs_count = stats.reinforcement_count if stats else 0
                attr_map[entity.entity_id][attr.attr_type].append(
                    (attr.value, entity.entity_id, obs_count)
                )

        for entity_id, attrs in attr_map.items():
            for attr_type, values in attrs.items():
                if len(values) < 2:
                    continue
                # Multiple values for same attribute -- find conflict
                unique_values = {v[0] for v in values}
                if len(unique_values) > 1:
                    # Sort by observation count, highest wins
                    sorted_vals = sorted(values, key=lambda x: x[2], reverse=True)
                    winner = sorted_vals[0]
                    for loser in sorted_vals[1:]:
                        if loser[0] != winner[0]:
                            contradictions.append(Contradiction(
                                contradiction_type=ContradictionType.FACT_CONFLICT,
                                layer="st_kg_dom",
                                record_id_a=winner[1],
                                record_id_b=loser[1],
                                detail=f"Entity {entity_id}: {attr_type}="
                                       f"'{winner[0]}' vs '{loser[0]}'",
                                winner_record_id=winner[1],
                                loser_record_id=loser[1],
                                winner_evidence=winner[2],
                                loser_evidence=loser[2],
                                resolution="DEMOTE_LOSER",
                            ))

        # 2. Sentiment mismatch: st_social vs observation emotional trail
        for social_entry in social:
            entity_obs = observation_evidence.entity_observations.get(
                social_entry.entity_id, []
            )
            if len(entity_obs) < config.min_observations_for_mismatch:
                continue

            # Compute average sentiment from observations
            sentiments = [o.sentiment_score for o in entity_obs if o.sentiment_score is not None]
            if not sentiments:
                continue
            obs_avg_sentiment = sum(sentiments) / len(sentiments)

            # Compare with stored sentiment
            stored_sentiment = social_entry.sentiment_score or 0.0
            delta = abs(obs_avg_sentiment - stored_sentiment)

            if delta >= config.sentiment_mismatch_threshold:
                contradictions.append(Contradiction(
                    contradiction_type=ContradictionType.SENTIMENT_MISMATCH,
                    layer="st_social",
                    record_id_a=social_entry.entity_id,
                    record_id_b=social_entry.entity_id,
                    detail=f"st_social sentiment={stored_sentiment:.2f} but "
                           f"{len(sentiments)} observations avg={obs_avg_sentiment:.2f}",
                    winner_record_id=social_entry.entity_id,
                    loser_record_id=social_entry.entity_id,
                    winner_evidence=len(sentiments),
                    loser_evidence=0,
                    resolution="FORCE_RECALC",
                ))

        # 3. Temporal impossibility: episodes claiming impossible overlap
        sorted_episodes = sorted(episodes, key=lambda e: e.temporal_start or 0)
        for i in range(len(sorted_episodes) - 1):
            ep_a = sorted_episodes[i]
            ep_b = sorted_episodes[i + 1]

            # Skip if no temporal bounds
            if not ep_a.temporal_end or not ep_b.temporal_start:
                continue

            # Check if same entity appears in both but time gap is impossible
            shared_entities = set(ep_a.entity_ids or []) & set(ep_b.entity_ids or [])
            if not shared_entities:
                continue

            # If episodes overlap temporally but are in different locations
            if ep_a.temporal_end > ep_b.temporal_start:
                loc_a = getattr(ep_a, 'location_name', None)
                loc_b = getattr(ep_b, 'location_name', None)
                if loc_a and loc_b and loc_a != loc_b:
                    stats_a = observation_evidence.record_stats.get(
                        ("st_epi", ep_a.episode_id)
                    )
                    stats_b = observation_evidence.record_stats.get(
                        ("st_epi", ep_b.episode_id)
                    )
                    count_a = stats_a.reinforcement_count if stats_a else 0
                    count_b = stats_b.reinforcement_count if stats_b else 0
                    contradictions.append(Contradiction(
                        contradiction_type=ContradictionType.TEMPORAL_IMPOSSIBLE,
                        layer="st_epi",
                        record_id_a=ep_a.episode_id,
                        record_id_b=ep_b.episode_id,
                        detail=f"Temporal overlap at different locations: "
                               f"'{loc_a}' vs '{loc_b}'",
                        winner_record_id=ep_a.episode_id if count_a >= count_b else ep_b.episode_id,
                        loser_record_id=ep_b.episode_id if count_a >= count_b else ep_a.episode_id,
                        winner_evidence=max(count_a, count_b),
                        loser_evidence=min(count_a, count_b),
                        resolution="DEMOTE_LOSER",
                    ))

        return contradictions
```

**Configuration**:

```python
@dataclass
class CTDConfig:
    min_observations_for_mismatch: int = 5     # Need this many obs before flagging mismatch
    sentiment_mismatch_threshold: float = 0.30  # Minimum delta to flag
```

**Outputs**: `List[Contradiction]`
**Target tables**: DEMOTE_LOSER lowers confidence on the losing record. ARCHIVE_LOSER removes it. FORCE_RECALC triggers SRE-style recalculation from observations.

**Why this matters for recall**: Every contradiction is a potential wrong answer. If st_social says sentiment=0.00 for Panda but observations show 0.72, recall will context K1 with the wrong emotional profile. CTD catches these before they damage recall quality. This is what CPN *should* have been -- finding real problems instead of imagining fictional ones.

---

### 4.12 EPC -- Episode Compression (new)

**Purpose**: Compress semantically similar recurring episodes into composite episodes with frequency metadata. Over time, "had family dinner" appears dozens of times. Recall doesn't need 50 separate episode fragments -- it needs to know "they eat dinner together regularly, ~4x/month, generally positive mood." EPC produces those composites.

**Inputs**:

- `accumulated_episodes` (st_epi clusters, with embeddings via st_vec)
- `observation_evidence.record_stats` (per-episode observation counts)
- `merged_edges` (entity co-occurrence data)

**Dataclasses**:

```python
@dataclass(frozen=True)
class CompositeEpisode:
    composite_id: str                   # New episode ID for the composite
    description: str                    # Synthesized description ("Regular family dinners")
    source_episode_ids: List[str]       # Episodes merged into this composite
    frequency_per_month: float          # How often this pattern occurs
    date_range_start: int               # Earliest source episode timestamp
    date_range_end: int                 # Latest source episode timestamp
    shared_entities: List[str]          # Entities common to all source episodes
    avg_sentiment: float                # Average sentiment across sources
    dominant_emotion: str               # Most common emotion across sources
    total_reinforcement_count: int      # Sum of all source reinforcements
    composite_salience: float           # Derived from frequency + recency + sentiment


@dataclass(frozen=True)
class EpisodeArchival:
    episode_id: str                     # Episode absorbed into a composite
    composite_id: str                   # The composite that absorbed it
    reason: str                         # "Merged into composite"
```

**Algorithm**:

```python
class EpisodeCompressor:
    """
    Compress recurring similar episodes into composite episodes.

    R3 handles dedup (exact/near-exact merges). EPC goes further:
    it identifies *semantically similar recurring events* and merges
    them into composites with frequency and date-range metadata.

    Process:
    1. Group episodes by shared entity overlap (>=2 shared entities)
    2. Within each group, compute pairwise text similarity
    3. Cluster similar episodes (threshold >= 0.85)
    4. For clusters with 3+ episodes, create a composite
    5. Archive the source episodes (they're now represented by the composite)

    Only compresses low-salience episodes. High-salience episodes
    (salience > 0.8) are kept individually -- they're unique events
    worth remembering in detail.
    """

    def compress(
        self,
        episodes: List[EpisodeCluster],
        observation_evidence: ObservationEvidence,
        config: EPCConfig,
    ) -> Tuple[List[CompositeEpisode], List[EpisodeArchival]]:
        composites = []
        archivals = []

        # Filter to compressible episodes (low salience, old enough)
        compressible = [
            ep for ep in episodes
            if (ep.salience_score or 0.5) < config.max_salience_for_compression
            and self._age_days(ep, config.now_ms) >= config.min_age_days
        ]

        # Group by entity overlap
        entity_groups = self._group_by_entity_overlap(
            compressible, config.min_shared_entities
        )

        for group in entity_groups:
            if len(group) < config.min_episodes_for_composite:
                continue

            # Cluster by text similarity within the group
            clusters = self._cluster_by_similarity(
                group, config.similarity_threshold
            )

            for cluster in clusters:
                if len(cluster) < config.min_episodes_for_composite:
                    continue

                # Build the composite
                shared_entities = self._find_shared_entities(cluster)
                sentiments = [
                    ep.sentiment_score for ep in cluster
                    if ep.sentiment_score is not None
                ]
                emotions = [
                    ep.dominant_emotion for ep in cluster
                    if ep.dominant_emotion
                ]
                timestamps = [
                    ep.temporal_start for ep in cluster
                    if ep.temporal_start
                ]

                if not timestamps:
                    continue

                date_range_ms = max(timestamps) - min(timestamps)
                months = max(1, date_range_ms / (30 * 86_400_000))

                # Sum reinforcement counts from observations
                total_reinforcements = sum(
                    (observation_evidence.record_stats.get(
                        ("st_epi", ep.episode_id)
                    ) or _EMPTY_STATS).reinforcement_count
                    for ep in cluster
                )

                composite = CompositeEpisode(
                    composite_id=generate_ulid(),
                    description=self._synthesize_description(cluster),
                    source_episode_ids=[ep.episode_id for ep in cluster],
                    frequency_per_month=round(len(cluster) / months, 1),
                    date_range_start=min(timestamps),
                    date_range_end=max(timestamps),
                    shared_entities=list(shared_entities),
                    avg_sentiment=round(
                        sum(sentiments) / len(sentiments), 3
                    ) if sentiments else 0.0,
                    dominant_emotion=max(
                        set(emotions), key=emotions.count
                    ) if emotions else "neutral",
                    total_reinforcement_count=total_reinforcements,
                    composite_salience=self._compute_composite_salience(
                        len(cluster), months, total_reinforcements
                    ),
                )
                composites.append(composite)

                # Archive source episodes
                for ep in cluster:
                    archivals.append(EpisodeArchival(
                        episode_id=ep.episode_id,
                        composite_id=composite.composite_id,
                        reason=f"Merged into composite ({len(cluster)} episodes)",
                    ))

        return composites, archivals

    def _group_by_entity_overlap(
        self, episodes: List[EpisodeCluster], min_shared: int
    ) -> List[List[EpisodeCluster]]:
        """Group episodes sharing >= min_shared entities."""
        # Union-Find approach: merge episodes that share enough entities
        ...

    def _cluster_by_similarity(
        self, group: List[EpisodeCluster], threshold: float
    ) -> List[List[EpisodeCluster]]:
        """
        Cluster episodes by text/embedding similarity.
        Uses pre-computed embeddings from st_vec where available,
        falls back to token overlap.
        """
        ...

    def _synthesize_description(self, cluster: List[EpisodeCluster]) -> str:
        """
        Create a composite description from cluster.
        Takes the most common tokens/phrases across all episodes.
        Example: 5 episodes about "family dinner" -> "Regular family dinners"
        """
        ...

    def _compute_composite_salience(
        self, count: int, months: float, reinforcements: int
    ) -> float:
        """Higher frequency + more reinforcements = higher salience."""
        freq_factor = min(1.0, count / (months * 10))  # 10/month = max
        reinf_factor = min(1.0, math.log2(1 + reinforcements) / 5)
        return round(0.4 + 0.3 * freq_factor + 0.3 * reinf_factor, 4)
```

**Configuration**:

```python
@dataclass
class EPCConfig:
    now_ms: int
    min_episodes_for_composite: int = 3        # Minimum cluster size
    min_shared_entities: int = 2               # Entities to consider episodes related
    similarity_threshold: float = 0.85         # Text/embedding similarity for clustering
    max_salience_for_compression: float = 0.60 # High-salience episodes kept individually
    min_age_days: int = 7                      # Don't compress very recent episodes
```

**Outputs**: `List[CompositeEpisode]` (INSERT into st_epi) + `List[EpisodeArchival]` (ARCHIVE source episodes)
**Target table**: `st_epi` via R6 -> R7

**Why this matters for recall**: When asked "do we eat dinner together?", recall finds one composite episode with `frequency_per_month=4.2, avg_sentiment=0.78, date_range: Jan-Dec 2025` instead of scanning 50 fragments. The composite carries more information in less space and directly answers frequency questions. It also keeps the episode count manageable -- without compression, st_epi grows unboundedly.

---

### 4.13 SPG -- Salience Propagation through Graph (new)

**Purpose**: Propagate salience from high-importance episodes to the entities and edges connected to them. Currently, salience is computed per-event in R1 and per-episode in R2, then frozen. Entities and edges have no salience signal at all. SPG gives entities and edges an importance score derived from the episodes they participate in.

**Inputs**:

- `accumulated_episodes` (st_epi with salience scores, post-EST update)
- `accumulated_entities` (st_kg_dom nodes)
- `merged_edges` (st_kg_edges, post-EWR update)

**Dataclasses**:

```python
@dataclass(frozen=True)
class EntitySalienceUpdate:
    entity_id: str
    propagated_salience: float      # Salience derived from connected episodes
    contributing_episodes: int      # How many episodes contributed
    max_episode_salience: float     # Highest contributing episode salience


@dataclass(frozen=True)
class EdgeSalienceUpdate:
    edge_id: str
    propagated_salience: float      # Salience derived from endpoint entities
    source_salience: float          # Source entity salience
    target_salience: float          # Target entity salience
```

**Algorithm**:

```python
class SaliencePropagator:
    """
    Single-hop salience propagation through the knowledge graph.

    Phase 1: Episode -> Entity
        For each high-salience episode, boost the salience of
        entities mentioned in that episode.

    Phase 2: Entity -> Edge
        For each edge, compute propagated salience from the
        salience of its endpoint entities.

    This is NOT full PageRank (too expensive for single-pass).
    It's one forward pass: episodes → entities → edges.

    Result: Entities mentioned in important episodes get higher
    salience. Edges between important entities get higher salience.
    EWR in future cycles benefits from these updated edge saliences.
    """

    def propagate(
        self,
        episodes: List[EpisodeCluster],
        entities: List[EntityRow],
        edges: List[EdgeRow],
        config: SPGConfig,
    ) -> Tuple[List[EntitySalienceUpdate], List[EdgeSalienceUpdate]]:
        entity_updates = []
        edge_updates = []

        # Phase 1: Episode -> Entity propagation
        entity_boost: Dict[str, List[float]] = defaultdict(list)
        for ep in episodes:
            if (ep.salience_score or 0.0) < config.min_episode_salience:
                continue
            for entity_id in (ep.entity_ids or []):
                entity_boost[entity_id].append(
                    ep.salience_score * config.episode_to_entity_factor
                )

        # Aggregate: take max + small bonus per additional episode
        entity_salience: Dict[str, float] = {}
        for entity_id, boosts in entity_boost.items():
            if not boosts:
                continue
            primary = max(boosts)
            secondary = sum(sorted(boosts, reverse=True)[1:]) * 0.1
            propagated = min(1.0, primary + secondary)
            entity_salience[entity_id] = propagated

            entity_updates.append(EntitySalienceUpdate(
                entity_id=entity_id,
                propagated_salience=round(propagated, 4),
                contributing_episodes=len(boosts),
                max_episode_salience=round(max(boosts) / config.episode_to_entity_factor, 4),
            ))

        # Phase 2: Entity -> Edge propagation
        for edge in edges:
            src_sal = entity_salience.get(edge.source_id, 0.0)
            tgt_sal = entity_salience.get(edge.target_id, 0.0)

            if src_sal == 0.0 and tgt_sal == 0.0:
                continue

            # Edge salience = geometric mean of endpoint saliences
            edge_propagated = math.sqrt(src_sal * tgt_sal) if src_sal > 0 and tgt_sal > 0 else (
                max(src_sal, tgt_sal) * config.single_endpoint_factor
            )

            if edge_propagated >= config.min_edge_salience_to_emit:
                edge_updates.append(EdgeSalienceUpdate(
                    edge_id=edge.edge_id,
                    propagated_salience=round(edge_propagated, 4),
                    source_salience=round(src_sal, 4),
                    target_salience=round(tgt_sal, 4),
                ))

        return entity_updates, edge_updates
```

**Configuration**:

```python
@dataclass
class SPGConfig:
    min_episode_salience: float = 0.50         # Only propagate from notable episodes
    episode_to_entity_factor: float = 0.80     # Damping: episode salience * this
    single_endpoint_factor: float = 0.50       # When only one endpoint has salience
    min_edge_salience_to_emit: float = 0.10    # Don't emit trivial edge updates
```

**Outputs**: `List[EntitySalienceUpdate]` + `List[EdgeSalienceUpdate]`
**Target tables**: `st_kg_dom.propagated_salience` (new field) + `st_kg_edges.propagated_salience` (new field) via R6 -> R7

**Why this matters for recall**: Currently 1330/1613 edges have avg weight 0.051 and entities have no salience. Recall treats all entities equally. With SPG, "Panda" (mentioned in 25 high-salience episodes) gets `propagated_salience=0.87`, while "Pizza Restaurant" (mentioned once, salience 0.3) gets 0.24. Graph-based recall (M57 EntityGraphExpander) can prioritize expanding high-salience entities first, producing more relevant context within the token budget.

---

### 4.14 NTD -- Narrative Thread Detection (new)

**Purpose**: Discover causal/temporal chains across episodes that form coherent stories. Individual episodes are memory snapshots. Narrative threads connect them into arcs: "Panda had trouble sleeping" -> "Took Panda to doctor" -> "Started new bedtime routine" -> "Panda sleeping better now." Threads are stored as high-confidence semantic patterns with story-arc metadata.

**Inputs**:

- `accumulated_episodes` (st_epi clusters, temporally ordered)
- `merged_edges` (temporal and causal edges from R4)
- `accumulated_entities` (for entity overlap detection)

**Dataclasses**:

```python
@dataclass(frozen=True)
class NarrativeThread:
    thread_id: str                      # ULID for the thread
    description: str                    # Synthesized narrative ("How we fixed Panda's sleep")
    episode_chain: List[str]            # Ordered list of episode IDs forming the thread
    shared_entities: List[str]          # Entities common to the thread
    temporal_span_days: int             # Days from first to last episode
    emotional_arc: str                  # NEGATIVE_TO_POSITIVE, ESCALATION, RESOLUTION, STABLE
    causal_strength: float              # How strong the causal links are (0-1)
    thread_confidence: float            # Overall confidence in this thread
```

**Algorithm**:

```python
class NarrativeThreadDetector:
    """
    Detect causal/temporal chains across episodes that form
    coherent narrative arcs.

    Process:
    1. Sort episodes by temporal_start
    2. For each episode, find subsequent episodes sharing 2+ entities
    3. Check for causal/temporal progression indicators:
       - Temporal ordering (A before B before C)
       - Causal language ("because", "after", "led to")
       - Emotional progression (negative -> positive = resolution)
    4. Chains of 3+ episodes with shared entities = narrative thread
    5. Store as st_sem pattern with type=NARRATIVE_THREAD

    This is fundamentally different from BGT-SM:
    - BGT-SM finds non-obvious connections via random walks
    - NTD finds linear causal/temporal chains between episodes
    """

    def detect(
        self,
        episodes: List[EpisodeCluster],
        edges: List[EdgeRow],
        config: NTDConfig,
    ) -> List[NarrativeThread]:
        threads = []

        # Sort episodes by temporal start
        temporal_episodes = [
            ep for ep in episodes
            if ep.temporal_start is not None
        ]
        temporal_episodes.sort(key=lambda e: e.temporal_start)

        # Build entity -> episode index
        entity_to_episodes: Dict[str, List[int]] = defaultdict(list)
        for i, ep in enumerate(temporal_episodes):
            for eid in (ep.entity_ids or []):
                entity_to_episodes[eid].append(i)

        # Build temporal edge index for causal strength scoring
        temporal_pairs: Set[Tuple[str, str]] = set()
        for edge in edges:
            if edge.edge_type in ("SEQUENTIAL", "CAUSAL_TEMPORAL", "CAUSAL"):
                temporal_pairs.add((edge.source_id, edge.target_id))

        # Find chains: BFS from each episode
        visited_chains: Set[FrozenSet[str]] = set()

        for start_idx, start_ep in enumerate(temporal_episodes):
            chain = [start_idx]
            chain_entities = set(start_ep.entity_ids or [])

            # Extend chain forward
            for next_idx in range(start_idx + 1, len(temporal_episodes)):
                next_ep = temporal_episodes[next_idx]
                next_entities = set(next_ep.entity_ids or [])

                # Must share enough entities
                shared = chain_entities & next_entities
                if len(shared) < config.min_shared_entities:
                    continue

                # Must be within temporal window
                time_gap_days = (
                    (next_ep.temporal_start - temporal_episodes[chain[-1]].temporal_start)
                    / 86_400_000
                )
                if time_gap_days > config.max_gap_days:
                    break  # Too far apart, stop extending

                chain.append(next_idx)
                chain_entities = chain_entities & next_entities  # Narrow shared

            if len(chain) < config.min_chain_length:
                continue

            # Deduplicate by episode set
            chain_key = frozenset(
                temporal_episodes[i].episode_id for i in chain
            )
            if chain_key in visited_chains:
                continue
            visited_chains.add(chain_key)

            # Score the chain
            chain_episodes = [temporal_episodes[i] for i in chain]
            shared = self._find_shared_entities(chain_episodes)
            emotional_arc = self._detect_emotional_arc(chain_episodes)
            causal_strength = self._compute_causal_strength(
                chain_episodes, temporal_pairs
            )

            span_days = int(
                (chain_episodes[-1].temporal_start - chain_episodes[0].temporal_start)
                / 86_400_000
            )

            # Confidence = chain length factor * causal strength * entity overlap
            confidence = min(0.95, (
                0.3 * min(1.0, len(chain) / config.max_chain_for_full_confidence)
                + 0.4 * causal_strength
                + 0.3 * (len(shared) / max(1, len(chain_episodes[0].entity_ids or [])))
            ))

            if confidence >= config.min_thread_confidence:
                threads.append(NarrativeThread(
                    thread_id=generate_ulid(),
                    description=self._synthesize_narrative(chain_episodes, shared),
                    episode_chain=[ep.episode_id for ep in chain_episodes],
                    shared_entities=list(shared),
                    temporal_span_days=span_days,
                    emotional_arc=emotional_arc,
                    causal_strength=round(causal_strength, 4),
                    thread_confidence=round(confidence, 4),
                ))

        return threads

    def _detect_emotional_arc(self, chain: List[EpisodeCluster]) -> str:
        """Classify emotional trajectory across the chain."""
        sentiments = [ep.sentiment_score for ep in chain if ep.sentiment_score is not None]
        if len(sentiments) < 2:
            return "STABLE"
        first_half = sum(sentiments[:len(sentiments)//2]) / max(1, len(sentiments)//2)
        second_half = sum(sentiments[len(sentiments)//2:]) / max(1, len(sentiments) - len(sentiments)//2)
        delta = second_half - first_half
        if delta > 0.2:
            return "NEGATIVE_TO_POSITIVE"
        elif delta < -0.2:
            return "ESCALATION"
        elif second_half > 0.6:
            return "RESOLUTION"
        return "STABLE"

    def _compute_causal_strength(
        self, chain: List[EpisodeCluster], temporal_pairs: Set
    ) -> float:
        """Score how causally connected the chain episodes are."""
        if len(chain) < 2:
            return 0.0
        causal_links = 0
        for i in range(len(chain) - 1):
            pair = (chain[i].episode_id, chain[i+1].episode_id)
            if pair in temporal_pairs:
                causal_links += 1
        return causal_links / (len(chain) - 1)

    def _synthesize_narrative(
        self, chain: List[EpisodeCluster], shared_entities: Set[str]
    ) -> str:
        """Create a narrative description from the chain."""
        # Takes entity names + emotional arc to construct:
        # "How [entity]'s [topic] developed over [N] days"
        ...
```

**Configuration**:

```python
@dataclass
class NTDConfig:
    min_chain_length: int = 3                   # Minimum episodes for a thread
    min_shared_entities: int = 2                # Entities that must persist across chain
    max_gap_days: int = 30                      # Maximum gap between consecutive episodes
    min_thread_confidence: float = 0.40         # Minimum confidence to emit
    max_chain_for_full_confidence: int = 8      # Chain length for max confidence factor
```

**Outputs**: `List[NarrativeThread]`
**Target table**: `st_sem` as `pattern_type=NARRATIVE_THREAD` via R6 -> R7. The thread's `episode_chain` is stored as a JSONB array for provenance.

**Why this matters for recall**: When K1 is asked "how did we fix Panda's sleep issue?", a NARRATIVE_THREAD pattern provides a complete story arc with ordered episodes, temporal span, emotional progression, and causal links. Without NTD, recall returns disconnected fragments and K1 must reconstruct the narrative at query time from scattered episodes -- wasting tokens and risking incomplete assembly.

```
R5 Dream Explorer Phase
    |
    |-- Phase 0: Observation Evidence Loading (REQUIRED FIRST)
    |   |-- ObservationEvidenceLoader.load(tenant_id, record_ids)
    |   |-- Result: ObservationEvidence shared by all algorithms
    |
    |-- Phase 1: Parallel (no dependencies between these)
    |   |-- EST (episode strength)      -- reads observation_evidence.record_stats
    |   |-- ASU (anchor seeding)         -- reads observation_evidence.distributions
    |   |-- SRE (social enrichment)      -- reads observation_evidence.entity_observations
    |   |-- SPR (semantic pattern)       -- reads observation_evidence.record_stats
    |   |-- SPC-UQ (prospective cleanup) -- reads observation_evidence.record_stats
    |
    |-- Phase 2: Sequential (depends on Phase 1 outputs)
    |   |-- EWR (edge refinement) -- reads observation_evidence + EST salience updates
    |   |-- BGT-SM (insights) -- benefits from EWR edge weights
    |
    |-- Phase 3: Sequential (depends on Phase 1+2)
    |   |-- TDL-HCO (routine optimization) -- uses updated routines
    |
    |-- Phase 4: Parallel (graph-level, depends on Phase 1+2 outputs)
    |   |-- SPG (salience propagation) -- reads Phase 1 EST salience + edges from Phase 2 EWR
    |   |-- NTD (narrative threads)    -- reads episodes + temporal edges
    |   |-- CTD (contradiction detect) -- reads entities + observations + social
    |   |-- CLV (coherence verify)     -- reads all truth tables + observations
    |
    |-- Phase 5: Sequential (depends on Phase 1-4 outputs)
    |   |-- MTP (tier promotion) -- reads observation_evidence + final salience/coherence state
    |   |-- EPC (episode compression) -- reads episodes + observation counts (runs last, may archive)
    |
    |-- Output: R5PhaseOutputs
        |-- observation_evidence: ObservationEvidence (shared, not persisted)
        |-- episode_strength_updates: List[EpisodeStrengthUpdate]
        |-- anchor_seeds: List[AnchorSeed]
        |-- anchor_updates: List[AnchorUpdate]
        |-- edge_weight_updates: List[EdgeWeightUpdate]
        |-- social_updates: List[SocialRelationshipUpdate]
        |-- prospective_updates: List[ProspectiveUpdate]
        |-- prospective_merges: List[ProspectiveMerge]
        |-- pattern_updates: List[SemanticPatternUpdate]
        |-- pattern_merges: List[PatternMerge]
        |-- insights: List[Insight]              (BGT-SM, kept)
        |-- routine_optimizations: List[...]     (TDL-HCO, kept)
        |-- new_prospective: List[ProspectiveMemory]  (SPC-UQ new items)
        |-- tier_promotions: List[TierPromotion]              (MTP, new)
        |-- coherence_repairs: List[CoherenceRepair]          (CLV, new)
        |-- contradictions: List[Contradiction]               (CTD, new)
        |-- composite_episodes: List[CompositeEpisode]        (EPC, new)
        |-- episode_archivals: List[EpisodeArchival]          (EPC, new)
        |-- entity_salience_updates: List[EntitySalienceUpdate]  (SPG, new)
        |-- edge_salience_updates: List[EdgeSalienceUpdate]      (SPG, new)
        |-- narrative_threads: List[NarrativeThread]           (NTD, new)
```

---

## 6. R6/R7 Integration

All new output types flow through the existing `R6Staging` -> `R7TruthWriter` pipeline:

| Output Type | R6 Staging Action | R7 Write Target | Write Operation | Observation Recorded |
|------------|-------------------|-----------------|-----------------|---------------------|
| `EpisodeStrengthUpdate` | `StagedWrite(UPDATE, st_epi)` | `st_epi.salience_score` | UPDATE | Yes (REINFORCEMENT) |
| `AnchorSeed` | `StagedWrite(INSERT, st_anchors)` | `st_anchors` | INSERT | Yes (FIRST_SEEN) |
| `AnchorUpdate` | `StagedWrite(UPDATE, st_anchors)` | `st_anchors.alpha/beta` | UPDATE | Yes (REINFORCEMENT) |
| `AnchorUpdate.observation` | `StagedWrite(INSERT, st_anchor_observations)` | `st_anchor_observations` | INSERT | No (child table) |
| `EdgeWeightUpdate` | `StagedWrite(UPDATE, st_kg_edges)` | `st_kg_edges.weight` | UPDATE | Yes (REINFORCEMENT) |
| `SocialRelationshipUpdate` | `StagedWrite(UPDATE, st_social)` | `st_social.*` | UPDATE | Yes (REINFORCEMENT) |
| `ProspectiveUpdate` | `StagedWrite(UPDATE, st_prospective)` | `st_prospective.status/confidence` | UPDATE | Yes (REINFORCEMENT) |
| `ProspectiveMerge` | `StagedWrite(ARCHIVE, st_prospective)` | `st_prospective` | ARCHIVE | No (removal) |
| `SemanticPatternUpdate` | `StagedWrite(UPDATE, st_sem)` | `st_sem.confidence` | UPDATE | Yes (REINFORCEMENT) |
| `PatternMerge` | `StagedWrite(ARCHIVE, st_sem)` | `st_sem` | ARCHIVE | No (removal) |
| `Insight` (BGT-SM) | Existing path | `st_sem` | INSERT | Yes (FIRST_SEEN) |
| `RoutineOptimization` (TDL-HCO) | Existing path | `st_procedural` | UPDATE | Yes (REINFORCEMENT) |
| `ProspectiveMemory` (new items) | Existing path | `st_prospective` | INSERT | Yes (FIRST_SEEN) |
| `TierPromotion` (MTP) | `StagedWrite(UPDATE, <layer>)` | Metadata on st_epi/st_sem/st_social/st_kg_dom | UPDATE | Yes (REINFORCEMENT) |
| `CoherenceRepair` (CLV) | `StagedWrite(varies)` | Depends on repair type: ARCHIVE/DEMOTE/SEED/FLAG | varies | Depends on action |
| `Contradiction` (CTD) | `StagedWrite(UPDATE, <layer>)` | Loser record confidence/ARCHIVE | UPDATE/ARCHIVE | Yes (REINFORCEMENT) |
| `CompositeEpisode` (EPC) | `StagedWrite(INSERT, st_epi)` | `st_epi` | INSERT | Yes (FIRST_SEEN) |
| `EpisodeArchival` (EPC) | `StagedWrite(ARCHIVE, st_epi)` | `st_epi` | ARCHIVE | No (removal) |
| `EntitySalienceUpdate` (SPG) | `StagedWrite(UPDATE, st_kg_dom)` | `st_kg_dom.propagated_salience` | UPDATE | Yes (REINFORCEMENT) |
| `EdgeSalienceUpdate` (SPG) | `StagedWrite(UPDATE, st_kg_edges)` | `st_kg_edges.propagated_salience` | UPDATE | Yes (REINFORCEMENT) |
| `NarrativeThread` (NTD) | `StagedWrite(INSERT, st_sem)` | `st_sem` as `pattern_type=NARRATIVE_THREAD` | INSERT | Yes (FIRST_SEEN) |

All writes are idempotent via existing UoW pattern. All staged through `P03StagedWrites` for atomic commit.

**R7 Observation Recording for R5 UPDATEs**: When R7 truth writers process UPDATE operations originating from R5, they call `ObservationRecorder.record_for_merge()` with `observation_type=REINFORCEMENT`. This creates the **self-reinforcing loop**: R5 reads observations to decide what to strengthen -> R7 records observations for those strengthenings -> next cycle's R5 sees more evidence. The loop is bounded by logarithmic scaling in each algorithm (e.g., EST uses `log2(1 + count)`).

---

## 7. Compute Budget

| Algorithm | Estimated Time | Notes |
|-----------|---------------|-------|
| **ObservationEvidenceLoader** | **~150ms** | **3 SQL queries against indexed st_observations (Phase 0)** |
| EST | ~50ms | Observation lookup + log2 scaling (no episode scan) |
| ASU | ~100ms | Distribution aggregates pre-loaded, Beta updates |
| EWR | ~250ms | Edge traversal + enricher source analysis |
| SRE | ~30ms | Pre-loaded entity observations, aggregation |
| SPC-UQ | ~80ms | Observation count checks + dedup |
| SPR | ~80ms | Observation lookup + specificity heuristics |
| BGT-SM | ~300ms | Random walk (kept, unchanged) |
| TDL-HCO | ~100ms | TD learning (kept, unchanged) |
| **Phase 1-3 Subtotal** | **~1.14s** | **Original 8 algorithms** |
| MTP | ~50ms | Dict lookups on observation_evidence, threshold checks |
| CLV | ~100ms | Set intersection on already-loaded truth tables |
| CTD | ~120ms | Attribute map + sentiment comparison + temporal scan |
| EPC | ~200ms | Entity grouping + embedding similarity clustering |
| SPG | ~80ms | One-hop propagation: episodes -> entities -> edges |
| NTD | ~150ms | Temporal sort + entity overlap chain detection |
| **Phase 4-5 Subtotal** | **~700ms** | **6 new single-pass algorithms** |
| **Total** | **~1.84s** | **Well within the 5-20% P03 compute budget (~9-36s for 3min pass)** |

**v2 efficiency gain**: The ObservationEvidenceLoader pays ~150ms upfront to pre-aggregate all observation data into an in-memory `ObservationEvidence` object. Individual algorithms then perform dict lookups instead of SQL queries or episode scans. Net savings vs v1: ~160ms (1.3s -> 1.14s) while providing richer evidence.

All algorithms are:

- **Deterministic**: Same inputs produce same outputs (seeded RNG where needed)
- **Idempotent**: Running twice on same data produces same writes
- **No LLM calls**: Pure algorithmic computation
- **No external dependencies**: Only reads from existing truth tables via syscalls

---

## 8. Feature Flags

```yaml
# Replace existing R5 mode flags
P03_FF_R5_MODE:
  type: enum
  values: [disabled, shadow, enabled]
  default: disabled           # Keep disabled until implementation complete
  description: "R5 memory strengthening mode control"

# Per-algorithm toggles for gradual rollout
P03_FF_R5_EST_ENABLED:
  type: boolean
  default: true
  description: "Enable Episodic Strength Tracker"

P03_FF_R5_ASU_ENABLED:
  type: boolean
  default: true
  description: "Enable Anchor Seeding & Update"

P03_FF_R5_EWR_ENABLED:
  type: boolean
  default: true
  description: "Enable Edge Weight Refinement"

P03_FF_R5_SRE_ENABLED:
  type: boolean
  default: true
  description: "Enable Social Relationship Enrichment"

P03_FF_R5_SPC_CLEANUP_ENABLED:
  type: boolean
  default: true
  description: "Enable Prospective Memory Cleanup"

P03_FF_R5_SPR_ENABLED:
  type: boolean
  default: true
  description: "Enable Semantic Pattern Reinforcement"

P03_FF_R5_MTP_ENABLED:
  type: boolean
  default: true
  description: "Enable Memory Tier Promotion"

P03_FF_R5_CLV_ENABLED:
  type: boolean
  default: true
  description: "Enable Cross-Layer Coherence Verification"

P03_FF_R5_CTD_ENABLED:
  type: boolean
  default: true
  description: "Enable Contradiction Detection"

P03_FF_R5_EPC_ENABLED:
  type: boolean
  default: true
  description: "Enable Episode Compression"

P03_FF_R5_SPG_ENABLED:
  type: boolean
  default: true
  description: "Enable Salience Propagation through Graph"

P03_FF_R5_NTD_ENABLED:
  type: boolean
  default: true
  description: "Enable Narrative Thread Detection"
```

---

## 9. Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `p03_r5_observation_loader_duration_ms` | Histogram | ObservationEvidenceLoader query time |
| `p03_r5_observation_records_loaded` | Gauge | Total record stats loaded |
| `p03_r5_observation_entities_loaded` | Gauge | Total entity observations loaded |
| `p03_r5_est_observation_boosted` | Counter | Episodes boosted via observation evidence (Tier 1) |
| `p03_r5_est_signature_boosted` | Counter | Episodes boosted via heuristic signature (Tier 2) |
| `p03_r5_asu_anchors_seeded` | Counter | New anchors created from distribution evidence |
| `p03_r5_asu_anchors_updated` | Counter | Existing anchors updated |
| `p03_r5_asu_drift_detected` | Counter | Anchors flagged as drifting |
| `p03_r5_ewr_multi_enricher_boosted` | Counter | Edges boosted (multi-enricher agreement) |
| `p03_r5_ewr_cooccurrence_boosted` | Counter | Edges boosted (episode co-occurrence) |
| `p03_r5_ewr_noise_demoted` | Counter | WeightNormalization-only edges demoted |
| `p03_r5_sre_relationships_updated` | Counter | Social relationships enriched via observations |
| `p03_r5_spc_counterfactuals_purged` | Counter | Counterfactual items archived |
| `p03_r5_spc_observation_completed` | Counter | Prospective items completed by observation trail |
| `p03_r5_spc_stale_marked` | Counter | Prospective items marked stale (no recent obs) |
| `p03_r5_spr_patterns_updated` | Counter | Patterns with confidence change |
| `p03_r5_spr_patterns_merged` | Counter | Duplicate patterns merged |
| `p03_r5_mtp_promotions_total` | Counter | Records promoted to higher tier |
| `p03_r5_mtp_tier_distribution` | Gauge (per tier) | Count of records per tier (TRANSIENT/ACTIVE/STABLE/CORE) |
| `p03_r5_mtp_core_records` | Gauge | Records at CORE tier (never decays) |
| `p03_r5_clv_repairs_total` | Counter | Total coherence repairs emitted |
| `p03_r5_clv_orphan_entities` | Counter | Entities with 0 edges flagged |
| `p03_r5_clv_dangling_edges` | Counter | Edges referencing missing entities archived |
| `p03_r5_clv_orphan_patterns` | Counter | Patterns with 0 supporting episodes demoted |
| `p03_r5_ctd_contradictions_total` | Counter | Total contradictions detected |
| `p03_r5_ctd_fact_conflicts` | Counter | Fact conflicts resolved |
| `p03_r5_ctd_sentiment_mismatches` | Counter | Sentiment mismatches resolved |
| `p03_r5_ctd_temporal_impossibles` | Counter | Temporal impossibilities resolved |
| `p03_r5_epc_composites_created` | Counter | Composite episodes created |
| `p03_r5_epc_episodes_archived` | Counter | Individual episodes archived into composites |
| `p03_r5_epc_compression_ratio` | Gauge | Episodes archived / composites created |
| `p03_r5_spg_entities_updated` | Counter | Entities receiving propagated salience |
| `p03_r5_spg_edges_updated` | Counter | Edges receiving propagated salience |
| `p03_r5_spg_avg_entity_salience` | Gauge | Average propagated entity salience |
| `p03_r5_ntd_threads_detected` | Counter | Narrative threads detected |
| `p03_r5_ntd_avg_chain_length` | Gauge | Average episodes per narrative thread |
| `p03_r5_ntd_emotional_arc_distribution` | Gauge (per arc) | Counts per arc type (NEG_TO_POS/ESCALATION/RESOLUTION/STABLE) |
| `p03_r5_phase4_duration_ms` | Histogram | Phase 4 (graph-level) total duration |
| `p03_r5_phase5_duration_ms` | Histogram | Phase 5 (tier/compression) total duration |
| `p03_r5_total_duration_ms` | Histogram | Total R5 phase duration (all 5 phases) |

---

## 10. What Gets Removed

| Item | Location | Action |
|------|----------|--------|
| CPN algorithm | `k0/modules/consolidation/dream/cpn.py` | Deprecate, mark for removal |
| TPN-MCTS algorithm | `k0/modules/consolidation/algorithms/mcts.py` | Deprecate, mark for removal |
| `CounterfactualScenario` output type | `k0/pipelines/p03/phase_outputs.py` | Mark deprecated |
| `r5_counterfactuals` on `R5PhaseOutputs` | `r5_dream_explorer.py` | Remove field |
| `mcts_scenarios` on `R5PhaseOutputs` | `r5_dream_explorer.py` | Remove field |
| `mcts_decisions_count` on `R5PhaseOutputs` | `r5_dream_explorer.py` | Remove field |
| `NewTemporalEdge` dataclass | EWR v1 proposal | Not created (R4 owns edge creation) |
| MCTS shadow validation config | `r5_config.py` | Remove |
| `st_mcts_shadow_log` references | Dossier Section 4.6.0 | Remove |
| MCTS rollout configuration | Dossier Section 4.6.2.1 | Remove |
| CPN `COUNTERFACTUAL` rows in `st_prospective` | Database | Archive existing 70 rows |
| Episode scanning in EST/SPR | v1 proposal | Replaced by observation lookups |
| Hard-coded EXTRACTORS in ASU | v1 proposal | Replaced by DistributionAnchorSpec |
| Keyword-based completion in SPC-UQ | v1 proposal | Replaced by observation-based completion |

---

## 11. Migration Plan

| Phase | Duration | What Happens |
|-------|----------|--------------|
| **Phase 0** | Week 1 | Implement `ObservationEvidenceLoader` shared infrastructure (3 SQL queries, `ObservationEvidence` dataclass) |
| **Phase 1** | Week 1-2 | Implement EST, ASU, SRE, SPR algorithms as modules using `ObservationEvidence` |
| **Phase 2** | Week 3 | Implement SPC-UQ refocused (cleanup mode) and EWR (enricher analysis) |
| **Phase 3** | Week 4 | Wire into R5 phase runner, update R6 staging for new output types |
| **Phase 4** | Week 5 | Shadow mode: run new algorithms, capture outputs, do not write |
| **Phase 5** | Week 5-6 | Wire R7 `ObservationRecorder.record_for_merge()` for R5 UPDATE operations (self-reinforcing loop) |
| **Phase 6** | Week 6 | Enable writes, verify via `explore_memory_layers.md` regeneration |
| **Phase 7** | Week 7 | Remove CPN, TPN-MCTS, archive counterfactual rows |
| **Phase 8** | Week 7-8 | Implement Phase 4 algorithms: SPG, NTD, CTD, CLV. Add `propagated_salience` column to st_kg_dom and st_kg_edges. Add `memory_tier` metadata to truth tables. |
| **Phase 9** | Week 8-9 | Implement Phase 5 algorithms: MTP, EPC. Shadow validate tier assignments and episode compression. |
| **Phase 10** | Week 9-10 | Enable Phase 4+5 writes. Validate: tier distribution across layers, 0 orphan edges, composite episodes created, narrative threads detected. |

Shadow validation criteria:

- ASU: Verify anchors are seeded with reasonable distributions (mean not 0.0 or 1.0)
- EST: Verify reinforced episodes show increased salience (Tier 1 observation-boosted > Tier 2 signature-boosted)
- EWR: Verify noise edges weight decreased, multi-enricher edges increased
- SRE: Verify Panda sentiment > 0.50 (was 0.00), based on per-observation emotional data
- SPR: Verify LESSON patterns > EMOTIONAL_TREND patterns in confidence, verify observation_count/reinforcement_count populated
- SPC-UQ: Verify counterfactuals archived, observation-based completions detected, stale items flagged

---

## 12. Success Criteria

After 30 days of enabled R5 strengthening:

1. **st_anchors**: 10+ active anchors with meaningful distributions (seeded from st_observations distribution evidence)
2. **st_social**: No relationships with 0.00 sentiment that have > 5 observations (currently Panda at 0.00 with 19+ observations)
3. **st_kg_edges**: Average weight of active edges > 0.10 (currently 0.051 dominated by WeightNormalization-only edges)
4. **st_kg_edges**: WeightNormalization-only edges demoted below active threshold
5. **st_sem**: Confidence range spans 0.30-0.95 (currently flat 0.80); LESSON patterns visibly higher than EMOTIONAL_TREND
6. **st_prospective**: 0 active counterfactual items, stale items flagged, observation-based completions detected
7. **st_epi**: Salience scores show variance (observation-reinforced episodes > unreinforced)
8. **Recall quality**: K1 recall returns more relevant results (measured by user corrections via P21 feedback pipeline)
9. **Self-reinforcing loop**: st_observations shows REINFORCEMENT rows generated from R5 UPDATE operations (via R7), confirming the evidence-strengthening-evidence cycle is active
10. **Audit trail**: Every R5 decision is traceable to specific st_observations records (observation_count, reinforcement_count fields on all output dataclasses)
11. **Memory tiers**: CORE tier records exist (20+ reinforcements over 90+ days). Tier distribution: majority TRANSIENT, fewer ACTIVE, fewer STABLE, select CORE. CORE records show zero decay across subsequent R3 passes.
12. **Cross-layer coherence**: 0 orphan edges (referencing missing entities). 0 person entities without st_social entry. Orphan patterns flagged or demoted.
13. **Contradictions resolved**: 0 unresolved SENTIMENT_MISMATCH contradictions where observation count > 5. Panda sentiment recalculated from 0.00 to observation-based value.
14. **Episode compression**: Episode count growth rate < 50% of pre-EPC rate. Composite episodes created for recurring patterns (family dinners, school routines). Composites carry frequency_per_month metadata.
15. **Entity salience**: st_kg_dom.propagated_salience shows variance (std_dev > 0.15). Key family entities (Panda, Mom, Dad) have salience > 0.70.
16. **Narrative threads**: At least 1 NARRATIVE_THREAD pattern detected per 30-day window. Threads connect 3+ episodes with shared entities and temporal ordering.

---

## 13. Implementation Plan — Code Discovery & Attaching Points

This section documents the complete code discovery conducted across all R5-related directories, identifies every file that must change, every new file to create, every file to deprecate, and every attaching point where new algorithms wire into the existing P03 pipeline. This is the bridge from proposal to implementation.

### 13.1 n-1 Cycle Architecture

**Critical architectural observation**: All P03 phases R0 through R6 buffer their outputs in the `P03BatchEnvelope` in memory. Only R7 (`TransactionCoordinator`) commits atomically to the database via a Unit of Work pattern. This means:

- **R5 reads committed database state (n-1 cycle)** when loading accumulated entities, edges, episodes, schemas, routines, and st_observations evidence.
- **R5 also reads current batch in-memory data** from `envelope.phases` (R2 clusters, R4 new entities/edges).
- **The self-reinforcing loop takes 2 cycles to stabilize**: Cycle N writes strengthened records via R7. Cycle N+1's R5 reads those strengthened records as evidence, producing further reinforcements.
- **This is natural and accepted** (matches biological consolidation: memories consolidate across multiple sleep cycles, not within one).

**Evidence from code** (`staged_writes.py` docstring):
> "StagedWrites accumulated during R1-R6, committed atomically by R7."

**Current data loading in `_execute_algorithms()`:**

| Load Method | Source | Data |
|---|---|---|
| `_load_accumulated_entities()` | st_kg_dom (DB, n-1) | KG entities for BGT-SM |
| `_load_accumulated_edges()` | st_kg_edges (DB, n-1) | KG edges for BGT-SM |
| `_load_accumulated_episodes()` | st_epi (DB, n-1) | Episodes for RoutineDetector, CPN, TDL-HCO |
| `_load_accumulated_schemas()` | st_sem (DB, n-1) | Semantic schemas for SPC-UQ |
| `_load_accumulated_routines()` | st_procedural (DB, n-1) | Routines for TDL-HCO |
| `envelope.phases.r2_clusters` | In-memory (current batch) | Current cycle episodes |
| `envelope.phases.r4_new_entities` | In-memory (current batch) | Current cycle KG entities |
| `envelope.phases.r4_new_edges` | In-memory (current batch) | Current cycle KG edges |

**New loader required**: `_load_observation_evidence()` — queries st_observations for the current tenant/space, returning evidence records grouped by target entity. This is the primary evidence source for all 14 new algorithms.

**Merge strategy**: Current batch data takes precedence. Accumulated (n-1) data fills gaps. Deduplication by ID (`entity_id`, `edge_id`, `cluster_id`).

#### 13.1.1 Existing Loader Signatures (Pattern to Follow)

All existing loaders follow the same pattern: `async def _load_accumulated_X(self, ctx, tenant_id, space_id) -> List[DataClass]`. They call `ctx.syscalls.X_query()`, parse result dicts into dataclasses, and return empty list on failure (error isolation via try/except with warning log).

```python
# Pattern from r5_dream_explorer.py line 668:
async def _load_accumulated_entities(
    self, ctx: "P03RunnerContext", tenant_id: str, space_id: str,
) -> List["KGEntity"]:
    result = await ctx.syscalls.kg_entities_query(
        tenant_id=tenant_id, space_id=space_id,
        limit=self.config.accumulated_kg_entity_limit,  # Default: 1000
    )
    # Parse rows into KGEntity dataclass with is_new=False
    # Also loads embeddings via syscalls.embedding_vectors_batch_query()
    # Returns [] on failure

# Three more loaders follow same pattern:
# _load_accumulated_edges()   → ctx.syscalls.kg_edges_query()       limit=5000
# _load_accumulated_episodes()→ ctx.syscalls.episodes_query()       limit=100
# _load_accumulated_schemas() → ctx.syscalls.semantic_schemas_query()
# _load_accumulated_routines()→ ctx.syscalls.procedural_routines_query() limit=50
```

#### 13.1.2 New Loader: `_load_observation_evidence()` Full Specification

The new loader follows the same pattern but queries st_observations instead of a truth layer. It wraps the `ObservationEvidenceLoader` defined in Section 4.0.1.

```python
async def _load_observation_evidence(
    self, ctx: "P03RunnerContext", tenant_id: str, space_id: str,
) -> ObservationEvidence:
    """Load pre-aggregated st_observations evidence for all R5 algorithms.

    Queries st_observations once and structures evidence by (layer, record_id).
    Uses indexed queries from migration 0067 for performance.
    Returns empty ObservationEvidence on failure (graceful degradation).
    """
    from k0.modules.consolidation.algorithms.observation_evidence_loader import (
        ObservationEvidenceLoader,
    )
    try:
        loader = ObservationEvidenceLoader()
        lookback_ms = self.config.observation_lookback_days * 86_400_000
        return await loader.load(
            uow=ctx.uow,
            tenant_id=tenant_id,
            lookback_ms=lookback_ms,
        )
    except Exception as e:
        self._logger.warning(
            "Failed to load observation evidence, proceeding without",
            extra={"error": str(e)},
        )
        return ObservationEvidence.empty()
```

**Config field to add to `R5Config`**: `observation_lookback_days: int = 90` (how far back to load distribution data).

**SQL queries** (executed by `ObservationEvidenceLoader.load()`, defined in Section 4.0.1):

| Query | Purpose | Index Used |
| --- | --- | --- |
| `_RECORD_STATS_SQL` | Per-record aggregate (count, reinforcement_count, avg_sentiment, etc.) | `idx_obs_record_time` |
| `_DISTRIBUTION_SQL` | Tenant-wide distribution (circadian, location, social, emotion) | `idx_obs_tenant_time` |
| `_ENTITY_OBSERVATIONS_SQL` | Per-entity emotional observations for SRE | `idx_obs_sentiment` |

#### 13.1.3 Merge Order in `_execute_algorithms()`

The current code merges data in this exact sequence:

```python
# 1. Load accumulated KG (n-1 committed state)
accumulated_entities = await self._load_accumulated_entities(ctx, tenant_id, space_id)
accumulated_edges = await self._load_accumulated_edges(ctx, tenant_id, space_id)

# 2. Merge with current batch (current takes precedence)
new_entities = list(envelope.phases.r4_new_entities)
new_entity_ids = {e.entity_id for e in new_entities}
merged_entities = new_entities + [
    e for e in accumulated_entities if e.entity_id not in new_entity_ids
]
# Same pattern for edges

# 3. Load accumulated episodes (n-1) and merge with R2 clusters (current)
accumulated_episodes = await self._load_accumulated_episodes(ctx, tenant_id, space_id)
current_episodes = list(envelope.phases.r2_clusters)
current_episode_ids = {e.cluster_id for e in current_episodes}
merged_episodes = current_episodes + [
    e for e in accumulated_episodes if e.cluster_id not in current_episode_ids
]

# 4. Load schemas and routines (n-1 only, no current batch equivalents)
accumulated_schemas = await self._load_accumulated_schemas(ctx, tenant_id, space_id)
accumulated_routines = await self._load_accumulated_routines(ctx, tenant_id, space_id)

# 5. NEW: Load observation evidence (n-1 committed state)
observation_evidence = await self._load_observation_evidence(ctx, tenant_id, space_id)

# 6. Build input
input_data = DreamExplorerInput(
    cycle_id=envelope.context.cycle_id,
    tenant_id=tenant_id,
    space_id=space_id,
    recent_episodes=merged_episodes,
    kg_entities=merged_entities,
    kg_edges=merged_edges,
    event_states=list(envelope.events),
    schemas=accumulated_schemas,
    accumulated_routines=accumulated_routines,
    observation_evidence=observation_evidence,  # NEW FIELD
)
```

---

### 13.2 Current R5 Architecture (What Exists Today)

#### 13.2.1 R5DreamExplorer Phase Runner

**File**: `k0/pipelines/p03/phases/r5_dream_explorer.py` (1070 lines)

**Class**: `R5DreamExplorer` — Phase runner implementing the P03PhaseInterface.

**Flow**:

1. `run()` — Entry point. Checks `should_skip()`, then calls `_execute_algorithms()`, then `_stage_outputs()`.
2. `should_skip()` — Checks R5Mode (DISABLED/SHADOW/ENABLED_LOW/ENABLED), backlog threshold, time window.
3. `_execute_algorithms()` — Builds `DreamExplorerInput` from envelope + accumulated DB data, delegates to `DreamExplorer.explore()`.
4. `_stage_outputs()` — Maps `R5PhaseOutputs` fields to `envelope.phases.r5_*` fields.

**Current `R5PhaseOutputs` dataclass fields**:

```
insights: List[Insight]
counterfactuals: List[CounterfactualScenario]        # CPN — TO REMOVE
routine_optimizations: List[RoutineOptimization]
routine_candidates: List[RoutineCandidate]
prospective_memories: List[ProspectiveMemory]
intent_signals: List[IntentSignal]
mcts_scenarios: List[MCTSScenario]                   # MCTS — TO REMOVE
mcts_decisions_count: int                             # MCTS — TO REMOVE
compute_seconds_saved: float
```

**Current `_stage_outputs()` mapping**:

```
envelope.phases.r5_insights            ← outputs.insights
envelope.phases.r5_counterfactuals     ← outputs.counterfactuals        # TO REMOVE
envelope.phases.r5_routine_optimizations ← outputs.routine_optimizations
envelope.phases.r5_routine_candidates  ← outputs.routine_candidates
envelope.phases.r5_prospective_memories ← outputs.prospective_memories
envelope.phases.r5_intent_signals      ← outputs.intent_signals
envelope.phases.r5_mcts_scenarios      ← outputs.mcts_scenarios         # TO REMOVE
```

#### 13.2.2 DreamExplorer Orchestrator

**File**: `k0/modules/consolidation/dream/dream_explorer.py` (1439 lines)

**Class**: `DreamExplorer` — Core orchestrator with 4-phase execution:

| Phase | Algorithms | Execution |
|---|---|---|
| Phase 1 | BGT-SM, CPN, SPC-UQ, MCTS, RoutineDetector | Parallel (`asyncio.gather`) |
| Phase 2 | TDL-HCO | Sequential (uses Phase 1 routine_candidates) |
| Phase 3 | Quality filters | `_rank_and_limit_*()` methods |
| Phase 4 | Intent signal detection | `IntentSignalDetector.detect_all()` |

**Algorithm dispatch methods**:

- `_run_bgt_sm()` — Bisociative Graph Traversal (KEEP, refactor to observation-driven)
- `_run_cpn()` — Counterfactual Perturbation Network (DEPRECATE)
- `_run_spc_uq()` — Sparse Predictive Coding (KEEP, refactor)
- `_run_mcts()` — Monte Carlo Tree Search (DEPRECATE)
- `_run_tdl_hco()` — Temporal Difference Learning (KEEP)
- `_run_routine_detector()` — Routine/habit detection (KEEP)

#### 13.2.3 Configuration

**File**: `k0/pipelines/p03/r5_config.py` (241 lines)

- `R5Mode` enum: DISABLED, SHADOW, ENABLED_LOW, ENABLED
- `R5Config` dataclass: ~30 fields including CPN/MCTS params to remove
- Feature flag: `P03_FF_R5_MODE = R5Mode.ENABLED`

**Exact R5Config fields to REMOVE**:

```python
# MCTS configuration (Issue 8.1.5, 8.1.6) — ALL REMOVE
mcts_rollouts_override: Optional[int] = None
mcts_exploration_constant: float = 1.414
mcts_max_depth: int = 10
mcts_early_termination_threshold: float = 0.95

# CPN configuration (Issue 8.1.4) — ALL REMOVE
max_counterfactuals_per_event: int = 5
cpn_perturbation_std: float = 0.1
cpn_counterfactual_types: tuple = ("UPWARD", "DOWNWARD", "SEMIFACTUAL")
cpn_emotional_threshold: float = 0.3

# Shadow validation — REMOVE (replaced by per-algorithm error isolation)
enable_shadow_validation: bool = True
```

**Exact R5Config fields to ADD**:

```python
# Observation evidence loading
observation_lookback_days: int = 90
observation_min_reinforcements: int = 2  # Min reinforcements before algorithms act

# Per-algorithm output limits (replace max_counterfactuals_per_event)
max_est_updates_per_batch: int = 50
max_asu_updates_per_batch: int = 30
max_ewr_updates_per_batch: int = 100
max_sre_updates_per_batch: int = 20
max_spr_actions_per_batch: int = 20
max_mtp_promotions_per_batch: int = 10
max_clv_repairs_per_batch: int = 30
max_ctd_resolutions_per_batch: int = 10
max_epc_composites_per_batch: int = 5
max_spg_updates_per_batch: int = 50
max_ntd_threads_per_batch: int = 3
```

**Exact R5Config fields to KEEP**:

```python
mode: R5Mode = R5Mode.DISABLED
backlog_threshold: int = 1000
min_remaining_window_seconds: int = 60
max_insights_per_batch: int = 10
bgt_sm_semantic_distance_threshold: float = 0.3
bgt_sm_pmi_threshold: float = 2.0
bgt_sm_corpus_size_n: int = 10000
bgt_sm_cold_start_threshold: int = 100
accumulated_kg_entity_limit: int = 1000
accumulated_kg_edge_limit: int = 5000
accumulated_episode_limit: int = 100
accumulated_routine_limit: int = 50
spc_uq_uncertainty_alpha: float = 1.0
spc_uq_uncertainty_beta: float = 1.0
spc_uq_simulation_count: int = 100
tdl_hco_learning_rate: float = 0.01
tdl_hco_discount_factor: float = 0.95
tdl_hco_eligibility_trace_decay: float = 0.9
```

**Also remove `effective_rollouts` property** (MCTS-specific) and `ROLLOUTS_PER_MODE` dict.

---

**File**: `k0/modules/consolidation/dream/config.py` (146 lines)

- `DreamConfig` dataclass: All CPN perturbation_std, MCTS rollout, CPN counterfactual_types fields to remove

**Exact DreamConfig fields to REMOVE**:

```python
cpn_perturbation_std: float = 0.1
cpn_counterfactual_types: tuple = ("UPWARD", "DOWNWARD", "SEMIFACTUAL")
cpn_emotional_threshold: float = 0.3
mcts_exploration_constant: float = 1.414
mcts_max_rollout_depth: int = 30
mcts_discount_factor: float = 0.9
mcts_max_total_rollouts: int = 1000
```

**Also remove from `from_r5_config()` class method**: all CPN/MCTS field mappings.

---

**File**: `k0/modules/consolidation/dream/models.py` (411 lines)

**Classes to DEPRECATE entirely**:

- `CounterfactualScenario` (frozen dataclass, 10 fields, ~40 lines) — CPN output
- `ScenarioType` (str Enum: UPWARD, DOWNWARD, SEMIFACTUAL) — CPN enum

**`DreamExplorerInput` — field to ADD**:

```python
observation_evidence: Optional[ObservationEvidence] = None  # NEW: R5 evidence
```

**`DreamExplorerOutput` — fields to REMOVE**:

```python
counterfactuals: List[CounterfactualScenario]  # REMOVE
mcts_scenarios: List["MCTSScenario"]           # REMOVE
mcts_decisions_evaluated: int = 0              # REMOVE
```

**`DreamExplorerOutput` — fields to ADD** (for new algorithms):

```python
est_updates: List[EpisodicStrengthUpdate] = field(default_factory=list)
asu_updates: List[SchemaConfidenceUpdate] = field(default_factory=list)
ewr_updates: List[EdgeWeightUpdate] = field(default_factory=list)
sre_updates: List[SocialRecalibration] = field(default_factory=list)
spr_actions: List[PredictionReaperAction] = field(default_factory=list)
mtp_promotions: List[TierPromotion] = field(default_factory=list)
clv_repairs: List[CrossLayerRepair] = field(default_factory=list)
ctd_resolutions: List[ContradictionResolution] = field(default_factory=list)
epc_composites: List[EpisodeComposite] = field(default_factory=list)
spg_salience: List[SaliencePropagation] = field(default_factory=list)
ntd_threads: List[NarrativeThread] = field(default_factory=list)
```

**`DreamExplorerOutput.total_outputs` property** — update to sum new fields.

#### 13.2.4 Current `P03PhaseOutputs` R5 Fields (Exact)

**File**: `k0/pipelines/p03/phase_outputs.py` lines 780-792:

```python
# =========================================================================
# R5 OUTPUTS (Dream Exploration)
# =========================================================================
r5_counterfactuals: List[CounterfactualScenario] = field(default_factory=list)  # REMOVE
r5_insights: List[Insight] = field(default_factory=list)                        # KEEP
r5_routine_optimizations: List[RoutineOptimization] = field(default_factory=list) # KEEP
r5_routine_candidates: List["RoutineCandidate"] = field(default_factory=list)   # KEEP
r5_prospective_memories: List[ProspectiveMemory] = field(default_factory=list)  # KEEP
r5_intent_signals: List["IntentSignal"] = field(default_factory=list)           # KEEP
r5_mcts_scenarios: List["MCTSScenario"] = field(default_factory=list)           # REMOVE
r5_skipped: bool = False                                                        # KEEP
r5_skip_reason: Optional[str] = None                                            # KEEP
```

**Also update `total_insights()` method** (line 859) — currently sums counterfactuals + insights + routine_optimizations + routine_candidates + prospective_memories + intent_signals. Must replace counterfactuals count with new algorithm counts.

**Also update `to_summary_dict()` method** (line 874) — R5 section currently reports insights, counterfactuals, prospective_memories, intent_signals. Must report new algorithm counts.

---

### 13.3 R6-R7 Write Pipeline (How R5 Outputs Reach the Database)

Understanding the complete write path is critical for attaching new algorithm outputs.

#### 13.3.1 R6 Staging

**File**: `k0/pipelines/p03/phases/r6_staging.py` (612 lines)

- `R6Staging._extract_phase_outputs()` passes the **entire** `P03PhaseOutputs` object to `R6Coordinator`.
- `R6Staging._populate_envelope()` routes `StagedWrite` objects to `envelope.staged` buckets by layer name.
- **No R5-specific code in R6Staging** — it passes everything generically to the coordinator.

#### 13.3.2 R6 Coordinator

**File**: `k0/modules/consolidation/staging/r6_coordinator.py` (590 lines)

- `R6Coordinator.execute()` runs 7 sequential steps, calling `TruthWriteAssembler` methods.
- Receives `P03PhaseOutputs` and iterates over all phases' outputs.
- **Change required**: Minor — add calls for new R5 output types if TruthWriteAssembler exposes new methods.

**Exact code showing how R6 extracts R5 outputs** (r6_coordinator.py lines 331-353):

```python
# === STEP 2: Assemble truth writes ===
# Issue 8.1.17: Include R5 outputs in truth write assembly
r5_insights = getattr(phase_outputs, "r5_insights", None) or []
r5_counterfactuals = getattr(phase_outputs, "r5_counterfactuals", None) or []  # REMOVE
r5_routine_optimizations = getattr(phase_outputs, "r5_routine_optimizations", None) or []
r5_routine_candidates = getattr(phase_outputs, "r5_routine_candidates", None) or []
r5_mcts_scenarios = getattr(phase_outputs, "r5_mcts_scenarios", None) or []    # REMOVE

truth_assembly = self.truth_assembler.assemble_all(
    clusters=getattr(phase_outputs, "r2_clusters", None),
    event_states=event_states,
    routines=getattr(phase_outputs, "r5_routines", None),
    social_relationships=getattr(phase_outputs, "r4_social_entities", None),
    intentions=getattr(phase_outputs, "r5_intentions", None),
    gaps=gaps,
    insights=r5_insights,
    counterfactuals=r5_counterfactuals,           # REMOVE
    routine_optimizations=r5_routine_optimizations,
    routine_candidates=r5_routine_candidates,
    mcts_scenarios=r5_mcts_scenarios,             # REMOVE
)
```

**New R5 field extractions to ADD** (same `getattr` pattern):

```python
r5_est_updates = getattr(phase_outputs, "r5_est_updates", None) or []
r5_asu_updates = getattr(phase_outputs, "r5_asu_updates", None) or []
r5_ewr_updates = getattr(phase_outputs, "r5_ewr_updates", None) or []
r5_sre_updates = getattr(phase_outputs, "r5_sre_updates", None) or []
r5_spr_actions = getattr(phase_outputs, "r5_spr_actions", None) or []
r5_mtp_promotions = getattr(phase_outputs, "r5_mtp_promotions", None) or []
r5_clv_repairs = getattr(phase_outputs, "r5_clv_repairs", None) or []
r5_ctd_resolutions = getattr(phase_outputs, "r5_ctd_resolutions", None) or []
r5_epc_composites = getattr(phase_outputs, "r5_epc_composites", None) or []
r5_spg_salience = getattr(phase_outputs, "r5_spg_salience", None) or []
r5_ntd_threads = getattr(phase_outputs, "r5_ntd_threads", None) or []
```

These get passed to `assemble_all()` which is updated with new keyword arguments (see Step 4).

#### 13.3.3 Truth Write Assembler

**File**: `k0/modules/consolidation/staging/truth_write_assembler.py` (2034 lines)

This is the **key translation layer**. It converts phase outputs into `StagedWrite` objects.

**Current R5-specific assembly methods** (with line numbers):

| Method | Line | Input Type | Layer | Status |
| --- | --- | --- | --- | --- |
| `assemble_insight_writes()` | 1358 | `Insight` | st_sem | KEEP |
| `assemble_counterfactual_writes()` | 1433 | `CounterfactualScenario` | st_prospective | REMOVE |
| `assemble_routine_optimization_writes()` | 1503 | `RoutineOptimization` | st_procedural | KEEP |
| `assemble_mcts_writes()` | 1568 | `MCTSScenario` | st_mcts | REMOVE |
| `assemble_intent_signal_writes()` | 1644 | `IntentSignal` | st_prospective | KEEP |
| `assemble_routine_candidate_writes()` | 1112 | `RoutineCandidate` | st_procedural | KEEP |

**Exact pattern** (from `assemble_insight_writes()` — use as template for all new methods):

```python
def assemble_insight_writes(
    self, insights: List[Insight],
) -> Dict[str, List[StagedWrite]]:
    writes: Dict[str, List[StagedWrite]] = {}
    for insight in insights:
        record_data = {
            "pattern_id": insight.pattern_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "pattern_type": "INSIGHT",
            "confidence_score": insight.confidence,
            "novelty_score": insight.novelty_score,
            "pmi_score": getattr(insight, "pmi_score", None),
            "category": insight.insight_type.value,
            "description": insight.description,
            "source_entity_ids": insight.supporting_entity_ids,
            "created_at": _now_iso(),
            "consolidation_cycle_id": self.consolidation_cycle_id,
        }
        write = StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id=insight.pattern_id,
            data=record_data,
            phase="R5",
            event_ids=insight.source_event_ids,
        )
        writes.setdefault(LAYER_ST_SEM, []).append(write)
    return writes
```

**Master method** `assemble_all()` (line 1850):

```python
def assemble_all(
    self,
    clusters: Optional[List] = None,
    event_states: Optional[List] = None,
    routines: Optional[List] = None,
    social_relationships: Optional[List] = None,
    intentions: Optional[List] = None,
    gaps: Optional[List] = None,
    insights: Optional[List] = None,
    counterfactuals: Optional[List] = None,           # REMOVE
    routine_optimizations: Optional[List] = None,
    intent_signals: Optional[List] = None,
    routine_candidates: Optional[List] = None,
    mcts_scenarios: Optional[List] = None,            # REMOVE
) -> Dict[str, List[StagedWrite]]:
    all_writes: Dict[str, List[StagedWrite]] = {}
    # Calls each assemble_* method and merges results by layer key
    # e.g.: _merge_writes(all_writes, self.assemble_insight_writes(insights))
    return all_writes
```

**New parameters to ADD** to `assemble_all()`:
```python
    est_updates: Optional[List[EpisodicStrengthUpdate]] = None,
    asu_updates: Optional[List[SchemaConfidenceUpdate]] = None,
    ewr_updates: Optional[List[EdgeWeightUpdate]] = None,
    sre_updates: Optional[List[SocialRecalibration]] = None,
    spr_actions: Optional[List[PredictionReaperAction]] = None,
    mtp_promotions: Optional[List[TierPromotion]] = None,
    clv_repairs: Optional[List[CrossLayerRepair]] = None,
    ctd_resolutions: Optional[List[ContradictionResolution]] = None,
    epc_composites: Optional[List[EpisodeComposite]] = None,
    spg_salience: Optional[List[SaliencePropagation]] = None,
    ntd_threads: Optional[List[NarrativeThread]] = None,
```

**Pattern for new assembly methods** (example: `assemble_est_writes()`):

```python
def assemble_est_writes(
    self, est_updates: List[EpisodicStrengthUpdate],
) -> Dict[str, List[StagedWrite]]:
    writes: Dict[str, List[StagedWrite]] = {}
    for update in est_updates:
        record_data = {
            "salience_score": update.new_salience,
            "observation_count": update.observation_count,
            "reinforcement_rate": update.reinforcement_rate,
            "last_reinforced_at": update.last_reinforced_at,
            "consolidation_cycle_id": self.consolidation_cycle_id,
        }
        write = StagedWrite.update(
            layer=LAYER_ST_EPI,
            record_id=update.episode_id,
            data=record_data,
            phase="R5",
            expected_version=update.current_version,
            event_ids=[],
        )
        writes.setdefault(LAYER_ST_EPI, []).append(write)
    return writes
```

**Key difference**: Existing insights use `StagedWrite.insert()`. New EST/ASU/EWR/SRE use `StagedWrite.update()` because they modify existing records. New EPC/NTD use `StagedWrite.insert()` for composite/thread records.

#### 13.3.4 Staged Writes Container

**File**: `k0/pipelines/p03/staged_writes.py` (629 lines)

`P03StagedWrites` has 12 layer buckets:

```
st_epi_writes            # Episodic layer
st_sem_writes            # Semantic layer
st_procedural_writes     # Procedural layer
st_social_writes         # Social layer
st_prospective_writes    # Prospective layer
st_kg_dom_writes         # Knowledge graph domain
st_kg_edges_writes       # Knowledge graph edges
st_vec_writes            # Vector embeddings
st_hipp_events_updates   # Hippocampal event updates
st_learning_queue_writes # Learning queue
st_mcts_writes           # MCTS scenarios (TO EVALUATE — may repurpose or remove)
outbox_events            # Outbound event bus events
```

`StagedWrite` dataclass fields:

```python
@dataclass
class StagedWrite:
    write_id: str                                    # ULID
    layer: str                                       # Target table (st_epi, st_sem, etc.)
    operation: WriteOperation                        # INSERT, UPDATE, ARCHIVE, TOMBSTONE
    record_id: str                                   # Primary key of target record
    record_data: Dict[str, Any]                      # Full/partial record data
    idempotency_key: str                             # Deterministic key for retry safety
    source_phase: str                                # "R1", "R2", ..., "R5", "R6"
    source_event_ids: List[str] = field(default_factory=list)
    expected_version: Optional[int] = None           # For optimistic locking on UPDATE
    created_at_ms: int = field(default_factory=_now_ms)
    observation_context: Optional[ObservationContext] = None  # 35+ field holistic context
```

**Factory methods used by assemblers**: `StagedWrite.insert(layer, record_id, data, phase, event_ids)`, `StagedWrite.update(layer, record_id, data, phase, expected_version, event_ids)`, `StagedWrite.archive(layer, record_id, phase, reason)`, `StagedWrite.tombstone(layer, record_id, phase)`.

**Idempotency key format**: `"{phase}:{layer}:{record_id}"` for INSERT, `"{phase}:{layer}:{record_id}:v{version}"` for UPDATE.

**Routing via `P03StagedWrites.add_write(write)`**: Uses `write.layer` to dispatch to the correct bucket (e.g., `write.layer == "st_epi"` → `self.st_epi_writes.append(write)`).

#### 13.3.5 R7 Atomic Commit

**File**: `k0/pipelines/p03/phases/r7_truth_writer.py` (1221 lines)

**Commit chain**: `TransactionCoordinator` → `DecisionRouter` → per-layer `LayerWriter` → SQL execution → all within one DB transaction.

**Layer writers** (9 total):

- `EpisodicLayerWriter` — st_epi (INSERT, UPDATE, UPSERT)
- `SemanticLayerWriter` — st_sem (INSERT, UPDATE, UPSERT)
- `ProceduralLayerWriter` — st_procedural (INSERT, UPDATE)
- `SocialLayerWriter` — st_social (INSERT, UPDATE, UPSERT)
- `ProspectiveLayerWriter` — st_prospective (INSERT, UPDATE)
- `MCTSLayerWriter` — st_mcts (INSERT) — TO EVALUATE for removal
- `KGLayerWriter` — st_kg_dom + st_kg_edges (INSERT, UPDATE, UPSERT)
- `VectorLayerWriter` — st_vec (INSERT, UPDATE)
- (st_hipp_events, st_learning_queue handled by separate writers)

**Dependency order** (to satisfy FK constraints):

```
st_vec → st_kg_dom → st_kg_edges → st_epi → st_sem → st_procedural →
st_social → st_prospective → st_mcts → st_learning_queue → st_hipp_events
```

**Key observation**: Layer writers are generic — they consume `StagedWrite` objects regardless of which phase produced them. Adding new R5 output types requires NO changes to R7 as long as `StagedWrite` objects target existing layers.

---

### 13.4 Files to Deprecate

| File | Lines | Class/Function | Reason |
|---|---|---|---|
| `k0/modules/consolidation/algorithms/cpn.py` | 1106 | `CausalPerturbationNetwork` | LLMs are sound enough for what-if — CPN adds no value for personal memory |
| `k0/modules/consolidation/algorithms/mcts.py` | 1113 | `TemporalProjectionMCTS` | Forward simulation adds no value — personal memory is not a game tree |
| `k0/modules/consolidation/algorithms/mcts_shadow.py` | 918 | Shadow validation harness | MCTS-specific shadow mode infrastructure |
| `k0/modules/consolidation/algorithms/mcts_persistence.py` | 447 | `MCTSDecisionPersistence` | MCTS-specific persistence — no longer needed |
| `k0/modules/consolidation/dream/compute_budget.py` | 276 | `ComputeBudget` | MCTS-centric rollout budget — replace with simple per-algorithm timeout |

**Total deprecated**: ~3,860 lines across 5 files.

#### 13.4.1 Classes and Fields to Remove from Existing Files

| File | Remove | Lines Affected |
| --- | --- | --- |
| `r5_dream_explorer.py` | `R5PhaseOutputs.counterfactuals`, `.mcts_scenarios`, `.mcts_decisions_count` fields. Remove CPN/MCTS imports. Remove `_run_cpn()`, `_run_mcts()` task entries in `_run_parallel_algorithms()`. | ~60 lines |
| `dream_explorer.py` | `_run_cpn()` method (~80 lines), `_run_mcts()` method (~100 lines). Remove from `_run_parallel_algorithms()` tasks dict. Remove `ComputeBudget` usage. Remove `from .compute_budget import ComputeBudget` import. | ~200 lines |
| `dream/config.py` | 7 fields: `cpn_perturbation_std`, `cpn_counterfactual_types`, `cpn_emotional_threshold`, `mcts_exploration_constant`, `mcts_max_rollout_depth`, `mcts_discount_factor`, `mcts_max_total_rollouts`. Also remove from `from_r5_config()` mapping. | ~20 lines |
| `dream/models.py` | `CounterfactualScenario` class (~40 lines), `ScenarioType` enum (~6 lines), `DreamExplorerOutput.counterfactuals` field, `.mcts_scenarios` field, `.mcts_decisions_evaluated` field. | ~50 lines |
| `r5_config.py` | 8 fields: `mcts_rollouts_override`, `mcts_exploration_constant`, `mcts_max_depth`, `mcts_early_termination_threshold`, `max_counterfactuals_per_event`, `cpn_perturbation_std`, `cpn_counterfactual_types`, `cpn_emotional_threshold`. Also `effective_rollouts` property and `ROLLOUTS_PER_MODE` dict. | ~30 lines |
| `phase_outputs.py` | `r5_counterfactuals` field, `r5_mcts_scenarios` field. Remove `CounterfactualScenario` import. Update `total_insights()` (line 859) and `to_summary_dict()` (line 874). | ~8 lines |
| `truth_write_assembler.py` | `assemble_counterfactual_writes()` method (line 1433, ~70 lines), `assemble_mcts_writes()` method (line 1568, ~75 lines). Remove from `assemble_all()` call chain and parameter list. | ~150 lines |
| `staged_writes.py` | `st_mcts_writes` bucket from `P03StagedWrites` (if full deprecation). Remove from `add_write()` routing dict and `get_all_writes_ordered()`. | ~10 lines |
| `r7_truth_writer.py` | `MCTSLayerWriter` class (if full deprecation). Remove from `TransactionCoordinator` writer registry. | ~50 lines |

**Total lines removed from existing files**: ~578 lines (in addition to 3,860 lines from deleted files)

#### 13.4.2 Import Chain Cleanup

When removing CPN/MCTS, these imports must be cleaned up across the codebase:

```python
# Remove from dream/__init__.py:
from .algorithms.cpn import CausalPerturbationNetwork
from .algorithms.mcts import TemporalProjectionMCTS
from .compute_budget import ComputeBudget

# Remove from dream/dream_explorer.py imports:
from ..algorithms.cpn import CausalPerturbationNetwork
from ..algorithms.mcts import TemporalProjectionMCTS
from ..algorithms.mcts_shadow import MCTSShadowValidator
from ..algorithms.mcts_persistence import MCTSDecisionPersistence
from .compute_budget import ComputeBudget
from .models import CounterfactualScenario, ScenarioType

# Remove from phase_outputs.py:
from k0.modules.consolidation.dream.models import CounterfactualScenario

# Remove from truth_write_assembler.py:
from k0.modules.consolidation.dream.models import CounterfactualScenario, MCTSScenario
```

**Verification**: After cleanup, run `grep -rn "cpn\|mcts\|counterfactual\|ComputeBudget\|ScenarioType" --include="*.py" k0/` to confirm no dangling references.

---

### 13.5 New Files to Create

#### 13.5.1 Shared Infrastructure

| File | Purpose | Lines (est.) |
|---|---|---|
| `k0/modules/consolidation/algorithms/observation_evidence_loader.py` | Loads batched st_observations evidence per entity. Shared by all 14 algorithms. SQL queries with tenant/space filtering, grouping by target. | ~300 |
| `k0/modules/consolidation/algorithms/observation_evidence.py` | `ObservationEvidence` dataclass — structured evidence container (observation_count, reinforcement_count, first_seen, last_seen, sentiment, distribution, tier). | ~150 |

#### 13.5.2 New Algorithm Files (14 algorithms, 13 new files)

| File | Algorithm | Section | Primary Layer Targets |
|---|---|---|---|
| `k0/modules/consolidation/algorithms/est.py` | EST — Episodic Strength Tracker | 4.1 | st_epi (salience UPDATE) |
| `k0/modules/consolidation/algorithms/asu.py` | ASU — Adaptive Schema Updater | 4.2 | st_sem (confidence UPDATE) |
| `k0/modules/consolidation/algorithms/ewr.py` | EWR — Evidence-Weighted Re-ranker | 4.3 | st_kg_edges (weight UPDATE) |
| `k0/modules/consolidation/algorithms/sre.py` | SRE — Social Recalibration Engine | 4.4 | st_social (sentiment UPSERT) |
| `k0/modules/consolidation/algorithms/spr.py` | SPR — Stale Prediction Reaper | 4.6 | st_prospective (status UPDATE, DELETE) |
| `k0/modules/consolidation/algorithms/mtp.py` | MTP — Memory Tier Promoter | 4.9 | st_epi, st_sem, st_kg_dom (tier UPDATE) |
| `k0/modules/consolidation/algorithms/clv.py` | CLV — Cross-Layer Validator | 4.10 | st_kg_edges, st_social (orphan cleanup) |
| `k0/modules/consolidation/algorithms/ctd.py` | CTD — Contradiction Detector | 4.11 | st_social, st_sem (contradiction resolution) |
| `k0/modules/consolidation/algorithms/epc.py` | EPC — Episode Compressor | 4.12 | st_epi (composite INSERT, source UPDATE) |
| `k0/modules/consolidation/algorithms/spg.py` | SPG — Salience Propagation on Graph | 4.13 | st_kg_dom (propagated_salience UPDATE) |
| `k0/modules/consolidation/algorithms/ntd.py` | NTD — Narrative Thread Detector | 4.14 | st_sem (NARRATIVE_THREAD INSERT) |

**Note**: SPC-UQ (4.5) and BGT-SM (4.7) already exist as `spc_uq.py` (1253 lines) and `bgt_sm.py` (1208 lines). They will be refactored in-place to become observation-driven.

**Note**: TDL-HCO (4.8) already exists as `tdl_hco.py` (1025 lines). It will be refactored to use observation evidence for TD target computation.

#### 13.5.3 New Orchestrator

| File | Purpose |
|---|---|
| `k0/modules/consolidation/dream/r5_orchestrator.py` | Replaces `DreamExplorer.explore()` with new 5-phase execution order (see Section 13.7). Removes CPN/MCTS dispatch. Adds ObservationEvidence loading as Phase 0. |

---

### 13.6 Algorithms Directory Inventory

**Directory**: `k0/modules/consolidation/algorithms/`

**Current state**: 48 `.py` files + 2 subdirectories (`edge_enrichers/` with 9 files, `text_generators/` with 8 files).

| File | Lines | Status |
|---|---|---|
| `bgt_sm.py` | 1208 | KEEP — refactor to observation-driven |
| `cpn.py` | 1106 | DEPRECATE |
| `mcts.py` | 1113 | DEPRECATE |
| `mcts_shadow.py` | 918 | DEPRECATE |
| `mcts_persistence.py` | 447 | DEPRECATE |
| `spc_uq.py` | 1253 | KEEP — refactor (drop uncertainty network, add observation evidence) |
| `tdl_hco.py` | 1025 | KEEP — refactor (observation evidence for TD targets) |
| `routine_detector.py` | 710 | KEEP unchanged |
| `intent_signal_detector.py` | ~350 | KEEP unchanged |
| `observation_context.py` | 365 | KEEP (ObservationContext with 35+ fields — used by all algorithms) |
| `observation_recorder.py` | ~280 | KEEP (ObservationRecorder — records to st_observations) |

**Subdirectories** (KEEP unchanged — owned by R4):

- `edge_enrichers/` — 9 files for R4 edge enrichment (not R5's concern)
- `text_generators/` — 8 files for narrative generation (not R5's concern)

---

### 13.7 Attaching Points (8 Steps)

This is the exact wiring sequence for connecting new algorithms to the existing pipeline.

#### Step 1: P03PhaseOutputs — New R5 Fields

**File**: `k0/pipelines/p03/phase_outputs.py`

Add new fields to `P03PhaseOutputs` for each new algorithm's output:

```
r5_est_updates: List[EpisodicStrengthUpdate]       # EST salience updates
r5_asu_updates: List[SchemaConfidenceUpdate]        # ASU confidence updates
r5_ewr_updates: List[EdgeWeightUpdate]              # EWR edge weight updates
r5_sre_updates: List[SocialRecalibration]           # SRE sentiment updates
r5_spr_actions: List[PredictionReaperAction]        # SPR stale prediction actions
r5_mtp_promotions: List[TierPromotion]              # MTP tier promotions
r5_clv_repairs: List[CrossLayerRepair]              # CLV orphan repairs
r5_ctd_resolutions: List[ContradictionResolution]   # CTD contradiction fixes
r5_epc_composites: List[EpisodeComposite]           # EPC compressed episodes
r5_spg_salience: List[SaliencePropagation]          # SPG propagated salience
r5_ntd_threads: List[NarrativeThread]               # NTD detected threads
```

Remove: `r5_counterfactuals`, `r5_mcts_scenarios`.

#### Step 2: R5PhaseOutputs — Replace Container

**File**: `k0/pipelines/p03/phases/r5_dream_explorer.py`

Replace current `R5PhaseOutputs` dataclass. Remove `counterfactuals`, `mcts_scenarios`, `mcts_decisions_count`. Add fields matching new algorithm outputs from Step 1.

**Complete new R5PhaseOutputs definition**:

```python
@dataclass
class R5PhaseOutputs:
    """Container for all R5 algorithm outputs."""

    # --- Existing algorithms (KEEP) ---
    insights: List[Insight] = field(default_factory=list)                     # BGT-SM
    routine_optimizations: List[RoutineOptimization] = field(default_factory=list)  # TDL-HCO
    routine_candidates: List["RoutineCandidate"] = field(default_factory=list)      # RoutineDetector
    prospective_memories: List[ProspectiveMemory] = field(default_factory=list)     # SPC-UQ
    intent_signals: List["IntentSignal"] = field(default_factory=list)              # IntentSignalDetector

    # --- New observation-driven algorithms ---
    est_updates: List[EpisodicStrengthUpdate] = field(default_factory=list)         # 4.1 EST
    asu_updates: List[SchemaConfidenceUpdate] = field(default_factory=list)          # 4.2 ASU
    ewr_updates: List[EdgeWeightUpdate] = field(default_factory=list)               # 4.3 EWR
    sre_updates: List[SocialRecalibration] = field(default_factory=list)            # 4.4 SRE
    spr_actions: List[PredictionReaperAction] = field(default_factory=list)         # 4.6 SPR
    mtp_promotions: List[TierPromotion] = field(default_factory=list)               # 4.9 MTP
    clv_repairs: List[CrossLayerRepair] = field(default_factory=list)               # 4.10 CLV
    ctd_resolutions: List[ContradictionResolution] = field(default_factory=list)    # 4.11 CTD
    epc_composites: List[EpisodeComposite] = field(default_factory=list)            # 4.12 EPC
    spg_salience: List[SaliencePropagation] = field(default_factory=list)           # 4.13 SPG
    ntd_threads: List[NarrativeThread] = field(default_factory=list)                # 4.14 NTD

    # --- Metadata ---
    compute_seconds_saved: float = 0.0
    algorithms_executed: List[str] = field(default_factory=list)
    algorithms_failed: List[str] = field(default_factory=list)

    # --- REMOVED (CPN/MCTS) ---
    # counterfactuals: List[CounterfactualScenario]  <-- DELETED
    # mcts_scenarios: List["MCTSScenario"]           <-- DELETED
    # mcts_decisions_count: int = 0                  <-- DELETED

    @property
    def total_outputs(self) -> int:
        return (
            len(self.insights) + len(self.routine_optimizations)
            + len(self.routine_candidates) + len(self.prospective_memories)
            + len(self.intent_signals)
            + len(self.est_updates) + len(self.asu_updates) + len(self.ewr_updates)
            + len(self.sre_updates) + len(self.spr_actions) + len(self.mtp_promotions)
            + len(self.clv_repairs) + len(self.ctd_resolutions) + len(self.epc_composites)
            + len(self.spg_salience) + len(self.ntd_threads)
        )
```

#### Step 3: `_execute_algorithms()` — Rewrite Core Orchestration

**File**: `k0/pipelines/p03/phases/r5_dream_explorer.py` (or delegate to new `r5_orchestrator.py`)

Replace current `_execute_algorithms()` flow:

**Current flow**:

1. Build `DreamExplorerInput` (merge accumulated + current batch)
2. `explorer.explore(input_data)` — runs CPN, BGT-SM, SPC-UQ, MCTS, RoutineDetector in parallel, then TDL-HCO

**New flow** (full pseudocode):

```python
async def _execute_algorithms(
    self,
    ctx: "P03RunnerContext",
    envelope: "P03BatchEnvelope",
) -> R5PhaseOutputs:
    tenant_id = envelope.context.tenant_id
    space_id = envelope.context.space_id
    outputs = R5PhaseOutputs()

    # --- Phase 0: Evidence Loading (sequential, required) ---
    observation_evidence = await self._load_observation_evidence(ctx, tenant_id, space_id)

    # --- Load accumulated data (same as current, see 13.1.3) ---
    accumulated_entities = await self._load_accumulated_entities(ctx, tenant_id, space_id)
    accumulated_edges = await self._load_accumulated_edges(ctx, tenant_id, space_id)
    accumulated_episodes = await self._load_accumulated_episodes(ctx, tenant_id, space_id)
    accumulated_schemas = await self._load_accumulated_schemas(ctx, tenant_id, space_id)
    accumulated_routines = await self._load_accumulated_routines(ctx, tenant_id, space_id)

    # --- Merge current batch with accumulated (current takes precedence) ---
    merged_entities = self._merge_entities(
        list(envelope.phases.r4_new_entities), accumulated_entities
    )
    merged_edges = self._merge_edges(
        list(envelope.phases.r4_new_edges), accumulated_edges
    )
    merged_episodes = self._merge_episodes(
        list(envelope.phases.r2_clusters), accumulated_episodes
    )

    # --- Build orchestrator input ---
    input_data = DreamExplorerInput(
        cycle_id=envelope.context.cycle_id,
        tenant_id=tenant_id,
        space_id=space_id,
        recent_episodes=merged_episodes,
        kg_entities=merged_entities,
        kg_edges=merged_edges,
        event_states=list(envelope.events),
        schemas=accumulated_schemas,
        accumulated_routines=accumulated_routines,
        observation_evidence=observation_evidence,  # NEW
    )

    config = DreamConfig.from_r5_config(self.config)

    # --- Phase 1: Independent Strengtheners (parallel via asyncio.gather) ---
    phase1_tasks = {
        "EST": self._run_with_error_isolation(
            "EST", est_algo.execute, input_data, observation_evidence, config
        ),
        "ASU": self._run_with_error_isolation(
            "ASU", asu_algo.execute, input_data, observation_evidence, config
        ),
        "EWR": self._run_with_error_isolation(
            "EWR", ewr_algo.execute, input_data, observation_evidence, config
        ),
        "SRE": self._run_with_error_isolation(
            "SRE", sre_algo.execute, input_data, observation_evidence, config
        ),
        "SPC-UQ": self._run_with_error_isolation(
            "SPC-UQ", spc_uq_algo.execute, input_data, observation_evidence, config
        ),
        "SPR": self._run_with_error_isolation(
            "SPR", spr_algo.execute, input_data, observation_evidence, config
        ),
        "MTP": self._run_with_error_isolation(
            "MTP", mtp_algo.execute, input_data, observation_evidence, config
        ),
    }
    phase1_results = dict(zip(
        phase1_tasks.keys(),
        await asyncio.gather(*phase1_tasks.values(), return_exceptions=True),
    ))
    # Map results to outputs (with None checks from error isolation)
    outputs.est_updates = phase1_results.get("EST") or []
    outputs.asu_updates = phase1_results.get("ASU") or []
    outputs.ewr_updates = phase1_results.get("EWR") or []
    outputs.sre_updates = phase1_results.get("SRE") or []
    outputs.prospective_memories = phase1_results.get("SPC-UQ") or []
    outputs.spr_actions = phase1_results.get("SPR") or []
    outputs.mtp_promotions = phase1_results.get("MTP") or []

    # --- Phase 2: Graph-Dependent (parallel, after Phase 1) ---
    phase2_tasks = {
        "BGT-SM": self._run_with_error_isolation(
            "BGT-SM", bgt_sm_algo.execute, input_data, observation_evidence, config
        ),
        "SPG": self._run_with_error_isolation(
            "SPG", spg_algo.execute, input_data, observation_evidence, config
        ),
        "CLV": self._run_with_error_isolation(
            "CLV", clv_algo.execute, input_data, observation_evidence, config
        ),
        "CTD": self._run_with_error_isolation(
            "CTD", ctd_algo.execute, input_data, observation_evidence, config
        ),
    }
    phase2_results = dict(zip(
        phase2_tasks.keys(),
        await asyncio.gather(*phase2_tasks.values(), return_exceptions=True),
    ))
    outputs.insights = phase2_results.get("BGT-SM") or []
    outputs.spg_salience = phase2_results.get("SPG") or []
    outputs.clv_repairs = phase2_results.get("CLV") or []
    outputs.ctd_resolutions = phase2_results.get("CTD") or []

    # --- Phase 3: Sequential (depend on Phase 1+2 outputs) ---
    routine_detector = RoutineDetector(config)
    outputs.routine_candidates = await self._run_with_error_isolation(
        "RoutineDetector", routine_detector.detect, input_data
    ) or []
    outputs.routine_optimizations = await self._run_with_error_isolation(
        "TDL-HCO", tdl_hco_algo.execute, input_data, observation_evidence,
        config, outputs.routine_candidates,
    ) or []
    outputs.epc_composites = await self._run_with_error_isolation(
        "EPC", epc_algo.execute, input_data, observation_evidence,
        config, outputs.est_updates,  # needs EST salience from Phase 1
    ) or []
    outputs.ntd_threads = await self._run_with_error_isolation(
        "NTD", ntd_algo.execute, input_data, observation_evidence,
        config, outputs.insights,  # needs BGT-SM insights from Phase 2
    ) or []

    # --- Phase 4: Quality Filters and Intent Signals ---
    outputs = self._apply_quality_filters(outputs, config)
    outputs.intent_signals = await self._run_with_error_isolation(
        "IntentSignal", intent_signal_detector.detect_all, input_data
    ) or []

    # Track which algorithms executed/failed
    outputs.algorithms_executed = [
        name for name, result in {**phase1_results, **phase2_results}.items()
        if not isinstance(result, Exception)
    ]
    outputs.algorithms_failed = [
        name for name, result in {**phase1_results, **phase2_results}.items()
        if isinstance(result, Exception)
    ]

    return outputs
```

**Error isolation pattern** (`_run_with_error_isolation`):

```python
async def _run_with_error_isolation(
    self, algorithm_name: str, func: Callable, *args, **kwargs,
) -> Any:
    """Run a single algorithm with full error isolation.

    If the algorithm raises, log warning and return None.
    The caller treats None as empty list (graceful degradation).
    """
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        self._logger.warning(
            "R5 algorithm %s failed, skipping",
            algorithm_name,
            extra={
                "algorithm": algorithm_name,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        self._metrics.emit_counter(
            "r5.algorithm.failure", 1,
            tags={"algorithm": algorithm_name},
        )
        return None
```

**New data loader required**:

```python
observation_evidence = await self._load_observation_evidence(
    ctx=ctx,
    tenant_id=envelope.context.tenant_id,
    space_id=envelope.context.space_id,
)
```

#### Step 4: TruthWriteAssembler — 14 New Assembly Methods

**File**: `k0/modules/consolidation/truth_writer/truth_write_assembler.py`

Add new assembly methods. Each converts an algorithm's output dataclass into `StagedWrite` objects targeting the correct layer:

| Method | Input Type | Layer | Operation |
|---|---|---|---|
| `assemble_est_writes()` | `EpisodicStrengthUpdate` | st_epi | UPDATE (salience) |
| `assemble_asu_writes()` | `SchemaConfidenceUpdate` | st_sem | UPDATE (confidence) |
| `assemble_ewr_writes()` | `EdgeWeightUpdate` | st_kg_edges | UPDATE (weight) |
| `assemble_sre_writes()` | `SocialRecalibration` | st_social | UPSERT (sentiment, trust) |
| `assemble_spc_uq_writes()` | `ProspectiveMemory` | st_prospective | INSERT (predictions) |
| `assemble_spr_writes()` | `PredictionReaperAction` | st_prospective | UPDATE/DELETE (status) |
| `assemble_bgt_sm_writes()` | `Insight` | st_sem | INSERT (insights) |
| `assemble_tdl_hco_writes()` | `RoutineOptimization` | st_procedural | UPDATE (optimizations) |
| `assemble_mtp_writes()` | `TierPromotion` | st_epi, st_sem, st_kg_dom | UPDATE (memory_tier) |
| `assemble_clv_writes()` | `CrossLayerRepair` | st_kg_edges, st_social | UPDATE/DELETE (orphans) |
| `assemble_ctd_writes()` | `ContradictionResolution` | st_social, st_sem | UPDATE (resolved values) |
| `assemble_epc_writes()` | `EpisodeComposite` | st_epi | INSERT (composite), UPDATE (sources) |
| `assemble_spg_writes()` | `SaliencePropagation` | st_kg_dom | UPDATE (propagated_salience) |
| `assemble_ntd_writes()` | `NarrativeThread` | st_sem | INSERT (NARRATIVE_THREAD) |

Remove: `assemble_counterfactual_writes()`, `assemble_mcts_writes()`.

Update `assemble_all()` to call new methods.

#### Step 5: R6Coordinator — Minor Update

**File**: `k0/modules/consolidation/staging/r6_coordinator.py`

Minimal change. `R6Coordinator.execute()` already passes the entire `P03PhaseOutputs` to `TruthWriteAssembler`. The changes needed:

**Remove** from Step 2 extraction block (lines 331-340):
```python
# DELETE these lines:
r5_counterfactuals = getattr(phase_outputs, "r5_counterfactuals", None) or []
r5_mcts_scenarios = getattr(phase_outputs, "r5_mcts_scenarios", None) or []
```

**Add** to Step 2 extraction block (after existing lines):
```python
# ADD these lines:
r5_est_updates = getattr(phase_outputs, "r5_est_updates", None) or []
r5_asu_updates = getattr(phase_outputs, "r5_asu_updates", None) or []
r5_ewr_updates = getattr(phase_outputs, "r5_ewr_updates", None) or []
r5_sre_updates = getattr(phase_outputs, "r5_sre_updates", None) or []
r5_spr_actions = getattr(phase_outputs, "r5_spr_actions", None) or []
r5_mtp_promotions = getattr(phase_outputs, "r5_mtp_promotions", None) or []
r5_clv_repairs = getattr(phase_outputs, "r5_clv_repairs", None) or []
r5_ctd_resolutions = getattr(phase_outputs, "r5_ctd_resolutions", None) or []
r5_epc_composites = getattr(phase_outputs, "r5_epc_composites", None) or []
r5_spg_salience = getattr(phase_outputs, "r5_spg_salience", None) or []
r5_ntd_threads = getattr(phase_outputs, "r5_ntd_threads", None) or []
```

**Update** `assemble_all()` call (remove counterfactuals/mcts_scenarios, add new params):
```python
truth_assembly = self.truth_assembler.assemble_all(
    clusters=getattr(phase_outputs, "r2_clusters", None),
    event_states=event_states,
    routines=getattr(phase_outputs, "r5_routines", None),
    social_relationships=getattr(phase_outputs, "r4_social_entities", None),
    intentions=getattr(phase_outputs, "r5_intentions", None),
    gaps=gaps,
    insights=r5_insights,
    # counterfactuals=r5_counterfactuals,       # REMOVED
    routine_optimizations=r5_routine_optimizations,
    routine_candidates=r5_routine_candidates,
    # mcts_scenarios=r5_mcts_scenarios,         # REMOVED
    est_updates=r5_est_updates,                  # NEW
    asu_updates=r5_asu_updates,                  # NEW
    ewr_updates=r5_ewr_updates,                  # NEW
    sre_updates=r5_sre_updates,                  # NEW
    spr_actions=r5_spr_actions,                  # NEW
    mtp_promotions=r5_mtp_promotions,            # NEW
    clv_repairs=r5_clv_repairs,                  # NEW
    ctd_resolutions=r5_ctd_resolutions,          # NEW
    epc_composites=r5_epc_composites,            # NEW
    spg_salience=r5_spg_salience,                # NEW
    ntd_threads=r5_ntd_threads,                  # NEW
)
```

If R6 has explicit per-phase step calls, add calls for new R5 output types.

#### Step 6: Layer Writers — No Changes Expected

R7 layer writers (`EpisodicLayerWriter`, `SemanticLayerWriter`, `KGLayerWriter`, etc.) are generic — they process `StagedWrite` objects by operation type (INSERT/UPDATE/UPSERT/DELETE). Since all new algorithms target existing layers via standard operations, **no R7 changes are needed** as long as `StagedWrite.record_data` matches the table schema.

**Exception**: If `st_mcts` table is fully deprecated, remove `MCTSLayerWriter` and the `st_mcts_writes` bucket.

#### Step 7: P03StagedWrites — Minor Update

**File**: `k0/pipelines/p03/staged_writes.py`

Evaluate whether `st_mcts_writes` bucket should be removed. No new buckets needed — all new algorithms target existing layer buckets (st_epi_writes, st_sem_writes, st_kg_edges_writes, etc.).

#### Step 8: Database Migrations

New migrations for schema additions required by new algorithms:

| Migration | Table | Changes |
| --- | --- | --- |
| `0070_add_memory_tier.sql` | st_epi, st_sem, st_kg_dom | Add `memory_tier` column (TRANSIENT/ACTIVE/STABLE/CORE), `tier_promoted_at` timestamp |
| `0071_add_propagated_salience.sql` | st_kg_dom | Add `propagated_salience` FLOAT column, index |
| `0072_add_composite_episode.sql` | st_epi | Add `is_composite` BOOLEAN, `composite_source_ids` JSONB, `frequency_per_month` FLOAT |
| `0073_add_narrative_thread.sql` | st_sem | Add support for `pattern_type = 'NARRATIVE_THREAD'`, `thread_entities` JSONB |
| `0074_drop_st_mcts.sql` | st_mcts | Drop table and related indexes (if full deprecation confirmed) |

**Full DDL for each migration**:

**0070_add_memory_tier.sql**:
```sql
-- Migration 0070: Add memory_tier to support MTP (Memory Tier Promoter)
-- Algorithms: MTP (4.9)
-- Rollback: ALTER TABLE st_epi DROP COLUMN IF EXISTS memory_tier, DROP COLUMN IF EXISTS tier_promoted_at;
--           (same for st_sem, st_kg_dom)

ALTER TABLE st_epi
    ADD COLUMN IF NOT EXISTS memory_tier VARCHAR(16) NOT NULL DEFAULT 'TRANSIENT'
        CHECK (memory_tier IN ('TRANSIENT', 'ACTIVE', 'STABLE', 'CORE')),
    ADD COLUMN IF NOT EXISTS tier_promoted_at TIMESTAMPTZ;

ALTER TABLE st_sem
    ADD COLUMN IF NOT EXISTS memory_tier VARCHAR(16) NOT NULL DEFAULT 'TRANSIENT'
        CHECK (memory_tier IN ('TRANSIENT', 'ACTIVE', 'STABLE', 'CORE')),
    ADD COLUMN IF NOT EXISTS tier_promoted_at TIMESTAMPTZ;

ALTER TABLE st_kg_dom
    ADD COLUMN IF NOT EXISTS memory_tier VARCHAR(16) NOT NULL DEFAULT 'TRANSIENT'
        CHECK (memory_tier IN ('TRANSIENT', 'ACTIVE', 'STABLE', 'CORE')),
    ADD COLUMN IF NOT EXISTS tier_promoted_at TIMESTAMPTZ;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_epi_memory_tier
    ON st_epi (memory_tier, tenant_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sem_memory_tier
    ON st_sem (memory_tier, tenant_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kg_dom_memory_tier
    ON st_kg_dom (memory_tier, tenant_id);
```

**0071_add_propagated_salience.sql**:
```sql
-- Migration 0071: Add propagated_salience to support SPG (Salience Propagation on Graph)
-- Algorithm: SPG (4.13)
-- Rollback: ALTER TABLE st_kg_dom DROP COLUMN IF EXISTS propagated_salience;

ALTER TABLE st_kg_dom
    ADD COLUMN IF NOT EXISTS propagated_salience FLOAT DEFAULT 0.0;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kg_dom_propagated_salience
    ON st_kg_dom (propagated_salience DESC)
    WHERE propagated_salience > 0.0;
```

**0072_add_composite_episode.sql**:
```sql
-- Migration 0072: Add composite episode fields for EPC (Episode Compressor)
-- Algorithm: EPC (4.12)
-- Rollback: ALTER TABLE st_epi DROP COLUMN IF EXISTS is_composite,
--           DROP COLUMN IF EXISTS composite_source_ids, DROP COLUMN IF EXISTS frequency_per_month;

ALTER TABLE st_epi
    ADD COLUMN IF NOT EXISTS is_composite BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS composite_source_ids JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS frequency_per_month FLOAT;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_epi_composite
    ON st_epi (is_composite)
    WHERE is_composite = TRUE;
```

**0073_add_narrative_thread.sql**:
```sql
-- Migration 0073: Add narrative thread support for NTD (Narrative Thread Detector)
-- Algorithm: NTD (4.14)
-- st_sem already supports pattern_type; this adds thread_entities JSONB for
-- NARRATIVE_THREAD records to store the ordered entity chain.
-- Rollback: ALTER TABLE st_sem DROP COLUMN IF EXISTS thread_entities;

ALTER TABLE st_sem
    ADD COLUMN IF NOT EXISTS thread_entities JSONB DEFAULT '[]'::jsonb;

-- Partial index for narrative thread lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sem_narrative_thread
    ON st_sem (tenant_id, created_at DESC)
    WHERE pattern_type = 'NARRATIVE_THREAD';
```

**0074_drop_st_mcts.sql** (conditional — only if full deprecation confirmed):
```sql
-- Migration 0074: Drop MCTS table (CPN/MCTS deprecation)
-- Prerequisite: Confirm no active consumers of st_mcts data
-- Rollback: Recreate table from backup DDL in docs/
-- WARNING: Data loss migration — back up st_mcts before applying

DROP TABLE IF EXISTS st_mcts CASCADE;
-- Also remove from st_observations CHECK constraint if st_mcts was included:
-- ALTER TABLE st_observations DROP CONSTRAINT IF EXISTS chk_obs_layer;
-- ALTER TABLE st_observations ADD CONSTRAINT chk_obs_layer
--     CHECK (layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective'));
```

**Migration ordering rule**: 0070-0073 are ADD COLUMN (safe, non-destructive, rollback-friendly). 0074 is DROP TABLE (destructive — requires explicit confirmation and data backup).

---

### 13.8 Execution Order (New 5-Phase Pipeline)

The new R5 orchestration replaces the current 4-phase `DreamExplorer.explore()` with a 5-phase pipeline:

#### Phase 0: Evidence Loading (Sequential, Required)

```
ObservationEvidenceLoader.load() → ObservationEvidence
```

Must complete before any algorithm runs. Queries st_observations once, structures evidence by target entity/layer.

#### Phase 1: Independent Strengtheners (Parallel)

These algorithms read observation evidence and produce layer-specific updates. No inter-algorithm dependencies.

```
┌─ EST (st_epi salience)
├─ ASU (st_sem confidence)
├─ EWR (st_kg_edges weight)
├─ SRE (st_social sentiment)
├─ SPC-UQ (st_prospective predictions) [refactored]
├─ SPR (st_prospective stale reaping)
└─ MTP (memory tier promotions)
```

#### Phase 2: Graph-Dependent Algorithms (Parallel, after Phase 1)

These algorithms need the full graph context (accumulated + current batch) and may read Phase 1 outputs.

```
┌─ BGT-SM (insight generation) [refactored]
├─ SPG (salience propagation on graph)
├─ CLV (cross-layer validation)
└─ CTD (contradiction detection)
```

#### Phase 3: Sequential Algorithms (After Phase 2)

These algorithms depend on Phase 1 and Phase 2 outputs.

```
RoutineDetector → TDL-HCO (routine optimization) [refactored]
EPC (episode compression — needs EST salience from Phase 1)
NTD (narrative threads — needs BGT-SM insights from Phase 2)
```

#### Phase 4: Quality Filters and Intent Signals

```
Quality filters (rank, limit, deduplicate per algorithm)
IntentSignalDetector.detect_all() (unchanged)
```

---

### 13.9 Files Changed Summary

#### 13.9.1 Existing Files Modified

| File | Change Type | Scope |
|---|---|---|
| `k0/pipelines/p03/phases/r5_dream_explorer.py` | MAJOR rewrite | New R5PhaseOutputs, new _execute_algorithms(), new _stage_outputs(), new _load_observation_evidence() |
| `k0/modules/consolidation/dream/dream_explorer.py` | MAJOR rewrite | Replace explore() with new 5-phase orchestration, remove CPN/MCTS dispatch |
| `k0/modules/consolidation/dream/config.py` | MODERATE | Remove CPN/MCTS fields, add new algorithm config fields |
| `k0/modules/consolidation/dream/models.py` | MODERATE | Remove CounterfactualScenario/ScenarioType, update DreamExplorerOutput |
| `k0/pipelines/p03/r5_config.py` | MODERATE | Remove MCTS/CPN config, add observation evidence config |
| `k0/pipelines/p03/phase_outputs.py` | MODERATE | Remove r5_counterfactuals/r5_mcts_scenarios, add 11 new r5_* fields |
| `k0/modules/consolidation/truth_writer/truth_write_assembler.py` | MAJOR | Remove 2 methods, add 14 new assembly methods, update assemble_all() |
| `k0/modules/consolidation/staging/r6_coordinator.py` | MINOR | Add calls for new R5 assembly methods if explicit |
| `k0/pipelines/p03/staged_writes.py` | MINOR | Evaluate st_mcts_writes removal |
| `k0/pipelines/p03/phases/r7_truth_writer.py` | MINOR | Evaluate MCTSLayerWriter removal |
| `k0/modules/consolidation/algorithms/bgt_sm.py` | MODERATE | Refactor to use ObservationEvidence input |
| `k0/modules/consolidation/algorithms/spc_uq.py` | MODERATE | Refactor to observation-driven, remove uncertainty network |
| `k0/modules/consolidation/algorithms/tdl_hco.py` | MODERATE | Refactor to use observation evidence for TD targets |
| `k0/modules/consolidation/dream/__init__.py` | MINOR | Update exports |
| `k0/modules/consolidation/algorithms/__init__.py` | MINOR | Update exports |

#### 13.9.2 New Files Created

| File | Purpose |
|---|---|
| `k0/modules/consolidation/algorithms/observation_evidence_loader.py` | Shared evidence loader |
| `k0/modules/consolidation/algorithms/observation_evidence.py` | Evidence dataclass |
| `k0/modules/consolidation/algorithms/est.py` | Episodic Strength Tracker |
| `k0/modules/consolidation/algorithms/asu.py` | Adaptive Schema Updater |
| `k0/modules/consolidation/algorithms/ewr.py` | Evidence-Weighted Re-ranker |
| `k0/modules/consolidation/algorithms/sre.py` | Social Recalibration Engine |
| `k0/modules/consolidation/algorithms/spr.py` | Stale Prediction Reaper |
| `k0/modules/consolidation/algorithms/mtp.py` | Memory Tier Promoter |
| `k0/modules/consolidation/algorithms/clv.py` | Cross-Layer Validator |
| `k0/modules/consolidation/algorithms/ctd.py` | Contradiction Detector |
| `k0/modules/consolidation/algorithms/epc.py` | Episode Compressor |
| `k0/modules/consolidation/algorithms/spg.py` | Salience Propagation on Graph |
| `k0/modules/consolidation/algorithms/ntd.py` | Narrative Thread Detector |
| `k0/modules/consolidation/dream/r5_orchestrator.py` | New 5-phase orchestrator |
| `k0/db/migrations/0070_add_memory_tier.sql` | Memory tier column migration |
| `k0/db/migrations/0071_add_propagated_salience.sql` | Propagated salience migration |
| `k0/db/migrations/0072_add_composite_episode.sql` | Composite episode migration |
| `k0/db/migrations/0073_add_narrative_thread.sql` | Narrative thread migration |
| `k0/db/migrations/0074_drop_st_mcts.sql` | MCTS table deprecation migration |

#### 13.9.3 Files Deprecated (Deleted)

| File | Lines Removed |
|---|---|
| `k0/modules/consolidation/algorithms/cpn.py` | 1,106 |
| `k0/modules/consolidation/algorithms/mcts.py` | 1,113 |
| `k0/modules/consolidation/algorithms/mcts_shadow.py` | 918 |
| `k0/modules/consolidation/algorithms/mcts_persistence.py` | 447 |
| `k0/modules/consolidation/dream/compute_budget.py` | 276 |
| **Total** | **3,860** |

---

### 13.10 Observation Recorder Integration

**File**: `k0/modules/consolidation/algorithms/observation_recorder.py` (~280 lines)

The `ObservationRecorder` is the existing mechanism for writing to st_observations. It supports:

- `record_for_insert()` — FIRST_SEEN observation (new entity/pattern discovered)
- `record_for_merge()` — REINFORCEMENT observation (existing pattern seen again)
- `record_batch()` — Batch insert for efficiency

**Key for R5**: Every R5 algorithm that modifies a memory layer record MUST also call `ObservationRecorder.record_for_merge()` to create a REINFORCEMENT observation. This closes the self-reinforcing loop:

```
st_observations → R5 algorithm reads evidence → R5 produces UPDATE →
R7 commits UPDATE → observation_recorder creates REINFORCEMENT →
next cycle's R5 reads stronger evidence → ...
```

The `ObservationContext` (35+ fields across 8 context categories) is already populated during R1 ingestion. R5 algorithms should reference the `observation_context` field on `StagedWrite` to link their outputs back to the originating observations.

---

### 13.11 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Large PR size (15+ files modified, 14+ new files) | High | Medium | Split into 3-4 PRs: deprecations first, then infrastructure, then algorithms, then wiring |
| R6/R7 regression from removed MCTS/CPN paths | Medium | High | Shadow mode: run old and new R5 in parallel for 2 weeks, compare outputs |
| Observation evidence queries slow at scale | Medium | Medium | Index st_observations by (tenant_id, space_id, target_entity_id). Batch load once per cycle. |
| n-1 stale reads produce incorrect decisions | Low | Medium | Accepted by design. 2-cycle stabilization is natural. Add metrics to track convergence rate. |
| New algorithm bugs corrupt memory layers | Medium | High | All operations are UPDATEs (not DELETEs). Worst case: incorrect confidence/salience values, fixable in next cycle. Add per-algorithm rollback flag. |
| Migration failures on existing data | Low | High | All migrations are ADD COLUMN with DEFAULT. No data transformation. Reversible. |

---

### 13.12 Implementation Sequence (Recommended PR Order)

**PR 1 — Deprecations (Low Risk)**

- Delete cpn.py, mcts.py, mcts_shadow.py, mcts_persistence.py, compute_budget.py
- Remove CPN/MCTS fields from config.py, models.py, r5_config.py
- Remove CPN/MCTS methods from dream_explorer.py
- Remove assemble_counterfactual_writes(), assemble_mcts_writes()
- Remove r5_counterfactuals, r5_mcts_scenarios from phase_outputs.py
- Update all imports and **init**.py files
- Run full test suite — fix broken tests

**PR 2 — Infrastructure (Medium Risk)**

- Create observation_evidence.py, observation_evidence_loader.py
- Create database migrations (0070-0074)
- Add memory_tier, propagated_salience, composite columns
- Add _load_observation_evidence() to r5_dream_explorer.py
- Unit tests for evidence loader and migrations

**PR 3 — New Algorithms (Medium Risk)**

- Create all 13 new algorithm files (est.py through ntd.py)
- Refactor bgt_sm.py, spc_uq.py, tdl_hco.py to accept ObservationEvidence
- Unit tests per algorithm with real st_observations fixtures
- Each algorithm is independently testable

**PR 4 — Wiring & Orchestration (High Risk)**

- Create r5_orchestrator.py with 5-phase execution
- Rewrite R5PhaseOutputs with new fields
- Add 14 new TruthWriteAssembler methods
- Update _stage_outputs() mapping
- Update phase_outputs.py with new r5_* fields
- Integration test: full R5 → R6 → R7 pipeline with new algorithms
- Shadow mode validation: compare old vs new outputs for 2 weeks

---

### 13.13 Verification Plan

| Test Type | Scope | Method |
|---|---|---|
| Unit tests (per algorithm) | Each of 14 algorithms | Feed known ObservationEvidence fixtures, assert correct output shape and values |
| Integration test (R5 pipeline) | R5 → R6 → R7 | Run full pipeline with test envelope, verify StagedWrites reach correct layers |
| n-1 validation | 2-cycle test | Run cycle N, commit via R7, run cycle N+1, verify R5 reads N's committed data |
| Shadow validation | Old vs new comparison | Run old R5 algorithms and new R5 algorithms on same input, compare layer-level diff |
| Regression test | Existing P03 tests | All existing P03 tests must pass with new R5 (outputs change but pipeline flow unchanged) |
| Performance test | R5 execution time | New R5 must complete within current R5 time budget (observation queries are indexed SQL, not MCTS rollouts) |
| Migration test | Schema changes | Verify migrations apply cleanly on existing production-like data, verify rollback works |

---

### 13.14 Output Dataclass Definitions (All 14 Algorithms)

Every new algorithm produces a typed, frozen dataclass. These are defined in the respective algorithm files and imported by `R5PhaseOutputs`, `DreamExplorerOutput`, and `TruthWriteAssembler`.

#### 13.14.1 Phase 1 Algorithm Outputs

```python
# --- EST (4.1) --- k0/modules/consolidation/algorithms/est.py
@dataclass(frozen=True)
class EpisodicStrengthUpdate:
    episode_id: str                    # Target st_epi record_id
    tenant_id: str
    space_id: str
    current_salience: float            # Existing salience score (from st_epi)
    new_salience: float                # Computed by EST formula (Section 4.1)
    observation_count: int             # Total observations for this episode
    reinforcement_count: int           # REINFORCEMENT observations only
    reinforcement_rate: float          # reinforcement_count / observation_count
    decay_factor: float                # Time-based decay applied
    last_reinforced_at: str            # ISO timestamp of most recent reinforcement
    current_version: int               # For optimistic locking on UPDATE
    confidence: float                  # Algorithm confidence in this update

# --- ASU (4.2) --- k0/modules/consolidation/algorithms/asu.py
@dataclass(frozen=True)
class SchemaConfidenceUpdate:
    pattern_id: str                    # Target st_sem record_id
    tenant_id: str
    space_id: str
    current_confidence: float          # Existing confidence_score (from st_sem)
    new_confidence: float              # Updated by ASU formula
    observation_count: int
    reinforcement_count: int
    contradiction_count: int           # Observations that contradicted the schema
    consistency_ratio: float           # (reinforcements - contradictions) / total
    current_version: int
    confidence: float

# --- EWR (4.3) --- k0/modules/consolidation/algorithms/ewr.py
@dataclass(frozen=True)
class EdgeWeightUpdate:
    edge_id: str                       # Target st_kg_edges record_id
    tenant_id: str
    space_id: str
    source_entity_id: str
    target_entity_id: str
    current_weight: float              # Existing weight (from st_kg_edges)
    new_weight: float                  # Updated by EWR formula
    observation_count: int
    reinforcement_count: int
    evidence_quality: float            # Weighted by observation sentiment/salience
    current_version: int
    confidence: float

# --- SRE (4.4) --- k0/modules/consolidation/algorithms/sre.py
@dataclass(frozen=True)
class SocialRecalibration:
    relationship_id: str               # Target st_social record_id
    tenant_id: str
    space_id: str
    entity_a_id: str
    entity_b_id: str
    current_sentiment: float           # Existing sentiment from st_social
    new_sentiment: float               # Recalibrated from recent emotional observations
    current_trust: float
    new_trust: float                   # Trust adjustment
    observation_window_days: int       # How far back observations were considered
    observation_count: int
    emotional_variance: float          # Variance in sentiment observations
    current_version: int
    confidence: float

# --- SPR (4.6) --- k0/modules/consolidation/algorithms/spr.py
@dataclass(frozen=True)
class PredictionReaperAction:
    prediction_id: str                 # Target st_prospective record_id
    tenant_id: str
    space_id: str
    action: str                        # "EXPIRE" | "DOWNGRADE" | "ARCHIVE"
    reason: str                        # Human-readable reason
    anchor_time_utc: Optional[str]     # Original prediction anchor time
    days_overdue: int                  # How many days past anchor time
    observation_count: int             # How many times the prediction was observed/missed
    was_fulfilled: bool                # Whether any observation confirmed the prediction
    current_version: int
    confidence: float

# --- MTP (4.9) --- k0/modules/consolidation/algorithms/mtp.py
@dataclass(frozen=True)
class TierPromotion:
    record_id: str                     # Target record in any tier-eligible layer
    layer: str                         # "st_epi" | "st_sem" | "st_kg_dom"
    tenant_id: str
    space_id: str
    current_tier: str                  # "TRANSIENT" | "ACTIVE" | "STABLE" | "CORE"
    new_tier: str                      # Promoted tier
    promotion_reason: str              # e.g. "reinforcement_threshold_met"
    observation_count: int
    reinforcement_count: int
    days_since_first_seen: int
    reinforcement_rate: float
    current_version: int
    confidence: float
```

#### 13.14.2 Phase 2 Algorithm Outputs

```python
# --- CLV (4.10) --- k0/modules/consolidation/algorithms/clv.py
@dataclass(frozen=True)
class CrossLayerRepair:
    record_id: str                     # Orphan or inconsistent record
    layer: str                         # Source layer where problem found
    tenant_id: str
    space_id: str
    repair_type: str                   # "ORPHAN_EDGE" | "MISSING_ENTITY" | "STALE_REF"
    repair_action: str                 # "DELETE" | "UPDATE_REF" | "FLAG_REVIEW"
    related_record_id: Optional[str]   # The missing/stale reference target
    related_layer: Optional[str]       # Layer of the related record
    description: str                   # Human-readable description
    current_version: int
    confidence: float

# --- CTD (4.11) --- k0/modules/consolidation/algorithms/ctd.py
@dataclass(frozen=True)
class ContradictionResolution:
    record_id_a: str                   # First conflicting record
    layer_a: str
    record_id_b: str                   # Second conflicting record
    layer_b: str
    tenant_id: str
    space_id: str
    contradiction_type: str            # "SENTIMENT_CONFLICT" | "FACT_CONFLICT" | "TEMPORAL_CONFLICT"
    resolution_strategy: str           # "PREFER_RECENT" | "PREFER_FREQUENT" | "MERGE" | "FLAG_REVIEW"
    resolved_value: Optional[str]      # JSON of the resolved field value
    observation_count_a: int           # How many observations support record A
    observation_count_b: int           # How many observations support record B
    confidence: float

# --- SPG (4.13) --- k0/modules/consolidation/algorithms/spg.py
@dataclass(frozen=True)
class SaliencePropagation:
    entity_id: str                     # Target st_kg_dom record_id
    tenant_id: str
    space_id: str
    current_salience: float            # Direct observation-based salience
    propagated_salience: float         # Computed via graph neighbors (PageRank-like)
    neighbor_count: int                # Number of graph neighbors contributing
    max_neighbor_salience: float       # Highest neighbor salience
    damping_factor: float              # Propagation damping (default 0.85)
    current_version: int
    confidence: float
```

#### 13.14.3 Phase 3 Algorithm Outputs

```python
# --- EPC (4.12) --- k0/modules/consolidation/algorithms/epc.py
@dataclass(frozen=True)
class EpisodeComposite:
    composite_id: str                  # New composite episode record_id (ULID)
    tenant_id: str
    space_id: str
    source_episode_ids: List[str]      # Episodes being merged
    composite_summary: str             # LLM-generated or rule-based summary
    frequency_per_month: float         # How often these episodes repeat
    combined_salience: float           # Aggregated salience score
    combined_observation_count: int    # Sum of source observation counts
    earliest_observed_at: str          # ISO timestamp
    latest_observed_at: str            # ISO timestamp
    entity_ids: List[str]             # Union of entities from source episodes
    confidence: float

# --- NTD (4.14) --- k0/modules/consolidation/algorithms/ntd.py
@dataclass(frozen=True)
class NarrativeThread:
    thread_id: str                     # New thread record_id (ULID)
    tenant_id: str
    space_id: str
    thread_name: str                   # Human-readable name
    thread_entities: List[str]         # Ordered entity chain forming the narrative
    thread_insights: List[str]         # Related insight pattern_ids (from BGT-SM)
    temporal_span_days: int            # How many days the thread spans
    observation_count: int             # Total observations across thread entities
    coherence_score: float             # How coherent the narrative is
    strength: float                    # Overall thread strength
    confidence: float
```

#### 13.14.4 Existing Algorithm Outputs (Unchanged)

These existing dataclasses are **already defined** in `k0/modules/consolidation/dream/models.py` and require no changes:

| Dataclass | Algorithm | Layer Target | Key Fields |
| --- | --- | --- | --- |
| `Insight` | BGT-SM | st_sem INSERT | pattern_id, insight_type, description, novelty_score, confidence, pmi_score, serendipity_score |
| `ProspectiveMemory` | SPC-UQ | st_prospective INSERT | memory_id, description, anchor_time_utc, confidence, trigger_conditions |
| `RoutineOptimization` | TDL-HCO | st_procedural UPDATE | routine_id, optimization_type, suggested_value, expected_improvement |
| `RoutineCandidate` | RoutineDetector | st_procedural INSERT | routine_id, pattern, frequency, confidence |
| `IntentSignal` | IntentSignalDetector | st_kg_dom/st_prospective | signal_id, intent_type, entity_ids, confidence |

---

### 13.15 Complete _stage_outputs() Mapping

**File**: `k0/pipelines/p03/phases/r5_dream_explorer.py`

The `_stage_outputs()` method maps `R5PhaseOutputs` fields to `envelope.phases.r5_*` fields. This is the exact bridge between R5's internal output container and the pipeline-wide `P03PhaseOutputs`.

**Current mapping** (to be replaced):

```python
def _stage_outputs(self, outputs: R5PhaseOutputs, envelope: P03BatchEnvelope) -> None:
    envelope.phases.r5_insights = outputs.insights
    envelope.phases.r5_counterfactuals = outputs.counterfactuals           # REMOVE
    envelope.phases.r5_routine_optimizations = outputs.routine_optimizations
    envelope.phases.r5_routine_candidates = outputs.routine_candidates
    envelope.phases.r5_prospective_memories = outputs.prospective_memories
    envelope.phases.r5_intent_signals = outputs.intent_signals
    envelope.phases.r5_mcts_scenarios = outputs.mcts_scenarios             # REMOVE
```

**New mapping**:

```python
def _stage_outputs(self, outputs: R5PhaseOutputs, envelope: P03BatchEnvelope) -> None:
    # --- Existing algorithms (KEEP) ---
    envelope.phases.r5_insights = outputs.insights
    envelope.phases.r5_routine_optimizations = outputs.routine_optimizations
    envelope.phases.r5_routine_candidates = outputs.routine_candidates
    envelope.phases.r5_prospective_memories = outputs.prospective_memories
    envelope.phases.r5_intent_signals = outputs.intent_signals

    # --- New observation-driven algorithms ---
    envelope.phases.r5_est_updates = outputs.est_updates
    envelope.phases.r5_asu_updates = outputs.asu_updates
    envelope.phases.r5_ewr_updates = outputs.ewr_updates
    envelope.phases.r5_sre_updates = outputs.sre_updates
    envelope.phases.r5_spr_actions = outputs.spr_actions
    envelope.phases.r5_mtp_promotions = outputs.mtp_promotions
    envelope.phases.r5_clv_repairs = outputs.clv_repairs
    envelope.phases.r5_ctd_resolutions = outputs.ctd_resolutions
    envelope.phases.r5_epc_composites = outputs.epc_composites
    envelope.phases.r5_spg_salience = outputs.spg_salience
    envelope.phases.r5_ntd_threads = outputs.ntd_threads

    # --- Metadata ---
    envelope.phases.r5_skipped = False
    envelope.phases.r5_skip_reason = None
```

---

### 13.16 Metrics Changes (Old to New)

**Current R5 metrics** (emitted by `r5_dream_explorer.py` and `dream_explorer.py`):

```python
# Counters (REMOVE — CPN/MCTS-specific)
"r5.counterfactuals.generated"          # Count of CPN counterfactuals
"r5.mcts.scenarios.generated"           # Count of MCTS scenarios
"r5.mcts.rollouts.executed"             # Total MCTS rollouts
"r5.mcts.decisions.evaluated"           # MCTS decision tree evaluations
"r5.compute_budget.remaining_ms"        # ComputeBudget remaining time

# Counters (KEEP)
"r5.insights.generated"                 # Count of BGT-SM insights
"r5.routine_optimizations.generated"    # Count of TDL-HCO optimizations
"r5.prospective_memories.generated"     # Count of SPC-UQ predictions
"r5.intent_signals.generated"           # Count of intent signals
"r5.skipped"                            # R5 phase was skipped
```

**New R5 metrics to ADD**:

```python
# Per-algorithm output counters
"r5.est.updates.generated"              # EST episodic salience updates
"r5.asu.updates.generated"              # ASU schema confidence updates
"r5.ewr.updates.generated"              # EWR edge weight updates
"r5.sre.updates.generated"              # SRE social recalibrations
"r5.spr.actions.generated"              # SPR stale prediction reaper actions
"r5.mtp.promotions.generated"           # MTP tier promotions
"r5.clv.repairs.generated"              # CLV cross-layer repairs
"r5.ctd.resolutions.generated"          # CTD contradiction resolutions
"r5.epc.composites.generated"           # EPC episode composites
"r5.spg.salience.generated"             # SPG salience propagations
"r5.ntd.threads.generated"              # NTD narrative threads

# Phase timing (NEW — replace ComputeBudget)
"r5.phase0.evidence_load_ms"            # Time to load observation evidence
"r5.phase1.parallel_ms"                 # Phase 1 total wall clock
"r5.phase2.parallel_ms"                 # Phase 2 total wall clock
"r5.phase3.sequential_ms"              # Phase 3 total wall clock
"r5.phase4.filters_ms"                  # Phase 4 total wall clock
"r5.total_execution_ms"                 # R5 total execution time

# Error isolation counters
"r5.algorithm.failure"                  # Per-algorithm failure (tagged by algorithm name)
"r5.algorithms.executed_count"          # How many algorithms ran successfully
"r5.algorithms.failed_count"            # How many algorithms failed

# Observation evidence metrics
"r5.observation_evidence.records_loaded"  # Total observation records loaded
"r5.observation_evidence.load_ms"         # Time to load evidence
```

---

### 13.17 st_observations Schema Reference

The `st_observations` table is the foundation for all observation-driven algorithms. Created by migration 0067.

**Full DDL**:

```sql
CREATE TABLE IF NOT EXISTS st_observations (
    -- Identity
    observation_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer           VARCHAR(32) NOT NULL
        CHECK (layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_kg_edges', 'st_social', 'st_prospective')),
    record_id       VARCHAR(128) NOT NULL,
    tenant_id       VARCHAR(64) NOT NULL,
    space_id        VARCHAR(64) NOT NULL,

    -- Temporal
    observed_at         TIMESTAMPTZ NOT NULL,
    anchor_time_utc     TIMESTAMPTZ,
    original_temporal_expr TEXT,
    time_of_day_bucket  VARCHAR(16),
    circadian_slot      VARCHAR(16),
    is_weekend          BOOLEAN,

    -- Emotional
    sentiment_score     FLOAT,
    sentiment_label     VARCHAR(16),
    affect_valence      FLOAT,
    affect_arousal      FLOAT,
    dominant_emotion    VARCHAR(32),

    -- Salience
    salience_score      FLOAT,
    salience_band       VARCHAR(16),
    novelty_score       FLOAT,

    -- Modality
    ingress_channel     VARCHAR(32),
    ingress_source      VARCHAR(64),
    device_kind         VARCHAR(32),

    -- Physical
    location_name       VARCHAR(128),
    location_type       VARCHAR(32),
    geohash_6           VARCHAR(6),

    -- Social
    social_context      VARCHAR(32),
    social_intimacy     FLOAT,
    is_solo_event       BOOLEAN,
    num_participants    INTEGER,

    -- Classification
    observation_type    VARCHAR(32) NOT NULL DEFAULT 'FIRST_SEEN',
    confidence          FLOAT DEFAULT 1.0,

    -- Provenance
    source_event_id         VARCHAR(128),
    consolidation_cycle_id  VARCHAR(128),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Indexes** (8 total, all created by migration 0067):

```sql
CREATE INDEX idx_obs_record_time  ON st_observations (layer, record_id, observed_at DESC);
CREATE INDEX idx_obs_tenant_time  ON st_observations (tenant_id, observed_at DESC);
CREATE INDEX idx_obs_anchor_time  ON st_observations (layer, anchor_time_utc DESC)
    WHERE layer = 'st_prospective';
CREATE INDEX idx_obs_sentiment    ON st_observations (sentiment_score)
    WHERE sentiment_score IS NOT NULL;
CREATE INDEX idx_obs_salience     ON st_observations (salience_score DESC)
    WHERE salience_score IS NOT NULL;
CREATE INDEX idx_obs_channel      ON st_observations (ingress_channel);
CREATE INDEX idx_obs_social       ON st_observations (social_context);
CREATE INDEX idx_obs_location     ON st_observations (geohash_6)
    WHERE geohash_6 IS NOT NULL;
```

**Key query patterns for R5 algorithms** (all use `idx_obs_record_time` or `idx_obs_tenant_time`):

| Query | Used By | Index | Returns |
| --- | --- | --- | --- |
| `SELECT ... GROUP BY layer, record_id` (per-record stats) | EST, ASU, EWR, MTP, SPR | `idx_obs_record_time` | count, reinforcement_count, avg_sentiment, first/last seen per record |
| `SELECT ... GROUP BY circadian_slot, location_type, social_context` (distributions) | SPC-UQ, SPG, NTD | `idx_obs_tenant_time` | distribution tables for tenant over lookback window |
| `SELECT ... WHERE layer = 'st_social' AND sentiment_score IS NOT NULL` (emotional) | SRE, CTD | `idx_obs_sentiment` | Emotional observations for social relationships |

---

### 13.18 Algorithm Data Flow Matrix

Complete mapping of what each algorithm reads, writes, and depends on.

| Algorithm | Section | Reads From | Observation Evidence Fields Used | Writes To | Operation | Depends On |
| --- | --- | --- | --- | --- | --- | --- |
| EST | 4.1 | st_epi (accumulated) | observation_count, reinforcement_count, decay | st_epi | UPDATE (salience) | None |
| ASU | 4.2 | st_sem (accumulated) | observation_count, contradiction_count, consistency_ratio | st_sem | UPDATE (confidence) | None |
| EWR | 4.3 | st_kg_edges (accumulated) | observation_count, evidence_quality | st_kg_edges | UPDATE (weight) | None |
| SRE | 4.4 | st_social (accumulated) | sentiment_score, affect_valence, emotional_variance | st_social | UPSERT (sentiment, trust) | None |
| SPC-UQ | 4.5 | st_prospective, distributions | circadian_slot, location_type distribution | st_prospective | INSERT | None |
| SPR | 4.6 | st_prospective (accumulated) | observation_count, anchor_time_utc | st_prospective | UPDATE/ARCHIVE | None |
| BGT-SM | 4.7 | st_kg_dom, st_kg_edges (accumulated) | pmi_score, novelty_score, observation evidence | st_sem | INSERT (insights) | None |
| TDL-HCO | 4.8 | st_procedural (accumulated) | reinforcement_rate, observation evidence | st_procedural | UPDATE | RoutineDetector (Phase 3) |
| MTP | 4.9 | st_epi, st_sem, st_kg_dom | observation_count, reinforcement_count, days_since_first | st_epi, st_sem, st_kg_dom | UPDATE (memory_tier) | None |
| CLV | 4.10 | st_kg_edges, st_kg_dom, st_social | cross-layer reference counts | st_kg_edges, st_social | UPDATE/DELETE | None |
| CTD | 4.11 | st_social, st_sem | observation_count per conflicting record | st_social, st_sem | UPDATE | None |
| EPC | 4.12 | st_epi (accumulated) | frequency_per_month, combined_salience | st_epi | INSERT (composite), UPDATE (sources) | EST (Phase 1 salience) |
| SPG | 4.13 | st_kg_dom, st_kg_edges (graph) | neighbor salience, edge weights | st_kg_dom | UPDATE (propagated_salience) | None |
| NTD | 4.14 | st_sem (insights), st_kg_dom (entities) | temporal observations, entity chains | st_sem | INSERT (NARRATIVE_THREAD) | BGT-SM (Phase 2 insights) |

---

### 13.19 ObservationContext — Full Field Reference

The `ObservationContext` dataclass (35+ fields, 365 lines) is used by `StagedWrite.observation_context` to carry the complete sensory context for every write operation. This is already populated during R1 ingestion and persisted to `st_observations` by `ObservationRecorder`.

**File**: `k0/modules/consolidation/algorithms/observation_context.py`

```python
@dataclass
class ObservationContext:
    # --- Temporal (6 fields) ---
    observed_at: str                          # REQUIRED. ISO8601 timestamp
    anchor_time_utc: Optional[str] = None     # For temporal anchoring
    time_of_day_bucket: Optional[str] = None  # MORNING, AFTERNOON, EVENING, NIGHT
    circadian_slot: Optional[str] = None      # EARLY_MORNING, MORNING, MIDDAY, AFTERNOON, EVENING, NIGHT, LATE_NIGHT
    is_weekend: Optional[bool] = None
    day_of_week: Optional[int] = None         # 0=Monday, 6=Sunday

    # --- Emotional (6 fields) ---
    sentiment_score: Optional[float] = None   # -1.0 to 1.0
    sentiment_label: Optional[str] = None     # POSITIVE, NEGATIVE, NEUTRAL, MIXED
    affect_valence: Optional[float] = None    # -1.0 to 1.0 (pleasure/displeasure)
    affect_arousal: Optional[float] = None    # 0.0 to 1.0 (calm/excited)
    dominant_emotion: Optional[str] = None    # JOY, SADNESS, ANGER, FEAR, etc.
    dominant_emotions_json: Optional[str] = None  # JSON array of top-k emotions

    # --- Intent (2 fields) ---
    intent_ultrabert: Optional[str] = None    # UltraBERT intent classification
    intent_confidence: Optional[float] = None # Intent classification confidence

    # --- Salience (3 fields) ---
    salience_score: Optional[float] = None    # 0.0 to 1.0
    salience_band: Optional[str] = None       # LOW, MEDIUM, HIGH, CRITICAL
    novelty_score: Optional[float] = None     # 0.0 to 1.0

    # --- Modality (4 fields) ---
    ingress_channel: Optional[str] = None     # CHAT, VOICE, API, SYSTEM
    ingress_category: Optional[str] = None
    ingress_source: Optional[str] = None      # Device/app identifier
    device_kind: Optional[str] = None         # PHONE, TABLET, DESKTOP, WATCH

    # --- Physical (3 fields) ---
    location_name: Optional[str] = None       # "Home", "Office", "Gym"
    location_type: Optional[str] = None       # HOME, WORK, TRANSIT, RECREATION
    geohash_6: Optional[str] = None           # 6-char geohash for proximity

    # --- Social (4 fields) ---
    social_context: Optional[str] = None      # SOLO, FAMILY, FRIENDS, WORK, PUBLIC
    social_intimacy: Optional[float] = None   # 0.0 (public) to 1.0 (intimate)
    is_solo_event: Optional[bool] = None
    num_participants: Optional[int] = None

    # --- Classification (2 fields) ---
    observation_type: Optional[str] = None    # FIRST_SEEN, REINFORCEMENT
    confidence: Optional[float] = None        # 0.0 to 1.0

    # --- Provenance (2 fields) ---
    source_event_id: Optional[str] = None
    consolidation_cycle_id: Optional[str] = None
```

**Factory methods**:

| Method | Purpose |
| --- | --- |
| `ObservationContext.from_event(event)` | Populate from a raw ingestion event (R1) |
| `ObservationContext.from_timestamp(ts)` | Minimal context with just temporal fields |
| `ObservationContext.from_episode_cluster(cluster)` | Populate from an R2 EpisodeCluster |

**Usage in R5**: Each new algorithm should set `observation_context` on its `StagedWrite` outputs so the observation loop is closed. For UPDATE operations where the original observation context is already on the target record, the algorithm can pass `None` (the recorder will use the existing context).

---

### 13.20 Complete _stage_outputs to R7 Commit Data Flow

This section traces a single algorithm output through the entire pipeline from R5 to database commit. Use this as the reference template for verifying end-to-end correctness.

**Example**: EST produces an `EpisodicStrengthUpdate` for episode `ep_001`.

```
STEP 1: R5 Algorithm Execution (r5_dream_explorer.py)
  _execute_algorithms() Phase 1 parallel:
    est_algo.execute(input_data, observation_evidence, config)
    -> Returns [EpisodicStrengthUpdate(episode_id="ep_001", new_salience=0.85, ...)]

STEP 2: R5 Output Collection (r5_dream_explorer.py)
  outputs.est_updates = phase1_results.get("EST") or []
  -> R5PhaseOutputs.est_updates = [EpisodicStrengthUpdate(episode_id="ep_001", ...)]

STEP 3: Stage to Envelope (r5_dream_explorer.py._stage_outputs)
  envelope.phases.r5_est_updates = outputs.est_updates
  -> P03PhaseOutputs.r5_est_updates = [EpisodicStrengthUpdate(...)]

STEP 4: R6 Extraction (r6_coordinator.py.execute)
  r5_est_updates = getattr(phase_outputs, "r5_est_updates", None) or []
  -> r5_est_updates = [EpisodicStrengthUpdate(episode_id="ep_001", ...)]

STEP 5: Truth Assembly (truth_write_assembler.py.assemble_all)
  assemble_est_writes(est_updates=r5_est_updates)
  -> Creates StagedWrite.update(
       layer="st_epi",
       record_id="ep_001",
       data={"salience_score": 0.85, "observation_count": 12, ...},
       phase="R5",
       expected_version=3,
     )
  -> Returns {"st_epi": [StagedWrite(...)]}

STEP 6: Staged Write Routing (r6_coordinator.py)
  for layer, writes in truth_assembly.items():
      for write in writes:
          envelope.staged.add_write(write)
  -> envelope.staged.st_epi_writes.append(StagedWrite(layer="st_epi", record_id="ep_001", ...))

STEP 7: R7 Atomic Commit (r7_truth_writer.py)
  TransactionCoordinator processes all writes within one DB transaction:
  get_all_writes_ordered() returns writes in dependency order:
    st_vec -> st_kg_dom -> st_kg_edges -> st_epi -> st_sem -> ...
  DecisionRouter dispatches StagedWrite to EpisodicLayerWriter:
    EpisodicLayerWriter.handle_update(write)
    -> SQL: UPDATE st_epi SET salience_score = 0.85, observation_count = 12, ...
            WHERE record_id = 'ep_001' AND version = 3
    -> Increments version to 4

STEP 8: Observation Recording (observation_recorder.py)
  ObservationRecorder.record_for_merge(
      layer="st_epi",
      record_id="ep_001",
      observation_context=write.observation_context,
      observation_type="REINFORCEMENT",
  )
  -> INSERT INTO st_observations (layer, record_id, observation_type, ...)
     VALUES ('st_epi', 'ep_001', 'REINFORCEMENT', ...)

STEP 9: Next Cycle (n+1)
  R5._load_observation_evidence() queries st_observations
  -> Finds ep_001 now has 13+ observations (including the REINFORCEMENT from Step 8)
  -> EST computes updated salience with stronger evidence
  -> Self-reinforcing loop continues
```

**Key invariants**:
1. All R5 outputs flow through `StagedWrite` — no direct database writes
2. All writes are atomic (committed in one transaction by R7)
3. Every UPDATE carries `expected_version` for optimistic locking
4. Observation recording happens AFTER commit (closes the loop for n+1)
5. If any algorithm fails, its outputs are empty lists — no partial state
6. R6/R7 are generic — they process `StagedWrite` objects regardless of source algorithm
